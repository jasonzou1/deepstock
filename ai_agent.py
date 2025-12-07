import requests
import json
import re
import config

class DeepSeekAgent:
    def __init__(self):
        self.url = config.OLLAMA_URL

    def analyze(self, model_name, symbol, price, market_report, qty, avg_price, prev_log=None):
        """
        升级版分析：支持加减仓逻辑 + 暴力容错解析 + 调试日志
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

        # 3. 提示词 (Prompt)
        # 针对 8B 模型简化了指令，强调格式
        # 3. 提示词 (Prompt) - 激进版
        prompt = f"""
        Role: Aggressive Crypto Day Trader.
        
        [Market] {symbol} | Price: ${price}
        {market_report}
        
        [Position] {position_status}
        {memory_block}
        
        [Goal]
        Capture trends aggressively. Do NOT be passive.
        
        [Logic]
        1. IF NO POSITION:
           - Trend is UP (Price > SMA20) -> BUY IMMEDIATELY.
           - Trend is DOWN -> HOLD.
           
        2. IF HOLDING:
           - Profit > 2% -> SELL 50% (Lock profit).
           - Trend reversal -> SELL 100% (Stop loss).
           - Trend continues -> HOLD or BUY more.

        [Strict Output Format]
        RETURN JSON ONLY. MUST INCLUDE "amount_pct".
        {{
            "action": "BUY", 
            "amount_pct": 100, 
            "reason": "Price broke above SMA20, valid entry"
        }}
        
        - amount_pct:
          * BUY: 100 = Full entry, 50 = Half entry.
          * SELL: 100 = Close all, 50 = Sell half.
          * HOLD: 0.
        """
        
        # 顺便把温度稍微回调到 0.2，让它敢于做决定，别太死板
        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2, "num_ctx": 4096} 
        }

        try:
            # 超时时间保持 120s
            resp = requests.post(self.url, json=payload, timeout=120)
            
            if resp.status_code == 200:
                raw_res = resp.json()['response']
                
                # --- 🔍 调试打印：让你看到 AI 到底回了什么 ---
                print(f"\n[{symbol}] AI RAW OUTPUT:\n{raw_res}\n{'-'*30}")
                
                # 1. 提取思考过程 (容错：如果找不到 tag，就取前 100 个字)
                thought = "无思考"
                think_match = re.search(r'<think>(.*?)</think>', raw_res, re.DOTALL)
                if think_match:
                    thought = think_match.group(1).strip()
                    # 把思考部分去掉，只留下正文用于提取 JSON
                    clean_text = re.sub(r'<think>.*?</think>', '', raw_res, flags=re.DOTALL)
                else:
                    # 如果没有 think 标签，可能模型直接回复了，或者格式乱了
                    clean_text = raw_res
                    thought = raw_res[:100] + "..." if len(raw_res) > 100 else raw_res

                # 2. 清洗 Markdown (有些模型喜欢加 ```json)
                clean_text = re.sub(r'```json', '', clean_text, flags=re.IGNORECASE)
                clean_text = clean_text.replace("```", "").strip()

                # 3. 第一重尝试：标准 JSON 提取
                json_match = re.search(r'\{.*\}', clean_text, re.DOTALL)
                if json_match:
                    try:
                        json_str = json_match.group()
                        # 修复常见的 JSON 错误（单引号变双引号）
                        if "'" in json_str and '"' not in json_str:
                            json_str = json_str.replace("'", '"')
                        
                        data = json.loads(json_str)
                        return (
                            data.get('action', 'HOLD').upper(), 
                            int(data.get('amount_pct', 0)), 
                            data.get('reason', 'JSON Parsed'), 
                            thought
                        )
                    except Exception as e:
                        print(f"JSON Parse Failed: {e}")
                        # JSON 失败，进入第二重尝试...

                # 4. 🔥 第二重尝试：暴力关键词提取 (Fallback)
                # 如果 JSON 崩了，直接在文本里找 "BUY", "SELL" 和数字
                print(f"[{symbol}] 启用暴力解析模式...")
                
                action = "HOLD"
                pct = 0
                
                # 找动作 (优先匹配最后的动作)
                act_matches = re.findall(r'\b(BUY|SELL|HOLD)\b', clean_text.upper())
                if act_matches:
                    action = act_matches[-1] # 取最后一个提到的动作
                
                # 找数字 (找离动作最近的数字，或者最大的数字)
                # 匹配 "50%", "amount: 50", "50 percent"
                pct_match = re.search(r'(\d+)%', clean_text)
                if not pct_match:
                    pct_match = re.search(r'amount.*?(\d+)', clean_text, re.IGNORECASE)
                
                if pct_match:
                    pct = int(pct_match.group(1))
                else:
                    # 如果没找到比例，默认给个保守值
                    pct = 50 if action != "HOLD" else 0

                return action, pct, "Regex Fallback", thought
            
            return "HOLD", 0, f"API Status {resp.status_code}", ""
            
        except Exception as e:
            print(f"AI Request Error: {e}")
            return "HOLD", 0, f"Net Err: {str(e)}", ""

