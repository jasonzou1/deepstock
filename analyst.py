# analyst.py
import requests
import json
import re
import config

class DeepSeekAnalyst:
    def __init__(self):
        self.model = config.MODEL_NAME

    def analyze(self, symbol, current_price, market_data_str):
        """调用本地 Ollama 进行分析"""
        
        prompt = f"""
        You are a crypto trader.
        Target: {symbol}
        Price: ${current_price:.2f}
        Data:
        {market_data_str}
        
        Analyze trend.
        - BUY if uptrend.
        - SELL if downtrend.
        - HOLD if unclear.
        
        Output JSON only: {{"action": "BUY/SELL/HOLD", "reason": "Short reason"}}
        """

        try:
            response = requests.post(
                config.OLLAMA_URL,
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.1}
                },
                timeout=30 # 稍微给点时间
            )
            
            if response.status_code == 200:
                raw_text = response.json()['response']
                
                # 去除 DeepSeek R1 的 <think> 标签，但保留内容作为日志可能更有趣？
                # 这里为了JSON解析稳定，我们先去掉标签，提取纯文本
                clean_text = re.sub(r'<think>.*?</think>', '', raw_text, flags=re.DOTALL).strip()
                
                # 尝试提取 JSON
                match = re.search(r'\{.*\}', clean_text, re.DOTALL)
                if match:
                    return json.loads(match.group())
                else:
                    # 如果没提取到 JSON，把原始回复的前50个字当理由返回
                    return {"action": "HOLD", "reason": f"Format Err: {clean_text[:50]}..."}
                
            return {"action": "HOLD", "reason": f"API Error {response.status_code}"}
            
        except Exception as e:
            return {"action": "HOLD", "reason": f"Connection Error: {str(e)}"}