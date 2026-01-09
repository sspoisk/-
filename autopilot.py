# autopilot.py
# Модуль логики Автопилота и Сканера
# SpreadMaker v6.56 TRAIL by криптоволк программер
# ИСПРАВЛЕНО (v6.59): Учитывает "Только LONG" / "Только SHORT" при переключении

import time
import numpy as np
import tkinter as tk # Нужно для _get_safe_...
import threading # Добавлен для finalize_switch

class AutopilotManager:
    def __init__(self, app, trader):
        self.app = app # Ссылка на главный класс SpreadMakerApp
        self.trader = trader # Ссылка на экземпляр BinanceTrader
    
    # ==============================================================================
    # БЛОК ЛОГИКИ АВТОПИЛОТА
    # ==============================================================================

    def check_for_switch(self):
        """Проверяет, не пора ли переключить пару."""
        self.app.queue_log("Автопилот: Начинаю фоновый поиск...", "info")

        # --- ИСПРАВЛЕНИЕ: Проверяем, не на паузе ли бот ---
        # --- v6.59: Учитываем принудительный режим, который отменяет паузу ---
        is_forced_mode = (self.app._get_safe_int(self.app.force_long_mode, 0) or 
                          self.app._get_safe_int(self.app.force_short_mode, 0))
        
        is_paused = (self.app._get_safe_int(self.app.trend_filter_enabled, 0) and 
                     not self.app.trading_allowed_by_trend and
                     not is_forced_mode) # Паузы нет, если режим принудительный
        # ---

        scan_results = self.run_scanner() # Используем свой же метод сканирования
        if not scan_results:
            self.app.queue_log("Автопилот: не удалось получить данные для оптимизации.", "warning"); return

        best_pair_info = scan_results[0] if scan_results else None
        if not best_pair_info:
            self.app.queue_log("Автопилот: Сканер не вернул результатов.", "info"); return

        force_switch_due_to_pause = False
        if best_pair_info['pair'] == self.app.trading_pair.get():
            if not is_paused:
                # Все в порядке: мы на лучшей паре и не на паузе
                self.app.queue_log("Автопилот: Текущая пара остается оптимальной.", "info"); return
            else:
                # ОШИБКА: Мы на лучшей паре, но она на ПАУЗЕ. Ищем замену.
                self.app.queue_log(f"Автопилот: Текущая пара {self.app.trading_pair.get()} на ПАУЗЕ. Ищу замену...", "warning")
                # Берем следующую пару из списка
                best_pair_info = next((p for p in scan_results[1:]), None)
                if not best_pair_info:
                    self.app.queue_log("Автопилот: Не найдено других подходящих пар для переключения.", "info"); return
                # Устанавливаем флаг принудительного переключения
                force_switch_due_to_pause = True
        
        # --- КОНЕЦ ИСПРАВЛЕНИЯ ---

        current_pair_info = next((p for p in scan_results if p['pair'] == self.app.trading_pair.get()), None)
        if not current_pair_info:
            self.app.queue_log(f"Автопилот: КРИТИЧЕСКАЯ ОШИБКА! Не удалось получить данные для текущей пары {self.app.trading_pair.get()}. Возможно, пара удалена с биржи. Остановка Автопилота.", "error")
            self.app.autopilot_mode.set(False) # Отключаем автопилот
            self.app.root.after(0, self.app.toggle_autopilot) # Обновляем UI
            self.app.root.after(0, self.app.stop_maker) # Останавливаем бота для безопасности
            return

        current_std = current_pair_info['std_dev_percent']
        best_std = best_pair_info['std_dev_percent']
        threshold = self.app._get_safe_double(self.app.autopilot_switch_threshold, 0.0)

        if current_std <= 0:
            self.app.queue_log("Автопилот: Текущая STD равна нулю. Пропуск проверки переключения.", "info"); return

        search_volatile = self.app._get_safe_int(self.app.scanner_volatile_mode, 0)
        improvement = 0.0; log_label = ""

        if search_volatile:
            improvement = (best_std - current_std) / current_std * 100
            log_label = "Прирост волатильности"
        else:
            improvement = (current_std - best_std) / current_std * 100
            log_label = "Выгода (снижение)"

        self.app.queue_log(f"Автопилот: Лучшая пара {best_pair_info['pair']} (STD: {best_std:.4f}%), текущая {self.app.trading_pair.get()} (STD: {current_std:.4f}%). {log_label}: {improvement:.2f}%", "info")

        # --- ИСПРАВЛЕНИЕ: Добавляем проверку на force_switch_due_to_pause ---
        if improvement > threshold or force_switch_due_to_pause:
            if force_switch_due_to_pause:
                 self.app.queue_log(f"Автопилот: Принудительное переключение с {self.app.trading_pair.get()} (ПАУЗА) на {best_pair_info['pair']}", "warning")
            else:
                self.app.queue_log(f"{log_label} ({improvement:.2f}%) > порога ({threshold}%)! Вхожу в режим 'Завершения сделки'...", "warning")
            
            self.app.potential_next_pair = best_pair_info['pair']
            self.app.autopilot_state = 'finishing'
            self.app.last_autopilot_recheck = time.time()
            if self.app._get_safe_int(self.app.autopilot_active_close, 0):
                self.app.queue_log("Автопилот: Включено активное закрытие. TP будет установлен на уровень безубытка.", "warning")
        else:
            self.app.queue_log(f"Автопилот: {log_label} не превышает порог.", "info")
        # --- КОНЕЦ ИСПРАВЛЕНИЯ ---

    def reevaluate_switch_decision(self):
        """Перепроверяет решение о переключении."""
        self.app.queue_log(f"Автопилот: Перепроверяю решение о переключении на {self.app.potential_next_pair}...", "info")

        # Запускаем сканер только для двух пар, но с правильной фильтрацией
        scan_results = self.run_scanner(pairs_to_check=[self.app.trading_pair.get(), self.app.potential_next_pair])

        potential_pair_info = next((p for p in (scan_results or []) if p['pair'] == self.app.potential_next_pair), None)
        current_pair_info = next((p for p in (scan_results or []) if p['pair'] == self.app.trading_pair.get()), None)

        if not potential_pair_info:
            self.app.queue_log(f"Автопилот: Целевая пара {self.app.potential_next_pair} больше не соответствует критериям. ОТМЕНА.", "warning")
            self.app.autopilot_state = 'trading'
            self.app.potential_next_pair = None
            self.app.create_grid(self.trader)
            return

        if not current_pair_info:
            self.app.queue_log(f"Автопилот: Не удалось получить данные для текущей пары {self.app.trading_pair.get()} при перепроверке. Переключение подтверждено.", "warning")
            return 

        current_std = current_pair_info['std_dev_percent']
        potential_std = potential_pair_info['std_dev_percent']

        if current_std <= 0:
            if potential_std > 0: 
                 self.app.queue_log(f"Автопилот: У текущей пары нулевая волатильность. Переключение на {self.app.potential_next_pair} выгодно.", "info")
                 return
            else: 
                 self.app.queue_log(f"Автопилот: Обе пары ({self.app.trading_pair.get()}, {self.app.potential_next_pair}) имеют нулевую волатильность. ОТМЕНА.", "warning")
                 self.app.autopilot_state = 'trading'
                 self.app.potential_next_pair = None
                 self.app.create_grid(self.trader)
                 return

        threshold = self.app._get_safe_double(self.app.autopilot_switch_threshold, 0.0)
        search_volatile = self.app._get_safe_int(self.app.scanner_volatile_mode, 0)
        improvement = 0.0

        if search_volatile:
            improvement = (potential_std - current_std) / current_std * 100
        else:
            improvement = (current_std - potential_std) / current_std * 100

        if improvement > threshold:
            self.app.queue_log(f"Автопилот: Переключение на {self.app.potential_next_pair} все еще выгодно ({improvement:.2f}% > {threshold}%). Продолжаю завершение.", "info")
        else:
            self.app.queue_log(f"Автопилот: Переключение больше не выгодно! ({improvement:.2f}% <= {threshold}%). ОТМЕНА.", "warning")
            self.app.autopilot_state = 'trading'
            self.app.potential_next_pair = None
            self.app.create_grid(self.trader)

    def finalize_switch(self):
        """Завершает переключение на новую пару."""
        self.app.queue_log("Текущая позиция закрыта. Финализирую переключение...", "success")
        self.app.autopilot_state = 'switching'

        self.reevaluate_switch_decision() # Вызываем свою же перепроверку
        if self.app.autopilot_state != 'switching':
            self.app.queue_log("Финальная проверка отменила переключение. Ищу новую сделку...", "info")
            self.app.autopilot_state = 'trading'
            return

        # --- ИСПРАВЛЕНИЕ "БАРДАКА" ---
        old_pair = self.app.trading_pair.get()
        self.app.queue_log(f"Автопилот: Очистка ВСЕХ ордеров для старой пары {old_pair}...", "warning")
        
        if not self.app._get_safe_int(self.app.paper_mode, 1):
             self.trader.cancel_all_open_orders(old_pair)
        
        self.app.paper_open_orders.clear()
        # --- КОНЕЦ ИСПРАВЛЕНИЯ ---

        self.app.stop_ws_flag.set();
        if self.app.ws and self.app.ws.sock and self.app.ws.sock.connected: self.app.ws.close()
        if self.app.ws_thread and self.app.ws_thread.is_alive(): self.app.ws_thread.join(timeout=3)

        self.app.queue_log("Автопилот: Очистка старого инвентаря перед переключением...", "info")
        self.app.paper_open_orders.clear()
        self.app.paper_inventory.clear()
        self.app.paper_base_balance = 0.0
        
        self.app.trading_pair.set(self.app.potential_next_pair)
        self.app.potential_next_pair = None

        self.app.queue_log(f"Переключился на новую пару: {self.app.trading_pair.get()}", "success")

        if not self.app.get_symbol_info(self.trader): self.app.root.after(0, self.app.stop_maker); return
        
        # --- ИСПРАВЛЕНИЕ v6.59: ОПРЕДЕЛЕНИЕ РЕЖИМА (LONG/SHORT) ДЛЯ НОВОЙ ПАРЫ С УЧЕТОМ ПРИНУЖДЕНИЯ ---
        self.app.queue_log(f"Автопилот: Определение режима (LONG/SHORT) для {self.app.trading_pair.get()}...", "info")
        
        new_price = self.trader.get_ticker_price(self.app.trading_pair.get())
        if not new_price:
             self.app.queue_log("Не удалось получить цену для новой пары. Остановка.", "error")
             self.app.root.after(0, self.app.stop_maker)
             return
        
        log_mode = "LONG" # По умолчанию
        
        if self.app._get_safe_int(self.app.force_long_mode, 0):
            # 1. Принудительный LONG
            self.app.is_short_mode = False
            log_mode = "ТОЛЬКО LONG (Принудительно)"
            
        elif self.app._get_safe_int(self.app.force_short_mode, 0):
            # 2. Принудительный SHORT
            if not self.app._get_safe_int(self.app.autopilot_allow_short, 0):
                self.app.queue_log("РЕЖИМ: 'Только SHORT' невозможен. Галочка 'Разрешить SHORT' неактивна. Запуск в LONG.", "error")
                self.app.is_short_mode = False
                log_mode = "LONG (Ошибка принуд. SHORT)"
            else:
                self.app.is_short_mode = True
                log_mode = "ТОЛЬКО SHORT (Принудительно)"
        
        else:
            # 3. Авто-определение по EMA (как было)
            ema_period = self.app._get_safe_int(self.app.ema_period, 200)
            trend_timeframe = self.app.trend_timeframe.get()
            
            klines = self.trader.get_klines(self.app.trading_pair.get(), trend_timeframe, ema_period)
            self.app.last_ema_value = self.app._calculate_ema(klines, ema_period)

            if self.app.last_ema_value > 0:
                is_below_ema = new_price < self.app.last_ema_value
                is_short_allowed = self.app._get_safe_int(self.app.autopilot_allow_short, 0)
                is_trend_enabled = self.app._get_safe_int(self.app.trend_filter_enabled, 0)

                # Устанавливаем режим торговли для новой пары
                self.app.is_short_mode = is_below_ema and is_short_allowed and is_trend_enabled
                log_mode = "SHORT (по EMA)" if self.app.is_short_mode else "LONG (по EMA)"
                self.app.queue_log(f"Автопилот: Новая пара {self.app.trading_pair.get()} (Цена: {new_price}, EMA: {self.app.last_ema_value:.4f}).", "info")
            
            else:
                self.app.queue_log(f"Автопилот: Не удалось рассчитать EMA для {self.app.trading_pair.get()}. Запуск в режиме LONG.", "warning")
                self.app.is_short_mode = False
                log_mode = "LONG (Ошибка EMA)"
        
        self.app.queue_log(f"Автопилот: Выбран режим: {log_mode}", "success")
        # --- КОНЕЦ ИСПРАВЛЕНИЯ v6.59 ---

        self.app.ws_thread = threading.Thread(target=self.app._run_websocket_stream, daemon=True)
        self.app.ws_thread.start()
        self.app.queue_log("Ожидание WS для новой пары (5 сек)...", "info"); time.sleep(5)
        
        # Используем цену, которую уже получили
        self.app.current_price['bid'] = new_price; self.app.current_price['ask'] = new_price
        self.app.create_grid(self.trader)
        self.app.autopilot_state = 'trading'


    # ==============================================================================
    # БЛОК ЛОГИКИ СКАНЕРА
    # ==============================================================================

    def run_scanner(self, update_ui=False, pairs_to_check=None):
        """
        Запускает сканер. 
        Если update_ui=True, обновляет GUI (для ручного запуска).
        Если pairs_to_check задан, сканирует только эти пары (для перепроверки).
        """
        if update_ui: self.app.queue_log("--- ЗАПУСК СКАНЕРА ---", "info")
        try:
            liq_filter = self.app._get_safe_double(self.app.scanner_liquidity_filter, 0.0); tf = self.app.scanner_timeframe.get()
            min_tf_volume = self.app._get_safe_double(self.app.scanner_min_tf_volume, 0.0)
            current_trading_pair = self.app.trading_pair.get()
        except tk.TclError: self.app.queue_log("Ошибка параметров сканера.", "error"); return None

        tickers = self.trader.get_24h_tickers()
        if not tickers: self.app.queue_log("Не удалось получить тикеры.", "error"); return None

        target_tickers_data = [] 
        target_symbols = set() 

        if pairs_to_check:
            target_tickers_data = [t for t in tickers if t.get('symbol') in pairs_to_check]
            target_symbols = set(pairs_to_check)
        else:
            for t in tickers:
                 symbol = t.get('symbol', '')
                 quote_volume = float(t.get('quoteVolume', 0))
                 if symbol.endswith('USDT') and quote_volume > liq_filter:
                     target_tickers_data.append(t)
                     target_symbols.add(symbol)

        results = []
        limit = len(target_tickers_data) 

        current_pair_found_in_scan = current_trading_pair in target_symbols
        
        for t in target_tickers_data[:limit]: 
            if not self.app.running.is_set() and update_ui and not pairs_to_check: break
            if update_ui and not pairs_to_check:
                current_index = target_tickers_data.index(t) + 1
                self.app.queue_log(f"Сканирование... ({current_index}/{limit}) {t['symbol']}", "info")


            klines = self.trader.get_klines(t['symbol'], tf, limit=100)
            if not klines or len(klines) < 12: continue

            is_current_pair = t['symbol'] == current_trading_pair
            apply_tf_volume_filter = not (is_current_pair and not pairs_to_check) 

            avg_tf_volume = np.mean([float(k[7]) for k in klines])

            if apply_tf_volume_filter and avg_tf_volume < min_tf_volume: continue
            
            closes = [float(k[4]) for k in klines]; mean = np.mean(closes)
            if mean == 0: continue
            std = (np.std(closes) / mean) * 100; vol = ((max(closes) - min(closes)) / mean) * 100
            results.append({'pair': t['symbol'], 'std_dev_percent': std, 'volatility_percent': vol, 'avg_volume': avg_tf_volume})

        if not current_pair_found_in_scan and not pairs_to_check:
            self.app.queue_log(f"Автопилот: Текущая пара {current_trading_pair} не прошла фильтр 24ч ({liq_filter}). Анализирую принудительно для сравнения.", "info")
            klines = self.trader.get_klines(current_trading_pair, tf, limit=100)
            if klines and len(klines) >= 12:
                avg_tf_volume = np.mean([float(k[7]) for k in klines])
                closes = [float(k[4]) for k in klines]; mean = np.mean(closes)
                if mean > 0:
                     std = (np.std(closes) / mean) * 100; vol = ((max(closes) - min(closes)) / mean) * 100
                     results.append({'pair': current_trading_pair, 'std_dev_percent': std, 'volatility_percent': vol, 'avg_volume': avg_tf_volume})
                     current_pair_found_in_scan = True 
            else:
                 self.app.queue_log(f"Автопилот: Не удалось получить данные klines для {current_trading_pair} при принудительном анализе.", "error")
        
        search_volatile = self.app._get_safe_int(self.app.scanner_volatile_mode, 0)
        if update_ui:
            log_msg = "Сканер: Идет поиск ВОЛАТИЛЬНОГО флэта (max std_dev)." if search_volatile else "Сканер: Идет поиск СТАБИЛЬНОГО флэта (min std_dev)."
            self.app.queue_log(log_msg, "warning")

        if results: 
             if search_volatile: results.sort(key=lambda x: x['std_dev_percent'], reverse=True)
             else: results.sort(key=lambda x: x['std_dev_percent'])

        if update_ui: 
            self.app.scanner_queue.put(results); 
            self.app.queue_log("--- СКАНИРОВАНИЕ ЗАВЕРШЕНО ---", "success"); 
            self.app.root.after(0, lambda: self.app.btn_scan.config(state=tk.NORMAL))
        
        return results if results else None