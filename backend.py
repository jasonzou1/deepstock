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
            # 确保数量精度，Crypto 通常允许小数，股票通常是整数(除非开启fractional)
            # 这里简单处理：如果是 Crypto 保留4位小数，股票保留2位
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
        直接请求 API 获取最新成交价，解决 Crypto 价格有时为 0 的问题
        """
        if not self.connected: return 0.0

        try:
            # --- 1. 加密货币 (带 / ) ---
            if "/" in symbol:
                # Alpaca v1beta3 Data API (必须带 /，例如 BTC/USD)
                url = "https://data.alpaca.markets/v1beta3/crypto/us/latest/trades"
                params = {"symbols": symbol}
                
                resp = requests.get(url, params=params, headers=self.headers, timeout=2)
                
                if resp.status_code == 200:
                    data = resp.json()
                    if "trades" in data and symbol in data["trades"]:
                        price = float(data["trades"][symbol]["p"])
                        if price > 0: return price
                    else:
                        # 偶尔数据为空时，不打印烦人的日志，直接返回0让上层处理
                        pass
                else:
                    print(f"❌ {symbol} HTTP请求失败: {resp.status_code}")

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
        🔥【Hybrid 终极版】
        既给 AI 看 K 线形态 (Arrays)，又给 AI 关键指标提示 (Hints)。
        这是平衡“高上限”与“稳定性”的最佳方案。
        """
        if not self.connected: return 0, "No Connection"
        
        try:
            now_utc = datetime.now(timezone.utc)
            
            # 1. 宽视野：获取足够的数据计算指标
            start_time = (now_utc - timedelta(hours=6)).isoformat()
            if "/" in symbol:
                bars = self.api.get_crypto_bars(symbol, tradeapi.TimeFrame.Minute, start=start_time, limit=300).df
            else:
                bars = self.api.get_bars(symbol, tradeapi.TimeFrame.Minute, start=start_time, limit=300).df

            if bars.empty: return 0, "No Data"

            # 2. 数据清洗与指标计算
            df = bars.copy()
            df.rename(columns={'c': 'close', 'o': 'open', 'h': 'high', 'l': 'low', 'v': 'volume'}, inplace=True)
            current_price = float(df.iloc[-1]['close'])

            # 计算技术指标
            df.ta.ema(length=20, append=True)
            df.ta.rsi(length=14, append=True)
            df.ta.macd(append=True)
            
            # 3. 【核心保留】序列化数据 (让 AI 看形态)
            # Alpha Arena 的精髓：提供最近 10-12 个点，让 AI 识别拐点和背离
            tail = df.tail(12)
            
            def to_seq(series):
                # 格式化为 [1.1, 1.2, ...] 字符串
                return "[" + ", ".join([f"{x:.2f}" for x in series.values]) + "]"

            price_seq = to_seq(tail['close'])
            rsi_seq   = to_seq(tail['RSI_14'])
            macd_seq  = to_seq(tail['MACD_12_26_9'])
            vol_seq   = to_seq(tail['volume'])

            # 4. 【安全垫】Python 计算硬结论 (辅助小模型不犯错)
            last = df.iloc[-1]
            # 趋势提示
            ema20 = last['EMA_20']
            trend_hint = "UP (Price > EMA20)" if current_price > ema20 else "DOWN (Price < EMA20)"
            # RSI 提示
            rsi_val = last['RSI_14']
            rsi_hint = "OVERBOUGHT (>70)" if rsi_val > 70 else ("OVERSOLD (<30)" if rsi_val < 30 else "NEUTRAL")

            # 5. 构建报告：既有“直接结论”，又有“原始数据”
            report = f"""
            *** MARKET SNAPSHOT ***
            Current Price: {current_price:.2f}
            
            [PYTHON HINTS] (Use these as baseline context)
            - Trend: {trend_hint}
            - RSI State: {rsi_hint} ({rsi_val:.1f})
            
            [RAW DATA SEQUENCES] (Analyze these for patterns, divergence, or momentum shifts)
            - Data Order: OLDEST -> NEWEST (Last 12 mins)
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
        📊【绘图通道 - 性能优化版】
        """
        if not self.connected: return None
        try:
            now_utc = datetime.now(timezone.utc)
            
            # 动态调整时间范围，不要拉太久远的数据，否则前端会卡死
            if timeframe_str == "5Min": 
                tf = tradeapi.TimeFrame(5, tradeapi.TimeFrameUnit.Minute)
                start_time = (now_utc - timedelta(days=3)).isoformat() # 缩短到3天
            elif timeframe_str == "15Min": 
                tf = tradeapi.TimeFrame(15, tradeapi.TimeFrameUnit.Minute)
                start_time = (now_utc - timedelta(days=7)).isoformat()
            else:
                # 1Min
                tf = tradeapi.TimeFrame.Minute
                start_time = (now_utc - timedelta(hours=12)).isoformat() # 缩短到12小时
            
            # 🔥 核心优化：从 3000 降到 800，大幅提升渲染速度
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
        """查询持仓 (通用)"""
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
        """下单"""
        if not self.connected: return False, "未连接"
        try:
            qty_usd = round(float(qty_usd), 2)
            if qty_usd < 1.0: return False, "金额太小"
            self.api.submit_order(symbol=symbol, notional=qty_usd, side=side, type='market', time_in_force='gtc')
            return True, f"已提交 {side} ${qty_usd}"
        except Exception as e: return False, str(e)

    def close_full_position(self, symbol):
        """清仓"""
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



