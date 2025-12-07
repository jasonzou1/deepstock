import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import time
import datetime
import json
import os
import pandas as pd
import mplfinance as mpf


from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk 

import config
# ...

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
        self.current_chart_symbol = None

        self.last_data_len = 0
        
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

    # 替换原来的 record_trade 函数
    def record_trade(self, symbol, action, price):
        if symbol not in self.trade_markers: self.trade_markers[symbol] = []
        
        # 🔥 关键修改：强制使用 UTC 时间保存
        # 这样才能和 Alpaca 的 K 线数据完美对齐
        utc_now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        self.trade_markers[symbol].append({
            "time": utc_now,
            "action": action,
            "price": price
        })
        try:
            with open(TRADES_FILE, "w") as f: json.dump(self.trade_markers, f)
        except Exception as e:
            print(f"Save Trade Error: {e}")

    # 替换原来的 plot_chart 函数
    def plot_chart(self, symbol):
        for widget in self.tab_chart.winfo_children(): widget.destroy()
        
        tf = self.combo_tf.get()
        df = self.backend.get_chart_data(symbol, tf)
        if df is None or df.empty:
            ttk.Label(self.tab_chart, text="无法获取K线数据").pack(expand=True)
            return

        # 确保 df 的索引是 UTC 时间 (防止时区混乱)
        if df.index.tz is None:
            df.index = df.index.tz_localize('UTC')
        else:
            df.index = df.index.tz_convert('UTC')

        add_plots = []
        
        # --- 绘制买卖标记 ---
        if symbol in self.trade_markers:
            history = self.trade_markers[symbol]
            buys = [float('nan')] * len(df)
            sells = [float('nan')] * len(df)
            
            for trade in history:
                try:
                    # 解析保存的时间
                    t_time = pd.to_datetime(trade['time'])
                    
                    # 如果保存的时间没有时区，强制设为 UTC
                    if t_time.tz is None:
                        t_time = t_time.tz_localize('UTC')
                    else:
                        t_time = t_time.tz_convert('UTC')
                    
                    # 🔥 智能过滤：只绘制在当前 K 线时间范围内的点
                    # 以前的代码因为试图画超出范围的点而出错，导致整个图没标记
                    if t_time < df.index[0] or t_time > df.index[-1]:
                        continue
                        
                    # 找到最近的时间点
                    idx = df.index.get_indexer([t_time], method='nearest')[0]
                    
                    # 设置标记位置 (Buy在最低价下方，Sell在最高价上方)
                    if trade['action'] == 'BUY': 
                        buys[idx] = df.iloc[idx]['low'] * 0.99 
                    elif trade['action'] == 'SELL': 
                        sells[idx] = df.iloc[idx]['high'] * 1.01
                except Exception as e: 
                    print(f"Marker logic error: {e}")
            
            # 添加到图表中
            # 只有当数组里真的有数据时才添加，防止空数组报错
            if not pd.isna(buys).all():
                add_plots.append(mpf.make_addplot(buys, type='scatter', markersize=100, marker='^', color='g'))
            if not pd.isna(sells).all():
                add_plots.append(mpf.make_addplot(sells, type='scatter', markersize=100, marker='v', color='r'))

        # --- 绘制持仓成本线 ---
        qty, pl, avg = self.backend.get_position(symbol)
        hlines_dict = dict()
        title_extra = ""
        if qty > 0:
            hlines_dict = dict(hlines=[avg], colors=['blue'], linestyle='-.')
            title_extra = f" | Holding {qty} @ ${avg:.2f}"

        try:
            s = mpf.make_mpf_style(marketcolors=mpf.make_marketcolors(up='green', down='red', inherit=True))
            fig, ax = mpf.plot(
                df, 
                type='candle', 
                mav=(5,10), 
                volume=True, 
                style=s, 
                addplot=add_plots, 
                hlines=hlines_dict,
                returnfig=True, 
                figsize=(10,6), 
                title=f"{symbol} ({tf}){title_extra}"
            )
            canvas = FigureCanvasTkAgg(fig, master=self.tab_chart)
            canvas.draw()
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        except Exception as e:
            ttk.Label(self.tab_chart, text=f"绘图错误: {e}").pack(expand=True)

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
        # 0. 视图记忆
        saved_xlim = None
        saved_ylim = None
        was_at_edge = False
        
        if symbol == self.current_chart_symbol and hasattr(self, 'ax_main'):
            try:
                saved_xlim = self.ax_main.get_xlim()
                saved_ylim = self.ax_main.get_ylim()
                if hasattr(self, 'last_data_len') and (self.last_data_len - saved_xlim[1] < 5):
                    was_at_edge = True
            except: pass

        self.current_chart_symbol = symbol

        # 1. 清理
        for widget in self.tab_chart.winfo_children(): widget.destroy()
        
        # 2. 获取数据
        tf_raw = self.combo_tf.get() 
        df = self.backend.get_chart_data(symbol, tf_raw)
        live_price = self.backend.get_latest_price_fast(symbol)

        if df is None or df.empty:
            ttk.Label(self.tab_chart, text="正在拉取最新数据...").pack(expand=True)
            return

        # ==========================================
        # 🔥 核心修复 1：统一转换为本地时间，并剥离时区信息 (tz-naive)
        # ==========================================
        # 1. 先确保 df 是 UTC
        if df.index.tz is None: df.index = df.index.tz_localize('UTC')
        else: df.index = df.index.tz_convert('UTC')
        
        # 2. 转为本地时间
        my_timezone = datetime.datetime.now().astimezone().tzinfo
        df.index = df.index.tz_convert(my_timezone)
        
        # 3. 🔥 剥离时区！变成纯粹的 "2023-12-07 16:22:00"
        # 这样后续比对时，绝对不会因为时区格式不同而失败
        df.index = df.index.tz_localize(None)

        # 4. 计算对齐频率
        freq_map = {"1Min": "1min", "5Min": "5min", "15Min": "15min", "1Hour": "1h"}
        pd_freq = freq_map.get(tf_raw, "1min")

        # 5. 加载交易记录
        self.trade_markers = self.load_trade_history()
        
        # 6. 绘图风格
        mc = mpf.make_marketcolors(up='#2ebd85', down='#f6465d', edge='inherit', wick='inherit', volume='in')
        s = mpf.make_mpf_style(base_mpf_style='nightclouds', marketcolors=mc)

        # 7. 辅助线
        hlines_list = []
        hlines_colors = []
        qty, pl, avg = self.backend.get_position(symbol)
        if qty > 0:
            hlines_list.append(avg)
            hlines_colors.append('cyan')
        if live_price > 0:
            hlines_list.append(live_price)
            hlines_colors.append('white')

        plot_kwargs = dict(
            type='candle', mav=(5, 20), volume=True, style=s, returnfig=True,
            figsize=(12, 8), tight_layout=True, ylabel='Price ($)',
            datetime_format='%m-%d %H:%M', xrotation=0
        )
        if hlines_list:
            plot_kwargs['hlines'] = dict(hlines=hlines_list, colors=hlines_colors, linestyle='--', linewidths=1.0)

        try:
            # 8. 生成图表
            self.fig, self.axlist = mpf.plot(df, **plot_kwargs)
            self.ax_main = self.axlist[0]
            
            # ==========================================
            # 🔥 核心修复 2：交易记录也剥离时区，进行纯时间比对
            # ==========================================
            if symbol in self.trade_markers:
                history = self.trade_markers[symbol]
                
                for trade in history:
                    try:
                        # A. 解析时间并转为本地
                        t_time = pd.to_datetime(trade['time'])
                        if t_time.tz is None: t_time = t_time.tz_localize('UTC')
                        else: t_time = t_time.tz_convert('UTC')
                        
                        t_time_local = t_time.tz_convert(my_timezone)
                        
                        # B. 🔥 剥离时区 (tz_localize(None))
                        t_naive = t_time_local.tz_localize(None)

                        # C. 地板除对齐 (16:22:52 -> 16:22:00)
                        t_floored = t_naive.floor(pd_freq)

                        # D. 核心判断：纯时间比对
                        if t_floored in df.index:
                            idx_label = t_floored
                            
                            # 获取坐标
                            candle_low = df.loc[idx_label]['low']
                            candle_high = df.loc[idx_label]['high']

                            # E. 绘制杆子
                            if trade['action'] == 'BUY':
                                self.ax_main.annotate('B', xy=(idx_label, candle_low), xytext=(0, -20), 
                                    textcoords='offset points', color='white', fontweight='bold', ha='center',
                                    bbox=dict(boxstyle='round,pad=0.2', fc='#00b300', alpha=0.8),
                                    arrowprops=dict(arrowstyle='->', color='#00b300', lw=1.5))
                            elif trade['action'] == 'SELL':
                                self.ax_main.annotate('S', xy=(idx_label, candle_high), xytext=(0, 20), 
                                    textcoords='offset points', color='white', fontweight='bold', ha='center',
                                    bbox=dict(boxstyle='round,pad=0.2', fc='#ff3333', alpha=0.8),
                                    arrowprops=dict(arrowstyle='->', color='#ff3333', lw=1.5))
                    except Exception as e:
                        # print(f"Marker Error: {e}")
                        pass

            # --- HUD ---
            last_bar = df.iloc[-1]
            # 因为剥离了时区，这里直接格式化
            t_str = last_bar.name.strftime('%Y-%m-%d %H:%M')
            initial_text = (
                f"{symbol} [{tf_raw}] {t_str}\n"
                f"O: {last_bar['open']:.2f}  H: {last_bar['high']:.2f}\n"
                f"L: {last_bar['low']:.2f}  C: {last_bar['close']:.2f}\n"
                f"Vol: {float(last_bar['volume']):.4f}"
            )
            self.text_artist = self.ax_main.text(
                0.02, 0.96, initial_text, 
                transform=self.ax_main.transAxes, fontsize=10, color='white', verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='black', alpha=0.7)
            )
            
            # 交互事件
            self.current_df = df
            self.fig.canvas.mpl_connect('scroll_event', self.on_scroll)
            self.fig.canvas.mpl_connect('button_press_event', self.on_press)
            self.fig.canvas.mpl_connect('button_release_event', self.on_release)
            self.fig.canvas.mpl_connect('motion_notify_event', self.on_drag_and_hover)
            self.is_dragging = False
            self.last_mouse_x = None

            # 8. 显示
            canvas = FigureCanvasTkAgg(self.fig, master=self.tab_chart)
            canvas.draw()
            canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

            # 恢复视角
            if saved_xlim:
                current_len = len(df)
                view_width = saved_xlim[1] - saved_xlim[0]
                if was_at_edge:
                    self.ax_main.set_xlim(current_len - view_width, current_len)
                else:
                    self.ax_main.set_xlim(saved_xlim)
            
            self.last_data_len = len(df)
            
        except Exception as e:
            print(f"Plot Error: {e}")
            ttk.Label(self.tab_chart, text=f"绘图出错: {e}").pack(expand=True)

    # ================= 交互事件处理函数 =================

    def on_scroll(self, event):
        """鼠标滚轮缩放"""
        if event.inaxes != self.ax_main: return
        x_min, x_max = self.ax_main.get_xlim()
        scale_factor = 0.8 if event.button == 'up' else 1.2
        range_width = x_max - x_min
        
        # 居中缩放计算
        mouse_rel = (event.xdata - x_min) / range_width
        new_range = range_width * scale_factor
        
        # 限制缩放极限
        if new_range < 10: new_range = 10
        if new_range > len(self.current_df): new_range = len(self.current_df)
        
        new_min = event.xdata - mouse_rel * new_range
        new_max = new_min + new_range
        
        # 边界检查
        if new_max > len(self.current_df):
            new_max = len(self.current_df)
            new_min = new_max - new_range
        if new_min < 0:
            new_min = 0
            new_max = new_range
            
        self.ax_main.set_xlim(new_min, new_max)
        self.fig.canvas.draw_idle()

    def on_press(self, event):
        if event.inaxes == self.ax_main and event.button == 1:
            self.is_dragging = True
            self.last_mouse_x = event.xdata

    def on_release(self, event):
        self.is_dragging = False
        self.last_mouse_x = None

    def on_drag_and_hover(self, event):
        if not hasattr(self, 'current_df') or self.current_df is None: return
        if event.inaxes != self.ax_main: return

        # 1. 拖拽平移
        if self.is_dragging and self.last_mouse_x is not None and event.xdata is not None:
            dx = event.xdata - self.last_mouse_x
            x_min, x_max = self.ax_main.get_xlim()
            new_min, new_max = x_min - dx, x_max - dx
            
            # 边界检查
            if new_max > len(self.current_df):
                diff = new_max - len(self.current_df)
                new_max -= diff
                new_min -= diff
            if new_min < 0:
                diff = 0 - new_min
                new_min += diff
                new_max += diff
                
            self.ax_main.set_xlim(new_min, new_max)
            self.fig.canvas.draw_idle()
            return

        # 2. 悬停 HUD 信息
        try:
            x_idx = int(round(event.xdata))
            if 0 <= x_idx < len(self.current_df):
                bar = self.current_df.iloc[x_idx]
                info = (f"{self.current_chart_symbol} {bar.name.strftime('%H:%M')}\n"
                        f"O:{bar['open']:.2f} H:{bar['high']:.2f}\n"
                        f"L:{bar['low']:.2f} C:{bar['close']:.2f}\n"
                        f"V:{float(bar['volume']):.4f}")
                self.text_artist.set_text(info)
                self.fig.canvas.draw_idle()
        except: pass

    def on_mouse_move(self, event):
        """鼠标移动时更新左上角数据"""
        if not hasattr(self, 'current_df') or self.current_df is None: return
        
        # 检查鼠标是否在K线图区域内
        if event.inaxes == self.axlist[0]:
            try:
                # 获取鼠标所在的 K 线索引 (X轴坐标)
                x_index = int(round(event.xdata))
                
                # 边界检查
                if 0 <= x_index < len(self.current_df):
                    # 获取该根 K 线的数据
                    bar = self.current_df.iloc[x_index]
                    t_str = bar.name.strftime('%Y-%m-%d %H:%M')
                    
                    # 更新文字内容
                    info_text = (
                        f"{self.current_chart_symbol}  {t_str}\n"
                        f"O: {bar['open']:.2f}  H: {bar['high']:.2f}\n"
                        f"L: {bar['low']:.2f}  C: {bar['close']:.2f}\n"
                        f"Vol: {float(bar['volume']):.4f}"  # 👈 修改这里：同样改为 float 保留小数
                    )                   
                    self.text_artist.set_text(info_text)
                    
                    # 快速重绘 (只更新变动部分)
                    self.fig.canvas.draw_idle()
            except: pass
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
        """【线程1】更新价格 + 自动刷新图表"""
        tick_count = 0
        while self.running:
            # 1. 更新价格 (保持原有逻辑)
            for symbol in self.symbols_list:
                if not self.running: break
                try:
                    price = self.backend.get_latest_price_fast(symbol)
                    if price > 0:
                        cache = self.market_cache[symbol]
                        cache['price'] = price
                        if cache['qty'] > 0:
                            cache['pl'] = (price - cache['avg']) * cache['qty']
                        self.root.after(0, lambda s=symbol: self.update_ui_safe(s))
                except: pass
            
            # 2. 🔥 自动刷新图表逻辑 (每 5 秒刷新一次)
            # 检查当前选中的是不是 "K线分析" 标签页
            try:
                current_tab = self.notebook.index(self.notebook.select())
                if current_tab == 1 and self.current_chart_symbol: # 1 是图表页的索引
                    tick_count += 1
                    if tick_count >= 5: # 每循环 5 次 (约5秒) 刷新一次图表
                        self.root.after(0, lambda: self.plot_chart(self.current_chart_symbol))
                        tick_count = 0
            except:
                pass

            time.sleep(1.0)

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

                    # 1. 获取详细数据
                    price, report = self.backend.get_analysis_data(symbol)
                    qty, pl, avg = self.backend.get_position(symbol)
                    
                    # 更新缓存
                    self.market_cache[symbol].update({'qty': qty, 'avg': avg})

                    # 2. 调用 AI (获取 动作 + 比例)
                    # 注意：现在 analyze 返回 4 个值
                    action, pct, reason, thought = self.ai.analyze("deepseek-r1:8b", symbol, price, report, qty, avg)
                    
                    # 格式化一下 AI 的决定显示
                    decision_str = f"{action} {pct}%" if action != "HOLD" else "HOLD"
                    self.log_ai(symbol, thought, decision_str, reason)
                    self.market_cache[symbol]['status'] = action 
                    self.root.after(0, lambda s=symbol: self.update_ui_safe(s))

                    # 3. 执行复杂交易逻辑
                    base_usd = float(self.entry_qty.get()) # 获取设置里的单笔金额

                    if action == "BUY":
                        # 买入逻辑：按 base_usd 的百分比买入
                        # 例如：Base=1000, AI说买50%，那就是加仓500刀
                        if pct > 0:
                            buy_usd = base_usd * (pct / 100.0)
                            
                            # 最小金额保护 ($10)
                            if buy_usd < 10: 
                                self.log_sys(f"[{symbol}] 买入金额 ${buy_usd:.2f} 太小，忽略")
                            else:
                                success, msg = self.backend.place_order(symbol, "buy", buy_usd, price)
                                tag = "BUY" if success else "ERR"
                                self.log_sys(f"[{symbol}] 买入 ${buy_usd:.0f} ({pct}%): {msg}", tag)
                                if success: 
                                    self.last_buy_time[symbol] = time.time()
                                    self.record_trade(symbol, 'BUY', price)

                    elif action == "SELL":
                        if qty > 0 and pct > 0:
                            # 卖出逻辑：按当前持仓数量的百分比卖出
                            # 例如：持仓 1.0 ETH，AI说卖 50%，那就是卖 0.5 ETH
                            
                            # 如果是 100%，直接清仓（更稳健）
                            if pct >= 99:
                                success, msg = self.backend.close_full_position(symbol)
                                sell_qty = qty
                            else:
                                # 计算卖出数量
                                sell_qty = qty * (pct / 100.0)
                                # 只有当卖出价值大于 $10 时才执行 (防止碎股报错)
                                if (sell_qty * price) < 10:
                                    self.log_sys(f"[{symbol}] 卖出价值太低，忽略")
                                    success = False
                                else:
                                    success, msg = self.backend.submit_qty_order(symbol, "sell", sell_qty)
                            
                            tag = "SELL" if success else "ERR"
                            if success:
                                self.log_sys(f"[{symbol}] 卖出 {sell_qty:.4f} ({pct}%): {msg}", tag)
                                self.record_trade(symbol, 'SELL', price)
                                # 如果清仓了，重置冷却时间 (可选)
                                if pct >= 99: 
                                    self.market_cache[symbol]['qty'] = 0
                        else:
                            if qty == 0: self.log_sys(f"[{symbol}] 无持仓，无法卖出")

                except Exception as e:
                    self.log_sys(f"Strategy Error {symbol}: {e}", "ERR")
            
            self.log_sys("⏳ 周期结束，等待 60 秒...")
            for _ in range(60):
                if not self.running: break
                time.sleep(1)

if __name__ == "__main__":
    root = tk.Tk()
    app = QuantGUI(root)
    root.mainloop()



