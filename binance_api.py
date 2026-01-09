# binance_api.py
# Модуль для работы с API Binance Futures
# SpreadMaker v6.56 TRAIL by криптоволк программер
# ИСПРАВЛЕНО (v6.58): Добавлен 'create_batch_orders'

import requests
import time
import hmac
import hashlib
import json # <--- ДОБАВЛЕНО
from urllib.parse import urlencode

# ==============================================================================
# КЛАСС ДЛЯ РАБОТЫ С API BINANCE (API HANDLER)
# ==============================================================================
class BinanceTrader:
    def __init__(self, api_key, api_secret, log_callback):
        self.base_url = "https://fapi.binance.com"
        self.api_key = api_key
        self.api_secret = api_secret
        self.log = log_callback # Это функция queue_log из SpreadMakerApp
        self.__version__ = "v6.58 BATCH-FIX" # <--- ИЗМЕНЕНО

    def _get_signature(self, params):
        query_string = urlencode(params)
        return hmac.new(self.api_secret.encode('utf-8'), msg=query_string.encode('utf-8'), digestmod=hashlib.sha256).hexdigest()

    def _send_request(self, method, endpoint, params=None, signed=False):
        if params is None: params = {}
        headers = {'X-MBX-APIKEY': self.api_key}

        if signed:
            params['timestamp'] = int(time.time() * 1000)
            params['recvWindow'] = 60000
            params['signature'] = self._get_signature(params)

        url = f"{self.base_url}{endpoint}"

        try:
            if method.upper() == 'GET':
                res = requests.get(url, headers=headers, params=params, timeout=15)
            elif method.upper() == 'POST':
                res = requests.post(url, headers=headers, params=params, timeout=15)
            elif method.upper() == 'DELETE':
                res = requests.delete(url, headers=headers, params=params, timeout=15)
            else:
                return None

            res.raise_for_status()
            return res.json()
        except requests.exceptions.HTTPError as e:
            error_text = "Unknown Error"
            try:
                # Пытаемся декодировать ответ, игнорируя ошибки
                error_text = e.response.text.encode('utf-8', 'ignore').decode('utf-8')
            except Exception:
                pass # Оставляем "Unknown Error"
            self.log(f"ОШИБКА HTTP API: {e.response.status_code} - {error_text}", "error")
        except Exception as e:
            self.log(f"КРИТИЧЕСКАЯ ОШИБКА API: {repr(e)}", "error")
        return None

    def get_exchange_info(self):
        return self._send_request('GET', '/fapi/v1/exchangeInfo')

    def get_klines(self, symbol, interval, limit=201):
        return self._send_request('GET', '/fapi/v1/klines', {'symbol': symbol, 'interval': interval, 'limit': limit})

    def get_24h_tickers(self):
        return self._send_request('GET', '/fapi/v1/ticker/24hr')

    def get_ticker_price(self, symbol):
        res = self._send_request('GET', '/fapi/v1/ticker/price', {'symbol': symbol})
        return float(res['price']) if res and 'price' in res else None

    def create_order(self, symbol, side, order_type, quantity, price=None, timeInForce=None):
        params = {'symbol': symbol, 'side': side, 'type': order_type, 'quantity': quantity}
        if price: params['price'] = price
        if timeInForce: params['timeInForce'] = timeInForce
        if order_type == 'MARKET':
            params.pop('price', None)
            params.pop('timeInForce', None)
        self.log(f"РЕАЛ: Отправка ордера: {params}", "warning")
        return self._send_request('POST', '/fapi/v1/order', params, signed=True)

    # --- НОВАЯ ФУНКЦИЯ ДЛЯ ПАКЕТНЫХ ОРДЕРОВ ---
    def create_batch_orders(self, batch_orders_list):
        """
        Отправляет пакет ордеров (до 10 шт. на fapi).
        batch_orders_list: список словарей, каждый из которых - параметры ордера.
        """
        if not batch_orders_list:
            return None
        
        # Binance API требует, чтобы список ордеров был в виде JSON-строки
        params = {
            'batchOrders': json.dumps(batch_orders_list)
        }
        self.log(f"РЕАЛ: Отправка ПАКЕТА из {len(batch_orders_list)} ордеров...", "warning")
        
        # Отправляем запрос на /fapi/v1/batchOrders
        return self._send_request('POST', '/fapi/v1/batchOrders', params, signed=True)
    # --- КОНЕЦ НОВОЙ ФУНКЦИИ ---

    def cancel_order(self, symbol, orderId):
        params = {'symbol': symbol, 'orderId': orderId}
        self.log(f"РЕАЛ: Отмена ордера: {params}", "warning")
        return self._send_request('DELETE', '/fapi/v1/order', params, signed=True)

    def cancel_all_open_orders(self, symbol):
        params = {'symbol': symbol}
        self.log(f"РЕАЛ: Отмена ВСЕХ ордеров для {symbol}", "warning")
        return self._send_request('DELETE', '/fapi/v1/allOpenOrders', params, signed=True)

    def get_open_orders(self, symbol):
        return self._send_request('GET', '/fapi/v1/openOrders', {'symbol': symbol}, signed=True)

    def get_account_balance(self):
        return self._send_request('GET', '/fapi/v2/balance', signed=True)

    def get_position_information(self):
        return self._send_request('GET', '/fapi/v2/positionRisk', signed=True)