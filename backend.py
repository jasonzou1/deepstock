import alpaca_trade_api as tradeapi
import pandas as pd
import pandas_ta as ta
import requests  # 👈 必须有这个，用于获取实时价
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
            
            # 保存 Header 用于手动 HTTP 请求 (获取实时价的关键)
            self.headers = {
                "APCA-API-KEY-ID": key,
                "APCA-API-SECRET-KEY": secret,
                "accept": "application/json"
            }
            return True, f"✅ 连接成功! 资金: ${float(account.cash):,.2f}"
        except Exception as e:
            return False, f"❌ 连接失败: {str(e)}"

    def get_market_data_detailed(self, symbol):
        """
        【集大成者】
        1. HTTP 请求 -> 获取毫秒级实时价 (解决滞后)
        2. K线数据 -> 计算 pandas_ta 指标 (RSI/MACD)
        """
        if not self.connected: return 0, "No Connection"
        
        try:
            current_price = 0.0
            
            # --- 🔥 1. 强力获取实时价 (HTTP Request) 🔥 ---
            # 这一步是为了解决 ETH 价格滞后问题
            try:
                if "/" in symbol:
                    clean_sym = symbol.replace("/", "")
                    # 直接访问数据接口
                    url = f"https://data.alpaca.markets/v1beta3/crypto/us/latest/trades?symbols={clean_sym}"
                    resp = requests.get(url, headers=self.headers, timeout=2)
                    
                    if resp.status_code == 200:
                        data = resp.json()
                        # 解析: {"trades": {"ETH/USD": {"p": 2950.5, ...}}}
                        if "trades" in data and symbol in data["trades"]:
                            current_price = float(data["trades"][symbol]["p"])
                else:
                    # 股票实时价
                    trade = self.api.get_latest_trade(symbol)
                    current_price = float(trade.price)
            except Exception as e:
                print(f"实时价获取微瑕: {e}")

            # --- 2. 获取 K 线用于计算指标 ---
            limit = 100
            if "/" in symbol:
                bars = self.api.get_crypto_bars(symbol, tradeapi.TimeFrame.Minute, limit=limit).df
            else:
                bars = self.api.get_bars(symbol, tradeapi.TimeFrame.Minute, limit=limit).df

            if bars.empty: return 0, "No Data"

            # 清洗数据
            df = bars.copy()
            map_cols = {'c': 'close', 'o': 'open', 'h': 'high', 'l': 'low', 'v': 'volume'}
            df.rename(columns=map_cols, inplace=True)
            df.sort_index(inplace=True)

            # 如果实时价刚才没取到，用 K 线收盘价兜底
            latest_bar = df.iloc[-1]
            if current_price == 0.0:
                current_price = float(latest_bar['close'])

            # --- 3. 计算 pandas_ta 高级指标 ---
            df.ta.rsi(length=14, append=True)
            df.ta.macd(fast=12, slow=26, signal=9, append=True)
            df.ta.bbands(length=20, std=2, append=True)
            df.ta.sma(length=20, append=True)
            df.ta.atr(length=14, append=True)

            # 获取最新指标值
            latest = df.iloc[-1]
            rsi = latest.get('RSI_14', 50)
            macd = latest.get('MACD_12_26_9', 0)
            upper = latest.get('BBU_20_2.0', 0)
            lower = latest.get('BBL_20_2.0', 0)
            sma20 = latest.get('SMA_20', 0)
            
            trend_str = "BULLISH" if current_price > sma20 else "BEARISH"
            
            # 生成投喂给 AI 的简报
            report = f"REAL-TIME Price: {current_price:.2f}\n"
            report += f"Trend Context: {trend_str} (Price vs SMA20)\n"
            report += f"Indicators (Based on 1m close):\n"
            report += f"- RSI(14): {rsi:.2f}\n"
            report += f"- MACD: {macd:.2f}\n"
            report += f"- Bollinger: {lower:.2f} / {upper:.2f}\n"
            
            return current_price, report

        except Exception as e:
            return 0, f"Error: {str(e)}"

    def get_chart_data(self, symbol, timeframe_str="1Min"):
        """
        【绘图专用接口】
        获取纯净的 OHLCV 数据给 mplfinance 画图用
        """
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

    def get_position(self, symbol):
        """万能查询持仓"""
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
        """下单 (精度修复)"""
        if not self.connected: return False, "未连接"
        try:
            qty_usd = round(float(qty_usd), 2)
            if qty_usd < 1.0: return False, "金额太小"
            self.api.submit_order(symbol=symbol, notional=qty_usd, side=side, type='market', time_in_force='gtc')
            return True, f"已提交 {side} ${qty_usd}"
        except Exception as e: return False, str(e)

    def close_full_position(self, symbol):
        """精准清仓 (数量修复)"""
        if not self.connected: return False, "未连接"
        try:
            qty, _, _ = self.get_position(symbol)
            if qty <= 0: return False, "无持仓"
            
            # 寻找真实 symbol (如 BTCUSD)
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