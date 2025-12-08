import alpaca_trade_api as tradeapi
import pandas as pd
import pandas_ta as ta
import requests
from datetime import datetime, timedelta, timezone

class AlpacaBackend:
    def __init__(self):
        self.api = None
        self.connected = False
        self.headers = {}

    def submit_qty_order(self, symbol, side, qty):
        """
        ⚖️【精确下单】按数量下单 (用于减仓或精确加仓)
        """
        if not self.connected: return False, "未连接"
        try:
            qty = float(qty)
            if qty <= 0: return False, "数量必须大于0"

            self.api.submit_order(
                symbol=symbol, 
                qty=qty, 
                side=side, 
                type='market', 
                time_in_force='gtc'
            )
            return True, f"精确{side}: {qty}"
        except Exception as e:
            return False, str(e)

    def connect(self, key, secret, url):
        try:
            self.api = tradeapi.REST(key, secret, url, api_version='v2')
            account = self.api.get_account()
            self.connected = True
            self.headers = {
                "APCA-API-KEY-ID": key,
                "APCA-API-SECRET-KEY": secret,
                "accept": "application/json"
            }
            return True, f"✅ 连接成功! 资金: ${float(account.cash):,.2f}"
        except Exception as e:
            return False, f"❌ 连接失败: {str(e)}"

    def get_latest_price_fast(self, symbol):
        """
        ⚡️【极速通道 - HTTP 稳健版】
        """
        if not self.connected: return 0.0
        try:
            if "/" in symbol:
                url = "https://data.alpaca.markets/v1beta3/crypto/us/latest/trades"
                params = {"symbols": symbol}
                resp = requests.get(url, params=params, headers=self.headers, timeout=2)
                if resp.status_code == 200:
                    data = resp.json()
                    if "trades" in data and symbol in data["trades"]:
                        price = float(data["trades"][symbol]["p"])
                        if price > 0: return price
            else:
                trade = self.api.get_latest_trade(symbol)
                return float(trade.price)
        except Exception as e:
            print(f"❌ 获取价格异常 [{symbol}]: {e}")
            return 0.0
        return 0.0

    # 🔥 修复报错的关键函数
    def get_account_info(self):
        """
        💰 获取账户资金信息 (修复 AttributeError)
        Returns: available_cash, total_equity
        """
        if not self.connected: return 0.0, 0.0
        try:
            account = self.api.get_account()
            # cash 是可用现金, equity 是总净值
            return float(account.cash), float(account.equity)
        except Exception as e:
            print(f"Get Account Info Error: {e}")
            return 0.0, 0.0

    # 🔥 新增功能：获取宏观趋势 (上帝视角)
    def get_macro_context(self, symbol):
        """
        🌍【上帝视角】获取日线级别的大趋势
        """
        if not self.connected: return "MACRO: UNKNOWN (Data Error)"
        try:
            # 拉取最近 60 天的日线
            now = datetime.now(timezone.utc)
            start = (now - timedelta(days=60)).isoformat()
            
            if "/" in symbol:
                bars = self.api.get_crypto_bars(symbol, tradeapi.TimeFrame.Day, start=start, limit=60).df
            else:
                bars = self.api.get_bars(symbol, tradeapi.TimeFrame.Day, start=start, limit=60).df
                
            if bars.empty: return "MACRO: UNKNOWN (No Bars)"
            
            df = bars.copy()
            map_cols = {'c': 'close', 'o': 'open', 'h': 'high', 'l': 'low', 'v': 'volume'}
            df.rename(columns=map_cols, inplace=True)
            
            # 计算宏观指标
            current_close = df.iloc[-1]['close']
            df['SMA_20'] = df['close'].rolling(20).mean()
            sma20 = df.iloc[-1]['SMA_20']
            
            # 判断趋势
            trend = "BULLISH 🟢" if current_close > sma20 else "BEARISH 🔴"
            dist_pct = (current_close - sma20) / sma20 * 100
            
            return f"Daily Trend: {trend} (Price ${current_close:.2f} vs SMA20 ${sma20:.2f}, Dist: {dist_pct:.2f}%)"
            
        except Exception as e:
            return f"MACRO: ERROR ({str(e)})"

    def get_analysis_data(self, symbol):
        """
        🔥【Hybrid 终极版 + Macro】
        既给 AI 看 K 线形态 (Arrays)，又给 AI 关键指标提示 (Hints)，还加上了宏观背景 (Macro)。
        """
        if not self.connected: return 0, "No Connection"
        
        try:
            # --- 0. 先获取宏观背景 ---
            macro_text = self.get_macro_context(symbol)

            # --- 1. 获取分钟级数据 ---
            now_utc = datetime.now(timezone.utc)
            start_time = (now_utc - timedelta(hours=6)).isoformat()
            if "/" in symbol:
                bars = self.api.get_crypto_bars(symbol, tradeapi.TimeFrame.Minute, start=start_time, limit=300).df
            else:
                bars = self.api.get_bars(symbol, tradeapi.TimeFrame.Minute, start=start_time, limit=300).df

            if bars.empty: return 0, "No Data"

            # 2. 数据清洗
            df = bars.copy()
            df.rename(columns={'c': 'close', 'o': 'open', 'h': 'high', 'l': 'low', 'v': 'volume'}, inplace=True)
            current_price = float(df.iloc[-1]['close'])

            # 3. 计算指标
            df.ta.ema(length=20, append=True)
            df.ta.rsi(length=14, append=True)
            df.ta.macd(append=True)
            
            # 4. 序列化数据 (让 AI 看形态)
            tail = df.tail(12)
            def to_seq(series):
                return "[" + ", ".join([f"{x:.2f}" for x in series.values]) + "]"

            price_seq = to_seq(tail['close'])
            rsi_seq   = to_seq(tail['RSI_14'])
            macd_seq  = to_seq(tail['MACD_12_26_9'])
            vol_seq   = to_seq(tail['volume'])

            # 5. Python 计算硬结论
            last = df.iloc[-1]
            ema20 = last['EMA_20']
            trend_hint = "UP (Price > EMA20)" if current_price > ema20 else "DOWN (Price < EMA20)"
            rsi_val = last['RSI_14']
            rsi_hint = "OVERBOUGHT (>70)" if rsi_val > 70 else ("OVERSOLD (<30)" if rsi_val < 30 else "NEUTRAL")

            # 6. 构建报告 (把 Macro 加进去)
            report = f"""
            *** GOD'S EYE VIEW (Daily Timeframe) ***
            {macro_text}
            
            *** TACTICAL SNAPSHOT (1-Min Timeframe) ***
            Current Price: {current_price:.2f}
            
            [PYTHON HINTS]
            - Short-Term Trend: {trend_hint}
            - RSI State: {rsi_hint} ({rsi_val:.1f})
            
            [RAW DATA SEQUENCES] (Last 12 mins)
            - Price: {price_seq}
            - RSI14: {rsi_seq}
            - MACD : {macd_seq}
            - Vol  : {vol_seq}
            """
            
            return current_price, report

        except Exception as e:
            return 0, f"Error: {str(e)}"

    def get_chart_data(self, symbol, timeframe_str="1Min"):
        """
        📊【绘图通道】
        """
        if not self.connected: return None
        try:
            now_utc = datetime.now(timezone.utc)
            if timeframe_str == "5Min": 
                tf = tradeapi.TimeFrame(5, tradeapi.TimeFrameUnit.Minute)
                start_time = (now_utc - timedelta(days=3)).isoformat()
            elif timeframe_str == "15Min": 
                tf = tradeapi.TimeFrame(15, tradeapi.TimeFrameUnit.Minute)
                start_time = (now_utc - timedelta(days=7)).isoformat()
            else:
                tf = tradeapi.TimeFrame.Minute
                start_time = (now_utc - timedelta(hours=12)).isoformat()
            
            limit = 800 
            
            if "/" in symbol:
                bars = self.api.get_crypto_bars(symbol, tf, start=start_time, limit=limit).df
            else:
                bars = self.api.get_bars(symbol, tf, start=start_time, limit=limit).df
                
            if bars.empty: return None
            
            df = bars.copy()
            map_cols = {'c': 'close', 'o': 'open', 'h': 'high', 'l': 'low', 'v': 'volume'}
            df.rename(columns=map_cols, inplace=True)
            df.index = pd.to_datetime(df.index)
            
            return df
        except Exception as e:
            print(f"Chart Data Error: {e}")
            return None

    def get_position(self, symbol):
        if not self.connected: return 0, 0, 0
        try:
            all_positions = self.api.list_positions()
            target_clean = symbol.replace("/", "").strip().upper()
            for pos in all_positions:
                pos_clean = pos.symbol.replace("/", "").strip().upper()
                if pos_clean == target_clean:
                    return float(pos.qty), float(pos.unrealized_pl), float(pos.avg_entry_price)
            return 0, 0, 0
        except: return 0, 0, 0

    def place_order(self, symbol, side, qty_usd, current_price):
        if not self.connected: return False, "未连接"
        try:
            qty_usd = round(float(qty_usd), 2)
            if qty_usd < 1.0: return False, "金额太小"
            self.api.submit_order(symbol=symbol, notional=qty_usd, side=side, type='market', time_in_force='gtc')
            return True, f"已提交 {side} ${qty_usd}"
        except Exception as e: return False, str(e)

    def close_full_position(self, symbol):
        if not self.connected: return False, "未连接"
        try:
            qty, _, _ = self.get_position(symbol)
            if qty <= 0: return False, "无持仓"
            real_symbol = symbol
            all_positions = self.api.list_positions()
            target_clean = symbol.replace("/", "").strip().upper()
            for pos in all_positions:
                if pos.symbol.replace("/", "").strip().upper() == target_clean:
                    real_symbol = pos.symbol
                    break
            self.api.submit_order(symbol=real_symbol, qty=qty, side='sell', type='market', time_in_force='gtc')
            return True, f"已清仓卖出 {qty}"
        except Exception as e: return False, str(e)



