import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import time
import datetime
import json
import os
import pandas as pd
import mplfinance as mpf
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import config
from backend import AlpacaBackend
from ai_agent import DeepSeekAgent

CONFIG_FILE = "settings.json"
TRADES_FILE = "trade_history.json"

class QuantGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("DeepStock V2 - 高频监控 & 深度决策")
        self.root.geometry("1400x900")
        
        self.backend = AlpacaBackend()
        self.ai = DeepSeekAgent()
        
        self.running = False
        self.symbols_list = []
        self.last_buy_time = {} 
        self.trade_markers = self.load_trade_history()
        
        # 共享数据缓存，用于UI和后台线程通信
        self.market_cache = {} # {symbol: {'price': 0, 'pl': 0, 'qty': 0, 'status': '等待'}}

        self.setup_ui()
        self.load_settings()

    def load_trade_history(self):
        if os.path.exists(TRADES_FILE):
            try:
                with open(TRADES_FILE, "r") as f: return json.load(f)
            except: return {}
        return {}

    def record_trade(self, symbol, action, price):
        if symbol not in self.trade_markers: self.trade_markers[symbol] = []
        
        # 🔥 升级点1：强制使用 UTC 时间，与 Alpaca 的 K 线数据对齐
        # 否则北京时间会比 UTC 早8小时，导致标记画在未来的 K 线上看不到
        utc_now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        self.trade_markers[symbol].append({
            "time": utc_now,
            "action": action,
            "price": price
        })
        try:
            with open(TRADES_FILE, "w") as f: json.dump(self.trade_markers, f)
        except: pass

    def setup_ui(self):
        # --- UI 部分代码保持不变，直接复用原代码即可 ---
        # (为了节省篇幅，这里只写关键变化部分，请保留你原来的 setup_ui 内容)
        config_frame = ttk.LabelFrame(self.root, text="🔧 全局配置", padding=10)
        config_frame.pack(fill=tk.X, padx=10, pady=5)
        
        row1 = ttk.Frame(config_frame)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="API Key:").pack(side=tk.LEFT)
        self.entry_key = ttk.Entry(row1, width=25, show="*")
        self.entry_key.pack(side=tk.LEFT, padx=5)
        ttk.Label(row1, text="Secret:").pack(side=tk.LEFT)
        self.entry_secret = ttk.Entry(row1, width=25, show="*")
        self.entry_secret.pack(side=tk.LEFT, padx=5)
        self.btn_connect = ttk.Button(row1, text="🔌 连接", command=self.connect_alpaca)
        self.btn_connect.pack(side=tk.LEFT, padx=10)
        self.lbl_status = ttk.Label(row1, text="未连接", foreground="red")
        self.lbl_status.pack(side=tk.LEFT)
        ttk.Button(row1, text="💾 保存", command=self.save_settings).pack(side=tk.RIGHT)

        row2 = ttk.Frame(config_frame)
        row2.pack(fill=tk.X, pady=10)
        ttk.Label(row2, text="列表:").pack(side=tk.LEFT)
        self.entry_symbols = ttk.Entry(row2, width=40)
        self.entry_symbols.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(row2, text="单笔($):").pack(side=tk.LEFT)
        self.entry_qty = ttk.Entry(row2, width=8)
        self.entry_qty.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(row2, text="K线周期:").pack(side=tk.LEFT)
        self.combo_tf = ttk.Combobox(row2, values=["1Min", "5Min", "15Min", "1Hour"], width=6)
        self.combo_tf.current(1)
        self.combo_tf.pack(side=tk.LEFT, padx=5)

        self.btn_start = ttk.Button(row2, text="▶ 启动", state="disabled", command=self.toggle_trading)
        self.btn_start.pack(side=tk.RIGHT, padx=5)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        tab_table = ttk.Frame(self.notebook)
        self.notebook.add(tab_table, text="📊 实时监控")
        cols = ("币种", "最新价", "持仓量", "持仓均价", "浮动盈亏", "AI 状态", "冷却")
        self.tree = ttk.Treeview(tab_table, columns=cols, show="headings", height=8)
        for col in cols:
            self.tree.heading(col, text=col)
            self.tree.column(col, anchor="center", width=100)
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<Double-1>", self.on_tree_double_click)

        self.tab_chart = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_chart, text="📈 K线分析")
        self.lbl_chart_hint = ttk.Label(self.tab_chart, text="双击列表查看图表", font=("Arial", 14))
        self.lbl_chart_hint.pack(expand=True)

        paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, sashrelief=tk.RAISED)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        frame_sys = ttk.LabelFrame(paned, text="🖥️ 交易日志")
        self.txt_sys = scrolledtext.ScrolledText(frame_sys, width=50, height=12, state='disabled', bg="#f0f0f0")
        self.txt_sys.pack(fill=tk.BOTH, expand=True)
        self.txt_sys.tag_config("BUY", foreground="green", font=("Arial", 10, "bold"))
        self.txt_sys.tag_config("SELL", foreground="red", font=("Arial", 10, "bold"))
        self.txt_sys.tag_config("ERR", foreground="red", background="yellow")
        self.txt_sys.tag_config("WARN", foreground="orange", font=("Arial", 10, "bold"))
        paned.add(frame_sys)
        frame_ai = ttk.LabelFrame(paned, text="🧠 AI 思考")
        self.txt_ai = scrolledtext.ScrolledText(frame_ai, width=50, height=12, state='disabled', bg="#fffde7")
        self.txt_ai.pack(fill=tk.BOTH, expand=True)
        paned.add(frame_ai)

    # ... save_settings, load_settings, log_sys, log_ai, connect_alpaca 保持不变 ...
    def save_settings(self):
        data = {"api_key": self.entry_key.get(), "api_secret": self.entry_secret.get(), "symbols": self.entry_symbols.get(), "qty": self.entry_qty.get()}
        try:
            with open(CONFIG_FILE, "w") as f: json.dump(data, f)
        except: pass

    def load_settings(self):
        if not os.path.exists(CONFIG_FILE): return
        try:
            with open(CONFIG_FILE, "r") as f: data = json.load(f)
            if "api_key" in data: self.entry_key.delete(0, tk.END); self.entry_key.insert(0, data["api_key"])
            if "api_secret" in data: self.entry_secret.delete(0, tk.END); self.entry_secret.insert(0, data["api_secret"])
            if "symbols" in data: self.entry_symbols.delete(0, tk.END); self.entry_symbols.insert(0, data["symbols"])
            if "qty" in data: self.entry_qty.delete(0, tk.END); self.entry_qty.insert(0, data["qty"])
        except: pass

    def log_sys(self, msg, tag=None):
        self.root.after(0, lambda: self._write_log(self.txt_sys, msg, tag))

    def log_ai(self, symbol, thought, decision, reason):
        msg = f"--- {symbol} ---\n[思考]\n{thought}\n[决定] {decision} | {reason}\n\n"
        self.root.after(0, lambda: self._write_log(self.txt_ai, msg, None))

    def _write_log(self, widget, msg, tag=None):
        widget.config(state='normal')
        t = datetime.datetime.now().strftime("%H:%M:%S")
        full_msg = f"[{t}] {msg}\n" if widget == self.txt_sys else msg
        widget.insert(tk.END, full_msg, tag)
        widget.see(tk.END)
        widget.config(state='disabled')

    def connect_alpaca(self):
        key, secret = self.entry_key.get(), self.entry_secret.get()
        if not key or not secret: return messagebox.showerror("错误", "Key缺失")
        success, msg = self.backend.connect(key, secret, config.BASE_URL)
        if success:
            self.lbl_status.config(text="已连接", foreground="green")
            self.btn_connect.config(state="disabled")
            self.btn_start.config(state="normal")
            self.log_sys(msg)
            self.save_settings()
        else: self.log_sys(msg, "ERR")

    def on_tree_double_click(self, event):
        item = self.tree.selection()[0]
        symbol = self.tree.item(item, "values")[0]
        self.notebook.select(self.tab_chart)
        self.plot_chart(symbol)

    def plot_chart(self, symbol):
        # 清空旧图表
        for widget in self.tab_chart.winfo_children(): widget.destroy()
        
        tf = self.combo_tf.get()
        # 获取 K 线数据
        df = self.backend.get_chart_data(symbol, tf)
        if df is None or df.empty:
            ttk.Label(self.tab_chart, text="无法获取K线数据 (可能是休市或网络问题)").pack(expand=True)
            return

        # 确保 df 的索引是 UTC 时间 (防止时区混乱)
        if df.index.tz is None:
            df.index = df.index.tz_localize('UTC')
        else:
            df.index = df.index.tz_convert('UTC')

        add_plots = []
        
        # --- 绘制买卖标记 (保持之前的逻辑) ---
        if symbol in self.trade_markers:
            history = self.trade_markers[symbol]
            buys = [float('nan')] * len(df)
            sells = [float('nan')] * len(df)
            
            for trade in history:
                try:
                    t_time = pd.to_datetime(trade['time'])
                    if t_time.tz is None: t_time = t_time.tz_localize('UTC')
                    else: t_time = t_time.tz_convert('UTC')
                    
                    if t_time < df.index[0] or t_time > df.index[-1]: continue
                    idx = df.index.get_indexer([t_time], method='nearest')[0]
                    
                    if trade['action'] == 'BUY': buys[idx] = df.iloc[idx]['low'] * 0.99 
                    elif trade['action'] == 'SELL': sells[idx] = df.iloc[idx]['high'] * 1.01
                except: pass
            
            if not pd.isna(buys).all():
                add_plots.append(mpf.make_addplot(buys, type='scatter', markersize=100, marker='^', color='g'))
            if not pd.isna(sells).all():
                add_plots.append(mpf.make_addplot(sells, type='scatter', markersize=100, marker='v', color='r'))

        # --- 🔥 修复核心：动态构建参数 ---
        qty, pl, avg = self.backend.get_position(symbol)
        
        # 1. 定义基础参数
        s = mpf.make_mpf_style(marketcolors=mpf.make_marketcolors(up='green', down='red', inherit=True))
        plot_kwargs = dict(
            type='candle',
            mav=(5, 10),
            volume=True,
            style=s,
            addplot=add_plots,
            returnfig=True,
            figsize=(10, 6),
            title=f"{symbol} ({tf})"
        )

        # 2. 只有当有持仓时，才添加 hlines 参数！
        # 之前就是因为没持仓时传了空字典导致报错
        if qty > 0:
            plot_kwargs['hlines'] = dict(hlines=[avg], colors=['blue'], linestyle='-.', linewidths=(1.5))
            plot_kwargs['title'] += f" | Holding {qty} @ ${avg:.2f}"

        try:
            # 3. 使用 **plot_kwargs 解包参数传给 plot
            fig, ax = mpf.plot(df, **plot_kwargs)
            canvas = FigureCanvasTkAgg(fig, master=self.tab_chart)
            canvas.draw()
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        except Exception as e:
            ttk.Label(self.tab_chart, text=f"绘图渲染错误: {e}").pack(expand=True)
            print(f"Plot Error: {e}")

    # ================= 核心修改区域 =================

    def toggle_trading(self):
        if not self.running:
            self.save_settings()
            raw = self.entry_symbols.get()
            self.symbols_list = [s.strip().upper() for s in raw.split(',') if s.strip()]
            if not self.symbols_list: return messagebox.showerror("错误", "交易对为空")
            
            self.running = True
            self.btn_start.config(text="⏹ 停止")
            
            # 初始化 Treeview 和 缓存
            for item in self.tree.get_children(): self.tree.delete(item)
            for sym in self.symbols_list: 
                self.tree.insert("", "end", iid=sym, values=(sym, "...", "0", "0", "0", "等待", "--"))
                self.market_cache[sym] = {'price': 0, 'qty': 0, 'avg': 0, 'pl': 0, 'status': '初始化'}

            self.log_sys(f"🚀 启动双线程系统: {self.symbols_list}")
            
            # 🧵 线程 1: 极速行情刷新 (每 1 秒)
            threading.Thread(target=self.monitor_prices_loop, daemon=True).start()
            
            # 🧵 线程 2: AI 策略分析 (每 60 秒)
            threading.Thread(target=self.strategy_loop, daemon=True).start()
        else:
            self.running = False
            self.btn_start.config(text="▶ 启动")
            self.log_sys("🛑 停止中...")

    def update_ui_safe(self, symbol):
        """线程安全的 UI 更新函数"""
        if not self.running or symbol not in self.market_cache: return
        data = self.market_cache[symbol]
        
        # 计算冷却倒计时显示
        last = self.last_buy_time.get(symbol, 0)
        rem = max(0, 300 - (time.time() - last))
        cd_text = f"{int(rem)}s" if rem > 0 else "就绪"

        if self.tree.exists(symbol):
            self.tree.item(symbol, values=(
                symbol, 
                f"${data['price']:,.2f}", 
                f"{data['qty']:.4f}", 
                f"${data['avg']:,.2f}", 
                f"${data['pl']:+.2f}", 
                data['status'], 
                cd_text
            ))

    def monitor_prices_loop(self):
        """【线程1】只负责更新价格和盈亏，不进行思考"""
        while self.running:
            for symbol in self.symbols_list:
                if not self.running: break
                try:
                    # 1. 快速获取价格
                    price = self.backend.get_latest_price_fast(symbol)
                    if price > 0:
                        # 2. 更新缓存
                        cache = self.market_cache[symbol]
                        cache['price'] = price
                        
                        # 如果有持仓，实时计算盈亏
                        if cache['qty'] > 0:
                            cache['pl'] = (price - cache['avg']) * cache['qty']
                        
                        # 3. 刷新 UI
                        self.root.after(0, lambda s=symbol: self.update_ui_safe(s))
                    
                except Exception as e:
                    print(f"Price Monitor Error {symbol}: {e}")
            
            time.sleep(1.5) # 高频刷新，但不至于卡死API

    def strategy_loop(self):
        """【线程2】负责重型任务：拉K线、AI思考、下单"""
        while self.running:
            self.log_sys("🔍 AI 开始新一轮全量扫描...")
            
            for symbol in self.symbols_list:
                if not self.running: break
                
                try:
                    # 更新状态显示
                    self.market_cache[symbol]['status'] = "分析中..."
                    self.root.after(0, lambda s=symbol: self.update_ui_safe(s))

                    # 1. 获取详细数据 (含指标)
                    price, report = self.backend.get_analysis_data(symbol)
                    
                    # 同步一下持仓信息
                    qty, pl, avg = self.backend.get_position(symbol)
                    self.market_cache[symbol].update({'qty': qty, 'avg': avg}) # 价格由另一个线程更新，这里只更新持仓

                    # 2. 调用 AI (这里会阻塞很久，但不会影响 UI 价格刷新!)
                    action, reason, thought = self.ai.analyze("deepseek-r1:8b", symbol, price, report, qty, avg)
                    
                    self.log_ai(symbol, thought, action, reason)
                    self.market_cache[symbol]['status'] = action # 更新状态
                    self.root.after(0, lambda s=symbol: self.update_ui_safe(s))

                    # 3. 执行交易
                    if action == "BUY":
                        if qty == 0:
                            success, msg = self.backend.place_order(symbol, "buy", float(self.entry_qty.get()), price)
                            tag = "BUY" if success else "ERR"
                            self.log_sys(f"[{symbol}] 买入: {msg}", tag)
                            if success: 
                                self.last_buy_time[symbol] = time.time()
                                self.record_trade(symbol, 'BUY', price)
                        else:
                            self.log_sys(f"[{symbol}] 持有中，跳过")

                    elif action == "SELL":
                        if qty > 0:
                            # 冷却检查
                            last = self.last_buy_time.get(symbol, 0)
                            if time.time() - last < 300: # 5分钟保护
                                self.log_sys(f"[{symbol}] 冷却保护中 (5min)", "WARN")
                            else:
                                success, msg = self.backend.close_full_position(symbol)
                                tag = "SELL" if success else "ERR"
                                self.log_sys(f"[{symbol}] 卖出: {msg}", tag)
                                if success:
                                    self.record_trade(symbol, 'SELL', price)
                                    self.market_cache[symbol]['qty'] = 0 # 立即重置本地缓存

                except Exception as e:
                    self.log_sys(f"Strategy Error {symbol}: {e}", "ERR")
            
            # 这里的休息时间决定了 AI 的频率，建议 60秒
            self.log_sys("⏳ 周期结束，等待 60 秒...")
            for _ in range(60):
                if not self.running: break
                time.sleep(1)

if __name__ == "__main__":
    root = tk.Tk()
    app = QuantGUI(root)
    root.mainloop()


