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
        ⚡️【极速通道】仅获取最新价格，不计算指标，不拉K线
        用于 UI 高频刷新
        """
        if not self.connected: return 0.0

        try:
            # 1. 加密货币 (HTTP 接口更快)
            if "/" in symbol:
                clean_sym = symbol.replace("/", "")
                url = f"https://data.alpaca.markets/v1beta3/crypto/us/latest/trades?symbols={clean_sym}"
                resp = requests.get(url, headers=self.headers, timeout=1.5) # 超时设置短一点
                if resp.status_code == 200:
                    data = resp.json()
                    if "trades" in data and symbol in data["trades"]:
                        return float(data["trades"][symbol]["p"])
            
            # 2. 股票
            else:
                trade = self.api.get_latest_trade(symbol)
                return float(trade.price)
                
        except Exception as e:
            # 忽略偶尔的网络抖动，返回 0 让 UI 保持上一次价格
            pass
        return 0.0

    def get_analysis_data(self, symbol):
        """
        🐢【分析通道】获取 K 线 + 计算指标
        用于 AI 深度思考
        """
        if not self.connected: return 0, "No Connection"
        
        try:
            # 获取 K 线
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

            current_price = float(df.iloc[-1]['close'])

            # 计算指标
            df.ta.rsi(length=14, append=True)
            df.ta.macd(fast=12, slow=26, signal=9, append=True)
            df.ta.bbands(length=20, std=2, append=True)
            df.ta.sma(length=20, append=True)

            latest = df.iloc[-1]
            
            # 生成报告
            trend_str = "BULLISH" if current_price > latest.get('SMA_20', 0) else "BEARISH"
            report = f"Price: {current_price:.2f}\n"
            report += f"Trend: {trend_str}\n"
            report += f"RSI: {latest.get('RSI_14', 50):.2f}\n"
            report += f"MACD: {latest.get('MACD_12_26_9', 0):.2f}\n"
            report += f"BB: {latest.get('BBL_20_2.0', 0):.2f} / {latest.get('BBU_20_2.0', 0):.2f}"
            
            return current_price, report

        except Exception as e:
            return 0, f"Error: {str(e)}"

    # ... get_chart_data, get_position, place_order 等保持不变 ...
    # (由于篇幅限制，这里假设你保留了 backend.py 的其他方法)
    def get_chart_data(self, symbol, timeframe_str="1Min"):
        # ... (保留原代码) ...
        return super().get_chart_data(symbol, timeframe_str) if hasattr(super(), 'get_chart_data') else None

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
