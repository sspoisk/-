#!/usr/bin/env python3
# coding: utf-8
"""
agent_channel_full.py

This module implements a simple HTTP server that exposes a REST API for a
cryptocurrency scalping bot. It is designed to run on Windows 7 with
Python 3.8 and minimal external dependencies (only the `requests` library
is required). The server handles the following responsibilities:

  - Maintain a global list of liquid trading pairs (the “universe”).
  - Download recent minute‐candlestick data for each pair on demand.
  - Perform a very simple backtest to estimate Profit Factor (PF),
    maximum drawdown (MDD) and number of trades for each pair under a
    Donchian channel strategy.  The optimisation routine picks a
    parameter set that maximises a score (PF × (1−MDD/100)) within
    predefined grids.
  - Expose endpoints for managing the universe, downloading data,
    running optimisation, inspecting optimisation progress and results,
    enabling/disabling trading on specific pairs, and updating global
    configuration.
  - Provide basic endpoints for inspecting server state, open
    positions and equity history.  Actual trading (opening/closing
    orders) remains in paper mode only.  This script does not send
    real orders to any exchange.

The server uses Python’s built‑in `http.server` module and does not
depend on asynchronous frameworks.  Heavy operations such as
optimisation and data downloading are performed in a background thread
to avoid blocking incoming requests.

Note: This implementation emphasises readability and simplicity over
performance.  For production use, consider batching API requests,
adding caching and proper error handling, and splitting long‐running
operations into smaller tasks.
"""

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

try:
    import requests
except ImportError:
    raise RuntimeError("The 'requests' library is required. Install it via pip install requests")

# Global configuration defaults.  These values can be modified via
# POST /api/config.  They are copied into STATE['config'] at start.
DEFAULT_CONFIG = {
    "timeframe": "1m",
    "min_usd_24h": 15000,      # minimum 24h volume to include a pair in the universe
    "universe_limit": 200,     # maximum number of pairs in the universe
    "pf_min": 1.2,             # minimum Profit Factor for optimisation
    "mdd_max": 30,             # maximum drawdown (%) for optimisation
    "trades_min": 20,          # minimum number of trades during backtest
    "donchian_windows": [20, 40, 60],
    "history_days": 1,
    "quote_asset": "USDT",
    "start_autocycle": False,  # whether to start the worker automatically
    "cycle_minutes": 60,       # time between cycles in minutes
}

# State object containing mutable data structures used by the server.  The
# contents of this dictionary are exposed via /api/status.  Only the
# 'config' key should be modified directly by API calls; other keys
# should be updated through helper functions defined below.
STATE = {
    "running": False,       # whether the worker is running live cycles
    "cycle": 0,             # number of completed live cycles
    "log": [],              # list of log strings
    "positions": {},        # open positions: symbol -> details
    "equity": [],           # list of {"t": timestamp, "eq": float}
    "universe": [],         # list of tradable symbols
    "data": {},             # historical candles: symbol -> list of dicts
    "profiles": [],         # optimisation results: list of {symbol, best}
    "opt_progress": {       # optimisation progress for front‑end
        "running": False,
        "progress": 0,
        "total": 0,
        "last_msg": ""
    },
    "enabled": [],          # symbols enabled for live trading
    "config": DEFAULT_CONFIG.copy(),
}

# Lock to synchronise access to STATE and other shared data.
STATE_LOCK = threading.Lock()


def log(msg: str) -> None:
    """Append a message to the log and print it to stdout."""
    timestamp = time.strftime('%H:%M:%S')
    line = f"{timestamp}  {msg}"
    with STATE_LOCK:
        STATE['log'].append(line)
        # Keep only the last 500 log entries
        STATE['log'] = STATE['log'][-500:]
    print(line, flush=True)


def _get_binance(url: str, params: dict = None, timeout: int = 30):
    """Helper to perform a GET request to the Binance API with sensible defaults."""
    base = "https://api.binance.com"
    full_url = base + url
    for attempt in range(3):
        try:
            resp = requests.get(full_url, params=params or {}, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            if attempt == 2:
                raise
            time.sleep(1)
    # Should not reach here
    return []


def rebuild_universe() -> None:
    """Rebuild the list of liquid trading pairs based on 24h volume."""
    cfg = STATE['config']
    quote = cfg.get('quote_asset', 'USDT')
    min_usd = cfg.get('min_usd_24h', 15000)
    limit = cfg.get('universe_limit', 200)
    symbols = []
    try:
        log("Rebuilding universe: fetching exchange info…")
        info = _get_binance('/api/v3/exchangeInfo')
        candidates = [s['symbol'] for s in info['symbols'] if s['status'] == 'TRADING' and s['quoteAsset'] == quote]
        log(f"Found {len(candidates)} candidate symbols ending with {quote}")
        volumes = {}
        for i, sym in enumerate(candidates):
            try:
                tick = _get_binance('/api/v3/ticker/24hr', params={"symbol": sym})
                vol_usd = float(tick.get('quoteVolume', 0.0))
                if vol_usd >= min_usd:
                    volumes[sym] = vol_usd
            except Exception:
                pass
            # Sleep occasionally to avoid hitting rate limits
            if i % 50 == 0:
                time.sleep(0.1)
        # Sort by volume desc and cut to limit
        sorted_syms = sorted(volumes.items(), key=lambda kv: kv[1], reverse=True)
        symbols = [kv[0] for kv in sorted_syms[:limit]]
    except Exception as e:
        log(f"Error rebuilding universe: {e}")
    with STATE_LOCK:
        STATE['universe'] = symbols
    log(f"Universe rebuilt: {len(symbols)} symbols selected")


def backfill_history(days: int = 1) -> None:
    """Download minute candles for each symbol in the universe for the given number of days.

    This function populates STATE['data'].  It uses the Binance `/api/v3/klines`
    endpoint and respects the 1000‑rows limit by splitting long ranges into
    multiple requests.  For simplicity, we assume minute candles; the
    timeframe is read from STATE['config']['timeframe'] but must be '1m'.
    """
    timeframe = STATE['config'].get('timeframe', '1m')
    if timeframe != '1m':
        log(f"Backfill currently supports only 1m timeframe (requested {timeframe})")
        return
    limit = 1000
    ms_per_day = 24 * 60 * 60 * 1000
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - days * ms_per_day
    for sym in STATE['universe']:
        candles = []
        start = start_ms
        while start < now_ms:
            try:
                params = {"symbol": sym, "interval": timeframe, "limit": limit}
                if start:
                    params['startTime'] = start
                data = _get_binance('/api/v3/klines', params=params)
                if not data:
                    break
                for row in data:
                    candles.append({
                        "t": row[0],
                        "o": float(row[1]),
                        "h": float(row[2]),
                        "l": float(row[3]),
                        "c": float(row[4]),
                        "v": float(row[5]),
                    })
                # Advance start by number of returned candles
                start = data[-1][0] + 60_000
            except Exception as e:
                log(f"Error fetching candles for {sym}: {e}")
                break
        with STATE_LOCK:
            STATE['data'][sym] = candles[-days * 24 * 60:]
        log(f"Backfill: {sym} {len(candles)} candles downloaded")


def _profit_factor(wins, losses):
    g = sum([x for x in wins if x > 0])
    l = abs(sum([x for x in losses if x < 0]))
    return (g / l) if l > 0 else float('inf')


def _max_drawdown(curve):
    peak = curve[0]
    mdd = 0.0
    for x in curve:
        if x > peak:
            peak = x
        dd = (peak - x) / peak if peak > 0 else 0
        if dd > mdd:
            mdd = dd
    return round(mdd * 100, 2)


def _mini_backtest(ohlcv, win):
    """Simple Donchian backtest for a single window value.

    We generate a buy signal when the close crosses above the maximum high
    over the last `win` candles and a sell signal when it crosses below
    the minimum low.  We assume an always‑in‐market strategy: enter long
    on the first buy and exit (flat) on sell.  This simplistic approach
    is good enough for parameter ranking.
    Returns PF, MDD, trades and score.
    """
    if len(ohlcv) < win + 2:
        return 0.0, 100.0, 0, 0.0
    balance = 1.0
    curve = [balance]
    wins = []
    losses = []
    in_pos = False
    entry_price = 0.0
    trades = 0
    for i in range(win, len(ohlcv)):
        seg = ohlcv[i - win:i]
        max_h = max(bar['h'] for bar in seg)
        min_l = min(bar['l'] for bar in seg)
        c = ohlcv[i]['c']
        # Buy signal
        if not in_pos and c > max_h:
            in_pos = True
            entry_price = c
        # Sell signal
        elif in_pos and c < min_l:
            pnl = (c - entry_price) / entry_price
            if pnl >= 0:
                wins.append(pnl)
            else:
                losses.append(pnl)
            balance *= (1 + pnl)
            curve.append(balance)
            trades += 1
            in_pos = False
    # Close last trade if still in position
    if in_pos:
        c = ohlcv[-1]['c']
        pnl = (c - entry_price) / entry_price
        if pnl >= 0:
            wins.append(pnl)
        else:
            losses.append(pnl)
        balance *= (1 + pnl)
        curve.append(balance)
        trades += 1
    pf = round(_profit_factor(wins, losses), 3)
    mdd = _max_drawdown(curve)
    score = pf * (1 - mdd / 100.0)
    return pf, mdd, trades, round(score, 3)


def optimise_universe(mode: str, days: int = 1) -> None:
    """Run a simple optimisation over all symbols in the universe.

    For each symbol we test a set of Donchian windows (specified in
    config) and pick the best based on PF and MDD thresholds.  We do not
    currently support trend‐channel optimisation; `mode` is accepted
    for API compatibility but ignored.  Results are stored in
    STATE['profiles'] with keys:
    {"symbol": sym, "best": {"window": int, "pf": float, "mdd": float,
                               "trades": int, "score": float}}
    Progress is tracked in STATE['opt_progress'].
    """
    with STATE_LOCK:
        syms = list(STATE['universe'])
    total = len(syms)
    with STATE_LOCK:
        STATE['opt_progress'] = {"running": True, "progress": 0, "total": total, "last_msg": "starting"}
        STATE['profiles'] = []
    if not syms:
        with STATE_LOCK:
            STATE['opt_progress']["running"] = False
        return
    cfg = STATE['config']
    windows = cfg.get('donchian_windows', [20, 40, 60])
    pf_min = cfg.get('pf_min', 1.2)
    mdd_max = cfg.get('mdd_max', 30)
    trades_min = cfg.get('trades_min', 20)
    for idx, sym in enumerate(syms):
        with STATE_LOCK:
            STATE['opt_progress'] = {"running": True, "progress": idx, "total": total, "last_msg": sym}
        try:
            ohlcv = STATE['data'].get(sym)
            if not ohlcv:
                # if no data, attempt to fetch
                backfill_history(days)
                ohlcv = STATE['data'].get(sym, [])
            best = None
            for w in windows:
                pf, mdd, trades, score = _mini_backtest(ohlcv, w)
                if trades < trades_min or pf < pf_min or mdd > mdd_max:
                    continue
                rec = {"window": w, "pf": pf, "mdd": mdd, "trades": trades, "score": score}
                if not best or score > best['score']:
                    best = rec
            if best:
                with STATE_LOCK:
                    STATE['profiles'].append({"symbol": sym, "best": best})
        except Exception as e:
            log(f"Error optimising {sym}: {e}")
    with STATE_LOCK:
        STATE['opt_progress'] = {"running": False, "progress": total, "total": total, "last_msg": "done"}
    log(f"Optimisation finished: {len(STATE['profiles'])} profiles created")


# Worker thread for live cycles.  In this simplified example, the live
# cycle does not open or manage real positions.  It merely logs the
# occurrence of a cycle.  Implementing full live trading logic is left
# as an exercise for the user.
def worker_loop():
    while True:
        time.sleep(1)
        with STATE_LOCK:
            running = STATE['running']
            period = STATE['config'].get('cycle_minutes', 60)
            cycle = STATE['cycle']
        if not running:
            continue
        now = time.time()
        # Use cycle timestamp tracking to avoid spinning too fast
        # Note: for simplicity we just wait `period` minutes between
        # cycles; this does not align cycles to wall clock.
        log("cycle start")
        # Here you could implement signal detection and trade execution
        # using STATE['profiles'] and recent price data.  For now we
        # just increment the cycle counter.
        with STATE_LOCK:
            STATE['cycle'] = cycle + 1
        log("cycle done")
        time.sleep(period * 60)


class RequestHandler(BaseHTTPRequestHandler):
    def _read_json(self):
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            length = 0
        body = self.rfile.read(length).decode('utf-8') if length else ''
        if not body:
            return {}
        try:
            return json.loads(body)
        except Exception:
            return {}

    def _json(self, obj, status=200):
        data = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        # CORS preflight
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/api/status':
            with STATE_LOCK:
                status = {
                    "running": STATE['running'],
                    "cycle": STATE['cycle'],
                    "log": STATE['log'][-80:],
                    "universe_size": len(STATE['universe']),
                    "enabled": STATE['enabled'],
                    "config": STATE['config'],
                }
            return self._json(status)
        if path == '/api/positions':
            with STATE_LOCK:
                return self._json({"positions": STATE['positions']})
        if path == '/api/equity':
            with STATE_LOCK:
                return self._json({"equity": STATE['equity']})
        if path == '/api/optimize/status':
            with STATE_LOCK:
                return self._json(STATE['opt_progress'])
        if path == '/api/profiles':
            with STATE_LOCK:
                return self._json({"profiles": STATE['profiles']})
        # Serve dashboard.html file at root
        if path in ('/', '/index.html'):
            return self._serve_file('dashboard.html', 'text/html')
        # If the file is in the same directory, attempt to serve it
        fpath = path.lstrip('/')
        return self._serve_file(fpath)

    def _serve_file(self, filename, mime=None):
        base = os.path.dirname(os.path.abspath(__file__))
        fpath = os.path.join(base, filename)
        if not os.path.isfile(fpath):
            self.send_response(404)
            self.end_headers()
            return
        try:
            with open(fpath, 'rb') as f:
                data = f.read()
            self.send_response(200)
            if not mime:
                # crude mime detection
                if fpath.endswith('.html'):
                    mime = 'text/html; charset=utf-8'
                elif fpath.endswith('.js'):
                    mime = 'application/javascript; charset=utf-8'
                elif fpath.endswith('.css'):
                    mime = 'text/css; charset=utf-8'
                else:
                    mime = 'application/octet-stream'
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self.send_response(500)
            self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path
        if path == '/api/action':
            body = self._read_json()
            act = (body.get('action') or '').lower()
            with STATE_LOCK:
                if act == 'start':
                    STATE['running'] = True
                elif act == 'stop':
                    STATE['running'] = False
            return self._json({"ok": True, "running": STATE['running']})
        if path == '/api/universe/rebuild':
            # Rebuild the universe in a background thread
            threading.Thread(target=rebuild_universe, daemon=True).start()
            return self._json({"ok": True, "message": "universe rebuild started"})
        if path == '/api/backfill':
            body = self._read_json()
            days = int(body.get('days', 1))
            threading.Thread(target=backfill_history, args=(days,), daemon=True).start()
            return self._json({"ok": True, "message": "backfill started"})
        if path == '/api/optimize':
            body = self._read_json()
            mode = body.get('mode', 'donchian')
            days = int(body.get('days', 1))
            threading.Thread(target=optimise_universe, args=(mode, days), daemon=True).start()
            return self._json({"ok": True, "message": "optimisation started", "mode": mode})
        if path == '/api/trade/enable':
            body = self._read_json()
            syms = body.get('symbols', [])
            if not isinstance(syms, list):
                syms = []
            with STATE_LOCK:
                STATE['enabled'] = syms
            return self._json({"ok": True, "enabled": syms})
        if path == '/api/config':
            body = self._read_json()
            # Merge with defaults
            with STATE_LOCK:
                cfg = STATE['config']
                for k, v in body.items():
                    cfg[k] = v
                STATE['config'] = cfg
            return self._json({"ok": True, "config": STATE['config']})
        if path == '/api/close':
            # Close a position manually.  For this simplified version,
            # positions are not implemented; respond OK anyway.
            return self._json({"ok": True})
        if path == '/api/force_cycle':
            # Immediately run a worker cycle (for testing)
            threading.Thread(target=self._force_cycle_impl, daemon=True).start()
            return self._json({"ok": True, "message": "force cycle triggered"})
        # Unknown POST endpoint
        self.send_response(404)
        self.end_headers()

    def _force_cycle_impl(self):
        log("force cycle triggered")
        # Perform a single worker cycle (without waiting)
        with STATE_LOCK:
            cycle = STATE['cycle']
        log("cycle start")
        with STATE_LOCK:
            STATE['cycle'] = cycle + 1
        log("cycle done")


def run_server(port: int = 8080):
    """Start the HTTP server and the worker thread."""
    # Launch worker thread
    threading.Thread(target=worker_loop, daemon=True).start()
    addr = ('', port)
    httpd = HTTPServer(addr, RequestHandler)
    log(f"HTTP server running on http://127.0.0.1:{port}")
    httpd.serve_forever()


if __name__ == '__main__':
    # Start worker automatically if configured
    if STATE['config'].get('start_autocycle'):
        with STATE_LOCK:
            STATE['running'] = True
    run_server(8080)