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
        Role: Crypto Strategy Expert (Continuity & Context Aware).
        
        [Current Market]
        Symbol: {symbol}
        Price: ${price}
        
        {memory_block}
        
        [Position]
        {position_status}
        
        [Technical Brief]
        {market_report}
        
        [Instructions]
        1. REVIEW YOUR LAST DECISION. Do not flip-flop (buy/sell/buy) unless trend drastically changes.
        2. IF you bought recently and price is slightly down, HOLD (give it room to breathe).
        3. IF holding and profit > 2%, consider SELL (take profit).
        4. IF holding and trend breaks SMA20 support, SELL (stop loss).
        
        [Task]
        Analyze recent data + your past decision. 
        Output JSON ONLY.
        Example: {{"action": "HOLD", "reason": "Still waiting for breakout, price consolidated since last check"}}
        """
        
        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.0, "num_ctx": 4096}
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