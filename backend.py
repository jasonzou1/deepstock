import alpaca_trade_api as tradeapi
import pandas as pd
import pandas_ta as ta
import requests
from datetime import datetime

class AlpacaBackend:
    def __init__(self):
        self.api = None
        self.connected = False
        self.headers = {}

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
        ⚡️【极速通道 - HTTP 修复版】
        直接请求 API，修复了符号格式问题，并增加了详细的错误打印
        """
        if not self.connected: return 0.0

        try:
            # --- 1. 加密货币 (带 / ) ---
            if "/" in symbol:
                # 🔴 关键修复：Alpaca API v1beta3 要求符号必须带 / (例如 BTC/USD)
                # 之前代码里的 .replace("/", "") 是导致获取不到数据的罪魁祸首
                
                # 直接构造 URL，requests 库会自动处理 URL 编码
                url = "https://data.alpaca.markets/v1beta3/crypto/us/latest/trades"
                params = {"symbols": symbol} # 这里传 "BTC/USD"
                
                # 发送请求
                resp = requests.get(url, params=params, headers=self.headers, timeout=2)
                
                if resp.status_code == 200:
                    data = resp.json()
                    # 调试打印：让你看到服务器到底返回了什么
                    # print(f"DEBUG {symbol}: {data}") 
                    
                    if "trades" in data and symbol in data["trades"]:
                        price = float(data["trades"][symbol]["p"])
                        if price > 0: return price
                    else:
                        print(f"⚠️ {symbol} 数据为空，API返回: {data}")
                else:
                    print(f"❌ {symbol} HTTP请求失败: {resp.status_code} - {resp.text}")

            # --- 2. 股票 (不带 / ) ---
            else:
                trade = self.api.get_latest_trade(symbol)
                return float(trade.price)
                
        except Exception as e:
            print(f"❌ 获取价格异常 [{symbol}]: {e}")
            return 0.0
        
        return 0.0

    def get_analysis_data(self, symbol):
        """
        🐢【分析通道 - 升级版】
        不仅计算指标，还提取最近的 K 线形态喂给 AI
        """
        if not self.connected: return 0, "No Connection"
        
        try:
            # 1. 获取 K 线 (保持不变)
            limit = 100
            if "/" in symbol:
                bars = self.api.get_crypto_bars(symbol, tradeapi.TimeFrame.Minute, limit=limit).df
            else:
                bars = self.api.get_bars(symbol, tradeapi.TimeFrame.Minute, limit=limit).df

            if bars.empty: return 0, "No Data"

            # 2. 清洗数据 (保持不变)
            df = bars.copy()
            map_cols = {'c': 'close', 'o': 'open', 'h': 'high', 'l': 'low', 'v': 'volume'}
            df.rename(columns=map_cols, inplace=True)
            df.sort_index(inplace=True)

            current_price = float(df.iloc[-1]['close'])

            # 3. 计算指标 (保持不变)
            df.ta.rsi(length=14, append=True)
            df.ta.macd(fast=12, slow=26, signal=9, append=True)
            df.ta.bbands(length=20, std=2, append=True)
            df.ta.sma(length=20, append=True)

            latest = df.iloc[-1]
            
            # 🔥 4. 【核心升级】构建“近期 K 线形态数据”
            # 取最近 15 根 K 线，格式化成文本，让 AI 能“看”到走势
            recent_candles = df.tail(15)
            candles_str = "Time (UTC)        | Open   | High   | Low    | Close  | Vol\n"
            candles_str += "-" * 60 + "\n"
            for index, row in recent_candles.iterrows():
                # 简化时间显示
                t_str = index.strftime("%H:%M")
                candles_str += f"{t_str} | {row['open']:.2f} | {row['high']:.2f} | {row['low']:.2f} | {row['close']:.2f} | {int(row['volume'])}\n"

            # 5. 生成综合报告
            trend_str = "BULLISH" if current_price > latest.get('SMA_20', 0) else "BEARISH"
            
            report = f"*** MARKET DATA ***\n"
            report += f"Current Price: {current_price:.2f}\n"
            report += f"Trend (vs SMA20): {trend_str}\n\n"
            
            report += f"*** TECHNICAL INDICATORS (Latest) ***\n"
            report += f"RSI(14): {latest.get('RSI_14', 50):.2f}\n"
            report += f"MACD: {latest.get('MACD_12_26_9', 0):.2f}\n"
            report += f"Bollinger: {latest.get('BBL_20_2.0', 0):.2f} (Low) / {latest.get('BBU_20_2.0', 0):.2f} (High)\n\n"
            
            report += f"*** RECENT 15 MIN PRICE ACTION (Must Analyze Patterns) ***\n"
            report += candles_str
            
            return current_price, report

        except Exception as e:
            return 0, f"Error: {str(e)}"

    def get_position(self, symbol):
        # ... (保留原代码，这里直接复制你的原逻辑即可) ...
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
        # ... (保留原代码) ...
        if not self.connected: return False, "未连接"
        try:
            qty_usd = round(float(qty_usd), 2)
            if qty_usd < 1.0: return False, "金额太小"
            self.api.submit_order(symbol=symbol, notional=qty_usd, side=side, type='market', time_in_force='gtc')
            return True, f"已提交 {side} ${qty_usd}"
        except Exception as e: return False, str(e)

    def close_full_position(self, symbol):
        # ... (保留原代码) ...
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
    
    # 为了防止上面的 get_chart_data 报错，这里补全它
    def get_chart_data(self, symbol, timeframe_str="1Min"):
        if not self.connected: return None
        try:
            tf = tradeapi.TimeFrame.Minute
            if timeframe_str == "5Min": tf = tradeapi.TimeFrame(5, tradeapi.TimeFrameUnit.Minute)
            elif timeframe_str == "15Min": tf = tradeapi.TimeFrame(15, tradeapi.TimeFrameUnit.Minute)
            elif timeframe_str == "1Hour": tf = tradeapi.TimeFrame.Hour
            limit = 100
            if "/" in symbol:
                bars = self.api.get_crypto_bars(symbol, tf, limit=limit).df
            else:
                bars = self.api.get_bars(symbol, tf, limit=limit).df
            if bars.empty: return None
            df = bars.copy()
            map_cols = {'c': 'close', 'o': 'open', 'h': 'high', 'l': 'low', 'v': 'volume'}
            df.rename(columns=map_cols, inplace=True)
            df.index = pd.to_datetime(df.index)
            return df
        except: return None


