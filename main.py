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
        self.root.title("DeepStock 终极量化终端 (RealTime + Charts)")
        self.root.geometry("1400x900")
        
        self.backend = AlpacaBackend()
        self.ai = DeepSeekAgent()
        self.running = False
        self.symbols_list = []
        self.last_buy_time = {} 
        self.trade_markers = self.load_trade_history()
        
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("Treeview", rowheight=30, font=('Arial', 10))
        
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
        self.trade_markers[symbol].append({
            "time": datetime.datetime.now().isoformat(),
            "action": action,
            "price": price
        })
        try:
            with open(TRADES_FILE, "w") as f: json.dump(self.trade_markers, f)
        except: pass

    def setup_ui(self):
        # 1. 配置区
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
        self.entry_symbols.insert(0, "BTC/USD, ETH/USD, NVDA")
        self.entry_symbols.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(row2, text="单笔($):").pack(side=tk.LEFT)
        self.entry_qty = ttk.Entry(row2, width=8)
        self.entry_qty.insert(0, "100")
        self.entry_qty.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(row2, text="K线周期:").pack(side=tk.LEFT)
        self.combo_tf = ttk.Combobox(row2, values=["1Min", "5Min", "15Min", "1Hour"], width=6)
        self.combo_tf.current(1)
        self.combo_tf.pack(side=tk.LEFT, padx=5)

        self.btn_start = ttk.Button(row2, text="▶ 启动", state="disabled", command=self.toggle_trading)
        self.btn_start.pack(side=tk.RIGHT, padx=5)

        # 2. 中间多标签
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

        # 3. 日志
        paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, sashrelief=tk.RAISED)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        frame_sys = ttk.LabelFrame(paned, text="🖥️ 交易日志")
        self.txt_sys = scrolledtext.ScrolledText(frame_sys, width=50, height=12, state='disabled', bg="#f0f0f0")
        self.txt_sys.pack(fill=tk.BOTH, expand=True)
        self.txt_sys.tag_config("BUY", foreground="green", font=("Arial", 10, "bold"))
        self.txt_sys.tag_config("SELL", foreground="red", font=("Arial", 10, "bold"))
        self.txt_sys.tag_config("ERR", foreground="red", background="yellow")
        paned.add(frame_sys)
        frame_ai = ttk.LabelFrame(paned, text="🧠 AI 思考")
        self.txt_ai = scrolledtext.ScrolledText(frame_ai, width=50, height=12, state='disabled', bg="#fffde7")
        self.txt_ai.pack(fill=tk.BOTH, expand=True)
        paned.add(frame_ai)

    # --- 绘图逻辑 ---
    def on_tree_double_click(self, event):
        item = self.tree.selection()[0]
        symbol = self.tree.item(item, "values")[0]
        self.notebook.select(self.tab_chart)
        self.plot_chart(symbol)

    def plot_chart(self, symbol):
        for widget in self.tab_chart.winfo_children(): widget.destroy()
        
        tf = self.combo_tf.get()
        df = self.backend.get_chart_data(symbol, tf)
        if df is None:
            ttk.Label(self.tab_chart, text="无法获取K线数据").pack(expand=True)
            return

        add_plots = []
        if symbol in self.trade_markers:
            history = self.trade_markers[symbol]
            buys = [float('nan')] * len(df)
            sells = [float('nan')] * len(df)
            
            for trade in history:
                try:
                    t_time = pd.to_datetime(trade['time'])
                    idx = df.index.get_indexer([t_time], method='nearest')[0]
                    if trade['action'] == 'BUY': buys[idx] = trade['price'] * 0.99
                    elif trade['action'] == 'SELL': sells[idx] = trade['price'] * 1.01
                except: pass
            
            if any(not pd.isna(x) for x in buys):
                add_plots.append(mpf.make_addplot(buys, type='scatter', markersize=100, marker='^', color='g'))
            if any(not pd.isna(x) for x in sells):
                add_plots.append(mpf.make_addplot(sells, type='scatter', markersize=100, marker='v', color='r'))

        try:
            s = mpf.make_mpf_style(marketcolors=mpf.make_marketcolors(up='green', down='red', inherit=True))
            fig, ax = mpf.plot(df, type='candle', mav=(5,10), volume=True, style=s, addplot=add_plots, returnfig=True, figsize=(10,6), title=f"{symbol} ({tf})")
            canvas = FigureCanvasTkAgg(fig, master=self.tab_chart)
            canvas.draw()
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        except Exception as e:
            ttk.Label(self.tab_chart, text=f"绘图错误: {e}").pack(expand=True)

    # --- 常规功能 ---
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

    def toggle_trading(self):
        if not self.running:
            self.save_settings()
            raw = self.entry_symbols.get()
            self.symbols_list = [s.strip().upper() for s in raw.split(',') if s.strip()]
            if not self.symbols_list: return messagebox.showerror("错误", "交易对为空")
            self.running = True
            self.btn_start.config(text="⏹ 停止")
            for item in self.tree.get_children(): self.tree.delete(item)
            for sym in self.symbols_list: self.tree.insert("", "end", iid=sym, values=(sym, "...", "0", "0", "0", "等待", "--"))
            threading.Thread(target=self.multi_symbol_loop, daemon=True).start()
            self.log_sys(f"🚀 启动: {self.symbols_list}")
        else:
            self.running = False
            self.btn_start.config(text="▶ 启动")
            self.log_sys("🛑 停止中...")

    def update_tree_row(self, symbol, price, qty, avg, pl, status, cd):
        if self.tree.exists(symbol):
            self.tree.item(symbol, values=(symbol, f"${price:,.2f}", f"{qty:.4f}", f"${avg:,.2f}", f"${pl:+.2f}", status, cd))

    def multi_symbol_loop(self):
        while self.running:
            for symbol in self.symbols_list:
                if not self.running: break
                success = False
                msg = ""
                try:
                    last = self.last_buy_time.get(symbol, 0)
                    rem = max(0, 300 - (time.time() - last))
                    cd_text = f"{int(rem)}s" if rem > 0 else "就绪"

                    self.root.after(0, lambda s=symbol: self.update_tree_row(s, 0, 0, 0, 0, "数据...", cd_text))
                    
                    price, report = self.backend.get_market_data_detailed(symbol)
                    if price == 0:
                        self.log_sys(f"{symbol} 失败", "ERR")
                        continue

                    pos_qty, _, pos_avg = self.backend.get_position(symbol)
                    
                    if pos_qty > 0 and price > 0:
                        pos_pl = (price - pos_avg) * pos_qty
                    else:
                        pos_pl = 0.0

                    self.root.after(0, lambda s=symbol, p=price, q=pos_qty, a=pos_avg, pl=pos_pl, c=cd_text: 
                        self.update_tree_row(s, p, q, a, pl, "AI...", c))

                    # 注意：这里我们写死模型名，或者你可以加回 entry_model
                    action, reason, thought = self.ai.analyze("deepseek-r1:8b", symbol, price, report, pos_qty, pos_avg)
                    self.log_ai(symbol, thought, action, reason)

                    self.root.after(0, lambda s=symbol, p=price, q=pos_qty, a=pos_avg, pl=pos_pl, act=action, c=cd_text: 
                        self.update_tree_row(s, p, q, a, pl, act, c))

                    if action == "BUY":
                        if pos_qty == 0:
                            success, msg = self.backend.place_order(symbol, "buy", float(self.entry_qty.get()), price)
                            tag = "BUY" if success else "ERR"
                            self.log_sys(f"[{symbol}] 买入: {msg}", tag)
                            if success: 
                                self.last_buy_time[symbol] = time.time()
                                self.record_trade(symbol, 'BUY', price)
                        else:
                            self.log_sys(f"[{symbol}] 持有中，跳过")
                            
                    elif action == "SELL":
                        if pos_qty > 0:
                            if rem > 0:
                                self.log_sys(f"[{symbol}] 冷却保护中", "WARN")
                            else:
                                success, msg = self.backend.close_full_position(symbol)
                                tag = "SELL" if success else "ERR"
                                self.log_sys(f"[{symbol}] 卖出: {msg}", tag)
                                if success:
                                    self.record_trade(symbol, 'SELL', price)
                        else:
                            self.log_sys(f"[{symbol}] 无持仓")

                    for _ in range(2): 
                        if not self.running: break
                        time.sleep(1)

                except Exception as e:
                    self.log_sys(f"{symbol} 错误: {e}", "ERR")
            
            if self.running:
                self.log_sys("💤 休息 10 秒...")
                time.sleep(10)

if __name__ == "__main__":
    root = tk.Tk()
    app = QuantGUI(root)
    root.mainloop()