# main.py
# SpreadMaker v6.56 (v1.27 ZERO-PROTECT) TRAIL by криптоволк программер
# REFACTORED v1.21: Добавлен Trailing Grid Down, фикс спама ордеров (Paper), UI stability fix.
# ИСПРАВЛЕНО (v1.25): ФИКС спама логов графика.
# ИСПРАВЛЕНО (v1.26): ФИНАЛЬНЫЙ ФИКС ЛОГИКИ ТРЕЙЛИНГА (конфликт Агрессивного и Чуткого).
# НОВОЕ (v1.27): РАДИКАЛЬНАЯ МЕРА - Защита от цен <= 0 при создании сетки.

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import time
import requests 
import json
import sys
import uuid
import datetime as dt
import ssl
import queue
import hmac 
import hashlib 
from urllib.parse import urlencode 
import numpy as np # pip install numpy
import webbrowser # <--- v6.66

# --- Библиотеки для графика и анализа ---
try:
    import pandas as pd
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    import mplfinance as mpf
    import matplotlib.dates as mdates
    ANALYSIS_AVAILABLE = True
except ImportError:
    ANALYSIS_AVAILABLE = False

# --- WebSocket библиотека ---
try:
    import websocket
    WS_AVAILABLE = True
except ImportError:
    WS_AVAILABLE = False

# --- НОВЫЕ ИМПОРТЫ НАШИХ МОДУЛЕЙ ---
# (Предполагается, что binance_api.py и autopilot.py/autopilot1.py в той же папке)
try:
    from binance_api1 import BinanceTrader
except ImportError:
    try:
        from binance_api import BinanceTrader
    except ImportError:
        print("КРИТИЧЕСКАЯ ОШИБКА: Не найден binance_api.py или binance_api1.py")
        sys.exit()

try:
    from autopilot1 import AutopilotManager
except ImportError:
    try:
        from autopilot import AutopilotManager
    except ImportError:
         print("КРИТИЧЕСКАЯ ОШИБКА: Не найден autopilot1.py или autopilot.py")
         sys.exit()
# ---

# --- Настройки среды ---
try:
    if sys.platform == 'win32':
        ssl._create_default_https_context = ssl._create_unverified_context
except Exception as e:
    print(f"WARNING: Failed to apply SSL-Fix: {e}")

if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

class SpreadMakerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("SpreadMaker v6.56 (v1.27 ZERO-PROTECT) TRAIL (by криптоволк)")
        self.root.geometry("1400x850")

        self.running = threading.Event()
        self.maker_thread = None
        self.ws_thread = None; self.ws = None

        self.autopilot_state = 'trading'
        self.potential_next_pair = None
        self.potential_next_pair_is_short = False 
        self.last_autopilot_recheck = 0
        self.last_active_close_log_time = 0

        self.first_real_mode_warning = True
        
        # --- ИЗМЕНЕНИЕ v6.63: Новые значения по умолчанию ---
        self.trading_pair = tk.StringVar(value="BTCUSDT")
        self.position_size_usd = tk.DoubleVar(value=60.0)
        self.leverage = tk.IntVar(value=10)
        self.grid_levels = tk.IntVar(value=50) # <--- ИЗМЕНЕНО
        self.grid_step = tk.DoubleVar(value=0.05)
        self.grid_scale_multiplier = tk.DoubleVar(value=1.0)
        self.update_interval = tk.DoubleVar(value=10.0)
        self.paper_start_balance = tk.DoubleVar(value=1000.0)
        self.maker_fee = tk.DoubleVar(value=0.02)
        self.dynamic_step_mode = tk.BooleanVar(value=True)
        self.atr_timeframe = tk.StringVar(value='1h') # <--- ИЗМЕНЕНО
        self.atr_period = tk.IntVar(value=14)
        self.atr_multiplier = tk.DoubleVar(value=0.2) # <--- ИЗМЕНЕНО
        
        # --- v1.21 УЛУЧШЕНИЯ ---
        self.trailing_grid_up_mode = tk.BooleanVar(value=True)
        self.trailing_grid_down_mode = tk.BooleanVar(value=True) # NEW v1.21
        # ---
        
        # --- НОВОЕ v1.22: Агрессивный Трейлинг ---
        self.aggressive_trailing_mode = tk.BooleanVar(value=False)
        # ---
        
        self.trend_filter_enabled = tk.BooleanVar(value=True)
        self.trend_timeframe = tk.StringVar(value='1h')
        self.ema_period = tk.IntVar(value=200)
        self.harpoon_mode = tk.BooleanVar(value=True)
        self.harpoon_tp_percent = tk.DoubleVar(value=1.0)
        self.take_profit_price = tk.DoubleVar(value=0.0)
        self.stop_loss_price = tk.DoubleVar(value=0.0)
        self.auto_stop_trigger_mode = tk.BooleanVar(value=True) # <--- ИЗМЕНЕНО
        self.auto_tp_offset_percent = tk.DoubleVar(value=1.0)
        self.auto_sl_offset_percent = tk.DoubleVar(value=1.0)
        self.adaptive_sl_mode = tk.BooleanVar(value=True) # <--- ИЗМЕНЕНО
        self.sl_atr_multiplier = tk.DoubleVar(value=2.0)
        self.stop_on_sl = tk.BooleanVar(value=False) # <--- ИЗМЕНЕНО
        self.scanner_liquidity_filter = tk.DoubleVar(value=100000000)
        self.scanner_min_tf_volume = tk.DoubleVar(value=50000.0)
        self.scanner_timeframe = tk.StringVar(value='1h')
        self.autopilot_switch_threshold = tk.DoubleVar(value=45.0)
        self.autopilot_mode = tk.BooleanVar(value=True)
        self.autopilot_active_close = tk.BooleanVar(value=False) # <--- ИЗМЕНЕНО
        self.autopilot_allow_short = tk.BooleanVar(value=False)
        
        # --- ИЗМЕНЕНИЕ v6.59: Добавлены переменные принудительного режима ---
        self.force_long_mode = tk.BooleanVar(value=False)
        self.force_short_mode = tk.BooleanVar(value=False)
        # --- КОНЕЦ ИЗМЕНЕНИЯ ---
        
        self.api_key = tk.StringVar(); self.api_secret = tk.StringVar()
        self.paper_mode = tk.BooleanVar(value=True)
        self.load_keys_flag = tk.BooleanVar(value=False)
        self.scanner_volatile_mode = tk.BooleanVar(value=True) # <--- ИЗМЕНЕНО
        # --- КОНЕЦ ИЗМЕНЕНИЯ v6.63 ---
        
        self.log_queue = queue.Queue()
        self.scanner_queue = queue.Queue()
        self.current_price = {'bid': 0.0, 'ask': 0.0}
        self.symbol_info = {}
        self.base_asset = ""; self.quote_asset = ""
        self.total_profit_usd = 0.0
        self.trade_count = 0
        self.grid = {'buy': [], 'sell': [], 'center': 0.0, 'step': 0.0}
        self.last_indicators_check_time = 0
        self.last_ema_value = 0.0
        self.sl_atr_value = 0.0
        self.trading_allowed_by_trend = True
        self.is_short_mode = False
        self.last_pause_log_time = 0
        self.last_switch_log_time = 0
        self.last_sync_time = 0
        self.last_trail_log_time = 0
        self.paper_base_balance = 0.0
        self.paper_quote_balance = 1000.0
        self.paper_open_orders = []
        self.paper_inventory = []
        self.real_open_orders = []
        self.real_position = {'positionAmt': 0.0, 'entryPrice': 0.0}
        self.real_quote_balance = 0.0
        self.real_available_balance = 0.0
        self.required_margin = tk.StringVar(value="N/A")
        self.grid_range = tk.StringVar(value="N/A")
        self.profit_per_level = tk.StringVar(value="N/A")
        self.floating_pnl = tk.StringVar(value="0.00")
        
        # Переменные для хранения ссылок на экземпляры
        self.trader = None
        self.autopilot = None
        
        self.metric_vars = {} # v1.21 FIX

        if ANALYSIS_AVAILABLE:
            self.chart_df = None
            self.pnl_history = []
            
        # --- ИЗМЕНЕНИЕ v6.60: Переменная для ТФ графика ---
        self.chart_timeframe = tk.StringVar(value='5m')
        # --- КОНЕЦ ИЗМЕНЕНИЯ ---
            
        self.ws_base_url = "wss://fstream.binance.com/ws/"
        self.stop_ws_flag = threading.Event()
        self.chart_update_lock = threading.Lock()
        self.last_chart_update_time = 0
        
        # --- v1.25 FIX: Убираем спам из логов ---
        self._last_chart_log_spam = 0 
        # ---

        # --- v1.21 ИЗМЕНЕНИЕ ПОРЯДКА ---
        self.setup_ui()
        self.start_periodic_updates()
        self.update_metrics()
        self.root.after(100, self.reset_history)
        self.root.after(100, self.update_risk_calculator)
        for var in [self.position_size_usd, self.grid_levels, self.grid_step, self.maker_fee, self.dynamic_step_mode, self.grid_scale_multiplier]:
            var.trace_add("write", self.update_risk_calculator)
        # ---

    def queue_log(self, message, level="info"): 
        # v1.21 FIX: Проверка на существование очереди
        if hasattr(self, 'log_queue'):
            self.log_queue.put((message, level))

    def _set_to_zero_on_empty(self, var):
        try:
            current_value = var.get()
            if not current_value or (isinstance(current_value, str) and current_value.strip() == ''):
                if isinstance(var, tk.IntVar): var.set(0)
                elif isinstance(var, tk.DoubleVar): var.set(0.0)
        except tk.TclError: pass

    def _get_safe_int(self, var, default=0):
        try: return var.get()
        except tk.TclError: return default

    def _get_safe_double(self, var, default=0.0):
        try: return var.get()
        except tk.TclError: return default

    def _get_allowed_orders(self):
        try:
            val_str = self.e_allowed_orders.get()
            return int(val_str) if val_str and int(val_str) >= 0 else 1
        except (ValueError, tk.TclError): return 1

    def _format_quantity(self, n, precision_key):
        precision = self.symbol_info.get(precision_key, 8)
        return f"{float(n):.{precision}f}"

    def _round_price_to_tick_size(self, price):
        tick_size = self.symbol_info.get('tickSize', 0.0)
        if tick_size > 0:
            return (price // tick_size) * tick_size
        return price

    def _format_and_round_price(self, price):
        rounded_price = self._round_price_to_tick_size(price)
        return self._format_quantity(rounded_price, 'pricePrecision')

    def setup_ui(self):
        self.bg_color = '#2E2E2E'; self.fg_color = '#FFFFFF'; self.entry_bg = '#3C3C3C'
        self.button_color = '#5A5A5A'; self.accent_color = '#007ACC'; self.profit_color = '#2E7D32'; self.loss_color = '#C62828'
        self.real_mode_color = '#B71C1C'; self.pause_color = '#FF8F00'; self.emergency_color = '#D32F2F'
        
        # --- ИЗМЕНЕНИЕ v6.59: Стили для новых галочек ---
        self.long_color = '#00C853'; self.short_color = '#FF5252'
        # --- КОНЕЦ ИЗМЕНЕНИЯ ---

        self.root.configure(bg=self.bg_color)
        style = ttk.Style(self.root)
        style.theme_use('clam')
        style.configure('.', background=self.bg_color, foreground=self.fg_color, fieldbackground=self.entry_bg)
        style.configure('TLabel', background=self.bg_color, foreground=self.fg_color, padding=(0,0))
        style.configure('TButton', background=self.button_color, foreground=self.fg_color)
        style.map('TButton', background=[('active', self.accent_color)])
        style.configure('Emergency.TButton', background=self.emergency_color, foreground=self.fg_color)
        style.map('Emergency.TButton', background=[('active', self.loss_color)])
        style.configure('TEntry', fieldbackground=self.entry_bg, foreground=self.fg_color, insertcolor=self.fg_color)
        style.configure('TLabelframe', background=self.bg_color, bordercolor=self.fg_color, padding=(5,0))
        style.configure('TLabelframe.Label', background=self.bg_color, foreground=self.fg_color)
        style.configure('Treeview', fieldbackground=self.entry_bg, background=self.entry_bg, foreground=self.fg_color)
        style.configure('Treeview.Heading', background=self.button_color, foreground=self.fg_color)
        style.map('Treeview.Heading', background=[('active', self.accent_color)])
        style.configure('TNotebook', background=self.bg_color, borderwidth=0)
        style.configure('TNotebook.Tab', background=self.button_color, foreground=self.fg_color)
        style.map('TNotebook.Tab', background=[('selected', self.accent_color)])
        style.configure('Real.TCheckbutton', foreground=self.real_mode_color, background=self.bg_color, font=('TkDefaultFont', 9, 'bold'))
        style.configure('Auto.TCheckbutton', foreground=self.accent_color, background=self.bg_color, font=('TkDefaultFont', 9, 'bold'))
        
        # --- ИЗМЕНЕНИЕ v6.59: Стили для новых галочек ---
        style.configure('ForceLong.TCheckbutton', foreground=self.long_color, background=self.bg_color, font=('TkDefaultFont', 9, 'bold'))
        style.configure('ForceShort.TCheckbutton', foreground=self.short_color, background=self.bg_color, font=('TkDefaultFont', 9, 'bold'))
        # --- КОНЕЦ ИЗМЕНЕНИЯ ---
        
        style.configure('Pause.TLabel', background=self.bg_color, foreground=self.pause_color, font=('TkDefaultFont', 9, 'bold'))
        style.configure('Finishing.TLabel', background=self.bg_color, foreground='#FFC107', font=('TkDefaultFont', 9, 'bold'))
        
        # --- ИЗМЕНЕНИЕ v6.60: Стиль для Combobox ---
        style.map('TCombobox', fieldbackground=[('readonly', self.entry_bg)])
        style.map('TCombobox', selectbackground=[('readonly', self.entry_bg)])
        style.map('TCombobox', selectforeground=[('readonly', self.fg_color)])
        # --- КОНЕЦ ИЗМЕНЕНИЯ ---

        paned_window = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned_window.pack(expand=True, fill="both", padx=10, pady=5)

        left_panel_container = ttk.Frame(paned_window, width=420)
        paned_window.add(left_panel_container, weight=1)
        canvas = tk.Canvas(left_panel_container, bg=self.bg_color, highlightthickness=0)
        scrollbar = ttk.Scrollbar(left_panel_container, orient=tk.VERTICAL, command=canvas.yview)
        
        left_panel = ttk.Frame(canvas) # v1.21 FIX: Восстановлена строка
        
        left_panel.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=left_panel, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        def _on_mousewheel(event):
            # v1.21 FIX: Защита от ошибки, если canvas уже удален
            try:
                if hasattr(canvas, 'winfo_exists') and canvas.winfo_exists():
                    canvas.yview_scroll(int(-1*(event.delta/120)), "units")
            except tk.TclError:
                pass
        
        # v1.21 FIX: Используем bind_all для left_panel, чтобы работало надежнее
        left_panel.bind_all("<MouseWheel>", _on_mousewheel)


        api_frame = ttk.LabelFrame(left_panel, text="Ключи API Binance")
        api_frame.pack(fill="x", pady=0, padx=5)
        ttk.Checkbutton(api_frame, text="Загрузить из binance_keys.txt", variable=self.load_keys_flag, command=self.toggle_load_keys).grid(row=0, column=0, columnspan=2, sticky="w", padx=5, pady=0)
        ttk.Label(api_frame, text="API Key:").grid(row=1, column=0, sticky="w", padx=5, pady=0)
        ttk.Entry(api_frame, textvariable=self.api_key, width=40).grid(row=1, column=1, padx=5, pady=0)
        ttk.Label(api_frame, text="API Secret:").grid(row=2, column=0, sticky="w", padx=5, pady=0)
        ttk.Entry(api_frame, textvariable=self.api_secret, show="*", width=40).grid(row=2, column=1, padx=5, pady=0)

        maker_frame = ttk.LabelFrame(left_panel, text="Параметры Сетки")
        maker_frame.pack(fill="x", pady=0, padx=5)
        ttk.Label(maker_frame, text="Торговая пара:").grid(row=0, column=0, sticky="w", padx=5, pady=0)
        self.pair_entry = ttk.Entry(maker_frame, textvariable=self.trading_pair, width=20)
        self.pair_entry.grid(row=0, column=1, padx=5, sticky="w", pady=0)

        ttk.Label(maker_frame, text="Размер позиции (USDT):").grid(row=1, column=0, sticky="w", padx=5, pady=0)
        e_pos_size = ttk.Entry(maker_frame, textvariable=self.position_size_usd, width=20)
        e_pos_size.grid(row=1, column=1, padx=5, sticky="w", pady=0)
        e_pos_size.bind('<FocusOut>', lambda e: self._set_to_zero_on_empty(self.position_size_usd))

        ttk.Label(maker_frame, text="Кредитное плечо (x):").grid(row=2, column=0, sticky="w", padx=5, pady=0)
        e_leverage = ttk.Entry(maker_frame, textvariable=self.leverage, width=20)
        e_leverage.grid(row=2, column=1, padx=5, sticky="w", pady=0)
        e_leverage.bind('<FocusOut>', lambda e: self._set_to_zero_on_empty(self.leverage))

        ttk.Label(maker_frame, text="Кол-во уровней сетки:").grid(row=3, column=0, sticky="w", padx=5, pady=0)
        e_levels = ttk.Entry(maker_frame, textvariable=self.grid_levels, width=20)
        e_levels.grid(row=3, column=1, padx=5, sticky="w", pady=0)
        e_levels.bind('<FocusOut>', lambda e: self._set_to_zero_on_empty(self.grid_levels))

        ttk.Label(maker_frame, text="Шаг сетки (ручной, %):").grid(row=4, column=0, sticky="w", padx=5, pady=0)
        e_step = ttk.Entry(maker_frame, textvariable=self.grid_step, width=20)
        e_step.grid(row=4, column=1, padx=5, sticky="w", pady=0)
        e_step.bind('<FocusOut>', lambda e: self._set_to_zero_on_empty(self.grid_step))

        ttk.Label(maker_frame, text="Множитель уровня:").grid(row=5, column=0, sticky="w", padx=5, pady=0)
        e_scale_mult = ttk.Entry(maker_frame, textvariable=self.grid_scale_multiplier, width=20)
        e_scale_mult.grid(row=5, column=1, padx=5, sticky="w", pady=0)
        e_scale_mult.bind('<FocusOut>', lambda e: self._set_to_zero_on_empty(self.grid_scale_multiplier))

        ttk.Label(maker_frame, text="Интервал обновления (сек):").grid(row=6, column=0, sticky="w", padx=5, pady=0)
        e_interval = ttk.Entry(maker_frame, textvariable=self.update_interval, width=20)
        e_interval.grid(row=6, column=1, padx=5, sticky="w", pady=0)
        e_interval.bind('<FocusOut>', lambda e: self._set_to_zero_on_empty(self.update_interval))

        pro_frame = ttk.LabelFrame(left_panel, text="Адаптивные Механизмы")
        pro_frame.pack(fill="x", pady=0, padx=5)
        ttk.Checkbutton(pro_frame, text="Динамический шаг сетки (ATR)", variable=self.dynamic_step_mode).grid(row=0, column=0, columnspan=2, sticky="w", padx=5, pady=0)

        ttk.Label(pro_frame, text="  Таймфрейм ATR:").grid(row=1, column=0, sticky="w", padx=5, pady=0)
        ttk.Entry(pro_frame, textvariable=self.atr_timeframe, width=10).grid(row=1, column=1, padx=5, sticky="w", pady=0)

        ttk.Label(pro_frame, text="  Период ATR:").grid(row=2, column=0, sticky="w", padx=5, pady=0)
        e_atr_period = ttk.Entry(pro_frame, textvariable=self.atr_period, width=10)
        e_atr_period.grid(row=2, column=1, padx=5, sticky="w", pady=0)
        e_atr_period.bind('<FocusOut>', lambda e: self._set_to_zero_on_empty(self.atr_period))

        ttk.Label(pro_frame, text="  Множитель ATR:").grid(row=3, column=0, sticky="w", padx=5, pady=0)
        e_atr_mult = ttk.Entry(pro_frame, textvariable=self.atr_multiplier, width=10)
        e_atr_mult.grid(row=3, column=1, padx=5, sticky="w", pady=0)
        e_atr_mult.bind('<FocusOut>', lambda e: self._set_to_zero_on_empty(self.atr_multiplier))

        ttk.Separator(pro_frame, orient='horizontal').grid(row=4, column=0, columnspan=2, sticky='ew', pady=0)
        ttk.Checkbutton(pro_frame, text="Следящая сетка вверх (Чуткая)", variable=self.trailing_grid_up_mode).grid(row=5, column=0, columnspan=2, sticky="w", padx=5, pady=0)
        
        # --- NEW v1.21 ---
        ttk.Checkbutton(pro_frame, text="Следящая сетка вниз (Чуткая)", variable=self.trailing_grid_down_mode).grid(row=6, column=0, columnspan=2, sticky="w", padx=5, pady=0)
        
        # --- НОВОЕ v1.22: Агрессивный Трейлинг ---
        ttk.Checkbutton(pro_frame, text="Агрессивный Трейлинг Сетки (NON-STOP)", variable=self.aggressive_trailing_mode).grid(row=7, column=0, columnspan=2, sticky="w", padx=5, pady=0)
        # --- КОНЕЦ v1.22 ---
        
        ttk.Separator(pro_frame, orient='horizontal').grid(row=8, column=0, columnspan=2, sticky='ew', pady=0) # v1.21: row 7 -> 8
        
        ttk.Checkbutton(pro_frame, text="Фильтр тренда (EMA)", variable=self.trend_filter_enabled).grid(row=9, column=0, columnspan=2, sticky="w", padx=5, pady=0) # v1.21: row 8 -> 9

        ttk.Label(pro_frame, text="  Таймфрейм EMA:").grid(row=10, column=0, sticky="w", padx=5, pady=0) # v1.21: row 9 -> 10
        ttk.Entry(pro_frame, textvariable=self.trend_timeframe, width=10).grid(row=10, column=1, padx=5, sticky="w", pady=0) # v1.21: row 9 -> 10

        ttk.Label(pro_frame, text="  Период EMA:").grid(row=11, column=0, sticky="w", padx=5, pady=0) # v1.21: row 10 -> 11
        e_ema_period = ttk.Entry(pro_frame, textvariable=self.ema_period, width=10)
        e_ema_period.grid(row=11, column=1, padx=5, sticky="w", pady=0) # v1.21: row 10 -> 11
        e_ema_period.bind('<FocusOut>', lambda e: self._set_to_zero_on_empty(self.ema_period))

        ttk.Label(pro_frame, text="  Лимит ордеров при паузе:").grid(row=12, column=0, sticky="w", padx=5, pady=0) # v1.21: row 11 -> 12
        self.e_allowed_orders = ttk.Entry(pro_frame, width=10)
        self.e_allowed_orders.grid(row=12, column=1, padx=5, sticky="w", pady=0) # v1.21: row 11 -> 12
        self.e_allowed_orders.insert(0, '5')

        ttk.Separator(pro_frame, orient='horizontal').grid(row=13, column=0, columnspan=2, sticky='ew', pady=0) # v1.21: row 12 -> 13
        ttk.Checkbutton(pro_frame, text="Режим Гарпун (Единый TP)", variable=self.harpoon_mode).grid(row=14, column=0, columnspan=2, sticky="w", padx=5, pady=0) # v1.21: row 13 -> 14
        
        ttk.Label(pro_frame, text="  Профит Гарпуна (%):").grid(row=15, column=0, sticky="w", padx=5, pady=0) # v1.21: row 14 -> 15
        e_harpoon_tp = ttk.Entry(pro_frame, textvariable=self.harpoon_tp_percent, width=10)
        e_harpoon_tp.grid(row=15, column=1, padx=5, sticky="w", pady=0) # v1.21: row 14 -> 15
        e_harpoon_tp.bind('<FocusOut>', lambda e: self._set_to_zero_on_empty(self.harpoon_tp_percent))

        risk_management_frame = ttk.LabelFrame(left_panel, text="Управление рисками")
        risk_management_frame.pack(fill="x", pady=0, padx=5)

        # --- ИЗМЕНЕНИЕ v6.67: Добавлено "окошко" для Маржи ---
        ttk.Label(risk_management_frame, text="Необходимая маржа:", font=('TkDefaultFont', 9, 'bold')).grid(row=0, column=0, sticky="w", padx=5, pady=0)
        ttk.Label(risk_management_frame, textvariable=self.required_margin).grid(row=0, column=1, sticky="w", padx=5, pady=0)
        # --- КОНЕЦ ИЗМЕНЕНИЯ ---

        auto_stops_check = ttk.Checkbutton(risk_management_frame, text="Автоматический расчет SL/TP", variable=self.auto_stop_trigger_mode, command=self.update_risk_ui)
        auto_stops_check.grid(row=1, column=0, columnspan=2, sticky="w", padx=5, pady=0) # <--- row 1

        ttk.Label(risk_management_frame, text="  Отступ TP от сетки (%):").grid(row=2, column=0, sticky="w", padx=5, pady=0) # <--- row 2
        self.auto_tp_entry = ttk.Entry(risk_management_frame, textvariable=self.auto_tp_offset_percent, width=10)
        self.auto_tp_entry.grid(row=2, column=1, padx=5, sticky="w", pady=0) # <--- row 2
        self.auto_tp_entry.bind('<FocusOut>', lambda e: self._set_to_zero_on_empty(self.auto_tp_offset_percent))

        ttk.Separator(risk_management_frame, orient='horizontal').grid(row=3, column=0, columnspan=2, sticky='ew', pady=0) # <--- row 3

        self.adaptive_sl_check = ttk.Checkbutton(risk_management_frame, text="Адаптивный Stop Loss (ATR)", variable=self.adaptive_sl_mode, command=self.update_risk_ui)
        self.adaptive_sl_check.grid(row=4, column=0, columnspan=2, sticky="w", padx=5, pady=0) # <--- row 4

        ttk.Label(risk_management_frame, text="    Множитель ATR для SL:").grid(row=5, column=0, sticky="w", padx=5, pady=0) # <--- row 5
        self.sl_atr_mult_entry = ttk.Entry(risk_management_frame, textvariable=self.sl_atr_multiplier, width=10)
        self.sl_atr_mult_entry.grid(row=5, column=1, padx=5, sticky="w", pady=0) # <--- row 5
        self.sl_atr_mult_entry.bind('<FocusOut>', lambda e: self._set_to_zero_on_empty(self.sl_atr_multiplier))

        ttk.Label(risk_management_frame, text="    Отступ SL от сетки (%):").grid(row=6, column=0, sticky="w", padx=5, pady=0) # <--- row 6
        self.auto_sl_entry = ttk.Entry(risk_management_frame, textvariable=self.auto_sl_offset_percent, width=10)
        self.auto_sl_entry.grid(row=6, column=1, padx=5, sticky="w", pady=0) # <--- row 6
        self.auto_sl_entry.bind('<FocusOut>', lambda e: self._set_to_zero_on_empty(self.auto_sl_offset_percent))

        ttk.Separator(risk_management_frame, orient='horizontal').grid(row=7, column=0, columnspan=2, sticky='ew', pady=0) # <--- row 7

        ttk.Label(risk_management_frame, text="Take Profit (цена):", foreground=self.profit_color).grid(row=8, column=0, sticky="w", padx=5, pady=0) # <--- row 8
        self.manual_tp_entry = ttk.Entry(risk_management_frame, textvariable=self.take_profit_price, width=20)
        self.manual_tp_entry.grid(row=8, column=1, padx=5, sticky="w", pady=0) # <--- row 8

        ttk.Label(risk_management_frame, text="Stop Loss (цена):", foreground=self.loss_color).grid(row=9, column=0, sticky="w", padx=5, pady=0) # <--- row 9
        self.manual_sl_entry = ttk.Entry(risk_management_frame, textvariable=self.stop_loss_price, width=20)
        self.manual_sl_entry.grid(row=9, column=1, padx=5, sticky="w", pady=0) # <--- row 9

        ttk.Checkbutton(risk_management_frame, text="Останавливать после SL", variable=self.stop_on_sl).grid(row=10, column=0, columnspan=2, sticky="w", padx=5, pady=0) # <--- row 10

        scanner_frame = ttk.LabelFrame(left_panel, text="Сканер и Автопилот")
        scanner_frame.pack(fill="x", pady=0, padx=5)

        ttk.Label(scanner_frame, text="Мин. объем 24ч (USDT):").grid(row=0, column=0, sticky="w", padx=5, pady=0)
        e_liq_filter = ttk.Entry(scanner_frame, textvariable=self.scanner_liquidity_filter, width=20)
        e_liq_filter.grid(row=0, column=1, padx=5, sticky="w", pady=0)
        e_liq_filter.bind('<FocusOut>', lambda e: self._set_to_zero_on_empty(self.scanner_liquidity_filter))

        ttk.Label(scanner_frame, text="Таймфрейм анализа:").grid(row=1, column=0, sticky="w", padx=5, pady=0)
        ttk.Entry(scanner_frame, textvariable=self.scanner_timeframe, width=20).grid(row=1, column=1, padx=5, sticky="w", pady=0)

        ttk.Label(scanner_frame, text="Мин. объем ТФ (USDT):").grid(row=2, column=0, sticky="w", padx=5, pady=0)
        e_tf_vol = ttk.Entry(scanner_frame, textvariable=self.scanner_min_tf_volume, width=20)
        e_tf_vol.grid(row=2, column=1, padx=5, sticky="w", pady=0)
        e_tf_vol.bind('<FocusOut>', lambda e: self._set_to_zero_on_empty(self.scanner_min_tf_volume))

        ttk.Label(scanner_frame, text="Выгода переключения (%):").grid(row=3, column=0, sticky="w", padx=5, pady=0)
        e_threshold = ttk.Entry(scanner_frame, textvariable=self.autopilot_switch_threshold, width=20)
        e_threshold.grid(row=3, column=1, padx=5, sticky="w", pady=0)
        e_threshold.bind('<FocusOut>', lambda e: self._set_to_zero_on_empty(self.autopilot_switch_threshold))

        ttk.Checkbutton(scanner_frame, text="Искать волатильный флэт", variable=self.scanner_volatile_mode).grid(row=4, column=0, columnspan=2, sticky="w", padx=5, pady=0)
        ttk.Checkbutton(scanner_frame, text="Активное закрытие Автопилота", variable=self.autopilot_active_close).grid(row=5, column=0, columnspan=2, sticky="w", padx=5, pady=0)
        ttk.Checkbutton(scanner_frame, text="Разрешить SHORT-Гарпун (Анти-Гарпун)", variable=self.autopilot_allow_short).grid(row=6, column=0, columnspan=2, sticky="w", padx=5, pady=0) # NEW: Разрешение Short
        
        # --- ИЗМЕНЕНИЕ v6.59: Добавлены галочки принудительного режима ---
        ttk.Separator(scanner_frame, orient='horizontal').grid(row=7, column=0, columnspan=2, sticky='ew', pady=2)
        
        force_mode_frame = ttk.Frame(scanner_frame)
        force_mode_frame.grid(row=8, column=0, columnspan=2, sticky="ew")
        
        ttk.Checkbutton(force_mode_frame, text="Только LONG", variable=self.force_long_mode, 
                        style="ForceLong.TCheckbutton", command=lambda: self._toggle_force_mode('long')).pack(side="left", expand=True, padx=5)
        ttk.Checkbutton(force_mode_frame, text="Только SHORT", variable=self.force_short_mode, 
                        style="ForceShort.TCheckbutton", command=lambda: self._toggle_force_mode('short')).pack(side="right", expand=True, padx=5)
        # --- КОНЕЦ ИЗМЕНЕНИЯ ---

        control_frame = ttk.LabelFrame(left_panel, text="Управление")
        control_frame.pack(fill="x", pady=0, padx=5)
        mode_frame = ttk.Frame(control_frame); mode_frame.pack(fill='x', pady=0)
        ttk.Checkbutton(mode_frame, text="РЕАЛЬНАЯ ТОРГОВЛЯ", variable=self.paper_mode, onvalue=False, offvalue=True, style="Real.TCheckbutton", command=self.toggle_mode).pack(side="left", padx=10)
        ttk.Checkbutton(mode_frame, text="АВТОПИЛОТ", variable=self.autopilot_mode, command=self.toggle_autopilot, onvalue=True, offvalue=False, style="Auto.TCheckbutton").pack(side="right", padx=10)

        btn_frame = ttk.Frame(control_frame); btn_frame.pack(fill='x', expand=True, pady=0)
        self.btn_start = ttk.Button(btn_frame, text="СТАРТ БОТА", command=self.start_maker)
        self.btn_start.pack(side="left", expand=True, fill="x", padx=5)
        self.btn_stop = ttk.Button(btn_frame, text="СТОП БОТА", command=self.stop_maker, state=tk.DISABLED)
        self.btn_stop.pack(side="left", expand=True, fill="x", padx=5)

        emergency_frame = ttk.Frame(control_frame); emergency_frame.pack(fill='x', expand=True, pady=(2,0))
        self.btn_close_all = ttk.Button(emergency_frame, text="Закрыть всё по рынку", command=self.close_all_market_emergency, style="Emergency.TButton")
        self.btn_close_all.pack(side="left", expand=True, fill="x", padx=5)

        self.status_label = ttk.Label(control_frame, text="Ожидание приказа...")
        self.status_label.pack(pady=0)

        metrics_frame = ttk.LabelFrame(left_panel, text="")
        metrics_frame.pack(fill="x", pady=0, padx=5)
        # self.metric_vars = {} # v1.21: Перенесено в __init__
        metrics = ["Режим", "Общий PnL ($)", "Плавающий PnL ($)", "Всего Сделок", "WS Статус", "Фильтр Тренда", "Баланс BASE", "Баланс QUOTE", "Доступно QUOTE"] # MODIFIED v6.56
        for i, metric in enumerate(metrics):
            var = tk.StringVar(value="N/A")
            if metric == "Плавающий PnL ($)": # NEW v6.56
                var = self.floating_pnl # Использовать специальную переменную

            ttk.Label(metrics_frame, text=f"{metric}:", font=('TkDefaultFont', 9, 'bold')).grid(row=i, column=0, sticky="w", padx=5, pady=0)
            label_widget = ttk.Label(metrics_frame, textvariable=var) # MODIFIED v6.56
            label_widget.grid(row=i, column=1, sticky="w", padx=5, pady=0)
            
            if metric == "Плавающий PnL ($)": # NEW v6.56
                self.floating_pnl_label = label_widget # Сохраняем для изменения цвета
                
            self.metric_vars[metric] = var
        ttk.Button(metrics_frame, text="Сбросить Статистику", command=self.reset_history).grid(row=len(metrics), columnspan=2, sticky="ew", padx=5, pady=(2,0))

        right_panel = ttk.Frame(paned_window); paned_window.add(right_panel, weight=3)
        self.notebook = ttk.Notebook(right_panel); self.notebook.pack(expand=True, fill="both")
        
        # --- ИЗМЕНЕНИЕ v6.60: Добавлен Combobox и фрейм управления графиком ---
        chart_tab = ttk.Frame(self.notebook); self.notebook.add(chart_tab, text="График")
        if ANALYSIS_AVAILABLE:
            mc = mpf.make_marketcolors(up=self.accent_color, down=self.loss_color, inherit=True)
            self.mpf_style = mpf.make_mpf_style(base_mpf_style='nightclouds', marketcolors=mc, facecolor=self.entry_bg)
            self.fig = Figure(figsize=(5, 5), dpi=100); self.fig.patch.set_facecolor(self.bg_color)
            self.ax_main, self.ax_volume = self.fig.subplots(2, 1, sharex=True, gridspec_kw={'height_ratios': [3, 1], 'hspace': 0})
            self.ax_main.set_facecolor(self.entry_bg); self.ax_volume.set_facecolor(self.entry_bg)
            
            # Фрейм для холста
            canvas_frame = ttk.Frame(chart_tab)
            canvas_frame.pack(expand=True, fill='both', padx=5, pady=5)
            self.canvas = FigureCanvasTkAgg(self.fig, master=canvas_frame)
            self.canvas.get_tk_widget().pack(expand=True, fill='both')

            # Фрейм для кнопок
            chart_control_frame = ttk.Frame(chart_tab)
            chart_control_frame.pack(fill='x', padx=5, pady=5)

            ttk.Label(chart_control_frame, text="Таймфрейм:").pack(side="left", padx=(0, 5))
            
            tf_values = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '12h', '1d']
            self.chart_tf_combobox = ttk.Combobox(chart_control_frame, textvariable=self.chart_timeframe, values=tf_values, state='readonly', width=5)
            self.chart_tf_combobox.pack(side="left", padx=5)
            self.chart_tf_combobox.bind('<<ComboboxSelected>>', self._on_chart_timeframe_change)
            
            ttk.Button(chart_control_frame, text="Сохранить график как изображение", command=self.save_chart).pack(side="right", fill='x', expand=True, padx=(10, 0))
        else:
            ttk.Label(chart_tab, text="График недоступен. Установите: pip install pandas matplotlib mplfinance", justify=tk.CENTER).pack(expand=True)
        # --- КОНЕЦ ИЗМЕНЕНИЯ ---

        pnl_tab = ttk.Frame(self.notebook); self.notebook.add(pnl_tab, text="Рост PnL")
        if ANALYSIS_AVAILABLE:
            self.pnl_fig = Figure(figsize=(5, 4), dpi=100)
            self.pnl_fig.patch.set_facecolor(self.bg_color)
            self.ax_pnl = self.pnl_fig.add_subplot(111)
            self.ax_pnl.set_facecolor(self.entry_bg)
            self.pnl_canvas = FigureCanvasTkAgg(self.pnl_fig, master=pnl_tab)
            self.pnl_canvas.get_tk_widget().pack(expand=True, fill='both', padx=5, pady=5)
            ttk.Button(pnl_tab, text="Сохранить график PnL как изображение", command=self.save_pnl_chart).pack(fill='x', padx=5, pady=5)
            self.update_pnl_chart()
        else:
            ttk.Label(pnl_tab, text="График недоступен.", justify=tk.CENTER).pack(expand=True)

        orders_tab = ttk.Frame(self.notebook); self.notebook.add(orders_tab, text="Открытые Ордера")
        cols_orders = ('ID', 'Пара', 'Тип', 'Цена', 'Количество');
        self.open_orders_tree = ttk.Treeview(orders_tab, columns=cols_orders, show='headings')
        for col in cols_orders: self.open_orders_tree.heading(col, text=col)
        self.open_orders_tree.pack(expand=True, fill='both')
        ttk.Button(orders_tab, text="Копировать открытые ордера", command=self.copy_open_orders).pack(fill='x', padx=5, pady=5)
        history_tab = ttk.Frame(self.notebook); self.notebook.add(history_tab, text="История Сделок")
        cols_hist = ('Время', 'Пара', 'Тип', 'Цена', 'Количество', 'PnL ($)');
        self.trade_history_tree = ttk.Treeview(history_tab, columns=cols_hist, show='headings')
        for col in cols_hist: self.trade_history_tree.heading(col, text=col)
        self.trade_history_tree.pack(expand=True, fill='both')
        ttk.Button(history_tab, text="Копировать историю сделок", command=self.copy_trade_history).pack(fill='x', padx=5, pady=5)
        scanner_tab = ttk.Frame(self.notebook); self.notebook.add(scanner_tab, text="Сканер Флэта")
        cols_scanner = ('Пара', 'Коэф. флэта (%)', 'Волатильность (%)');
        self.scanner_tree = ttk.Treeview(scanner_tab, columns=cols_scanner, show='headings')
        for col in cols_scanner: self.scanner_tree.heading(col, text=col)
        self.scanner_tree.pack(expand=True, fill='both')
        
        # --- ИЗМЕНЕНИЕ v6.65: Привязка двойного клика (Левый и Правый) ---
        self.scanner_tree.bind("<Double-1>", self._on_scanner_left_double_click)
        self.scanner_tree.bind("<Double-Button-3>", self._on_scanner_right_double_click)
        # --- КОНЕЦ ИЗМЕНЕНИЯ ---
        
        self.btn_scan = ttk.Button(scanner_tab, text="Запустить сканирование", command=self.start_scanner_thread)
        self.btn_scan.pack(fill='x', padx=5, pady=5)
        
        # --- ИЗМЕНЕНИЕ v6.68: Сохраняем ссылку на log_tab ---
        self.log_tab = ttk.Frame(self.notebook); self.notebook.add(self.log_tab, text="Логи")
        self.log_text = scrolledtext.ScrolledText(self.log_tab, wrap=tk.WORD, height=10, bg=self.entry_bg, fg=self.fg_color)
        # --- КОНЕЦ ИЗМЕНЕНИЯ ---
        
        self.log_text.pack(expand=True, fill="both", pady=(0, 5))
        ttk.Button(self.log_tab, text="Копировать лог", command=self.copy_log).pack(fill='x', padx=5, pady=5)
        self.root.after(100, self.update_risk_ui)
        self.root.after(100, self.toggle_autopilot)
        

    def start_maker(self):
        if self.running.is_set(): return
        self.running.set()
        
        # v1.21 FIX: Проверка UI
        if hasattr(self, 'btn_start') and self.btn_start.winfo_exists():
            self.btn_start.config(state=tk.DISABLED)
        if hasattr(self, 'btn_stop') and self.btn_stop.winfo_exists():
            self.btn_stop.config(state=tk.NORMAL)
        if hasattr(self, 'pair_entry') and self.pair_entry.winfo_exists():
            self.pair_entry.config(state=tk.DISABLED)
        if hasattr(self, 'status_label') and self.status_label.winfo_exists():
            self.status_label.config(text="Запускается...")
            
        self.maker_thread = threading.Thread(target=self._start_maker_core, daemon=True)
        self.maker_thread.start()

    def stop_maker(self):
        if not self.running.is_set(): return
        self.running.clear()
        
        # v1.21 FIX: Проверка UI
        if hasattr(self, 'btn_stop') and self.btn_stop.winfo_exists():
            self.btn_stop.config(state=tk.DISABLED)
            
        self.queue_log("--- ОСТАНОВКА БОТА ---", "warning");
        
        # v1.21 FIX: Проверка UI
        if hasattr(self, 'status_label') and self.status_label.winfo_exists():
            self.status_label.config(text="Останавливается...")

    def close_all_market_emergency(self):
        if not self.running.is_set():
            self.queue_log("Бот не запущен, нечего закрывать.", "warning")
            return

        if not messagebox.askyesno("Подтверждение", "Вы уверены, что хотите НЕМЕДЛЕННО закрыть все позиции и отменить все ордера по текущей паре по рынку? \n\nЭто действие необратимо и приведет к остановке бота."):
            return

        self.queue_log("--- ПОЛУЧЕНА КОМАНДА РУЧНОГО ЗАКРЫТИЯ ПО РЫНКУ ---", "emergency")

        threading.Thread(target=self._emergency_close_thread, daemon=True).start()

    def _emergency_close_thread(self):
        is_paper = self._get_safe_int(self.paper_mode, 1)

        if is_paper:
            self.root.after(0, self._close_position_and_stop, "Ручное закрытие")
        else:
            # Создаем ВРЕМЕННЫЙ экземпляр трейдера ТОЛЬКО для экстренного закрытия
            trader = BinanceTrader(self.api_key.get(), self.api_secret.get(), self.queue_log)
            symbol = self.trading_pair.get()

            trader.cancel_all_open_orders(symbol)
            time.sleep(1)

            positions_data = trader.get_position_information()
            if positions_data:
                current_pos = next((p for p in positions_data if p['symbol'] == symbol), None)
                if current_pos:
                    pos_amt = float(current_pos['positionAmt'])
                    if pos_amt != 0:
                        side = 'SELL' if pos_amt > 0 else 'BUY'
                        qty_to_close = self._format_quantity(abs(pos_amt), 'quantityPrecision')
                        self.queue_log(f"РЕАЛ: Закрытие позиции {pos_amt} {self.base_asset} по рынку.", "emergency")
                        trader.create_order(symbol, side, 'MARKET', quantity=qty_to_close)
                    else:
                        self.queue_log("РЕАL: Открытой позиции не найдено.", "info")

            self.root.after(0, self.stop_maker)

    # --- ИЗМЕНЕНИЕ v6.63: Перестроена логика старта (Сначала Пара, потом Режим) ---
    def _start_maker_core(self):
        try:
            # 1. Инициализируем BinanceTrader
            self.trader = BinanceTrader(self.api_key.get(), self.api_secret.get(), self.queue_log)
            # 2. Инициализируем AutopilotManager и передаем ему self (приложение) и trader
            self.autopilot = AutopilotManager(self, self.trader)
            
            self.autopilot_state = 'trading'
            self.potential_next_pair = None
            
            # --- v6.63: ЗАДАЧА 1: ОПРЕДЕЛЕНИЕ ПАРЫ ---
            if self._get_safe_int(self.autopilot_mode, 0):
                if self._get_safe_int(self.scanner_volatile_mode, 0):
                    self.queue_log("Автопилот: Поиск самой волатильной пары для старта...", "warning")
                else:
                     self.queue_log("Автопилот: Поиск самой стабильной пары для старта...", "warning")

                scan_results = self.autopilot.run_scanner()
                best_pair_info = scan_results[0] if scan_results else None

                if best_pair_info:
                    best_pair = best_pair_info['pair']
                    self.trading_pair.set(best_pair)
                    self.queue_log(f"Автопилот: Выбрана пара для старта: {best_pair}", "success")
                else:
                    self.queue_log("Автопилот: Не удалось найти подходящую пару, старт на BTCUSDT.", "warning")
                    self.trading_pair.set("BTCUSDT")
            else:
                self.queue_log(f"Старт на {self.trading_pair.get()} без автопилота...", "info")
            
            if not self.running.is_set(): self.root.after(0, self.stop_maker_ui); return

            # --- v6.63: ЗАДАЧА 2: ОПРЕДЕЛЕНИЕ РЕЖИМА (с приоритетом галочек) ---
            self.queue_log("РЕЖИМ: Определение режима LONG/SHORT...", "info")
            log_mode = "LONG" # По умолчанию
            
            if self._get_safe_int(self.force_long_mode, 0):
                # 1. Принудительный LONG
                self.is_short_mode = False
                log_mode = "ТОЛЬКО LONG (Принудительно)"
                
            elif self._get_safe_int(self.force_short_mode, 0):
                # 2. Принудительный SHORT
                if not self._get_safe_int(self.autopilot_allow_short, 0):
                     self.queue_log("РЕЖИМ: 'Только SHORT' невозможен. Галочка 'Разрешить SHORT' неактивна. Запуск в LONG.", "error")
                     self.is_short_mode = False
                     log_mode = "LONG (Ошибка принуд. SHORT)"
                else:
                    self.is_short_mode = True
                    log_mode = "ТОЛЬКО SHORT (Принудительно)"
            
            elif self._get_safe_int(self.trend_filter_enabled, 0):
                # 3. Авто-определение по EMA (если фильтр включен)
                self.queue_log("РЕЖИМ: Запрос EMA для определения режима...", "info")
                ema_period = self._get_safe_int(self.ema_period, 200)
                trend_timeframe = self.trend_timeframe.get()
                klines = self.trader.get_klines(self.trading_pair.get(), trend_timeframe, ema_period)
                self.last_ema_value = self._calculate_ema(klines, ema_period)
                
                # v6.62: Нужна цена для сравнения с EMA
                current_price = self.trader.get_ticker_price(self.trading_pair.get()) or 0.0 

                if self.last_ema_value > 0 and current_price > 0:
                    is_below_ema = current_price < self.last_ema_value
                    is_short_allowed = self._get_safe_int(self.autopilot_allow_short, 0)
                    self.is_short_mode = is_below_ema and is_short_allowed
                    log_mode = "SHORT (по EMA)" if self.is_short_mode else "LONG (по EMA)"
                    self.queue_log(f"РЕЖИМ: (Цена: {current_price}, EMA: {self.last_ema_value:.4f}). Выбран {log_mode}", "info")
                else:
                    self.queue_log("РЕЖИМ: Не удалось получить цену или EMA. Запуск в LONG.", "warning")
                    self.is_short_mode = False
                    log_mode = "LONG (Ошибка EMA)"
            else:
                # 4. Фильтр EMA выключен, галочки не нажаты
                self.is_short_mode = False 
                log_mode = "LONG (По умолчанию)"
            
            self.queue_log(f"РЕЖИМ: Итоговый режим для старта: {log_mode}", "success")
            # --- КОНЕЦ v6.63 ЛОГИКИ ОПРЕДЕЛЕНИЯ РЕЖИМА ---

            # --- v6.62: Добавлено логирование "Зависания" ---
            self.queue_log("РЕЖИМ: Запрос информации о символе...", "info")
            if not self.get_symbol_info(self.trader): 
                self.root.after(0, self.stop_maker_ui); return
            
            self.queue_log("Получение цены для быстрой расстановки сетки...", "info")
            initial_price = self.trader.get_ticker_price(self.trading_pair.get())
            if not initial_price:
                self.queue_log("Не удалось получить цену для старта. Остановка.", "error")
                self.root.after(0, self.stop_maker_ui)
                return
            # --- КОНЕЦ v6.62 ---

            self.current_price['bid'] = initial_price; self.current_price['ask'] = initial_price
            self.reset_history(); self.root.after(0, self.toggle_mode); self.create_grid(self.trader)
            self.ws_thread = threading.Thread(target=self._run_websocket_stream, daemon=True)
            self.ws_thread.start()

            self.queue_log(f"--- СЕТОЧНЫЙ БОТ ЗАПУЩЕН для {self.trading_pair.get()} в режиме {'SHORT' if self.is_short_mode else 'LONG'} ---", "success")
            
            # v1.21 FIX: Проверка UI
            if hasattr(self, 'status_label') and self.status_label.winfo_exists():
                self.root.after(0, self.status_label.config, {'text': 'Работает...'})
                
            self.market_maker_loop(self.trader, self.autopilot)

        except Exception as e:
            # --- v6.62: Ловим ошибки старта (для "Зависания") ---
            self.queue_log(f"КРИТ. ОШИБКА в _start_maker_core: {repr(e)}", "error")
            import traceback; self.queue_log(traceback.format_exc(), "error")
            self.root.after(0, self.stop_maker_ui)
            return
        # --- КОНЕЦ v6.62 ---

        if self.ws:
            self.stop_ws_flag.set()
            if self.ws.sock and self.ws.sock.connected: self.ws.close()
            if self.ws_thread and self.ws_thread.is_alive(): self.ws_thread.join(timeout=0.5)

        self.root.after(0, self.stop_maker_ui)
    def get_symbol_info(self, trader):
        try:
            info = trader.get_exchange_info()
            if not info: return False
            s_data = next((s for s in info['symbols'] if s['symbol'] == self.trading_pair.get().upper()), None)
            if not s_data:
                self.queue_log(f"ОШИБКА: Пара {self.trading_pair.get()} не найдена.", "error")
                return False

            self.base_asset = s_data['baseAsset']; self.quote_asset = s_data['quoteAsset']
            self.symbol_info['quantityPrecision'] = s_data['quantityPrecision']
            self.symbol_info['pricePrecision'] = s_data['pricePrecision']
            lot_size_filter = next((f for f in s_data['filters'] if f['filterType'] == 'LOT_SIZE'), None)
            self.symbol_info['minQty'] = float(lot_size_filter['minQty']) if lot_size_filter else 0.001
            price_filter = next((f for f in s_data['filters'] if f['filterType'] == 'PRICE_FILTER'), None)
            self.symbol_info['tickSize'] = float(price_filter['tickSize']) if price_filter else 0.0
            self.queue_log(f"Пара {self.base_asset}/{self.quote_asset} найдена. Мин. кол-во: {self.symbol_info['minQty']}. Шаг цены: {self.symbol_info['tickSize']}", "success")
            return True
        except Exception as e:
            self.queue_log(f"КРИТ. ОШИБКА get_symbol_info: {repr(e)}", "error")
            return False

    def market_maker_loop(self, trader, autopilot):
        last_autopilot_scan = time.time()

        if not self._get_safe_int(self.paper_mode, 1):
            self.queue_log("РЕАЛ: Первичная синхронизация с биржей...", "info")
            self.last_sync_time = 0
            time.sleep(2)

        while self.running.is_set():
            try:
                if self.current_price['bid'] == 0.0: time.sleep(1); continue

                position_closed = self._check_stop_triggers()
                if not self.running.is_set(): break

                # --- v1.28: РАДИКАЛЬНЫЙ ФИКС ТРЕЙЛИНГА (Приоритет + 2 Стороны) ---
                is_aggressive_trailing = self._get_safe_int(self.aggressive_trailing_mode, 0)

                if is_aggressive_trailing:
                    # АГРЕССИВНЫЙ (NON-STOP): Абсолютный приоритет.
                    # Проверяем ОБА направления, чтобы сетка "липла" к цене
                    self._aggressive_trailing_up_logic(trader)
                    self._aggressive_trailing_down_logic(trader)
                
                elif not self.is_short_mode:
                    # ЧУТКИЙ (LONG): (PosSize == 0)
                    if self._get_safe_int(self.trailing_grid_up_mode, 0):
                        self._trailing_grid_up_logic(trader) # Старая логика
                else:
                    # ЧУТКИЙ (SHORT): (PosSize == 0)
                    if self._get_safe_int(self.trailing_grid_down_mode, 0):
                        self._trailing_grid_down_logic(trader) # Старая логика
                # --- КОНЕЦ v1.28 ---


                if self._get_safe_int(self.autopilot_mode, 0):
                    # --- ИСПРАВЛЕНИЕ "ЗАВИСАНИЯ" АВТОПИЛОТА (v6.57) ---
                    if self.autopilot_state == 'finishing':
                        current_pos_size = self._get_current_position_size()
                        
                        if position_closed:
                            self.queue_log("Автопилот: Позиция закрыта по TP/SL. Начинаю переключение...", "info")
                            autopilot.finalize_switch()
                            continue
                        elif current_pos_size == 0.0:
                            self.queue_log("Автопилот: Позиции нет (pos=0). Начинаю принудительное переключение...", "warning")
                            autopilot.finalize_switch()
                            continue
                    # --- КОНЕЦ ИСПРАВЛЕНИЯ ---

                    if self.autopilot_state == 'trading' and time.time() - last_autopilot_scan > 300:
                        autopilot.check_for_switch()
                        last_autopilot_scan = time.time()

                    elif self.autopilot_state == 'finishing' and time.time() - self.last_autopilot_recheck > 60:
                        autopilot.reevaluate_switch_decision()
                        self.last_autopilot_recheck = time.time()

                self._update_technical_indicators(trader)
                self.root.after(0, self.update_metrics)
                # v1.21 FIX: Проверка UI
                if hasattr(self, 'status_label') and self.status_label.winfo_exists():
                    if self.autopilot_state == 'finishing':
                         log_mode = "SHORT" if self.potential_next_pair_is_short else "LONG"
                         self.status_label.config(style='Finishing.TLabel', text=f"Завершение... -> {self.potential_next_pair} ({log_mode})")
                    # --- v6.62: Пауза не активна в принудительном режиме ---
                    elif not self.trading_allowed_by_trend and self._get_safe_int(self.trend_filter_enabled, 0) and not (self._get_safe_int(self.force_long_mode, 0) or self._get_safe_int(self.force_short_mode, 0)):
                        allowed_orders = self._get_allowed_orders()
                        self.status_label.config(style='Pause.TLabel', text=f"ПАУЗА ({'SHORT' if self.is_short_mode else 'LONG'} Лимит: {allowed_orders})")
                        if time.time() - self.last_pause_log_time > 60:
                            self.queue_log(f"Состояние: ПАУЗА ({'SHORT' if self.is_short_mode else 'LONG'} Лимит: {allowed_orders})", "info"); self.last_pause_log_time = time.time()
                    else:
                        log_mode = "SHORT" if self.is_short_mode else "LONG"
                        # --- v6.59: Отображение принудительного режима ---
                        if self._get_safe_int(self.force_long_mode, 0): log_mode = "ТОЛЬКО LONG"
                        elif self._get_safe_int(self.force_short_mode, 0): log_mode = "ТОЛЬКО SHORT"
                        # ---
                        self.status_label.config(style='TLabel', text=f"Работает ({log_mode})...")

                if self._get_safe_int(self.paper_mode, 1):
                    self.paper_grid_logic(trader)
                else:
                    self.real_grid_logic(trader)

                # v1.25 FIX: Убираем спам из логов (проверка таймера добавлена в _update_chart_data_thread)
                if ANALYSIS_AVAILABLE and time.time() - self.last_chart_update_time > self._get_safe_double(self.update_interval, 10):
                     current_chart_tf = self.chart_timeframe.get()
                     if current_chart_tf == '5m' or time.time() - self.last_chart_update_time > 60:
                        threading.Thread(target=self._update_chart_data_thread, args=(trader,), daemon=True).start()
                        # self.last_chart_update_time = time.time() # v1.25: Таймер теперь внутри функции
                     
            except Exception as e:
                self.queue_log(f"КРИТ. ОШИБКА в цикле: {repr(e)}", "error")
                import traceback; self.queue_log(traceback.format_exc(), "error")
                time.sleep(1)

            self.running.wait(timeout=self._get_safe_double(self.update_interval, 10))

    def _get_current_position_size(self):
        if self._get_safe_int(self.paper_mode, 1):
            return self.paper_base_balance
        else:
            return float(self.real_position.get('positionAmt', 0.0))

    # --- НОВАЯ ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ДЛЯ РАЗМЕРОВ ОРДЕРОВ (АГРЕССИВНЫЙ ГАРПУН) ---
    def _calculate_grid_order_sizes(self):
        """Возвращает список размеров ордеров в USDT для каждого уровня сетки, с учетом множителя."""
        levels = self._get_safe_int(self.grid_levels, 0)
        base_size = self._get_safe_double(self.position_size_usd, 0.0)
        scale_multiplier = self._get_safe_double(self.grid_scale_multiplier, 1.0)
        
        sizes = []
        current_size = base_size
        for _ in range(levels):
            if current_size <= 0: break
            sizes.append(current_size)
            current_size *= scale_multiplier
            
        return sizes

    # ==============================================================================
    # ЛОГИКА "ЧУТКОЙ" СЛЕДЯЩЕЙ СЕТКИ (v1.21)
    # (Вызывается, только если "Агрессивный" ВЫКЛЮЧЕН)
    # ==============================================================================
    def _trailing_grid_up_logic(self, trader):
        """Для LONG-режима. Перестраивает сетку ВВЕРХ, если цена ушла ВЫШЕ 0.5 шага."""
        if not self.grid['center'] or not self.grid['step'] or self.grid['step'] == 0:
            return

        current_pos_size = self._get_current_position_size()
        # v1.21 FIX: Триггер на 0.5 шага
        trigger_price = self.grid['center'] * (1 + self.grid['step'] * 0.5)

        if current_pos_size == 0 and self.current_price['bid'] > trigger_price:
            if time.time() - self.last_trail_log_time > 30: 
                self.queue_log(f"Чуткая Сетка (ВВЕРХ): Цена {self.current_price['bid']:.{self.symbol_info.get('pricePrecision', 2)}f} > триггера {trigger_price:.{self.symbol_info.get('pricePrecision', 2)}f}. Перестраиваю сетку...", "info")
                self.last_trail_log_time = time.time()
            self.create_grid(trader)

    def _trailing_grid_down_logic(self, trader):
        """NEW v1.21: Для SHORT-режима. Перестраивает сетку ВНИЗ, если цена ушла НИЖЕ 0.5 шага."""
        if not self.grid['center'] or not self.grid['step'] or self.grid['step'] == 0:
            return

        current_pos_size = self._get_current_position_size()
        # v1.21 NEW: Триггер на 0.5 шага вниз
        trigger_price = self.grid['center'] * (1 - self.grid['step'] * 0.5)

        if current_pos_size == 0 and self.current_price['ask'] < trigger_price:
            if time.time() - self.last_trail_log_time > 30: 
                self.queue_log(f"Чуткая Сетка (ВНИЗ): Цена {self.current_price['ask']:.{self.symbol_info.get('pricePrecision', 2)}f} < триггера {trigger_price:.{self.symbol_info.get('pricePrecision', 2)}f}. Перестраиваю сетку...", "info")
                self.last_trail_log_time = time.time()
            self.create_grid(trader)
            
    # ==============================================================================
    # РАДИКАЛЬНЫЙ ФИКС (v1.28): ЛОГИКА "АГРЕССИВНОЙ" СЛЕДЯЩЕЙ СЕТКИ
    # (Двигает сетку накопления в ОБЕ стороны, "липнет" к цене)
    # ==============================================================================
    def _aggressive_trailing_up_logic(self, trader):
        """(v1.28) Двигает сетку накопления ВВЕРХ (NON-STOP), если цена ушла ВВЕРХ."""
        if not self.grid['center'] or not self.grid['step'] or self.grid['step'] == 0:
            return

        # Триггер (0.5 шага)
        trigger_price = self.grid['center'] * (1 + self.grid['step'] * 0.5)

        if self.current_price['bid'] > trigger_price:
            if time.time() - self.last_trail_log_time > 30: 
                self.queue_log(f"Агрессивный (ВВЕРХ): Цена {self.current_price['bid']:.{self.symbol_info.get('pricePrecision', 2)}f} > {trigger_price:.{self.symbol_info.get('pricePrecision', 2)}f}. Двигаю сетку...", "info")
                self.last_trail_log_time = time.time()
            
            new_center = self.current_price['bid']
            levels = self._get_safe_int(self.grid_levels, 10)
            step = self.grid['step']

            if self.is_short_mode:
                # SHORT-РЕЖИМ: Двигаем SELL-сетку (накопления) ВВЕРХ (догоняем цену)
                self.grid['center'] = new_center
                self.grid['sell'] = [new_center * (1 + step * (i + 0.5)) for i in range(levels)]
                if self._get_safe_int(self.paper_mode, 1): self.paper_open_orders = [o for o in self.paper_open_orders if o['side'] == 'BUY'] # Оставляем TP
            else:
                # LONG-РЕЖИМ: Двигаем BUY-сетку (накопления) ВВЕРХ (догоняем цену)
                self.grid['center'] = new_center
                self.grid['buy'] = [new_center * (1 - step * (i + 0.5)) for i in range(levels)]
                if self._get_safe_int(self.paper_mode, 1): self.paper_open_orders = [o for o in self.paper_open_orders if o['side'] == 'SELL'] # Оставляем TP

    def _aggressive_trailing_down_logic(self, trader):
        """(v1.28) Двигает сетку накопления ВНИЗ (NON-STOP), если цена ушла ВНИЗ."""
        if not self.grid['center'] or not self.grid['step'] or self.grid['step'] == 0:
            return

        # Триггер (0.5 шага)
        trigger_price = self.grid['center'] * (1 - self.grid['step'] * 0.5)

        if self.current_price['ask'] < trigger_price:
            if time.time() - self.last_trail_log_time > 30: 
                self.queue_log(f"Агрессивный (ВНИЗ): Цена {self.current_price['ask']:.{self.symbol_info.get('pricePrecision', 2)}f} < {trigger_price:.{self.symbol_info.get('pricePrecision', 2)}f}. Двигаю сетку...", "info")
                self.last_trail_log_time = time.time()
            
            new_center = self.current_price['ask']
            levels = self._get_safe_int(self.grid_levels, 10)
            step = self.grid['step']

            if self.is_short_mode:
                # SHORT-РЕЖИМ: Двигаем SELL-сетку (накопления) ВНИЗ (догоняем цену)
                self.grid['center'] = new_center
                self.grid['sell'] = [new_center * (1 + step * (i + 0.5)) for i in range(levels)]
                if self._get_safe_int(self.paper_mode, 1): self.paper_open_orders = [o for o in self.paper_open_orders if o['side'] == 'BUY'] # Оставляем TP
            else:
                # LONG-РЕЖИМ: Двигаем BUY-сетку (накопления) ВНИЗ (!!! РАДИКАЛЬНЫЙ ФИКС !!!)
                self.grid['center'] = new_center
                self.grid['buy'] = [new_center * (1 - step * (i + 0.5)) for i in range(levels)]
                if self._get_safe_int(self.paper_mode, 1): self.paper_open_orders = [o for o in self.paper_open_orders if o['side'] == 'SELL'] # Оставляем TP
    # ==============================================================================
    # КОНЕЦ ФИКСА v1.28
    # ==============================================================================

    def paper_grid_logic(self, trader):
        user_pos_size = self._get_safe_double(self.position_size_usd, 0.0)

        if self.current_price['bid'] <= 0 or user_pos_size <= 0: return

        order_sizes_usd = self._calculate_grid_order_sizes()
        min_qty = self.symbol_info.get('minQty', 0.001)

        executed = []
        for o in self.paper_open_orders:
            filled = False
            
            # --- ЛОГИКА ИСПОЛНЕНИЯ ОРДЕРОВ (LONG/SHORT) ---
            if self.is_short_mode:
                # SHORT-РЕЖИМ:
                # 1. Накопление SELL (цена растет/достигает уровня)
                if o['side'] == 'SELL' and self.current_price['bid'] >= o['price']:
                    # v1.21 FIX: Проверка баланса (хотя для шорта это менее критично, но для единообразия)
                    cost = o['qty'] * o['price'] 
                    self.paper_quote_balance += cost # При открытии шорта баланс USDT растет
                    self.paper_inventory.append({'qty': -o['qty'], 'price': o['price']}) # Отрицательное кол-во = SHORT
                    self.add_trade_to_history('SELL (Short)', o['price'], o['qty'], 0.0)
                    filled = True
                # 2. Закрытие Анти-Гарпуна (BUY-TP)
                elif o['side'] == 'BUY' and self.current_price['ask'] <= o['price']:
                    pnl = 0
                    if self.paper_inventory:
                        total_cost = sum(item['qty'] * item['price'] for item in self.paper_inventory if item['qty'] < 0)
                        total_qty = sum(item['qty'] for item in self.paper_inventory) # Отрицательное число
                        avg_price = -total_cost / -total_qty if total_qty < 0 else 0 # Средняя цена SHORT-позиции
                        
                        cost_to_close = o['qty'] * o['price']
                        
                        # v1.21 FIX: Проверка баланса
                        if self.paper_quote_balance >= cost_to_close:
                            self.paper_quote_balance -= cost_to_close
                            
                            # PnL = (Цена_входа - Цена_закрытия) * Количество
                            pnl = (avg_price - o['price']) * abs(total_qty) if avg_price > 0 else 0
                            self.total_profit_usd += pnl
                            self.add_trade_to_history('BUY (Anti-Harpoon)', o['price'], abs(total_qty), pnl)
                            self.paper_inventory.clear()
                            self.queue_log("Бумага: Анти-Гарпун исполнен. Перестраиваю сетку.", "success")
                            self.create_grid(trader)
                            filled = True
                        else:
                            self.queue_log(f"Бумага: Недостаточно QUOTE ({self.paper_quote_balance:.2f}) для закрытия SHORT @ {o['price']}. Нужно {cost_to_close:.2f}", "error")

            
            else:
                # LONG-РЕЖИМ (оригинальный Гарпун):
                # 1. Накопление BUY (цена падает/достигает уровня)
                if o['side'] == 'BUY' and self.current_price['ask'] <= o['price']:
                    cost = o['qty'] * o['price']
                    
                    # v1.21 FIX: Проверка баланса
                    if self.paper_quote_balance >= cost:
                        self.paper_quote_balance -= cost
                        self.paper_inventory.append({'qty': o['qty'], 'price': o['price']})
                        self.add_trade_to_history('BUY', o['price'], o['qty'], 0.0)
                        filled = True
                    else:
                         self.queue_log(f"Бумага: Недостаточно QUOTE ({self.paper_quote_balance:.2f}) для покупки @ {o['price']}. Нужно {cost:.2f}", "error")
                         
                # 2. Закрытие Гарпуна (SELL-TP)
                elif o['side'] == 'SELL' and self.current_price['bid'] >= o['price']:
                    pnl = 0
                    if self._get_safe_int(self.harpoon_mode, 0):
                        if self.paper_inventory:
                            total_cost = sum(item['qty'] * item['price'] for item in self.paper_inventory if item['qty'] > 0)
                            total_qty = sum(item['qty'] for item in self.paper_inventory)
                            avg_price = total_cost / total_qty if total_qty > 0 else 0
                            revenue = o['qty'] * o['price']
                            self.paper_quote_balance += revenue
                            pnl = (o['price'] - avg_price) * total_qty if avg_price > 0 else 0
                            self.total_profit_usd += pnl
                            self.add_trade_to_history('SELL (Harpoon)', o['price'], total_qty, pnl)
                            self.paper_inventory.clear()
                            self.queue_log("Бумага: Гарпун исполнен. Перестраиваю сетку.", "success")
                            self.create_grid(trader)
                            filled = True
                    else:
                        buy_to_cover = next((b for b in self.paper_inventory if b['price'] < o['price'] and b['qty'] > 0), None)
                        if buy_to_cover:
                            revenue = o['qty'] * o['price']
                            self.paper_quote_balance += revenue
                            self.paper_inventory.remove(buy_to_cover)
                            pnl = (o['price'] - buy_to_cover['price']) * o['qty']
                            self.total_profit_usd += pnl
                            self.add_trade_to_history('SELL', o['price'], o['qty'], pnl)
                            filled = True
            # --- КОНЕЦ ЛОГИКИ ИСПОЛНЕНИЯ ОРДЕРОВ ---


            if filled:
                if ANALYSIS_AVAILABLE and hasattr(self, 'pnl_history'): # v1.21 FIX: Добавлена проверка
                    self.pnl_history.append((dt.datetime.now(), self.total_profit_usd))
                    self.root.after(0, self.update_pnl_chart)

            if filled:
                self.trade_count += 1; executed.append(o)
                self.root.after(0, self._plot_chart_ui)
                
                # Выходим, если закрыли позицию (Long/Short Harpoon)
                is_harpoon_close = self._get_safe_int(self.harpoon_mode, 0) and (
                    (o['side'] == 'SELL' and not self.is_short_mode) or
                    (o['side'] == 'BUY' and self.is_short_mode)
                )
                if is_harpoon_close:
                    break 

        if executed: self.paper_open_orders = [o for o in self.paper_open_orders if o not in executed]

        # --- ЛОГИКА ВЫСТАВЛЕНИЯ ОРДЕРОВ (LONG/SHORT) ---
        grid_levels = self._get_safe_int(self.grid_levels, 0)
        allowed_orders = self._get_allowed_orders()
        trend_filter_on = self._get_safe_int(self.trend_filter_enabled, 0)
        
        inventory = sum(item['qty'] for item in self.paper_inventory)

        # Определяем лимит для ордеров "накопления"
        accumulation_limit = 0
        if self.autopilot_state == 'trading':
            # --- ИЗМЕНЕНИЕ v6.59: Принудительный режим отменяет "Паузу" ---
            is_forced_mode = self._get_safe_int(self.force_long_mode, 0) or self._get_safe_int(self.force_short_mode, 0)
            if (self.trading_allowed_by_trend or not trend_filter_on or is_forced_mode):
            # --- КОНЕЦ ИЗМЕНЕНИЯ ---
                accumulation_limit = grid_levels
            else:
                accumulation_limit = allowed_orders
        
        if self.is_short_mode:
            # SHORT-РЕЖИМ: Выставляем SELL-ордера (копим позицию)
            active_sells = {o['price'] for o in self.paper_open_orders if o['side'] == 'SELL'}
            
            # --- ИСПРАВЛЕНИЕ v6.57 ---
            # Собираем цены УЖЕ исполненных SELL-ордеров (Short-позиций)
            executed_sell_prices = {item['price'] for item in self.paper_inventory if item['qty'] < 0}
            # --- КОНЕЦ ИСПРАВЛЕНИЯ ---
            
            if accumulation_limit > 0 and self.grid['sell']:
                for i, p in enumerate(self.grid['sell']):
                    # v1.27 ЗАЩИТА ОТ НУЛЯ
                    if p <= 0: continue 
                    if i >= len(order_sizes_usd): break
                    
                    order_pos_size = order_sizes_usd[i]
                    order_qty = max(min_qty, order_pos_size / self.current_price['bid'])
                    
                    # v1.21 FIX: Предохранитель от спама ордеров (Paper)
                    price_threshold = p * 0.0001 # 0.01%
                    
                    # --- ИСПРАВЛЕНИЕ v6.57 + ФИКС "Паузы" (убрано 'abs(inventory) +') ---
                    if p not in active_sells and p not in executed_sell_prices and len(active_sells) < accumulation_limit and self.current_price['bid'] < p - price_threshold:
                        self.paper_open_orders.append({'id': str(uuid.uuid4()), 'side': 'SELL', 'price': p, 'qty': order_qty, 'pair': self.trading_pair.get()})

            # Логика TP (Анти-Гарпун)
            if self._get_safe_int(self.harpoon_mode, 0) and inventory < 0:
                self.paper_open_orders = [o for o in self.paper_open_orders if o['side'] == 'SELL']
                
                total_cost = sum(item['qty'] * item['price'] for item in self.paper_inventory if item['qty'] < 0)
                avg_price = -total_cost / abs(inventory) if inventory < 0 else 0
                
                target_price = 0
                if avg_price > 0:
                    if self.autopilot_state == 'finishing' and self._get_safe_int(self.autopilot_active_close, 0):
                        maker_fee_val = self._get_safe_double(self.maker_fee, 0.0)
                        target_price = avg_price * (1 - (maker_fee_val / 100 * 2.1))
                    else:
                        tp_percent = self._get_safe_double(self.harpoon_tp_percent, 1.0) / 100
                        target_price = avg_price * (1 - tp_percent)

                if target_price > 0: # v1.27 ЗАЩИТА ОТ НУЛЯ
                    self.paper_open_orders.append({'id': 'ANTI-HARPOON', 'side': 'BUY', 'price': target_price, 'qty': abs(inventory), 'pair': self.trading_pair.get()})
            elif not self._get_safe_int(self.harpoon_mode, 0) and inventory < 0:
                self.queue_log("SHORT-РЕЖИМ БЕЗ ГАРПУНА НЕ ПОДДЕРЖИВАЕТСЯ. Используйте Гарпун.", "error")

        else:
            # LONG-РЕЖИМ: Выставляем BUY-ордера (копим позицию)
            active_buys = {o['price'] for o in self.paper_open_orders if o['side'] == 'BUY'}
            
            # --- ИСПРАВЛЕНИЕ v6.57 ---
            # Собираем цены УЖЕ исполненных BUY-ордеров (Long-позиций)
            executed_buy_prices = {item['price'] for item in self.paper_inventory if item['qty'] > 0}
            # --- КОНЕЦ ИСПРАВЛЕНИЯ ---
            
            if accumulation_limit > 0 and self.grid['buy']:
                for i, p in enumerate(self.grid['buy']):
                    # v1.27 ЗАЩИТА ОТ НУЛЯ
                    if p <= 0: continue 
                    if i >= len(order_sizes_usd): break 
                    
                    order_pos_size = order_sizes_usd[i] 
                    order_qty = max(min_qty, order_pos_size / self.current_price['bid'])
                    final_order_qty = order_qty 

                    # v1.21 FIX: Предохранитель от спама ордеров (Paper)
                    price_threshold = p * 0.0001 # 0.01%

                    # --- ИСПРАВЛЕНИЕ v6.57 + ФИКС "Паузы" (убрано 'inventory +') ---
                    if p not in active_buys and p not in executed_buy_prices and len(active_buys) < accumulation_limit and self.current_price['ask'] > p + price_threshold:
                        self.paper_open_orders.append({'id': str(uuid.uuid4()), 'side': 'BUY', 'price': p, 'qty': final_order_qty, 'pair': self.trading_pair.get()})

            # Логика TP (Гарпун/Не-гарпун)
            if self._get_safe_int(self.harpoon_mode, 0) and inventory > 0:
                self.paper_open_orders = [o for o in self.paper_open_orders if o['side'] == 'BUY']
                if self.paper_inventory:
                    total_cost = sum(item['qty'] * item['price'] for item in self.paper_inventory if item['qty'] > 0)
                    avg_price = total_cost / inventory if inventory > 0 else 0
                    target_price = 0

                    if avg_price > 0:
                        if self.autopilot_state == 'finishing' and self._get_safe_int(self.autopilot_active_close, 0):
                            maker_fee_val = self._get_safe_double(self.maker_fee, 0.0)
                            target_price = avg_price * (1 + (maker_fee_val / 100 * 2.1))
                        else:
                            tp_percent = self._get_safe_double(self.harpoon_tp_percent, 1.0) / 100
                            target_price = avg_price * (1 + tp_percent)

                    if target_price > 0: # v1.27 ЗАЩИТА ОТ НУЛЯ
                        self.paper_open_orders.append({'id': 'HARPOON', 'side': 'SELL', 'price': target_price, 'qty': inventory, 'pair': self.trading_pair.get()})
            elif inventory > 0:
                active_sells = {o['price'] for o in self.paper_open_orders if o['side'] == 'SELL'}
                for trade in self.paper_inventory:
                    target = min(self.grid['sell'], key=lambda x:abs(x - (trade['price'] * (1 + self.grid['step'])))) if self.grid['sell'] else 0
                    if target not in active_sells and target > 0: # v1.27 ЗАЩИТА ОТ НУЛЯ
                        self.paper_open_orders.append({'id': str(uuid.uuid4()), 'side': 'SELL', 'price': target, 'qty': trade['qty'], 'pair': self.trading_pair.get()})

        # --- КОНЕЦ ЛОГИКИ ВЫСТАВЛЕНИЯ ОРДЕРОВ ---
        
        self.paper_base_balance = sum(item['qty'] for item in self.paper_inventory)
        self.root.after(0, self.update_balance_metrics)
        self.root.after(0, self.update_open_orders_tree)

    # ==============================================================================
    # --- ИСПРАВЛЕНИЕ (v6.58): 'real_grid_logic' ПЕРЕПИСАН ДЛЯ ПАКЕТНЫХ ОРДЕРОВ ---
    # ==============================================================================
    def real_grid_logic(self, trader):
        current_time = time.time()
        
        # --- 1. СИНХРОНИЗАЦИЯ (раз в 30 сек) ---
        if current_time - self.last_sync_time > 30:
            self.queue_log("РЕАЛ: Синхронизация данных с биржей...", "info")
            sync_success = True

            open_orders_data = trader.get_open_orders(self.trading_pair.get())
            if open_orders_data is not None: 
                self.real_open_orders = open_orders_data
            else: 
                sync_success = False; self.queue_log("РЕАЛ: Ошибка синхронизации 'get_open_orders'", "error")

            positions_data = trader.get_position_information()
            if positions_data:
                current_pos = next((p for p in positions_data if p['symbol'] == self.trading_pair.get()), None)
                old_pos_amt = self.real_position.get('positionAmt', 0.0)
                new_pos_amt, new_entry_price = 0.0, 0.0
                if current_pos:
                    new_pos_amt = float(current_pos['positionAmt'])
                    new_entry_price = float(current_pos['entryPrice'])
                    
                self.real_position = {'positionAmt': new_pos_amt, 'entryPrice': new_entry_price}
                pos_closed_by_tp = (old_pos_amt > 0 and new_pos_amt <= 0) or (old_pos_amt < 0 and new_pos_amt >= 0)
                
                if pos_closed_by_tp:
                    self.queue_log("РЕАЛ: Позиция закрыта (TP/Гарпун). Перестраиваю сетку.", "success")
                    self.create_grid(trader) # create_grid сам отменит ордера
                    self.last_sync_time = 0 
                    return 
            else:
                sync_success = False; self.queue_log("РЕАЛ: Ошибка синхронизации 'get_position_information'", "error")

            balance_data = trader.get_account_balance()
            if balance_data:
                quote_bal = next((b for b in balance_data if b['asset'] == self.quote_asset), None)
                if quote_bal:
                    self.real_quote_balance = float(quote_bal['balance'])
                    self.real_available_balance = float(quote_bal['availableBalance'])
            else:
                sync_success = False; self.queue_log("РЕАЛ: Ошибка синхронизации 'get_account_balance'", "error")

            self.root.after(0, self.update_balance_metrics)
            self.root.after(0, self.update_open_orders_tree)
            
            if sync_success:
                self.last_sync_time = current_time
            else:
                self.queue_log("РЕАЛ: Ошибка синхронизации. Повтор через 5 сек.", "error")
                self.last_sync_time = current_time - 25 # Ускоренная повторная синхронизация

        # --- 2. ПРОВЕРКА УСЛОВИЙ ---
        user_pos_size_usd = self._get_safe_double(self.position_size_usd, 0.0)
        if self.current_price['bid'] <= 0 or user_pos_size_usd <= 0: 
            return

        order_sizes_usd = self._calculate_grid_order_sizes()
        min_qty = self.symbol_info.get('minQty', 0.001)
        leverage = self._get_safe_int(self.leverage, 1)
        if leverage == 0: leverage = 1
        
        current_pos_amt = self.real_position.get('positionAmt', 0.0)

        # --- 3. ОЧИСТКА СТАРЫХ ИЛИ ЛИШНИХ ОРДЕРОВ ---
        # (Этот блок остается, т.к. он отменяет ордера по одному, что безопасно)
        target_grid_prices = set()
        if self.is_short_mode:
            target_grid_prices = {self._format_and_round_price(p) for p in self.grid['sell'] if p > 0} # v1.27
        else:
            target_grid_prices = {self._format_and_round_price(p) for p in self.grid['buy'] if p > 0} # v1.27

        for o in self.real_open_orders[:]:
            is_accumulation_order = (o['side'] == 'BUY' and not self.is_short_mode) or (o['side'] == 'SELL' and self.is_short_mode)
            is_tp_order = (o['side'] == 'SELL' and not self.is_short_mode) or (o['side'] == 'BUY' and self.is_short_mode)
            
            if is_accumulation_order and o['price'] not in target_grid_prices:
                self.queue_log(f"РЕАЛ: Отмена устаревшего {o['side']} ордера {o['orderId']} @ {o['price']}", "info")
                if trader.cancel_order(self.trading_pair.get(), o['orderId']): self.last_sync_time = 0
                time.sleep(0.2)
            
            if is_tp_order and current_pos_amt == 0.0:
                 self.queue_log(f"РЕАЛ: Позиции нет. Отмена TP {o['side']} ордера {o['orderId']}", "info")
                 if trader.cancel_order(self.trading_pair.get(), o['orderId']): self.last_sync_time = 0
                 time.sleep(0.2)
        
        # --- 4. ВЫСТАВЛЕНИЕ ОРДЕРОВ НАКОПЛЕНИЯ (ПАКЕТНЫЙ РЕЖИМ) ---
        accumulation_limit = 0
        if self.autopilot_state == 'trading':
            # --- ИЗМЕНЕНИЕ v6.59: Принудительный режим отменяет "Паузу" ---
            is_forced_mode = self._get_safe_int(self.force_long_mode, 0) or self._get_safe_int(self.force_short_mode, 0)
            if (self.trading_allowed_by_trend or not self._get_safe_int(self.trend_filter_enabled, 0) or is_forced_mode):
            # --- КОНЕЦ ИЗМЕНЕНИЯ ---
                accumulation_limit = self._get_safe_int(self.grid_levels, 0)
            else:
                accumulation_limit = self._get_allowed_orders()

        active_accumulation_prices = {o['price'] for o in self.real_open_orders if (o['side'] == 'BUY' and not self.is_short_mode) or (o['side'] == 'SELL' and self.is_short_mode)}
        
        target_grid = self.grid['buy'] if not self.is_short_mode else self.grid['sell']
        accumulation_side = 'BUY' if not self.is_short_mode else 'SELL'
        
        orders_to_place = [] # Список ордеров для пакетной отправки
        
        if accumulation_limit > 0 and target_grid:
            available_margin_for_grid = self.real_available_balance
            
            for i, p in enumerate(target_grid):
                # v1.27 ЗАЩИТА ОТ НУЛЯ
                if p <= 0: continue 
                if i >= len(order_sizes_usd): break
                if len(active_accumulation_prices) + len(orders_to_place) >= accumulation_limit: break

                order_pos_size_usd = order_sizes_usd[i]
                required_margin_for_order = order_pos_size_usd / leverage
                
                order_qty_raw = order_pos_size_usd / p
                if order_qty_raw < min_qty: order_qty_raw = min_qty
                
                order_qty_str = self._format_quantity(order_qty_raw, 'quantityPrecision')
                price_str = self._format_and_round_price(p)
                
                if price_str not in active_accumulation_prices:
                    if available_margin_for_grid < required_margin_for_order:
                        self.queue_log(f"РЕАЛ: Недостаточно маржи для {price_str}. {required_margin_for_order:.2f} (Уровень {i+1}).", "error")
                        break # Прерываем цикл, если нет маржи

                    # Готовим ордер для пакета
                    orders_to_place.append({
                        "symbol": self.trading_pair.get(),
                        "side": accumulation_side,
                        "type": "LIMIT",
                        "quantity": order_qty_str,
                        "price": price_str,
                        "timeInForce": "GTC"
                    })
                    
                    available_margin_for_grid -= required_margin_for_order
                    
        # Отправляем ордера пачками по 10 (лимит fapi)
        if orders_to_place:
            BATCH_SIZE = 10 
            self.queue_log(f"РЕАЛ: Подготовлено {len(orders_to_place)} ордеров. Отправка пакетами...", "info")
            for i in range(0, len(orders_to_place), BATCH_SIZE):
                batch = orders_to_place[i:i + BATCH_SIZE]
                if trader.create_batch_orders(batch):
                    self.last_sync_time = 0 # Форсируем немедленную синхронизацию
                else:
                    self.queue_log(f"РЕАЛ: ОШИБКА отправки пакета ордеров.", "error")
                time.sleep(0.5) # Небольшая задержка между пакетами


        # --- 5. ВЫСТАВЛЕНИЕ ОРДЕРА TAKE PROFIT (HARPOON/ANTI-HARPOON) ---
        # (Этот блок остается, т.к. он выставляет один ордер)
        if current_pos_amt != 0.0:
            entry_price = self.real_position.get('entryPrice', 0.0)
            tp_side = 'SELL' if current_pos_amt > 0 else 'BUY'
            pos_qty = abs(current_pos_amt)
            pos_qty_str = self._format_quantity(pos_qty, 'quantityPrecision')
            target_price = 0.0

            if entry_price > 0:
                if self.autopilot_state == 'finishing' and self._get_safe_int(self.autopilot_active_close, 0):
                    maker_fee_val = self._get_safe_double(self.maker_fee, 0.0)
                    factor = 1 + (maker_fee_val / 100 * 2.1) if current_pos_amt > 0 else 1 - (maker_fee_val / 100 * 2.1)
                    target_price = entry_price * factor
                    if time.time() - self.last_active_close_log_time > 60:
                        self.queue_log(f"Автопилот: Активное закрытие. TP = {target_price:.{self.symbol_info.get('pricePrecision', 2)}f}", "warning")
                        self.last_active_close_log_time = time.time()
                elif self._get_safe_int(self.harpoon_mode, 0):
                    tp_percent = self._get_safe_double(self.harpoon_tp_percent, 1.0) / 100
                    factor = 1 + tp_percent if current_pos_amt > 0 else 1 - tp_percent
                    target_price = entry_price * factor
                elif not self._get_safe_int(self.harpoon_mode, 0) and current_pos_amt > 0 and self.grid['sell']:
                    sell_levels_above = [p for p in self.grid['sell'] if p > entry_price]
                    target_price = min(sell_levels_above) if sell_levels_above else max(self.grid['sell'])
                # SHORT НЕ ГАРПУН НЕ ПОДДЕРЖИВАЕТСЯ

            if target_price > 0: # v1.27 ЗАЩИТА ОТ НУЛЯ
                price_str = self._format_and_round_price(target_price)
                active_tp_orders = [o for o in self.real_open_orders if o['side'] == tp_side]
                needs_new_tp_order = True
                
                for o in active_tp_orders:
                    if o['price'] == price_str and o['origQty'] == pos_qty_str: needs_new_tp_order = False
                    else:
                        self.queue_log(f"РЕАЛ: Обновление TP. Отмена {o['orderId']}", "info")
                        if trader.cancel_order(self.trading_pair.get(), o['orderId']): self.last_sync_time = 0
                        time.sleep(0.3)

                if needs_new_tp_order:
                    self.queue_log(f"РЕАЛ: Выставляю TP {tp_side} @ {price_str} для позиции {pos_qty_str}", "info")
                    if trader.create_order(self.trading_pair.get(), tp_side, 'LIMIT', quantity=pos_qty_str, price=price_str, timeInForce='GTC'): self.last_sync_time = 0

    # ==============================================================================
    # --- КОНЕЦ ИСПРАВЛЕНИЯ v6.58 ---
    # ==============================================================================
    # --- КОНЕЦ ФИКСА v1.28 ---
    # ==============================================================================

    def paper_grid_logic(self, trader):
        user_pos_size = self._get_safe_double(self.position_size_usd, 0.0)

        if self.current_price['bid'] <= 0 or user_pos_size <= 0: return

        order_sizes_usd = self._calculate_grid_order_sizes()
        min_qty = self.symbol_info.get('minQty', 0.001)

        executed = []
        for o in self.paper_open_orders:
            filled = False
            
            # --- ЛОГИКА ИСПОЛНЕНИЯ ОРДЕРОВ (LONG/SHORT) ---
            if self.is_short_mode:
                # SHORT-РЕЖИМ:
                # 1. Накопление SELL (цена растет/достигает уровня)
                if o['side'] == 'SELL' and self.current_price['bid'] >= o['price']:
                    # v1.21 FIX: Проверка баланса (хотя для шорта это менее критично, но для единообразия)
                    cost = o['qty'] * o['price'] 
                    self.paper_quote_balance += cost # При открытии шорта баланс USDT растет
                    self.paper_inventory.append({'qty': -o['qty'], 'price': o['price']}) # Отрицательное кол-во = SHORT
                    self.add_trade_to_history('SELL (Short)', o['price'], o['qty'], 0.0)
                    filled = True
                # 2. Закрытие Анти-Гарпуна (BUY-TP)
                elif o['side'] == 'BUY' and self.current_price['ask'] <= o['price']:
                    pnl = 0
                    if self.paper_inventory:
                        total_cost = sum(item['qty'] * item['price'] for item in self.paper_inventory if item['qty'] < 0)
                        total_qty = sum(item['qty'] for item in self.paper_inventory) # Отрицательное число
                        avg_price = -total_cost / -total_qty if total_qty < 0 else 0 # Средняя цена SHORT-позиции
                        
                        cost_to_close = o['qty'] * o['price']
                        
                        # v1.21 FIX: Проверка баланса
                        if self.paper_quote_balance >= cost_to_close:
                            self.paper_quote_balance -= cost_to_close
                            
                            # PnL = (Цена_входа - Цена_закрытия) * Количество
                            pnl = (avg_price - o['price']) * abs(total_qty) if avg_price > 0 else 0
                            self.total_profit_usd += pnl
                            self.add_trade_to_history('BUY (Anti-Harpoon)', o['price'], abs(total_qty), pnl)
                            self.paper_inventory.clear()
                            self.queue_log("Бумага: Анти-Гарпун исполнен. Перестраиваю сетку.", "success")
                            self.create_grid(trader)
                            filled = True
                        else:
                            self.queue_log(f"Бумага: Недостаточно QUOTE ({self.paper_quote_balance:.2f}) для закрытия SHORT @ {o['price']}. Нужно {cost_to_close:.2f}", "error")

            
            else:
                # LONG-РЕЖИМ (оригинальный Гарпун):
                # 1. Накопление BUY (цена падает/достигает уровня)
                if o['side'] == 'BUY' and self.current_price['ask'] <= o['price']:
                    cost = o['qty'] * o['price']
                    
                    # v1.21 FIX: Проверка баланса
                    if self.paper_quote_balance >= cost:
                        self.paper_quote_balance -= cost
                        self.paper_inventory.append({'qty': o['qty'], 'price': o['price']})
                        self.add_trade_to_history('BUY', o['price'], o['qty'], 0.0)
                        filled = True
                    else:
                         self.queue_log(f"Бумага: Недостаточно QUOTE ({self.paper_quote_balance:.2f}) для покупки @ {o['price']}. Нужно {cost:.2f}", "error")
                         
                # 2. Закрытие Гарпуна (SELL-TP)
                elif o['side'] == 'SELL' and self.current_price['bid'] >= o['price']:
                    pnl = 0
                    if self._get_safe_int(self.harpoon_mode, 0):
                        if self.paper_inventory:
                            total_cost = sum(item['qty'] * item['price'] for item in self.paper_inventory if item['qty'] > 0)
                            total_qty = sum(item['qty'] for item in self.paper_inventory)
                            avg_price = total_cost / total_qty if total_qty > 0 else 0
                            revenue = o['qty'] * o['price']
                            self.paper_quote_balance += revenue
                            pnl = (o['price'] - avg_price) * total_qty if avg_price > 0 else 0
                            self.total_profit_usd += pnl
                            self.add_trade_to_history('SELL (Harpoon)', o['price'], total_qty, pnl)
                            self.paper_inventory.clear()
                            self.queue_log("Бумага: Гарпун исполнен. Перестраиваю сетку.", "success")
                            self.create_grid(trader)
                            filled = True
                    else:
                        buy_to_cover = next((b for b in self.paper_inventory if b['price'] < o['price'] and b['qty'] > 0), None)
                        if buy_to_cover:
                            revenue = o['qty'] * o['price']
                            self.paper_quote_balance += revenue
                            self.paper_inventory.remove(buy_to_cover)
                            pnl = (o['price'] - buy_to_cover['price']) * o['qty']
                            self.total_profit_usd += pnl
                            self.add_trade_to_history('SELL', o['price'], o['qty'], pnl)
                            filled = True
            # --- КОНЕЦ ЛОГИКИ ИСПОЛНЕНИЯ ОРДЕРОВ ---


            if filled:
                if ANALYSIS_AVAILABLE and hasattr(self, 'pnl_history'): # v1.21 FIX: Добавлена проверка
                    self.pnl_history.append((dt.datetime.now(), self.total_profit_usd))
                    self.root.after(0, self.update_pnl_chart)

            if filled:
                self.trade_count += 1; executed.append(o)
                self.root.after(0, self._plot_chart_ui)
                
                # Выходим, если закрыли позицию (Long/Short Harpoon)
                is_harpoon_close = self._get_safe_int(self.harpoon_mode, 0) and (
                    (o['side'] == 'SELL' and not self.is_short_mode) or
                    (o['side'] == 'BUY' and self.is_short_mode)
                )
                if is_harpoon_close:
                    break 

        if executed: self.paper_open_orders = [o for o in self.paper_open_orders if o not in executed]

        # --- ЛОГИКА ВЫСТАВЛЕНИЯ ОРДЕРОВ (LONG/SHORT) ---
        grid_levels = self._get_safe_int(self.grid_levels, 0)
        allowed_orders = self._get_allowed_orders()
        trend_filter_on = self._get_safe_int(self.trend_filter_enabled, 0)
        
        inventory = sum(item['qty'] for item in self.paper_inventory)

        # Определяем лимит для ордеров "накопления"
        accumulation_limit = 0
        if self.autopilot_state == 'trading':
            # --- ИЗМЕНЕНИЕ v6.59: Принудительный режим отменяет "Паузу" ---
            is_forced_mode = self._get_safe_int(self.force_long_mode, 0) or self._get_safe_int(self.force_short_mode, 0)
            if (self.trading_allowed_by_trend or not trend_filter_on or is_forced_mode):
            # --- КОНЕЦ ИЗМЕНЕНИЯ ---
                accumulation_limit = grid_levels
            else:
                accumulation_limit = allowed_orders
        
        if self.is_short_mode:
            # SHORT-РЕЖИМ: Выставляем SELL-ордера (копим позицию)
            active_sells = {o['price'] for o in self.paper_open_orders if o['side'] == 'SELL'}
            
            # --- ИСПРАВЛЕНИЕ v6.57 ---
            # Собираем цены УЖЕ исполненных SELL-ордеров (Short-позиций)
            executed_sell_prices = {item['price'] for item in self.paper_inventory if item['qty'] < 0}
            # --- КОНЕЦ ИСПРАВЛЕНИЯ ---
            
            if accumulation_limit > 0 and self.grid['sell']:
                for i, p in enumerate(self.grid['sell']):
                    # v1.27 ЗАЩИТА ОТ НУЛЯ
                    if p <= 0: continue 
                    if i >= len(order_sizes_usd): break
                    
                    order_pos_size = order_sizes_usd[i]
                    order_qty = max(min_qty, order_pos_size / self.current_price['bid'])
                    
                    # v1.21 FIX: Предохранитель от спама ордеров (Paper)
                    price_threshold = p * 0.0001 # 0.01%
                    
                    # --- ИСПРАВЛЕНИЕ v6.57 + ФИКС "Паузы" (убрано 'abs(inventory) +') ---
                    if p not in active_sells and p not in executed_sell_prices and len(active_sells) < accumulation_limit and self.current_price['bid'] < p - price_threshold:
                        self.paper_open_orders.append({'id': str(uuid.uuid4()), 'side': 'SELL', 'price': p, 'qty': order_qty, 'pair': self.trading_pair.get()})

            # Логика TP (Анти-Гарпун)
            if self._get_safe_int(self.harpoon_mode, 0) and inventory < 0:
                self.paper_open_orders = [o for o in self.paper_open_orders if o['side'] == 'SELL']
                
                total_cost = sum(item['qty'] * item['price'] for item in self.paper_inventory if item['qty'] < 0)
                avg_price = -total_cost / abs(inventory) if inventory < 0 else 0
                
                target_price = 0
                if avg_price > 0:
                    if self.autopilot_state == 'finishing' and self._get_safe_int(self.autopilot_active_close, 0):
                        maker_fee_val = self._get_safe_double(self.maker_fee, 0.0)
                        target_price = avg_price * (1 - (maker_fee_val / 100 * 2.1))
                    else:
                        tp_percent = self._get_safe_double(self.harpoon_tp_percent, 1.0) / 100
                        target_price = avg_price * (1 - tp_percent)

                if target_price > 0: # v1.27 ЗАЩИТА ОТ НУЛЯ
                    self.paper_open_orders.append({'id': 'ANTI-HARPOON', 'side': 'BUY', 'price': target_price, 'qty': abs(inventory), 'pair': self.trading_pair.get()})
            elif not self._get_safe_int(self.harpoon_mode, 0) and inventory < 0:
                self.queue_log("SHORT-РЕЖИМ БЕЗ ГАРПУНА НЕ ПОДДЕРЖИВАЕТСЯ. Используйте Гарпун.", "error")

        else:
            # LONG-РЕЖИМ: Выставляем BUY-ордера (копим позицию)
            active_buys = {o['price'] for o in self.paper_open_orders if o['side'] == 'BUY'}
            
            # --- ИСПРАВЛЕНИЕ v6.57 ---
            # Собираем цены УЖЕ исполненных BUY-ордеров (Long-позиций)
            executed_buy_prices = {item['price'] for item in self.paper_inventory if item['qty'] > 0}
            # --- КОНЕЦ ИСПРАВЛЕНИЯ ---
            
            if accumulation_limit > 0 and self.grid['buy']:
                for i, p in enumerate(self.grid['buy']):
                    # v1.27 ЗАЩИТА ОТ НУЛЯ
                    if p <= 0: continue 
                    if i >= len(order_sizes_usd): break 
                    
                    order_pos_size = order_sizes_usd[i] 
                    order_qty = max(min_qty, order_pos_size / self.current_price['bid'])
                    final_order_qty = order_qty 

                    # v1.21 FIX: Предохранитель от спама ордеров (Paper)
                    price_threshold = p * 0.0001 # 0.01%

                    # --- ИСПРАВЛЕНИЕ v6.57 + ФИКС "Паузы" (убрано 'inventory +') ---
                    if p not in active_buys and p not in executed_buy_prices and len(active_buys) < accumulation_limit and self.current_price['ask'] > p + price_threshold:
                        self.paper_open_orders.append({'id': str(uuid.uuid4()), 'side': 'BUY', 'price': p, 'qty': final_order_qty, 'pair': self.trading_pair.get()})

            # Логика TP (Гарпун/Не-гарпун)
            if self._get_safe_int(self.harpoon_mode, 0) and inventory > 0:
                self.paper_open_orders = [o for o in self.paper_open_orders if o['side'] == 'BUY']
                if self.paper_inventory:
                    total_cost = sum(item['qty'] * item['price'] for item in self.paper_inventory if item['qty'] > 0)
                    avg_price = total_cost / inventory if inventory > 0 else 0
                    target_price = 0

                    if avg_price > 0:
                        if self.autopilot_state == 'finishing' and self._get_safe_int(self.autopilot_active_close, 0):
                            maker_fee_val = self._get_safe_double(self.maker_fee, 0.0)
                            target_price = avg_price * (1 + (maker_fee_val / 100 * 2.1))
                        else:
                            tp_percent = self._get_safe_double(self.harpoon_tp_percent, 1.0) / 100
                            target_price = avg_price * (1 + tp_percent)

                    if target_price > 0: # v1.27 ЗАЩИТА ОТ НУЛЯ
                        self.paper_open_orders.append({'id': 'HARPOON', 'side': 'SELL', 'price': target_price, 'qty': inventory, 'pair': self.trading_pair.get()})
            elif inventory > 0:
                active_sells = {o['price'] for o in self.paper_open_orders if o['side'] == 'SELL'}
                for trade in self.paper_inventory:
                    target = min(self.grid['sell'], key=lambda x:abs(x - (trade['price'] * (1 + self.grid['step'])))) if self.grid['sell'] else 0
                    if target not in active_sells and target > 0: # v1.27 ЗАЩИТА ОТ НУЛЯ
                        self.paper_open_orders.append({'id': str(uuid.uuid4()), 'side': 'SELL', 'price': target, 'qty': trade['qty'], 'pair': self.trading_pair.get()})

        # --- КОНЕЦ ЛОГИКИ ВЫСТАВЛЕНИЯ ОРДЕРОВ ---
        
        self.paper_base_balance = sum(item['qty'] for item in self.paper_inventory)
        self.root.after(0, self.update_balance_metrics)
        self.root.after(0, self.update_open_orders_tree)

    # ==============================================================================
    # --- ИСПРАВЛЕНИЕ (v6.58): 'real_grid_logic' ПЕРЕПИСАН ДЛЯ ПАКЕТНЫХ ОРДЕРОВ ---
    # ==============================================================================
    def real_grid_logic(self, trader):
        current_time = time.time()
        
        # --- 1. СИНХРОНИЗАЦИЯ (раз в 30 сек) ---
        if current_time - self.last_sync_time > 30:
            self.queue_log("РЕАЛ: Синхронизация данных с биржей...", "info")
            sync_success = True

            open_orders_data = trader.get_open_orders(self.trading_pair.get())
            if open_orders_data is not None: 
                self.real_open_orders = open_orders_data
            else: 
                sync_success = False; self.queue_log("РЕАЛ: Ошибка синхронизации 'get_open_orders'", "error")

            positions_data = trader.get_position_information()
            if positions_data:
                current_pos = next((p for p in positions_data if p['symbol'] == self.trading_pair.get()), None)
                old_pos_amt = self.real_position.get('positionAmt', 0.0)
                new_pos_amt, new_entry_price = 0.0, 0.0
                if current_pos:
                    new_pos_amt = float(current_pos['positionAmt'])
                    new_entry_price = float(current_pos['entryPrice'])
                    
                self.real_position = {'positionAmt': new_pos_amt, 'entryPrice': new_entry_price}
                pos_closed_by_tp = (old_pos_amt > 0 and new_pos_amt <= 0) or (old_pos_amt < 0 and new_pos_amt >= 0)
                
                if pos_closed_by_tp:
                    self.queue_log("РЕАЛ: Позиция закрыта (TP/Гарпун). Перестраиваю сетку.", "success")
                    self.create_grid(trader) # create_grid сам отменит ордера
                    self.last_sync_time = 0 
                    return 
            else:
                sync_success = False; self.queue_log("РЕАЛ: Ошибка синхронизации 'get_position_information'", "error")

            balance_data = trader.get_account_balance()
            if balance_data:
                quote_bal = next((b for b in balance_data if b['asset'] == self.quote_asset), None)
                if quote_bal:
                    self.real_quote_balance = float(quote_bal['balance'])
                    self.real_available_balance = float(quote_bal['availableBalance'])
            else:
                sync_success = False; self.queue_log("РЕАЛ: Ошибка синхронизации 'get_account_balance'", "error")

            self.root.after(0, self.update_balance_metrics)
            self.root.after(0, self.update_open_orders_tree)
            
            if sync_success:
                self.last_sync_time = current_time
            else:
                self.queue_log("РЕАЛ: Ошибка синхронизации. Повтор через 5 сек.", "error")
                self.last_sync_time = current_time - 25 # Ускоренная повторная синхронизация

        # --- 2. ПРОВЕРКА УСЛОВИЙ ---
        user_pos_size_usd = self._get_safe_double(self.position_size_usd, 0.0)
        if self.current_price['bid'] <= 0 or user_pos_size_usd <= 0: 
            return

        order_sizes_usd = self._calculate_grid_order_sizes()
        min_qty = self.symbol_info.get('minQty', 0.001)
        leverage = self._get_safe_int(self.leverage, 1)
        if leverage == 0: leverage = 1
        
        current_pos_amt = self.real_position.get('positionAmt', 0.0)

        # --- 3. ОЧИСТКА СТАРЫХ ИЛИ ЛИШНИХ ОРДЕРОВ ---
        # (Этот блок остается, т.к. он отменяет ордера по одному, что безопасно)
        target_grid_prices = set()
        if self.is_short_mode:
            target_grid_prices = {self._format_and_round_price(p) for p in self.grid['sell'] if p > 0} # v1.27
        else:
            target_grid_prices = {self._format_and_round_price(p) for p in self.grid['buy'] if p > 0} # v1.27

        for o in self.real_open_orders[:]:
            is_accumulation_order = (o['side'] == 'BUY' and not self.is_short_mode) or (o['side'] == 'SELL' and self.is_short_mode)
            is_tp_order = (o['side'] == 'SELL' and not self.is_short_mode) or (o['side'] == 'BUY' and self.is_short_mode)
            
            if is_accumulation_order and o['price'] not in target_grid_prices:
                self.queue_log(f"РЕАЛ: Отмена устаревшего {o['side']} ордера {o['orderId']} @ {o['price']}", "info")
                if trader.cancel_order(self.trading_pair.get(), o['orderId']): self.last_sync_time = 0
                time.sleep(0.2)
            
            if is_tp_order and current_pos_amt == 0.0:
                 self.queue_log(f"РЕАЛ: Позиции нет. Отмена TP {o['side']} ордера {o['orderId']}", "info")
                 if trader.cancel_order(self.trading_pair.get(), o['orderId']): self.last_sync_time = 0
                 time.sleep(0.2)
        
        # --- 4. ВЫСТАВЛЕНИЕ ОРДЕРОВ НАКОПЛЕНИЯ (ПАКЕТНЫЙ РЕЖИМ) ---
        accumulation_limit = 0
        if self.autopilot_state == 'trading':
            # --- ИЗМЕНЕНИЕ v6.59: Принудительный режим отменяет "Паузу" ---
            is_forced_mode = self._get_safe_int(self.force_long_mode, 0) or self._get_safe_int(self.force_short_mode, 0)
            if (self.trading_allowed_by_trend or not self._get_safe_int(self.trend_filter_enabled, 0) or is_forced_mode):
            # --- КОНЕЦ ИЗМЕНЕНИЯ ---
                accumulation_limit = self._get_safe_int(self.grid_levels, 0)
            else:
                accumulation_limit = self._get_allowed_orders()

        active_accumulation_prices = {o['price'] for o in self.real_open_orders if (o['side'] == 'BUY' and not self.is_short_mode) or (o['side'] == 'SELL' and self.is_short_mode)}
        
        target_grid = self.grid['buy'] if not self.is_short_mode else self.grid['sell']
        accumulation_side = 'BUY' if not self.is_short_mode else 'SELL'
        
        orders_to_place = [] # Список ордеров для пакетной отправки
        
        if accumulation_limit > 0 and target_grid:
            available_margin_for_grid = self.real_available_balance
            
            for i, p in enumerate(target_grid):
                # v1.27 ЗАЩИТА ОТ НУЛЯ
                if p <= 0: continue 
                if i >= len(order_sizes_usd): break
                if len(active_accumulation_prices) + len(orders_to_place) >= accumulation_limit: break

                order_pos_size_usd = order_sizes_usd[i]
                required_margin_for_order = order_pos_size_usd / leverage
                
                order_qty_raw = order_pos_size_usd / p
                if order_qty_raw < min_qty: order_qty_raw = min_qty
                
                order_qty_str = self._format_quantity(order_qty_raw, 'quantityPrecision')
                price_str = self._format_and_round_price(p)
                
                if price_str not in active_accumulation_prices:
                    if available_margin_for_grid < required_margin_for_order:
                        self.queue_log(f"РЕАЛ: Недостаточно маржи для {price_str}. {required_margin_for_order:.2f} (Уровень {i+1}).", "error")
                        break # Прерываем цикл, если нет маржи

                    # Готовим ордер для пакета
                    orders_to_place.append({
                        "symbol": self.trading_pair.get(),
                        "side": accumulation_side,
                        "type": "LIMIT",
                        "quantity": order_qty_str,
                        "price": price_str,
                        "timeInForce": "GTC"
                    })
                    
                    available_margin_for_grid -= required_margin_for_order
                    
        # Отправляем ордера пачками по 10 (лимит fapi)
        if orders_to_place:
            BATCH_SIZE = 10 
            self.queue_log(f"РЕАЛ: Подготовлено {len(orders_to_place)} ордеров. Отправка пакетами...", "info")
            for i in range(0, len(orders_to_place), BATCH_SIZE):
                batch = orders_to_place[i:i + BATCH_SIZE]
                if trader.create_batch_orders(batch):
                    self.last_sync_time = 0 # Форсируем немедленную синхронизацию
                else:
                    self.queue_log(f"РЕАЛ: ОШИБКА отправки пакета ордеров.", "error")
                time.sleep(0.5) # Небольшая задержка между пакетами


        # --- 5. ВЫСТАВЛЕНИЕ ОРДЕРА TAKE PROFIT (HARPOON/ANTI-HARPOON) ---
        # (Этот блок остается, т.к. он выставляет один ордер)
        if current_pos_amt != 0.0:
            entry_price = self.real_position.get('entryPrice', 0.0)
            tp_side = 'SELL' if current_pos_amt > 0 else 'BUY'
            pos_qty = abs(current_pos_amt)
            pos_qty_str = self._format_quantity(pos_qty, 'quantityPrecision')
            target_price = 0.0

            if entry_price > 0:
                if self.autopilot_state == 'finishing' and self._get_safe_int(self.autopilot_active_close, 0):
                    maker_fee_val = self._get_safe_double(self.maker_fee, 0.0)
                    factor = 1 + (maker_fee_val / 100 * 2.1) if current_pos_amt > 0 else 1 - (maker_fee_val / 100 * 2.1)
                    target_price = entry_price * factor
                    if time.time() - self.last_active_close_log_time > 60:
                        self.queue_log(f"Автопилот: Активное закрытие. TP = {target_price:.{self.symbol_info.get('pricePrecision', 2)}f}", "warning")
                        self.last_active_close_log_time = time.time()
                elif self._get_safe_int(self.harpoon_mode, 0):
                    tp_percent = self._get_safe_double(self.harpoon_tp_percent, 1.0) / 100
                    factor = 1 + tp_percent if current_pos_amt > 0 else 1 - tp_percent
                    target_price = entry_price * factor
                elif not self._get_safe_int(self.harpoon_mode, 0) and current_pos_amt > 0 and self.grid['sell']:
                    sell_levels_above = [p for p in self.grid['sell'] if p > entry_price]
                    target_price = min(sell_levels_above) if sell_levels_above else max(self.grid['sell'])
                # SHORT НЕ ГАРПУН НЕ ПОДДЕРЖИВАЕТСЯ

            if target_price > 0: # v1.27 ЗАЩИТА ОТ НУЛЯ
                price_str = self._format_and_round_price(target_price)
                active_tp_orders = [o for o in self.real_open_orders if o['side'] == tp_side]
                needs_new_tp_order = True
                
                for o in active_tp_orders:
                    if o['price'] == price_str and o['origQty'] == pos_qty_str: needs_new_tp_order = False
                    else:
                        self.queue_log(f"РЕАЛ: Обновление TP. Отмена {o['orderId']}", "info")
                        if trader.cancel_order(self.trading_pair.get(), o['orderId']): self.last_sync_time = 0
                        time.sleep(0.3)

                if needs_new_tp_order:
                    self.queue_log(f"РЕАЛ: Выставляю TP {tp_side} @ {price_str} для позиции {pos_qty_str}", "info")
                    if trader.create_order(self.trading_pair.get(), tp_side, 'LIMIT', quantity=pos_qty_str, price=price_str, timeInForce='GTC'): self.last_sync_time = 0

    # ==============================================================================
    # --- КОНЕЦ ИСПРАВЛЕНИЯ v6.58 ---
    # ==============================================================================

    # --- ИЗМЕНЕНИЕ v6.68: Логика масштабирования графика ("Сжатие") ---
    def plot_chart(self):
        if not ANALYSIS_AVAILABLE or self.chart_df is None or self.chart_df.empty: return
        
        # v1.21 FIX: Защита от TclError при закрытии
        try:
            if not hasattr(self, 'ax_main') or not hasattr(self, 'canvas') or not self.canvas.get_tk_widget().winfo_exists():
                return
        except (tk.TclError, AttributeError):
            return

        self.ax_main.clear(); self.ax_volume.clear()

        active_orders = self.real_open_orders if not self._get_safe_int(self.paper_mode,1) else self.paper_open_orders
        
        buy_orders = [float(o.get('price', 0)) for o in active_orders if o.get('side') == 'BUY']
        sell_orders = [float(o.get('price', 0)) for o in active_orders if o.get('side') == 'SELL']

        hlines_grid = buy_orders + sell_orders
        colors_grid = ['g'] * len(buy_orders) + ['r'] * len(sell_orders)

        tp = self._get_safe_double(self.take_profit_price, 0.0)
        sl = self._get_safe_double(self.stop_loss_price, 0.0)
        hlines_stops, colors_stops = [], []
        if tp > 0: hlines_stops.append(tp); colors_stops.append(self.profit_color)
        if sl > 0: hlines_stops.append(sl); colors_stops.append(self.loss_color)
        
        all_hlines = hlines_grid + hlines_stops
        
        # --- v6.68: Расчет диапазона Y (Фикс "сжатия") ---
        min_val = self.chart_df['Low'].min()
        max_val = self.chart_df['High'].max()
        
        # 1. Сначала учитываем только ордера сетки (hlines_grid)
        # v1.27 FIX: Учитываем только > 0
        valid_hlines = [h for h in hlines_grid if h > 0]
        
        if valid_hlines:
            min_val = min(min_val, min(valid_hlines))
            max_val = max(max_val, max(valid_hlines))

        price_range = max_val - min_val
        if price_range <= 0: price_range = max_val * 0.01 if max_val > 0 else 0.1
        buffer = price_range * 0.1 # Буфер 10% от диапазона сетки

        # 2. Устанавливаем жесткие рамки
        self.ax_main.set_ylim(min_val - buffer, max_val + buffer)
        
        # 3. Получаем эти рамки
        ymin, ymax = self.ax_main.get_ylim()
        
        # 4. Фильтруем ВСЕ линии (включая SL/TP), чтобы рисовать только то, что помещается
        final_hlines = [h for h in all_hlines if ymin <= h <= ymax]
        final_colors = [colors_grid[i] for i, h in enumerate(hlines_grid) if ymin <= h <= ymax] + \
                       [colors_stops[i] for i, h in enumerate(hlines_stops) if ymin <= h <= ymax]
        # --- Конец v6.68 ---

        hlines_config = dict(hlines=final_hlines, colors=final_colors, linestyle='--')

        volume_panel = self.ax_volume if self.chart_df['Volume'].max() > 0 else None

        mpf.plot(self.chart_df, ax=self.ax_main, volume=volume_panel, type='candle', style=self.mpf_style, hlines=hlines_config)

        legend_items = []

        # --- v6.68: Рисуем EMA/Цену, только если они попадают в видимый диапазон ---
        if self.last_ema_value > 0 and self._get_safe_int(self.trend_filter_enabled, 0):
             if ymin < self.last_ema_value < ymax: # Проверка
                 self.ax_main.axhline(self.last_ema_value, color='orange', linestyle=':', label=f'EMA({self._get_safe_int(self.ema_period, 200)})', linewidth=1.5)
                 legend_items.append(self.ax_main.get_lines()[-1])

        current_bid = self.current_price['bid']
        if current_bid > 0:
            if ymin < current_bid < ymax: # Проверка
                price_precision = self.symbol_info.get('pricePrecision', 2)
                price_str = f"{current_bid:.{price_precision}f}"
                self.ax_main.axhline(current_bid, color='#00BCD4', linestyle='--', linewidth=1.5, label=f'Цена: {price_str}')
                legend_items.append(self.ax_main.get_lines()[-1])
        # --- Конец v6.68 ---

        if legend_items:
             self.ax_main.legend(handles=legend_items, loc='upper left', fontsize='small', frameon=True, facecolor=self.entry_bg, edgecolor='none', framealpha=0.7)

        # --- v6.60: Показываем ТФ в заголовке ---
        self.ax_main.set_title(f"Текущая пара: {self.trading_pair.get()} ({self.chart_timeframe.get()})", color=self.fg_color, fontsize=10)
        # ---
        
        self.ax_main.tick_params(axis='y', colors='white', labelsize=9)
        self.ax_volume.tick_params(axis='x', colors='white', labelsize=9, rotation=20)

        if volume_panel:
            self.ax_volume.tick_params(axis='y', colors='white', labelsize=9)
            self.ax_volume.set_ylabel("Объем", color='white')
        else:
            self.ax_volume.set_ylabel(""); self.ax_volume.set_yticks([])

        self.ax_main.set_ylabel("Цена (USDT)", color='white')
        self.fig.subplots_adjust(left=0.1, right=0.95, top=0.95, bottom=0.15)
        
        # v1.21 FIX: Защита от TclError при закрытии
        try:
            self.canvas.draw()
        except tk.TclError:
            self.queue_log("Ошибка отрисовки графика (TclError).", "info")
    # --- КОНЕЦ ИЗМЕНЕНИЯ ---


    def update_pnl_chart(self):
        if not ANALYSIS_AVAILABLE: return

        # v1.21 FIX: Защита от TclError при закрытии
        try:
            if not hasattr(self, 'ax_pnl') or not hasattr(self, 'pnl_canvas') or not self.pnl_canvas.get_tk_widget().winfo_exists():
                return
        except (tk.TclError, AttributeError):
            return

        self.ax_pnl.clear()

        if self.pnl_history:
            times, pnls = zip(*self.pnl_history)
            self.ax_pnl.plot(times, pnls, marker='o', linestyle='-', color=self.accent_color)
        else:
            self.ax_pnl.plot([], [])

        self.ax_pnl.set_title("Динамика PnL", color=self.fg_color)
        self.ax_pnl.set_xlabel("Время", color=self.fg_color)
        self.ax_pnl.set_ylabel("Общий PnL (USDT)", color=self.fg_color)

        self.ax_pnl.tick_params(axis='x', colors='white', rotation=15, labelsize=8)
        self.ax_pnl.tick_params(axis='y', colors='white', labelsize=8)

        formatter = mdates.DateFormatter('%d-%m %H:%M')
        self.ax_pnl.xaxis.set_major_formatter(formatter)

        self.ax_pnl.grid(True, linestyle='--', color='gray', alpha=0.5)
        self.pnl_fig.tight_layout(pad=1.5)
        
        # v1.21 FIX: Защита от TclError при закрытии
        try:
            self.pnl_canvas.draw()
        except tk.TclError:
            self.queue_log("Ошибка отрисовки PnL (TclError).", "info")


    def stop_maker_ui(self):
        self.running.clear()
        
        # v1.21 FIX: Проверка UI
        try:
            if hasattr(self, 'btn_start') and self.btn_start.winfo_exists():
                self.btn_start.config(state=tk.NORMAL)
            if hasattr(self, 'btn_stop') and self.btn_stop.winfo_exists():
                self.btn_stop.config(state=tk.DISABLED)
            if hasattr(self, 'pair_entry') and self.pair_entry.winfo_exists():
                if not self._get_safe_int(self.autopilot_mode, 0): 
                    self.pair_entry.config(state=tk.NORMAL)
            if hasattr(self, 'status_label') and self.status_label.winfo_exists():
                self.status_label.config(text="Остановлен.")
        except tk.TclError:
            pass # Окно уже закрывается
            
        self.queue_log("--- БОТ ОСТАНОВЛЕН ---", "warning")
        self.update_open_orders_tree()

    def on_closing(self):
        self.queue_log("Получена команда на закрытие...", "warning")
        self.running.clear()
        if self.maker_thread and self.maker_thread.is_alive(): 
            self.queue_log("Ожидание завершения потока бота...", "info")
            self.maker_thread.join(timeout=3)
        if self.ws: 
            self.queue_log("Закрытие WS...", "info")
            self.ws.close()
        
        # v1.21 FIX: Проверка root
        try:
            if hasattr(self, 'root') and self.root.winfo_exists():
                self.root.destroy()
        except tk.TclError:
            pass # Уже уничтожено

    def copy_log(self):
        try: self.root.clipboard_clear(); self.root.clipboard_append(self.log_text.get('1.0', tk.END)); self.queue_log("Лог скопирован.", "success")
        except tk.TclError: self.queue_log("Ошибка копирования.", "error")

    def copy_trade_history(self):
        try:
            content = "Время,Пара,Тип,Цена,Количество,PnL ($)\n" + "\n".join([",".join(map(str, self.trade_history_tree.item(i, 'values'))) for i in self.trade_history_tree.get_children('')])
            self.root.clipboard_clear(); self.root.clipboard_append(content); self.queue_log("История сделок скопирована.", "success")
        except tk.TclError: self.queue_log("Ошибка копирования.", "error")

    # --- ИЗМЕНЕНИЕ v6.61: Фикс копирования ордеров ---
    def copy_open_orders(self):
        try:
            # ОШИБКА БЫЛА ЗДЕСЬ: (было self.trade_history_tree)
            content = "ID,Пара,Тип,Цена,Количество\n" + "\n".join([",".join(map(str, self.open_orders_tree.item(i, 'values'))) for i in self.open_orders_tree.get_children('')])
            self.root.clipboard_clear(); self.root.clipboard_append(content); self.queue_log("Открытые ордера скопированы.", "success")
        except tk.TclError: self.queue_log("Ошибка копирования.", "error")
    # --- КОНЕЦ ИЗМЕНЕНИЯ ---

    def save_chart(self, reason=None):
        if not ANALYSIS_AVAILABLE or self.chart_df is None: self.queue_log("Нет данных для сохранения.", "warning"); return
        try:
            filename = f"chart_{self.trading_pair.get()}_{dt.datetime.now():%Y%m%d_%H%M%S}"
            if reason: filename += f"_{reason.replace(' ', '_')}"
            filename += ".png"
            self.fig.savefig(filename, facecolor=self.bg_color, dpi=150)
            self.queue_log(f"График сохранен: {filename}", "success")
        except Exception as e: self.queue_log(f"Ошибка сохранения графика: {e}", "error")

    def save_pnl_chart(self):
        if not ANALYSIS_AVAILABLE: self.queue_log("Нет данных для сохранения.", "warning"); return
        try:
            filename = f"pnl_chart_{dt.datetime.now():%Y%m%d_%H%M%S}.png"
            self.pnl_fig.savefig(filename, facecolor=self.bg_color, dpi=150)
            self.queue_log(f"График PnL сохранен: {filename}", "success")
        except Exception as e: self.queue_log(f"Ошибка сохранения графика PnL: {e}", "error")

    def _on_error(self, ws, error): self.queue_log(f"КРИТ. ОШИБКА WS: {error}", "error")
    def _on_close(self, ws, code, msg): self.queue_log(f"WS-соединение закрыто.", "warning")

    def _on_message(self, ws, message):
        try:
            data = json.loads(message)
            if 'b' in data and 'a' in data:
                self.current_price['bid'] = float(data['b'])
                self.current_price['ask'] = float(data['a'])
            self.root.after(0, self.update_risk_calculator)
            self.root.after(0, self._calculate_floating_pnl)
        except Exception as e:
            if time.time() - getattr(self, '_last_ws_error_log', 0) > 30:
                 self.queue_log(f"Ошибка парсинга WS сообщения: {repr(e)}", "error")
                 self._last_ws_error_log = time.time()

    def _on_open(self, ws):
        self.queue_log("WS-соединение успешно установлено.", "success")
        try:
            ws.send(json.dumps({"method": "SUBSCRIBE", "params": [f"{self.trading_pair.get().lower()}@bookTicker"], "id": 1}))
        except Exception as e:
            self.queue_log(f"Ошибка подписки WS: {e}", "error")

    # --- ИЗМЕНЕНИЕ v6.60: Используем self.chart_timeframe.get() ---
    def _update_chart_data_thread(self, trader):
        if not ANALYSIS_AVAILABLE: return # v6.61 Убрано 'or not self.running.is_set()'
        
        # v1.25 FIX: Убираем спам из логов
        current_time = time.time()
        if current_time - self._last_chart_log_spam < 300: # 5 минут
             pass # Не спамим
        else:
            self.queue_log(f"График: Загрузка данных {self.chart_timeframe.get()}...", "info")
            self._last_chart_log_spam = current_time # Сбрасываем таймер
        
        # Если трейдер (бот) не запущен, используем временный экземпляр
        active_trader = self.trader
        if not active_trader:
            # self.queue_log("График: Бот не запущен, использую временный API-клиент...", "info") # v1.25: Убираем лишний лог
            active_trader = BinanceTrader(self.api_key.get(), self.api_secret.get(), self.queue_log)
            
        with self.chart_update_lock:
            try:
                # Получаем ТФ из переменной
                timeframe = self.chart_timeframe.get()
                # self.queue_log(f"График: Загрузка данных {timeframe}...", "info") # v1.25: Перенесено выше
                
                # Определяем лимит свечей в зависимости от ТФ
                limit = 100
                if timeframe in ['6h', '12h', '1d']:
                    limit = 200 # Больше данных для крупных ТФ
                
                klines = active_trader.get_klines(self.trading_pair.get(), timeframe, limit=limit)
                if not klines or len(klines) < 10: 
                    self.queue_log(f"График: Недостаточно данных для {timeframe}.", "warning")
                    return
                    
                df = pd.DataFrame(klines, columns=['ts', 'o', 'h', 'l', 'c', 'v', 'ct', 'qav', 'not', 'tbbav', 'tbqav', 'i'])
                df['ts'] = pd.to_datetime(df['ts'], unit='ms'); df.set_index('ts', inplace=True)
                df_plot = df[['o', 'h', 'l', 'c', 'v']].copy()
                df_plot.columns = ['Open', 'High', 'Low', 'Close', 'Volume']; df_plot = df_plot.astype(float)
                self.chart_df = df_plot
                
                # v1.25: Переносим таймер обновления сюда, чтобы он срабатывал ТОЛЬКО
                # после успешной загрузки данных.
                self.last_chart_update_time = time.time()
                
                self.root.after(0, self._plot_chart_ui)
            except Exception as e: self.queue_log(f"Ошибка получения данных для графика: {e}", "error")
    # --- КОНЕЦ ИЗМЕНЕНИЯ v1.25 ---

    def _plot_chart_ui(self):
        self._calculate_and_set_stop_triggers()
        self.plot_chart()

    # --- ИЗМЕНЕНИЕ v6.60: Новая функция для Combobox ---
    def _on_chart_timeframe_change(self, event=None):
        """Вызывается при смене ТФ в Combobox, принудительно обновляет график."""
        
        # v1.25 FIX: Сбрасываем таймер спама, чтобы лог сразу отобразился
        self._last_chart_log_spam = 0 
        
        if not self.trader and not self.running.is_set():
            # Если бот не запущен, нужен временный трейдер
            temp_trader = BinanceTrader(self.api_key.get(), self.api_secret.get(), self.queue_log)
            threading.Thread(target=self._update_chart_data_thread, args=(temp_trader,), daemon=True).start()
        elif self.trader:
            # Если бот запущен, используем его трейдер
            threading.Thread(target=self._update_chart_data_thread, args=(self.trader,), daemon=True).start()
    # --- КОНЕЦ ИЗМЕНЕНИЯ ---

    def update_and_plot_chart(self, trader):
        if not ANALYSIS_AVAILABLE or not self.running.is_set(): return
        # v6.60: Используем штатную функцию обновления, которая уже знает о ТФ
        threading.Thread(target=self._update_chart_data_thread, args=(trader,), daemon=True).start()

    def update_risk_ui(self):
        # v1.21 FIX: Защита UI
        try:
            if not hasattr(self, 'auto_tp_entry') or not self.auto_tp_entry.winfo_exists():
                return # UI еще не готово или уже закрыто
                
            is_auto = self._get_safe_int(self.auto_stop_trigger_mode, 0)
            is_adaptive_sl = self._get_safe_int(self.adaptive_sl_mode, 0)
            self.auto_tp_entry.config(state=tk.NORMAL if is_auto else tk.DISABLED)
            self.adaptive_sl_check.config(state=tk.NORMAL if is_auto else tk.DISABLED)
            self.manual_tp_entry.config(state='readonly' if is_auto else tk.NORMAL)
            self.manual_sl_entry.config(state='readonly' if is_auto else tk.NORMAL)
            if is_auto:
                self.sl_atr_mult_entry.config(state=tk.NORMAL if is_adaptive_sl else tk.DISABLED)
                self.auto_sl_entry.config(state=tk.DISABLED if is_adaptive_sl else tk.NORMAL)
            else:
                self.sl_atr_mult_entry.config(state=tk.DISABLED)
                self.auto_sl_entry.config(state=tk.DISABLED)
        except tk.TclError:
            pass
            
        self._calculate_and_set_stop_triggers() # FIX: Этот метод должен быть доступен

    def _calculate_and_set_stop_triggers(self):
        if not self._get_safe_int(self.auto_stop_trigger_mode, 0) or not self.grid['buy'] and not self.grid['sell']: return
        try:
            tp_offset = self._get_safe_double(self.auto_tp_offset_percent, 0.0) / 100
            sl_offset = self._get_safe_double(self.auto_sl_offset_percent, 0.0) / 100
            
            new_tp = 0.0
            new_sl = 0.0
            
            if not self.is_short_mode:
                # LONG: TP = max(SELL), SL = min(BUY)
                # v1.27 FIX: Учитываем пустые сетки (если все <= 0)
                if self.grid['sell']: new_tp = max(self.grid['sell']) * (1 + tp_offset)
                if self.grid['buy']:
                    lowest_buy = min(self.grid['buy'])
                    if self._get_safe_int(self.adaptive_sl_mode, 0) and self.sl_atr_value > 0:
                         new_sl = lowest_buy - (self.sl_atr_value * self._get_safe_double(self.sl_atr_multiplier, 2.0))
                    else:
                         new_sl = lowest_buy * (1 - sl_offset)
            else:
                # SHORT: TP = min(BUY), SL = max(SELL)
                # v1.27 FIX: Учитываем пустые сетки (если все <= 0)
                if self.grid['buy']: new_tp = min(self.grid['buy']) * (1 - tp_offset)
                if self.grid['sell']:
                    highest_sell = max(self.grid['sell'])
                    if self._get_safe_int(self.adaptive_sl_mode, 0) and self.sl_atr_value > 0:
                         new_sl = highest_sell + (self.sl_atr_value * self._get_safe_double(self.sl_atr_multiplier, 2.0))
                    else:
                         new_sl = highest_sell * (1 + sl_offset)

            self.take_profit_price.set(new_tp)
            self.stop_loss_price.set(new_sl)
        except Exception: pass

    def _check_stop_triggers(self):
        try:
            tp = self._get_safe_double(self.take_profit_price, 0.0)
            sl = self._get_safe_double(self.stop_loss_price, 0.0)
            bid = self.current_price['bid']
            ask = self.current_price['ask']
            if bid == 0.0 or ask == 0.0: return False

            position_size = self._get_current_position_size()

            if position_size > 0: # LONG-позиция
                if tp > 0 and bid >= tp:
                    self.queue_log(f"!!! TAKE PROFIT LONG: {bid} >= {tp} !!!", "success")
                    self._close_position_and_stop("Take Profit")
                    return True
                elif sl > 0 and ask <= sl:
                    self.queue_log(f"!!! STOP LOSS LONG: {ask} <= {sl} !!!", "error")
                    self._close_position_and_stop("Stop Loss")
                    return True
            elif position_size < 0: # SHORT-позиция
                if tp > 0 and ask <= tp:
                    self.queue_log(f"!!! TAKE PROFIT SHORT (Anti-Harpoon): {ask} <= {tp} !!!", "success")
                    self._close_position_and_stop("Take Profit")
                    return True
                elif sl > 0 and bid >= sl:
                    self.queue_log(f"!!! STOP LOSS SHORT: {bid} >= {sl} !!!", "error")
                    self._close_position_and_stop("Stop Loss")
                    return True

        except Exception: pass
        return False

    def _close_position_and_stop(self, reason: str):
        self.queue_log(f"--- АВАРИЙНОЕ ЗАКРЫТИЕ ({reason}) ---", "warning")
        self.save_chart(reason=reason)

        current_pos_size = self._get_current_position_size()
        if current_pos_size != 0.0:
            if self._get_safe_int(self.paper_mode, 1):
                if self.paper_inventory:
                    total_cost = sum(item['qty'] * item['price'] for item in self.paper_inventory)
                    total_qty = self.paper_base_balance
                    
                    if total_qty != 0:
                        avg_price = total_cost / total_qty
                        
                        if total_qty > 0: # Long
                            pnl = (self.current_price['bid'] - avg_price) * total_qty
                            close_price = self.current_price['bid']
                        else: # Short
                            pnl = (avg_price - self.current_price['ask']) * abs(total_qty)
                            close_price = self.current_price['ask']

                        self.total_profit_usd += pnl
                        
                        if ANALYSIS_AVAILABLE and hasattr(self, 'pnl_history'): # v1.21 FIX
                            self.pnl_history.append((dt.datetime.now(), self.total_profit_usd))
                            self.root.after(0, self.update_pnl_chart)
                            
                        self.queue_log(f"Закрытие {total_qty:.4f} {self.base_asset} @ {close_price:.4f} (PnL: {pnl:+.4f})", "warning")
                        side_label = f'MARKET {"SELL" if total_qty > 0 else "BUY"} ({reason})'
                        self.add_trade_to_history(side_label, close_price, abs(total_qty), pnl)

        self.paper_open_orders.clear(); self.paper_inventory.clear(); self.paper_base_balance = 0.0

        if not (self._get_safe_int(self.stop_on_sl, 1) and "Ручное" not in reason):
             if self.trader: 
                self.queue_log(f"Закрытие ({reason}): Перестраиваю сетку по новой цене.", "warning")
                self.create_grid(self.trader)
        
        if self._get_safe_int(self.stop_on_sl, 1) and "Ручное" not in reason:
            self.root.after(0, self.stop_maker)
        elif "Ручное" not in reason:
            self.queue_log("Продолжаю работу...", "warning")

    def create_grid(self, trader):
        if self.current_price['bid'] <= 0: return

        if not self._get_safe_int(self.paper_mode, 1):
            # В реальном режиме отмена ордеров происходит принудительно
            # при перестроении сетки.
            trader.cancel_all_open_orders(self.trading_pair.get())
            self.last_sync_time = 0 # Сразу же синхронизируемся после отмены
        else:
            self.paper_open_orders.clear()
            self.queue_log("Бумага: Все старые ордера очищены для перестройки сетки.", "info")

        self.grid['center'] = self.current_price['bid']
        grid_step_val = self._get_safe_double(self.grid_step, 0.05)
        grid_levels_val = self._get_safe_int(self.grid_levels, 10)
        step = self._calculate_atr_and_step(trader) if self._get_safe_int(self.dynamic_step_mode, 0) else grid_step_val / 100
        self.grid['step'] = step
        levels = grid_levels_val
        
        # --- v1.27: РАДИКАЛЬНАЯ МЕРА (ЗАЩИТА ОТ НУЛЯ) ---
        original_buy_levels = []
        original_sell_levels = []

        if self.is_short_mode:
            # SHORT: SELL-ордера ВЫШЕ, BUY-TP НИЖЕ
            original_sell_levels = [self.grid['center'] * (1 + step * (i + 0.5)) for i in range(levels)]
            original_buy_levels = [self.grid['center'] * (1 - step * (i + 0.5)) for i in range(levels)] 
            
            self.grid['sell'] = [p for p in original_sell_levels if p > 0]
            self.grid['buy'] = [p for p in original_buy_levels if p > 0]
            
            if len(self.grid['buy']) < len(original_buy_levels):
                 self.queue_log(f"РАДИКАЛЬНАЯ МЕРА: Обрезано {len(original_buy_levels) - len(self.grid['buy'])} BUY-ордеров (цена <= 0). Уменьшите Кол-во/Шаг!", "error")
            
            self.queue_log(f"SHORT-СЕТКА (0.5 шага) создана: центр={self.grid['center']:.4f}, шаг={step*100:.3f}%", "info")
        else:
            # LONG: BUY-ордера НИЖЕ, SELL-TP ВЫШЕ
            original_buy_levels = [self.grid['center'] * (1 - step * (i + 0.5)) for i in range(levels)]
            original_sell_levels = [self.grid['center'] * (1 + step * (i + 0.5)) for i in range(levels)] 
            
            self.grid['buy'] = [p for p in original_buy_levels if p > 0]
            self.grid['sell'] = [p for p in original_sell_levels if p > 0]
            
            if len(self.grid['buy']) < len(original_buy_levels):
                 self.queue_log(f"РАДИКАЛЬНАЯ МЕРА: Обрезано {len(original_buy_levels) - len(self.grid['buy'])} BUY-ордеров (цена <= 0). Уменьшите Кол-во/Шаг!", "error")

            self.queue_log(f"LONG-СЕТКА (0.5 шага) создана: центр={self.grid['center']:.4f}, шаг={step*100:.3f}%", "info")
        # --- КОНЕЦ v1.27 ---
        
        self._calculate_and_set_stop_triggers()
        self.root.after(0, self.update_risk_calculator)
        self.update_and_plot_chart(trader)

    def _calculate_ema(self, klines, period):
        if not ANALYSIS_AVAILABLE or not klines: return 0
        df = pd.DataFrame(klines, columns=['ts', 'o', 'h', 'l', 'c', 'v', 'ct', 'qav', 'not', 'tbbav', 'tbqav', 'i'])
        try: return pd.to_numeric(df['c']).ewm(span=period, adjust=False).mean().iloc[-1]
        except: return 0.0

    def _calculate_atr(self, klines, period):
        if not ANALYSIS_AVAILABLE or not klines or len(klines) < period + 1: return 0.0
        df = pd.DataFrame(klines, columns=['ts', 'o', 'h', 'l', 'c', 'v', 'ct', 'qav', 'not', 'tbbav', 'tbqav', 'i'])
        for col in ['h', 'l', 'c']: df[col] = pd.to_numeric(df[col])
        df['tr'] = pd.concat([df['h'] - df['l'], abs(df['h'] - df['c'].shift()), abs(df['l'] - df['c'].shift())], axis=1).max(axis=1)
        return df['tr'].ewm(span=period, adjust=False).mean().iloc[-1]

    def _calculate_atr_and_step(self, trader):
        try:
            atr_period = self._get_safe_int(self.atr_period, 14)
            atr_timeframe = self.atr_timeframe.get()
            atr_multiplier = self._get_safe_double(self.atr_multiplier, 0.5)
            klines = trader.get_klines(self.trading_pair.get(), atr_timeframe, limit=atr_period + 2)
            atr = self._calculate_atr(klines, atr_period)
            price = self.current_price['bid']
            if price == 0 or atr == 0: return self._get_safe_double(self.grid_step, 0.1) / 100
            step = (atr / price) * atr_multiplier
            self.queue_log(f"ATR Сетки: ATR={atr:.4f}, Шаг={step*100:.3f}%", "info")
            return step
        except Exception as e:
            self.queue_log(f"КРИТ. ОШИБКА в ATR сетки: {e}", "error")
            return self._get_safe_double(self.grid_step, 0.1) / 100

    # --- ИЗМЕНЕНИЕ v6.62: Фикс "Двух сеток" ---
    def _update_technical_indicators(self, trader):
        if time.time() - self.last_indicators_check_time < 180: return
        self.last_indicators_check_time = time.time()
        
        # --- v6.59: Проверка принудительных режимов ---
        if self._get_safe_int(self.force_long_mode, 0):
            if self.is_short_mode: # Если режим БЫЛ short
                self.queue_log("РЕЖИМ: Принудительный LONG. Перестраиваю сетку...", "warning")
                self.is_short_mode = False
                self.trading_allowed_by_trend = True
                self.create_grid(trader) # <--- ФИКС v6.62
            else:
                self.trading_allowed_by_trend = True
                self.is_short_mode = False
            return 
            
        if self._get_safe_int(self.force_short_mode, 0):
            if not self.is_short_mode: # Если режим БЫЛ long
                self.queue_log("РЕЖИМ: Принудительный SHORT. Перестраиваю сетку...", "warning")
                self.is_short_mode = True
                self.trading_allowed_by_trend = True
                self.create_grid(trader) # <--- ФИКС v6.62
            else:
                self.trading_allowed_by_trend = True
                self.is_short_mode = True
            return
        # --- КОНЕЦ v6.59 ---
            
        def task():
            try:
                if self._get_safe_int(self.trend_filter_enabled, 0):
                    ema_period = self._get_safe_int(self.ema_period, 200)
                    trend_timeframe = self.trend_timeframe.get()
                    klines_ema = trader.get_klines(self.trading_pair.get(), trend_timeframe, ema_period)
                    if klines_ema and len(klines_ema) >= ema_period:
                        self.last_ema_value = self._calculate_ema(klines_ema, ema_period)
                        
                        # --- v6.62: Логика определения смены режима ---
                        old_is_short_mode = self.is_short_mode 
                        
                        # ОПРЕДЕЛЯЕМ РЕЖИМ (LONG/SHORT)
                        is_below_ema = self.current_price['bid'] < self.last_ema_value
                        is_short_allowed = self._get_safe_int(self.autopilot_allow_short, 0)
                        self.is_short_mode = is_below_ema and is_short_allowed
                        
                        # ОПРЕДЕЛЯЕМ ПАУЗУ
                        if self.is_short_mode:
                            # Для шорта: разрешено, если цена НИЖЕ EMA
                            self.trading_allowed_by_trend = self.current_price['bid'] < self.last_ema_value
                        else:
                            # Для лонга: разрешено, если цена ВЫШЕ EMA
                            self.trading_allowed_by_trend = self.current_price['bid'] > self.last_ema_value
                            
                        # --- v6.62: Если режим изменился, перестраиваем сетку ---
                        if old_is_short_mode != self.is_short_mode:
                            new_mode_str = "SHORT" if self.is_short_mode else "LONG"
                            self.queue_log(f"РЕЖИМ: EMA определил смену режима на {new_mode_str}. Перестраиваю сетку...", "warning")
                            self.root.after(0, self.create_grid, self.trader)
                        # --- КОНЕЦ v6.62 ---
                            
                else: 
                    self.trading_allowed_by_trend = True
                    # --- v6.63: Если фильтр выключен, не меняем режим, он уже задан при старте ---
                    # self.is_short_mode = False 
                    pass
                    # ---
                    
                if self._get_safe_int(self.auto_stop_trigger_mode, 0) and self._get_safe_int(self.adaptive_sl_mode, 0):
                    atr_period = self._get_safe_int(self.atr_period, 14)
                    klines_sl = trader.get_klines(self.trading_pair.get(), self.trend_timeframe.get(), atr_period + 2)
                    self.sl_atr_value = self._calculate_atr(klines_sl, atr_period)
            except Exception as e: self.queue_log(f"Ошибка расчета индикаторов: {e}", "error")
        threading.Thread(target=task, daemon=True).start()

    def load_api_keys_from_file(self):
        try:
            with open('binance_keys.txt', 'r', encoding='utf-8-sig') as f:
                self.api_key.set(f.readline().strip()); self.api_secret.set(f.readline().strip())
                self.queue_log(f"Ключи API загружены.", "success")
        except Exception as e: self.queue_log(f"Не удалось загрузить ключи. {e}", "error")

    def toggle_load_keys(self):
        if self._get_safe_int(self.load_keys_flag, 0): self.load_api_keys_from_file()

    def toggle_autopilot(self):
        is_autopilot_on = self._get_safe_int(self.autopilot_mode, 0)
        
        # v1.21 FIX: Проверка UI
        try:
            if hasattr(self, 'pair_entry') and self.pair_entry.winfo_exists():
                if is_autopilot_on:
                    self.pair_entry.config(state=tk.DISABLED)
                    self.queue_log("АВТОПИЛОТ АКТИВИРОВАН.", "warning")
                else:
                    if not self.running.is_set():
                        self.pair_entry.config(state=tk.NORMAL)
                    self.queue_log("Автопилот отключен.", "info")
        except tk.TclError:
            pass

    # --- ИЗМЕНЕНИЕ v6.59: Новая функция для управления галочками ---
    def _toggle_force_mode(self, mode):
        """Управляет эксклюзивным включением галочек 'Только LONG' / 'Только SHORT'."""
        if mode == 'long':
            if self.force_long_mode.get():
                self.force_short_mode.set(False) # Отключаем SHORT, если включили LONG
                self.queue_log("РЕЖИМ: Включен 'Только LONG'. EMA и Автопилот игнорируются.", "warning")
            else:
                 self.queue_log("РЕЖИМ: 'Только LONG' отключен. Управление у EMA/Автопилота.", "info")
                 
        elif mode == 'short':
            if self.force_short_mode.get():
                self.force_long_mode.set(False) # Отключаем LONG, если включили SHORT
                if not self._get_safe_int(self.autopilot_allow_short, 0):
                    self.queue_log("РЕЖИМ: 'Только SHORT' невозможен. Включите 'Разрешить SHORT-Гарпун'.", "error")
                    self.force_short_mode.set(False)
                else:
                    self.queue_log("РЕЖИМ: Включен 'Только SHORT'. EMA и Автопилот игнорируются.", "warning")
            else:
                self.queue_log("РЕЖИМ: 'Только SHORT' отключен. Управление у EMA/Автопилота.", "info")
                
        # Принудительно обновляем индикаторы, чтобы сразу применить режим
        if self.trader:
            self.last_indicators_check_time = 0
            # v6.62: Вызываем _update_technical_indicators, который теперь сам вызовет create_grid, если нужно
            self._update_technical_indicators(self.trader)
    # --- КОНЕЦ ИЗМЕНЕНИЯ ---

    def toggle_mode(self):
        if not self._get_safe_int(self.paper_mode, 1) and self.first_real_mode_warning:
            if not messagebox.askyesno("ПРЕДУПРЕЖДЕНИЕ О РИСКАХ", "Вы собираетесь включить РЕАЛЬНЫЙ РЕЖИМ.\nПрограмма будет отправлять настоящие ордера на ваш счет Binance.\n\n- Убедитесь, что вы понимаете риски.\n- Начните с небольших сумм.\n- Автор не несет ответственности за ваши финансовые потери.\n\nПродолжить?"):
                self.paper_mode.set(True)
                return
            self.first_real_mode_warning = False
        self.update_metrics()
        if not self._get_safe_int(self.paper_mode, 1) and (not self.api_key.get() or not self.api_secret.get()):
            messagebox.showerror("Ошибка", "API Key/Secret должны быть заполнены для реальной торговли."); self.paper_mode.set(True); return
        self.queue_log("!!! РЕАЛЬНЫЙ РЕЖИМ АКТИВИРОВАН !!!" if not self._get_safe_int(self.paper_mode, 1) else "Бумажный режим активирован.", "error" if not self._get_safe_int(self.paper_mode, 1) else "info")

    def update_risk_calculator(self, *args):
        try:
            pos_size = self._get_safe_double(self.position_size_usd, 0.0); levels = self._get_safe_int(self.grid_levels, 0)
            lev = self._get_safe_int(self.leverage, 0); step_val = self._get_safe_double(self.grid_step, 0.0)
            step = (step_val / 100) if not self._get_safe_int(self.dynamic_step_mode, 0) else self.grid.get('step', 0.001)
            
            # --- РАСЧЕТ МАРЖИ ДЛЯ АГРЕССИВНОЙ СЕТКИ ---
            scale_multiplier = self._get_safe_double(self.grid_scale_multiplier, 1.0)
            total_size_usd = 0.0
            if scale_multiplier > 0:
                current_size = pos_size
                for _ in range(levels):
                    total_size_usd += current_size
                    current_size *= scale_multiplier
            else:
                total_size_usd = pos_size * levels

            if lev <= 0: self.required_margin.set("Ошибка"); return
            self.required_margin.set(f"{(total_size_usd / lev):.2f} USDT")
            # --- КОНЕЦ РАСЧЕТА МАРЖИ ---

            center = self.grid.get('center', 0)
            if center > 0 and step > 0:
                prec = self.symbol_info.get('pricePrecision', 2)
                
                # v1.27 FIX: Учитываем пустые сетки
                min_price_list = [p for p in self.grid.get('buy', []) if p > 0]
                max_price_list = [p for p in self.grid.get('sell', []) if p > 0]
                
                min_price = min(min_price_list) if min_price_list else center * (1 - step * (levels - 0.5))
                max_price = max(max_price_list) if max_price_list else center * (1 + step * (levels - 0.5))
                
                self.grid_range.set(f"{min_price:.{prec}f} - {max_price:.{prec}f} $")
                
            maker_fee_val = self._get_safe_double(self.maker_fee, 0.0)
            self.profit_per_level.set(f"≈ {(pos_size * step) - ((pos_size * maker_fee_val/100) * 2):.4f} USDT")
        except Exception: pass

    # --- NEW v6.56: Расчет Плавающего PnL ---
    def _calculate_floating_pnl(self):
        try:
            current_pos_size = self._get_current_position_size()
            if current_pos_size == 0:
                self.floating_pnl.set("0.00")
                if hasattr(self, 'floating_pnl_label') and self.floating_pnl_label.winfo_exists(): # v1.21 FIX
                    self.floating_pnl_label.config(foreground=self.fg_color)
                return

            entry_price = 0.0
            if self._get_safe_int(self.paper_mode, 1):
                if self.paper_inventory:
                    total_cost = sum(item['qty'] * item['price'] for item in self.paper_inventory)
                    total_qty = sum(item['qty'] for item in self.paper_inventory)
                    entry_price = total_cost / total_qty if total_qty != 0 else 0
            else:
                entry_price = self.real_position.get('entryPrice', 0.0)

            if entry_price > 0:
                if current_pos_size > 0:
                    current_price = self.current_price['bid']
                    pnl = (current_price - entry_price) * current_pos_size
                else: # Short position
                    current_price = self.current_price['ask']
                    pnl = (entry_price - current_price) * abs(current_pos_size)
                    
                self.floating_pnl.set(f"{pnl:+.4f}")
                
                if hasattr(self, 'floating_pnl_label') and self.floating_pnl_label.winfo_exists(): # v1.21 FIX
                    color = self.profit_color if pnl >= 0 else self.loss_color
                    self.floating_pnl_label.config(foreground=color)
            else:
                self.floating_pnl.set("0.00")
                if hasattr(self, 'floating_pnl_label') and self.floating_pnl_label.winfo_exists(): # v1.21 FIX
                    self.floating_pnl_label.config(foreground=self.fg_color)
        except (tk.TclError, Exception): # v1.21 FIX
            self.floating_pnl.set("Ошибка")
    # --- END NEW v6.56 ---

    def start_periodic_updates(self):
        # v1.21 FIX: Обернуто в try для стабильности
        try:
            while not self.log_queue.empty():
                msg, lvl = self.log_queue.get()
                if hasattr(self, 'log_text') and self.log_text.winfo_exists():
                    self.log_text.insert(tk.END, f"[{dt.datetime.now().strftime('%H:%M:%S')}] {msg}\n")
                    self.log_text.see(tk.END)
            
            while not self.scanner_queue.empty():
                res = self.scanner_queue.get()
                if hasattr(self, 'scanner_tree') and self.scanner_tree.winfo_exists():
                    self.scanner_tree.delete(*self.scanner_tree.get_children())
                    for r in res: 
                        self.scanner_tree.insert('', 'end', values=(r['pair'], f"{r['std_dev_percent']:.4f}%", f"{r['volatility_percent']:.4f}%"))
            
            # v1.21 FIX: Проверка root
            if hasattr(self, 'root') and self.root.winfo_exists():
                self.root.after(200, self.start_periodic_updates)
                
        except tk.TclError:
            print("TclError в start_periodic_updates (Окно закрыто?)")
        except Exception as e:
            print(f"Ошибка в start_periodic_updates: {e}")


    def reset_history(self):
        if self.running.is_set(): return
        self.total_profit_usd = 0.0; self.trade_count = 0; self.paper_quote_balance = self._get_safe_double(self.paper_start_balance, 1000.0)
        self.paper_base_balance = 0.0; self.paper_open_orders.clear(); self.paper_inventory.clear()
        if ANALYSIS_AVAILABLE:
            if hasattr(self, 'pnl_history'): self.pnl_history.clear() # v1.21 FIX
            self.root.after(0, self.update_pnl_chart)
            
        # v1.21 FIX: Проверка UI
        try:
            if hasattr(self, 'trade_history_tree') and self.trade_history_tree.winfo_exists():
                for i in self.trade_history_tree.get_children(): self.trade_history_tree.delete(i)
        except tk.TclError:
            pass
            
        self.update_metrics(); self.root.after(0, self.update_balance_metrics); self.queue_log("История и статистика сброшены.", "warning")
        self.floating_pnl.set("0.00")
        
        # v1.21 FIX: Проверка UI
        try:
            if hasattr(self, 'floating_pnl_label') and self.floating_pnl_label.winfo_exists():
                self.floating_pnl_label.config(foreground=self.fg_color)
        except tk.TclError:
            pass
            
        if ANALYSIS_AVAILABLE: self.chart_df = None

    def _run_websocket_stream(self):
        self.stop_ws_flag.clear(); url = f"{self.ws_base_url}{self.trading_pair.get().lower()}@bookTicker"
        self.ws = websocket.WebSocketApp(url, on_open=self._on_open, on_message=self._on_message, on_error=self._on_error, on_close=self._on_close)
        while self.running.is_set() and not self.stop_ws_flag.is_set():
            try:
                self.ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE}, ping_interval=60)
            except Exception as e:
                self.queue_log(f"Ошибка WS run_forever: {e}. Перезапуск...", "error")
            if self.running.is_set() and not self.stop_ws_flag.is_set(): time.sleep(1)
        self.queue_log("WS-поток завершен.", "info")

    def add_trade_to_history(self, side, price, qty, pnl):
        self.root.after(0, lambda: self._add_trade_to_history_ui(side, price, qty, pnl))

    def _add_trade_to_history_ui(self, side, price, qty, pnl):
        # v1.21 FIX: Проверка UI
        try:
            if hasattr(self, 'trade_history_tree') and self.trade_history_tree.winfo_exists():
                prec_p = self.symbol_info.get('pricePrecision', 2); prec_q = self.symbol_info.get('quantityPrecision', 3)
                self.trade_history_tree.insert('', 'end', values=(dt.datetime.now().strftime("%H:%M:%S"), self.trading_pair.get(), side, f"{price:.{prec_p}f}", f"{qty:.{prec_q}f}",f"{pnl:+.4f}"))
                self.update_metrics()
        except tk.TclError:
            pass # Окно закрывается

    def start_scanner_thread(self):
        # v1.21 FIX: Проверка UI
        try:
            if hasattr(self, 'btn_scan') and self.btn_scan.winfo_exists():
                self.btn_scan.config(state=tk.DISABLED)
        except tk.TclError:
            pass
            
        def manual_scan_task():
            trader = BinanceTrader(self.api_key.get(), self.api_secret.get(), self.queue_log)
            autopilot = AutopilotManager(self, trader)
            autopilot.run_scanner(update_ui=True)
            
        threading.Thread(target=manual_scan_task, daemon=True).start()

    # --- ИЗМЕНЕНИЕ v6.65: Двойной клик (Левый) ---
    def _on_scanner_left_double_click(self, event):
        """Обрабатывает двойной клик (Левый) по дереву сканера."""
        try:
            if self.running.is_set():
                self.queue_log("Сканер: Нельзя менять пару, пока бот запущен.", "error")
                return
                
            if self._get_safe_int(self.autopilot_mode, 0):
                self.queue_log("Сканер: Нельзя менять пару, пока включен Автопилот.", "error")
                return
                
            item_id = self.scanner_tree.identify_row(event.y)
            if not item_id: return
            
            item_values = self.scanner_tree.item(item_id, 'values')
            if not item_values: return
            
            pair = item_values[0]
            self.trading_pair.set(pair)
            self.queue_log(f"Сканер: Пара вручную установлена на {pair}", "success")
            
        except Exception as e:
            self.queue_log(f"Ошибка двойного клика (Левый) в сканере: {repr(e)}", "error")
    # --- КОНЕЦ ИЗМЕНЕНИЯ ---

    # --- ИЗМЕНЕНИЕ v6.68: Двойной клик (Правый) для Google Search (webbrowser) ---
    def _on_scanner_right_double_click(self, event):
        """Обрабатывает двойной клик (Правый) по дереву сканера для поиска Google."""
        try:
            item_id = self.scanner_tree.identify_row(event.y)
            if not item_id: return
            
            item_values = self.scanner_tree.item(item_id, 'values')
            if not item_values: return
            
            pair = item_values[0]
            # Убираем USDT, чтобы получить чистое имя монеты
            coin_name = pair.replace("USDT", "")
            
            self.queue_log(f"Google: Поиск информации о {coin_name}...", "info")
            # Запускаем поиск в отдельном потоке, чтобы не вешать UI
            threading.Thread(target=self._google_search_thread, args=(coin_name,), daemon=True).start()

        except Exception as e:
            self.queue_log(f"Ошибка двойного клика (Правый) в сканере: {repr(e)}", "error")

    def _google_search_thread(self, coin_name):
        """Выполняет поиск Google в отдельном потоке, открывая браузер."""
        try:
            query = f"что такое криптовалюта {coin_name} история проекта"
            # v6.66: Используем urlencode для безопасного URL
            url = f"https://www.google.com/search?q={urlencode({'q': query})}" 
            
            self.queue_log(f"Google: Открываю браузер с запросом: '{query}'", "info")
            
            # --- ВЫЗОВ WEBBROWSER ---
            webbrowser.open_new_tab(url)
            # --- КОНЕЦ ВЫЗОВА ---
            
            # --- v6.68: Фикс TclError (гонка состояний) ---
            # Проверяем, существует ли еще главное окно, прежде чем переключать вкладку
            if hasattr(self, 'root') and self.root.winfo_exists():
                self.root.after(0, self.notebook.select, self.log_tab)
            # --- КОНЕЦ v6.68 ---

        except Exception as e:
            self.queue_log(f"КРИТ. ОШИБКА Google Search (webbrowser): {repr(e)}", "error")
    # --- КОНЕЦ ИЗМЕНЕНИЯ v6.68 ---

    # --- ИЗМЕНЕНИЕ v6.59: Метрики учитывают принудительный режим ---
    def update_metrics(self):
        # v1.21 FIX: Проверка UI (metric_vars)
        try:
            if not hasattr(self, 'metric_vars') or not self.metric_vars:
                return # Еще не инициализировано
                
            self.metric_vars['Режим'].set("Бумажный" if self._get_safe_int(self.paper_mode, 1) else "РЕАЛЬНЫЙ")
            self.metric_vars['Общий PnL ($)'].set(f"{self.total_profit_usd:+.4f}")
            self.metric_vars['Всего Сделок'].set(str(self.trade_count))
            self.metric_vars['WS Статус'].set("Подключен" if self.ws and self.ws.sock and self.ws.sock.connected else "Отключен")
            
            # --- v6.59: Логика отображения статуса ---
            if self._get_safe_int(self.force_long_mode, 0):
                status = "ТОЛЬКО LONG"
            elif self._get_safe_int(self.force_short_mode, 0):
                status = "ТОЛЬКО SHORT"
            elif self._get_safe_int(self.trend_filter_enabled, 0):
                trend_status = ("АКТИВЕН" if self.trading_allowed_by_trend else "ПАУЗА")
                status = f"LONG ({trend_status})" if not self.is_short_mode else f"SHORT ({trend_status})"
            else:
                status = "LONG (Фильтр Откл.)" if not self.is_short_mode else "SHORT (Фильтр Откл.)"
            # --- КОНЕЦ v6.59 ---
            
            self.metric_vars['Фильтр Тренда'].set(status)
        except (tk.TclError, AttributeError):
            pass # Окно закрывается
    # --- КОНЕЦ ИЗМЕНЕНИЯ ---


    def update_balance_metrics(self):
        # v1.21 FIX: Проверка UI (metric_vars)
        try:
            if not hasattr(self, 'metric_vars') or not self.metric_vars:
                return # Еще не инициализировано

            base = self.base_asset or "BASE"; quote = self.quote_asset or "QUOTE"
            if self._get_safe_int(self.paper_mode, 1):
                self.metric_vars['Баланс BASE'].set(f"{self.paper_base_balance:+.{self.symbol_info.get('quantityPrecision', 4)}f} {base}")
                self.metric_vars['Баланс QUOTE'].set(f"{self.paper_quote_balance:.2f} {quote}")
                self.metric_vars['Доступно QUOTE'].set(f"{self.paper_quote_balance:.2f} {quote}")
            else:
                self.metric_vars['Баланс BASE'].set(f"{float(self.real_position.get('positionAmt', 0.0)):+.{self.symbol_info.get('quantityPrecision', 4)}f} {base}")
                self.metric_vars['Баланс QUOTE'].set(f"{self.real_quote_balance:.2f} {quote}")
                self.metric_vars['Доступно QUOTE'].set(f"{self.real_available_balance:.2f} {quote}")
        except (tk.TclError, AttributeError):
            pass # Окно закрывается

    def update_open_orders_tree(self):
        # v1.21 FIX: Проверка UI
        try:
            if not hasattr(self, 'open_orders_tree') or not self.open_orders_tree.winfo_exists():
                return
                
            self.open_orders_tree.delete(*self.open_orders_tree.get_children())
            prec_p = self.symbol_info.get('pricePrecision', 2); prec_q = self.symbol_info.get('quantityPrecision', 3)
            orders_to_display = self.real_open_orders if not self._get_safe_int(self.paper_mode, 1) else self.paper_open_orders
            for o in orders_to_display:
                order_id = o.get('orderId') or o.get('id', '')
                price = o.get('price'); qty = o.get('origQty') or o.get('qty')
                self.open_orders_tree.insert('', 'end', values=(str(order_id)[:8], o.get('symbol', ''), o.get('side', ''), f"{float(price):.{prec_p}f}", f"{float(qty):.{prec_q}f}"))
        except tk.TclError:
            pass # Окно закрывается

if __name__ == "__main__":
    app = None
    try:
        root = tk.Tk()
        app = SpreadMakerApp(root)
        root.protocol("WM_DELETE_WINDOW", app.on_closing)
        root.mainloop()
    except Exception as e:
        print(f"Критическая ошибка в __main__: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # v1.21 FIX: Гарантированное закрытие при ошибке
        if app:
            app.on_closing()
        print("Программа завершена.")