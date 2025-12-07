# config.py

# config.py

# --- 默认设置 ---
DEFAULT_SYMBOL = "BTC/USD, ETH/USD, LTC/USD"
DEFAULT_QTY_USD = 100

# 🔴 关键修改 1：把间隔从 10 改为 60 (甚至 300)
# 让 AI 每 1 分钟看一次盘，而不是每 10 秒看一次，防止它这一秒买下一秒卖
DEFAULT_INTERVAL = 60

# 🔴 关键修改 2：把温度调低，让 AI 更稳重
AI_TEMPERATURE = 0.0  # 设为 0，让决策更确定性

# --- Alpaca 地址 ---
BASE_URL = "https://paper-api.alpaca.markets"

# --- Ollama 地址 ---
OLLAMA_URL = "http://localhost:11434/api/generate"