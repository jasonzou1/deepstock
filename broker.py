# broker.py
import alpaca_trade_api as tradeapi
import pandas as pd
from datetime import datetime, timedelta
import config

class AlpacaBroker:
    def __init__(self):
        try:
            self.api = tradeapi.REST(
                config.API_KEY,
                config.API_SECRET,
                config.BASE_URL,
                api_version='v2'
            )
            # 获取账户信息
            self.account = self.api.get_account()
            print(f"✅ Alpaca 连接成功! 模拟资金: ${float(self.account.cash):,.2f}")
        except Exception as e:
            print(f"❌ Alpaca 连接失败: {e}")
            raise e

    def get_market_data(self, symbol):
        """获取历史K线数据 (自动识别 股票 vs 加密货币)"""
        try:
            # 1. 判断是股票还是加密货币 (Crypto 带 '/')
            if '/' in symbol:
                # --- 加密货币获取逻辑 ---
                barset = self.api.get_crypto_bars(
                    symbol,
                    tradeapi.TimeFrame.Minute,
                    limit=config.HISTORY_LIMIT
                ).df
            else:
                # --- 股票获取逻辑 ---
                # 为了防止周末拿不到数据，我们不限制 start 时间，直接拿最新的 limit 条
                barset = self.api.get_bars(
                    symbol,
                    tradeapi.TimeFrame.Minute,
                    limit=config.HISTORY_LIMIT
                ).df

            # 2. 数据判空
            if barset.empty:
                return None, 0

            # 3. 简单的指标计算
            # 确保按时间排序
            if 'timestamp' in barset.columns:
                barset = barset.set_index('timestamp')
            
            # 这里的字段名 Alpaca 有时候返回 close 有时候返回 c，做个兼容
            if 'close' not in barset.columns and 'c' in barset.columns:
                barset['close'] = barset['c']
            if 'volume' not in barset.columns and 'v' in barset.columns:
                barset['volume'] = barset['v']

            barset['SMA_5'] = barset['close'].rolling(window=5).mean()
            current_price = barset.iloc[-1]['close']
            
            # 4. 整理数据喂给 AI
            data_str = barset[['close', 'volume', 'SMA_5']].tail(10).to_string()
            return data_str, current_price

        except Exception as e:
            # 调试用：打印具体错误
            # print(f"数据获取错误 {symbol}: {e}")
            return None, 0

    def get_position(self, symbol):
        """检查持仓"""
        try:
            # 尝试获取持仓
            pos = self.api.get_position(symbol)
            return float(pos.qty), float(pos.avg_entry_price)
        except:
            # 如果报错说明没持仓
            return 0, 0

    def submit_order(self, symbol, side, qty):
        """下单"""
        try:
            # 加密货币不需要检查 clock.is_open
            if '/' not in symbol:
                clock = self.api.get_clock()
                if not clock.is_open:
                    return False, "休市中"

            self.api.submit_order(
                symbol=symbol,
                qty=qty,
                side=side,
                type='market',
                time_in_force='gtc'
            )
            return True, f"已提交: {side} {qty} {symbol}"
        except Exception as e:
            return False, str(e)