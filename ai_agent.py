import requests
import json
import re
import config
import time
from datetime import datetime  # 必须保留这行导入

class DeepSeekAgent:
    def __init__(self):
        self.url = config.OLLAMA_URL

    def analyze(self, model_name, symbol, price, market_report, qty, avg_price, cash, equity, system_state, prev_memory=None):
        """
        Hybrid 模式专用分析器：教 AI 结合硬指标与软形态，并拥有连续记忆
        """
        
        # 1. 构建持仓状态
        position_block = "NO POSITION."
        if qty > 0:
            unrealized_pl = (price - avg_price) * qty
            pl_pct = (price - avg_price) / avg_price * 100
            position_block = f"""
            [CURRENT POSITION]
            - Symbol: {symbol}
            - Quantity: {qty:.4f}
            - Entry Price: ${avg_price:.2f}
            - Current Price: ${price:.2f}
            - Unrealized PnL: ${unrealized_pl:.2f} ({pl_pct:.2f}%)
            """

        # 2. 构建记忆模块 (新增)
        memory_block = "No previous memory (First run or reset)."
        if prev_memory:
            # 计算距离上次思考过了多久
            time_diff = int(time.time() - prev_memory.get('timestamp', time.time()))
            memory_block = f"""
            [YOUR PREVIOUS THOUGHTS] ({time_diff} seconds ago)
            - Last Action: {prev_memory.get('action', 'UNKNOWN')}
            - Last Reasoning: "{prev_memory.get('reason', 'None')}"
            
            (SELF-REFLECTION: Does your previous logic still hold true? Don't flip-flop unless market structure changed.)
            """

        # 3. 构建 Prompt
        prompt = f"""
        [SYSTEM STATUS]
        - Runtime: {system_state.get('run_time_min', 0)} min | Loop: {system_state.get('loop_count', 0)}
        - Time: {datetime.now().strftime("%H:%M:%S")}
        
        [OBJECTIVE]
        Aggressive Scalper. Capitalize on trends, but protect capital strictly.
        
        [STRATEGY MEMORY]
        {memory_block}
        
        [DATA INPUT]
        {market_report}
        
        [ACCOUNT]
        - Cash: ${cash:.2f} | Equity: ${equity:.2f}
        {position_block}
        
        [HYBRID DECISION PROTOCOL] (Follow Strictly)
        
        1. **STEP 1: Read [PYTHON HINTS]**
           - This is your BASELINE. If Trend is 'DOWN' and RSI is 'NEUTRAL', your bias is SELL or STAY OUT.
           
        2. **STEP 2: Analyze [RAW DATA SEQUENCES]**
           - Look for DIVERGENCE or MOMENTUM SHIFTS.
           - Compare with [STRATEGY MEMORY]: If you bought recently, give the trade room to breathe unless invalidation hit.
           
        3. **STEP 3: Execute**
           - BUY: If Trend is UP or significant Bullish Divergence found. (Max 20% of Cash).
           - SELL: If Trend is DOWN, RSI Overbought (>70), Stop Loss hit, or Thesis Failed.
           - HOLD: If signals are mixed or chopping.

        [OUTPUT JSON ONLY]
        {{
            "action": "BUY" | "SELL" | "HOLD",
            "amount_usd": <float>,
            "reason": "Brief logic. E.g. 'Trend UP + RSI Divergence detected'."
        }}
        """
        
        # --- 发送请求 ---
        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2, "num_ctx": 4096} 
        }

        try:
            resp = requests.post(self.url, json=payload, timeout=120)

            if resp.status_code == 200:
                raw_res = resp.json()['response']
                print(f"\n[{symbol}] AI RAW OUTPUT:\n{raw_res}\n{'-'*30}")
                
                # --- 解析逻辑 ---
                thought = "无思考"
                think_match = re.search(r'<think>(.*?)</think>', raw_res, re.DOTALL)
                if think_match:
                    thought = think_match.group(1).strip()
                    clean_text = re.sub(r'<think>.*?</think>', '', raw_res, flags=re.DOTALL)
                else:
                    clean_text = raw_res

                clean_text = re.sub(r'```json', '', clean_text, flags=re.IGNORECASE)
                clean_text = clean_text.replace("```", "").strip()

                json_match = re.search(r'\{.*\}', clean_text, re.DOTALL)
                if json_match:
                    try:
                        json_str = json_match.group().replace("'", '"')
                        data = json.loads(json_str)
                        return (data.get('action', 'HOLD').upper(), float(data.get('amount_usd', 0.0)), data.get('reason', 'JSON'), thought)
                    except: pass

                # Fallback Regex
                action = "HOLD"
                amount_usd = 0.0
                act_matches = re.findall(r'\b(BUY|SELL|HOLD)\b', clean_text.upper())
                if act_matches: action = act_matches[-1]
                amt_match = re.search(r'(\d[\d\.\,]*)\s*(USD|DOLLAR)', clean_text, re.IGNORECASE)
                if not amt_match: amt_match = re.search(r'amount_usd["\']?:?\s*([\d\.\,]+)', clean_text, re.IGNORECASE)
                if amt_match: 
                    try: amount_usd = float(amt_match.group(1).replace(',', ''))
                    except: pass
                
                if amount_usd <= 0:
                    if action == "BUY": amount_usd = min(cash * 0.1, 100.0)
                    elif action == "SELL" and qty > 0: amount_usd = qty * price * 0.5

                return action, amount_usd, "Regex Fallback", thought
            
            return "HOLD", 0.0, f"Status {resp.status_code}", ""
            
        except Exception as e:
            return "HOLD", 0.0, f"Net Err: {str(e)}", ""
