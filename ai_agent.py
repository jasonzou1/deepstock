import requests
import json
import re
import config

class DeepSeekAgent:
    def __init__(self):
        self.url = config.OLLAMA_URL

    import requests
import json
import re
import config

class DeepSeekAgent:
    def __init__(self):
        self.url = config.OLLAMA_URL

    def analyze(self, model_name, symbol, price, market_report, qty, avg_price, cash, equity, prev_log=None):
        """
        升级版分析：AI直接决定交易金额 (USD)
        """
        
        # 1. 构建持仓状态
        position_status = "NO POSITION"
        if qty > 0:
            profit_pct = (price - avg_price) / avg_price * 100
            position_status = f"HOLDING {qty:.4f} units. Avg Cost: ${avg_price:.2f}. PnL: {profit_pct:.2f}%"

        # 2. 构建记忆
        memory_block = ""
        if prev_log:
            memory_block = f"""
            [LAST ACTION] {prev_log['time_ago']} ago, you did: {prev_log['action']} at ${prev_log['price']}.
            Reason: "{prev_log['reason']}"
            """
        else:
            memory_block = "[LAST ACTION] None (First run)."

        # 3. 提示词 (Prompt) - 核心修改
        prompt = f"""
        Role: Capital Allocator and Aggressive Crypto Day Trader.
        
        [Account Info]
        Available Cash (可用资金): ${cash:,.2f}
        Total Equity (总净值): ${equity:,.2f}
        
        [Market] {symbol} | Price: ${price}
        {market_report}
        
        [Position] {position_status}
        {memory_block}
        
        [Goal]
        Capture trends aggressively while managing total portfolio risk.
        
        [Logic]
        1. IF NO POSITION:
           - Trend is UP (Price > SMA20) -> BUY. Recommended Allocation: Up to 20% of Available Cash.
           - Trend is DOWN -> HOLD.
           
        2. IF HOLDING:
           - Profit > 2% -> SELL. Recommended: 50% of current position value (Lock profit).
           - Trend reversal -> SELL. Recommended: 100% of current position value (Stop loss).
           - Trend continues -> HOLD or BUY more (Small size, up to 5% of Available Cash).

        [STRICT OUTPUT FORMAT & CAPITAL ALLOCATION]
        RETURN JSON ONLY. MUST include "amount_usd" for BUY/SELL actions.
        
        - amount_usd: MUST be the absolute dollar amount (USD) to transact.
          * For BUY: amount_usd <= Available Cash. Do NOT exceed cash.
          * For SELL: amount_usd should represent the dollar value of the position to be sold (e.g. current QTY * Price * 0.5).
          * For HOLD: amount_usd MUST be 0.0.
          
        Example (BUY): {{ "action": "BUY", "amount_usd": 1200.00, "reason": "Aggressive entry, using 10% of cash." }}
        Example (SELL): {{ "action": "SELL", "amount_usd": 5000.00, "reason": "Taking 50% profit." }}
        Example (HOLD): {{ "action": "HOLD", "amount_usd": 0.0, "reason": "Waiting for clearer signals." }}
        """
        
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
                
                # 1. 提取思考过程
                thought = "无思考"
                think_match = re.search(r'<think>(.*?)</think>', raw_res, re.DOTALL)
                if think_match:
                    thought = think_match.group(1).strip()
                    clean_text = re.sub(r'<think>.*?</think>', '', raw_res, flags=re.DOTALL)
                else:
                    clean_text = raw_res
                    thought = raw_res[:100] + "..." if len(raw_res) > 100 else raw_res

                # 2. 清洗 Markdown
                clean_text = re.sub(r'```json', '', clean_text, flags=re.IGNORECASE)
                clean_text = clean_text.replace("```", "").strip()

                # 3. 第一重尝试：标准 JSON 提取 (修改为提取 amount_usd)
                json_match = re.search(r'\{.*\}', clean_text, re.DOTALL)
                if json_match:
                    try:
                        json_str = json_match.group()
                        if "'" in json_str and '"' not in json_str:
                            json_str = json_str.replace("'", '"')
                        
                        data = json.loads(json_str)
                        # 🔥 核心修改：提取 amount_usd 并返回浮点数
                        return (
                            data.get('action', 'HOLD').upper(), 
                            float(data.get('amount_usd', 0.0)), 
                            data.get('reason', 'JSON Parsed'), 
                            thought
                        )
                    except Exception as e:
                        print(f"JSON Parse Failed: {e}")

                # 4. 🔥 第二重尝试：暴力关键词提取 (Fallback)
                print(f"[{symbol}] 启用暴力解析模式 (金额)...")
                
                action = "HOLD"
                amount_usd = 0.0 
                
                act_matches = re.findall(r'\b(BUY|SELL|HOLD)\b', clean_text.upper())
                if act_matches:
                    action = act_matches[-1]
                
                # 找金额 (尝试匹配 "amount_usd": 1234.56, 或者 1234.56 USD)
                amount_match = re.search(r'amount_usd["\']?:?\s*([\d\.\,]+)', clean_text, re.IGNORECASE)
                if not amount_match:
                    amount_match = re.search(r'(\d[\d\.\,]*)\s*(USD|DOLLAR)', clean_text, re.IGNORECASE)
                
                if amount_match:
                    amount_str = amount_match.group(1).replace(',', '').strip()
                    try:
                        amount_usd = float(amount_str)
                    except:
                        pass
                
                # Fallback Logic: 如果解析失败，给一个安全默认值
                if amount_usd <= 0.0 and action == "BUY" and cash > 50:
                    amount_usd = min(cash * 0.05, 100.0) # 默认使用可用现金的5%或$100 (取小值)
                elif amount_usd <= 0.0 and action == "SELL" and qty > 0 and price > 0:
                    amount_usd = qty * price * 0.5 # 默认卖出当前仓位的50%
                
                # 最终安全检查
                if action == "BUY": amount_usd = min(amount_usd, cash)

                return action, amount_usd, "Regex Fallback (USD)", thought
            
            return "HOLD", 0.0, f"API Status {resp.status_code}", ""
            
        except Exception as e:
            print(f"AI Request Error: {e}")
            return "HOLD", 0.0, f"Net Err: {str(e)}", ""

