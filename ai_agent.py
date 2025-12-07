import requests
import json
import re
import config

class DeepSeekAgent:
    def __init__(self):
        self.url = config.OLLAMA_URL

    def analyze(self, model_name, symbol, price, market_report, qty, avg_price, prev_log=None):
        """
        新增参数 prev_log: 上一次的分析记录 (字典)
        包含: {'action': 'BUY', 'reason': '...', 'price': 100, 'time_ago': '5m'}
        """
        
        # 1. 构建持仓状态
        position_status = "NO POSITION"
        if qty > 0:
            profit_pct = (price - avg_price) / avg_price * 100
            position_status = f"HOLDING {qty:.4f}. Avg Cost: ${avg_price:.2f}. Current PnL: {profit_pct:.2f}%"

        # 2. 构建记忆模块 (关键升级)
        if prev_log:
            memory_block = f"""
            [YOUR LAST ANALYSIS]
            - Time ago: {prev_log['time_ago']}
            - You decided: {prev_log['action']}
            - At Price: ${prev_log['price']}
            - Your Reason: "{prev_log['reason']}"
            """
        else:
            memory_block = "[YOUR LAST ANALYSIS]\nNone (This is the first scan)."

        # 3. 提示词 (Prompt)
        prompt = f"""
        Role: Senior Crypto Quant Trader (Specialized in Price Action & Scalping).
        
        [Context]
        Symbol: {symbol}
        Current Price: ${price}
        
        {memory_block}
        
        [Position Status]
        {position_status}
        
        [Market Data Input]
        {market_report}
        
        [Instructions]
        1. FIRST, analyze the "RECENT 15 MIN PRICE ACTION" table deeply.
           - Look for patterns: Doji, Hammer, Engulfing, higher-highs/lower-lows.
           - Check volume spikes.
        2. Combine with Indicators (RSI, MACD, SMA20).
           - Is RSI diverging from the price action in the table?
        3. Decide Strategy:
           - BUY: Trend is strong OR clear reversal pattern at support.
           - SELL: Trend broke OR resistance hit OR profit target reached.
           - HOLD: Choppy market or waiting for confirmation.
        
        [Output Format]
        You utilize a Chain-of-Thought process. 
        First, write your thinking process inside <think> tags.
        Then, output the JSON decision.
        
        Format:
        <think>
        (Your deep analysis of the 15 candles, volatility, and setup...)
        </think>
        {{
            "action": "BUY", 
            "reason": "Bullish engulfing pattern detected on 1m chart with RSI rising"
        }}
        """
        
        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            # 🔥 关键修改：提高温度到 0.6，允许 R1 进行推理探索
            # num_ctx 保持 4096 以容纳更长的 K 线数据
            "options": {"temperature": 0.6, "num_ctx": 4096}
        }
        try:
            resp = requests.post(self.url, json=payload, timeout=120)
            if resp.status_code == 200:
                raw_res = resp.json()['response']
                
                # 清洗数据
                thought = "无思考"
                think_match = re.search(r'<think>(.*?)</think>', raw_res, re.DOTALL)
                if think_match:
                    thought = think_match.group(1).strip()
                    raw_res = re.sub(r'<think>.*?</think>', '', raw_res, flags=re.DOTALL)

                raw_res = re.sub(r'```json', '', raw_res).replace("```", "").strip()
                
                json_match = re.search(r'\{.*\}', raw_res, re.DOTALL)
                if json_match:
                    clean_json = json_match.group()
                    if "'" in clean_json and '"' not in clean_json:
                        clean_json = clean_json.replace("'", '"')
                    try:
                        data = json.loads(clean_json)
                        return data.get('action', 'HOLD'), data.get('reason', 'N/A'), thought
                    except:
                        return "HOLD", "JSON Syntax Error", thought
                
                return "HOLD", "No JSON found", thought
            
            return "HOLD", f"API Err {resp.status_code}", ""
        except Exception as e:

            return "HOLD", f"Net Err: {str(e)}", ""
