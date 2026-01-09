import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import random
import os
import glob
import copy
import datetime


# ==========================================
# 1. 自定义流式布局容器
# ==========================================
class FlowPanel(tk.Frame):
    def __init__(self, container, *args, **kwargs):
        super().__init__(container, *args, **kwargs)
        self.bind("<Configure>", self._on_configure)
        self._widgets = []

    def add_widget(self, widget, **pack_kwargs):
        self._widgets.append((widget, pack_kwargs))

    def _on_configure(self, event=None):
        if event:
            width = event.width
        else:
            width = self.winfo_width()

        if width < 100: return

        available_width = width - 10
        current_x = 0
        current_y = 0
        row_height = 0

        for widget, kwargs in self._widgets:
            padx = kwargs.get('padx', 2)
            pady = kwargs.get('pady', 2)
            w = widget.winfo_reqwidth() + padx * 2
            h = widget.winfo_reqheight() + pady * 2

            if current_x > 0 and (current_x + w > available_width):
                current_x = 0
                current_y += row_height
                row_height = 0

            widget.place(x=current_x + padx, y=current_y + pady, width=w - padx * 2, height=h - pady * 2)
            current_x += w
            row_height = max(row_height, h)

        needed_height = current_y + row_height
        if needed_height != self.winfo_reqheight():
            self.configure(height=needed_height + 5)


# ==========================================
# 2. 可滚动画布容器
# ==========================================
class ScrollableFrame(tk.Frame):
    def __init__(self, container, *args, **kwargs):
        super().__init__(container, *args, **kwargs)
        self.canvas = tk.Canvas(self, bg="#f0f2f5", highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_content = tk.Frame(self.canvas, bg="#f0f2f5")
        self.scrollable_content.bind("<Configure>",
                                     lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_content, anchor="nw")
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.scrollable_content.bind("<Enter>", self._bind_mouse)
        self.scrollable_content.bind("<Leave>", self._unbind_mouse)

    def _on_canvas_configure(self, event):
        self.canvas.itemconfig(self.canvas_window, width=event.width)

    def _bind_mouse(self, event):
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>", self._on_mousewheel)
        self.canvas.bind_all("<Button-5>", self._on_mousewheel)

    def _unbind_mouse(self, event):
        self.canvas.unbind_all("<MouseWheel>")
        self.canvas.unbind_all("<Button-4>")
        self.canvas.unbind_all("<Button-5>")

    def _on_mousewheel(self, event):
        if event.num == 5 or event.delta == -120:
            self.canvas.yview_scroll(1, "units")
        elif event.num == 4 or event.delta == 120:
            self.canvas.yview_scroll(-1, "units")


# ==========================================
# 3. 主程序逻辑
# ==========================================
class PromptPanel(tk.Frame):
    def __init__(self, parent, config):
        super().__init__(parent, bg="#f0f2f5")
        self.config = config
        self.pack(fill="both", expand=True)
        self.master_window = self.winfo_toplevel()

        self.style = ttk.Style()
        self.style.configure("TScale", background="white")
        self.style.layout("Locked.Horizontal.TScale", self.style.layout("Horizontal.TScale"))
        self.style.configure("Locked.Horizontal.TScale", background="#ffeaa7", troughcolor="#fab1a0")
        self.style.map("Locked.Horizontal.TScale", background=[('disabled', '#ffeaa7')],
                       troughcolor=[('disabled', '#fab1a0')])
        self.style.configure("Disabled.Horizontal.TScale", background="#dfe6e9", troughcolor="#b2bec3")

        # === [核心修复] 智能路径判断逻辑 ===
        # 1. 获取当前文件所在目录: src/gui
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # 2. 推导项目根目录: src/gui -> src -> root
        project_root = os.path.dirname(os.path.dirname(current_dir))

        # 3. 定义默认绝对路径
        default_data = os.path.join(project_root, "data")
        default_presets = os.path.join(project_root, "presets")

        # 4. 从配置读取，如果为空字符串或None，则使用默认绝对路径
        raw_data_path = self.config.get("prompt_data_path")
        raw_preset_path = self.config.get("prompt_preset_path")

        self.data_folder = raw_data_path if (raw_data_path and str(raw_data_path).strip()) else default_data
        self.preset_folder = raw_preset_path if (raw_preset_path and str(raw_preset_path).strip()) else default_presets

        print(f"[PromptPanel] Data Path: {self.data_folder}")  # 控制台调试信息

        self.ensure_folders()

        self.data = self.load_all_data()
        self.category_vars = {}
        self.file_enabled_vars = {}
        self.file_btn_refs = {}
        self.category_ui_refs = {}

        self.prob_lock_vars = {}
        self.prompt_lock_vars = {}
        self.ui_frames = {}
        self.content_frames = {}
        self.last_results = {}
        self.undo_stack = []
        self.max_undo_steps = 20
        self.history_data_list = []
        self.display_mode = tk.StringVar(value="mixed")
        self.current_cols = 0
        self.ITEM_WIDTH = 210
        self.mode_buttons = {}

        self.setup_output_panel()
        self.setup_control_panel()
        self.setup_scrollable_frame()
        self.create_dynamic_widgets()

        self.update_display_mode_btn_color()

        self.bind("<Control-z>", self.perform_undo)
        self.bind("<Command-z>", self.perform_undo)
        # self.focus_set()

    def ensure_folders(self):
        for folder in [self.data_folder, self.preset_folder]:
            if not os.path.exists(folder):
                try:
                    os.makedirs(folder)
                except:
                    pass

    def load_all_data(self):
        combined_data = {}
        # 增加健全性检查
        if not os.path.exists(self.data_folder):
            print(f"[Error] Data folder not found: {self.data_folder}")
            return {}

        json_files = glob.glob(os.path.join(self.data_folder, "*.json"))
        if not json_files:
            print(f"[Warning] No json files found in: {self.data_folder}")

        for file_path in json_files:
            try:
                name = os.path.basename(file_path)
                cat = os.path.splitext(name)[0]
                with open(file_path, 'r', encoding='utf-8') as f:
                    combined_data[cat] = json.load(f)
            except Exception as e:
                print(f"[Error] Failed to load {file_path}: {e}")
                pass
        return combined_data

    def setup_output_panel(self):
        output_outer = tk.Frame(self, pady=5, padx=10, height=180)
        output_outer.pack(side=tk.TOP, fill=tk.X)
        output_outer.pack_propagate(False)

        self.notebook = ttk.Notebook(output_outer)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.tab_preview = tk.Frame(self.notebook, bg="#f0f2f5")
        self.notebook.add(self.tab_preview, text=" 🏷️ 标签生成区 ")
        self.tags_container = ScrollableFrame(self.tab_preview, bg="#f0f2f5")
        self.tags_container.pack(fill=tk.BOTH, expand=True)

        self.tab_history = tk.Frame(self.notebook, bg="#f0f2f5")
        self.notebook.add(self.tab_history, text=" 📜 历史记录 ")
        self.history_text = tk.Text(self.tab_history, height=8, font=("Arial", 9), cursor="arrow")
        self.history_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.history_text.tag_config("hover", background="#dff9fb")
        self.history_text.tag_config("dim", foreground="#b2bec3")
        self.history_text.tag_config("sys_msg", foreground="#636e72", font=("Arial", 9, "italic"))

    def setup_control_panel(self):
        self.control_panel = FlowPanel(self, bg="#dfe6e9", height=80)
        self.control_panel.pack(side=tk.TOP, fill=tk.X, padx=0, pady=0)

        def add_btn(text, cmd, bg="#f1f2f6", fg="black", width=None):
            btn = tk.Button(self.control_panel, text=text, command=cmd, bg=bg, fg=fg, relief=tk.RAISED,
                            font=("微软雅黑", 9))
            if width: btn.config(width=width)
            self.control_panel.add_widget(btn, padx=3, pady=3)
            return btn

        self.mode_buttons['mixed'] = add_btn("中/英", lambda: self.switch_mode("mixed"), width=6)
        self.mode_buttons['cn'] = add_btn("中", lambda: self.switch_mode("cn"), width=3)
        self.mode_buttons['en'] = add_btn("英", lambda: self.switch_mode("en"), width=3)

        add_btn("↩ 撤回", lambda: self.perform_undo(None), bg="#fdcb6e", width=6)
        add_btn("✨ 单抽", lambda: self.generate_prompts(False), bg="#6c5ce7", fg="white", width=8)

        lbl_batch = tk.Label(self.control_panel, text="数量:", bg="#dfe6e9", font=("微软雅黑", 9))
        self.control_panel.add_widget(lbl_batch, padx=2, pady=5)
        self.batch_count = tk.Spinbox(self.control_panel, from_=1, to=50, width=3, font=("Arial", 9))
        self.batch_count.delete(0, "end")
        self.batch_count.insert(0, 5)
        self.control_panel.add_widget(self.batch_count, padx=2, pady=5)

        add_btn("🚀 批量生成", self.run_batch_generation, bg="#00b894", fg="white", width=12)

        add_btn("📂 读取", self.load_preset, width=6)
        add_btn("💾 保存", self.save_preset, width=6)
        add_btn("📥 导出", self.export_history, width=6)
        add_btn("复制WebUI", self.copy_positive, width=9)
        add_btn("清空", self.clear_all, width=5)
        add_btn("🔓 全解锁", self.unlock_all, bg="#ff7675", fg="white", width=7)

    def setup_scrollable_frame(self):
        outer_frame = tk.LabelFrame(self, text="🎲 概率配置", font=("微软雅黑", 9, "bold"), padx=2, pady=2)
        outer_frame.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.file_tags_frame = FlowPanel(outer_frame, bg="#f7f9fa", height=40)
        self.file_tags_frame.pack(side=tk.TOP, fill=tk.X, padx=2, pady=(0, 5))

        tools_header = tk.Frame(outer_frame, bg="#f0f2f5")
        tools_header.pack(side=tk.TOP, fill=tk.X, padx=2, pady=0)
        tk.Button(tools_header, text="📁 折叠全部", font=("Arial", 8), command=lambda: self.toggle_all_sections(False),
                  bg="white").pack(side=tk.RIGHT, padx=2)
        tk.Button(tools_header, text="📂 展开全部", font=("Arial", 8), command=lambda: self.toggle_all_sections(True),
                  bg="white").pack(side=tk.RIGHT, padx=2)

        self.canvas = tk.Canvas(outer_frame)
        scrollbar = ttk.Scrollbar(outer_frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")

        self.scrollable_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.bind("<Enter>", self._bind_mouse)
        self.canvas.bind("<Leave>", self._unbind_mouse)

    def _on_frame_configure(self, event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfig(self.canvas_window, width=event.width)
        self.rearrange_layout(event.width)

    def _bind_mouse(self, event):
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_mouse(self, event):
        self.canvas.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(-1 * (event.delta // 120), "units")

    def rearrange_layout(self, width):
        available_width = width - 40
        new_cols = max(1, available_width // self.ITEM_WIDTH)
        self.current_cols = new_cols

        for big, frames_map in self.ui_frames.items():
            if big not in self.category_ui_refs or not self.category_ui_refs[big]['content_frame']:
                continue

            content_frame = self.category_ui_refs[big]['content_frame']
            for i in range(20):
                content_frame.grid_columnconfigure(i, weight=0)
            for i in range(new_cols):
                content_frame.grid_columnconfigure(i, weight=1)

            row, col = 0, 0
            for small, frame in frames_map.items():
                frame.grid(row=row, column=col, sticky="ew", pady=2, padx=4)
                col += 1
                if col >= new_cols:
                    col = 0
                    row += 1

    def create_dynamic_widgets(self):
        row_idx = 0

        if not self.data:
            # [修改] 错误提示显示具体的绝对路径，方便用户排查
            msg = f"未找到数据文件\n请检查: {self.data_folder}\n或者去[全局设置]手动指定Data目录"
            lbl = tk.Label(self.scrollable_frame, text=msg, fg="red", font=("微软雅黑", 10), justify=tk.LEFT)
            lbl.pack(pady=20)
            return

        for big_cat in sorted(self.data.keys()):
            self.file_enabled_vars[big_cat] = True
            btn = tk.Button(self.file_tags_frame, text=big_cat, font=("微软雅黑", 8), relief=tk.RAISED, width=10)

            def toggle_file(b=btn, cat=big_cat):
                current = self.file_enabled_vars[cat]
                new_state = not current
                self.file_enabled_vars[cat] = new_state
                self.update_file_btn_style(b, new_state)
                self.update_category_visuals(cat, new_state)

            btn.config(command=toggle_file)
            self.file_tags_frame.add_widget(btn, padx=2, pady=2)
            self.file_btn_refs[big_cat] = btn
            self.update_file_btn_style(btn, True)

        for big_cat in sorted(self.data.keys()):
            small_cats = self.data[big_cat]
            if not isinstance(small_cats, dict): continue

            self.category_ui_refs[big_cat] = {
                'outer_container': None,
                'header': None,
                'header_label': None,
                'content_frame': None,
                'sliders': []
            }

            outer_container = tk.Frame(self.scrollable_frame, relief=tk.RIDGE, bd=1, bg="#f7f9fa")
            outer_container.grid(row=row_idx, column=0, sticky="ew", padx=5, pady=5)
            self.category_ui_refs[big_cat]['outer_container'] = outer_container
            row_idx += 1

            header = tk.Frame(outer_container, bg="#ecf0f1", height=25)
            header.pack(side=tk.TOP, fill=tk.X)
            self.category_ui_refs[big_cat]['header'] = header

            collapse_btn = tk.Button(header, text="▼", width=2, relief=tk.FLAT, bg="#ecf0f1", font=("Arial", 8))
            collapse_btn.pack(side=tk.LEFT)

            header_lbl = tk.Label(header, text=f" {big_cat}", font=("微软雅黑", 9, "bold"), bg="#ecf0f1")
            header_lbl.pack(side=tk.LEFT)
            self.category_ui_refs[big_cat]['header_label'] = header_lbl

            big_lock_btn = tk.Button(header, text="🔓", width=2, bg="#ecf0f1", relief=tk.FLAT, font=("Arial", 9))
            big_lock_btn.pack(side=tk.LEFT, padx=10)

            content = tk.Frame(outer_container, bg="#ffffff", pady=5)
            content.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
            self.category_ui_refs[big_cat]['content_frame'] = content

            def toggle_section(c=content, b=collapse_btn):
                if c.winfo_viewable():
                    c.pack_forget();
                    b.config(text="▶")
                else:
                    c.pack(side=tk.TOP, fill=tk.BOTH, expand=True);
                    b.config(text="▼")

            collapse_btn.config(command=toggle_section)
            self.content_frames[big_cat] = (content, collapse_btn)

            self.category_vars[big_cat] = {}
            self.prob_lock_vars[big_cat] = {}
            self.prompt_lock_vars[big_cat] = {}
            self.ui_frames[big_cat] = {}
            sub_lock_triggers = []

            for small_cat, items in small_cats.items():
                frame = tk.Frame(content, bg="white")
                self.ui_frames[big_cat][small_cat] = frame
                if 'sub_frames' not in self.category_ui_refs[big_cat]:
                    self.category_ui_refs[big_cat]['sub_frames'] = []
                self.category_ui_refs[big_cat]['sub_frames'].append(frame)

                lbl_name = tk.Label(frame, text=f"{small_cat}:", width=6, anchor="w", bg="white", font=("微软雅黑", 8))
                lbl_name.pack(side=tk.LEFT)

                prob_var = tk.IntVar(value=50)
                self.category_vars[big_cat][small_cat] = prob_var
                scale = ttk.Scale(frame, from_=0, to=100, orient=tk.HORIZONTAL, variable=prob_var, length=90,
                                  style="TScale")
                scale.pack(side=tk.LEFT, padx=2)
                self.category_ui_refs[big_cat]['sliders'].append(scale)

                lbl_val = tk.Label(frame, text="50%", width=3, bg="white", font=("Arial", 8))
                lbl_val.pack(side=tk.LEFT)

                def update_lbl(val, l=lbl_val, v=prob_var):
                    i = int(float(val));
                    l.config(text=f"{i}%");
                    v.set(i)

                scale.configure(command=update_lbl)

                p_lock_var = tk.BooleanVar(value=False)
                self.prob_lock_vars[big_cat][small_cat] = p_lock_var

                def toggle_prob_lock(var=p_lock_var, btn=None, s=scale, target=None):
                    new_state = target if target is not None else not var.get()
                    var.set(new_state)
                    if new_state:
                        btn.config(text="🔒", bg="#ffeaa7")
                        s.configure(style="Locked.Horizontal.TScale")
                        s.state(['disabled'])
                    else:
                        btn.config(text="🔓", bg="#f1f2f6")
                        if not self.file_enabled_vars[big_cat]:
                            s.configure(style="Disabled.Horizontal.TScale")
                            s.state(['disabled'])
                        else:
                            s.configure(style="TScale")
                            s.state(['!disabled'])

                btn_p_lock = tk.Button(frame, text="🔓", width=2, bg="#f1f2f6", relief=tk.FLAT, font=("Arial", 8))
                btn_p_lock.config(command=lambda b=btn_p_lock, v=p_lock_var, s=scale: toggle_prob_lock(v, b, s))
                btn_p_lock.pack(side=tk.LEFT, padx=(2, 0))

                sub_lock_triggers.append(lambda t, b=btn_p_lock, v=p_lock_var, s=scale: toggle_prob_lock(v, b, s, t))

                pt_lock_var = tk.BooleanVar(value=False)
                self.prompt_lock_vars[big_cat][small_cat] = pt_lock_var

                def toggle_prompt_lock(var=pt_lock_var, btn=None):
                    new = not var.get()
                    var.set(new)
                    if new:
                        btn.config(text="📌", bg="#ff7675", fg="white")
                    else:
                        btn.config(text="📌", bg="#f1f2f6", fg="#b2bec3")

                btn_pt_lock = tk.Button(frame, text="📌", width=2, bg="#f1f2f6", fg="#b2bec3", relief=tk.FLAT,
                                        font=("Arial", 8))
                btn_pt_lock.config(command=lambda b=btn_pt_lock, v=pt_lock_var: toggle_prompt_lock(v, b))
                btn_pt_lock.pack(side=tk.LEFT, padx=(2, 0))

            def toggle_big(btn=big_lock_btn, trigs=sub_lock_triggers):
                is_locking = (btn['text'] == "🔓")
                btn.config(text="🔒" if is_locking else "🔓", bg="#ffeaa7" if is_locking else "#ecf0f1")
                for t in trigs: t(is_locking)

            big_lock_btn.config(command=toggle_big, text="🔓")

        self.scrollable_frame.grid_columnconfigure(0, weight=1)

    def update_file_btn_style(self, btn, enabled):
        if enabled:
            btn.config(bg="#a29bfe", fg="white", relief=tk.RAISED)
        else:
            btn.config(bg="#dfe6e9", fg="#b2bec3", relief=tk.SUNKEN)

    def update_category_visuals(self, big_cat, enabled):
        refs = self.category_ui_refs.get(big_cat)
        if not refs: return
        if enabled:
            bg_header, bg_content, bg_frame, fg_text, scale_style, scale_state = "#ecf0f1", "#ffffff", "white", "black", "TScale", "!disabled"
        else:
            bg_header, bg_content, bg_frame, fg_text, scale_style, scale_state = "#b2bec3", "#dfe6e9", "#dfe6e9", "#636e72", "Disabled.Horizontal.TScale", "disabled"

        refs['header'].config(bg=bg_header)
        refs['header_label'].config(bg=bg_header, fg=fg_text)
        refs['content_frame'].config(bg=bg_content)
        if 'sub_frames' in refs:
            for frame in refs['sub_frames']:
                frame.config(bg=bg_frame)
                for child in frame.winfo_children():
                    if isinstance(child, tk.Label): child.config(bg=bg_frame, fg=fg_text)
        for scale in refs['sliders']:
            if not enabled:
                scale.configure(style=scale_style)
                scale.state([scale_state])
            else:
                scale.configure(style="TScale")
                scale.state(['!disabled'])

    def log_system_message(self, message):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        msg_str = f"[{timestamp}] [系统] {message}\n"
        self.history_text.insert(tk.END, msg_str, "sys_msg")
        self.history_text.see(tk.END)

    def switch_mode(self, mode):
        self.display_mode.set(mode)
        self.render_tags()
        self.update_display_mode_btn_color()

    def update_display_mode_btn_color(self):
        current_mode = self.display_mode.get()
        active_bg, normal_bg = "#81ecec", "#f1f2f6"
        for mode_key, btn in self.mode_buttons.items():
            if mode_key == current_mode:
                btn.config(bg=active_bg, relief=tk.SUNKEN)
            else:
                btn.config(bg=normal_bg, relief=tk.RAISED)

    def get_random_result_dict(self):
        current_result_dict = {}
        for big, smalls in self.data.items():
            has_pinned = False
            if big in self.prompt_lock_vars:
                for k, v in self.prompt_lock_vars[big].items():
                    if v.get(): has_pinned = True; break
            if not has_pinned:
                if big in self.file_enabled_vars and not self.file_enabled_vars[big]:
                    continue
            for small, items in smalls.items():
                key = (big, small)
                is_pinned = False
                if big in self.prompt_lock_vars and small in self.prompt_lock_vars[big]:
                    is_pinned = self.prompt_lock_vars[big][small].get()
                if is_pinned:
                    if key in self.last_results:
                        current_result_dict[key] = self.last_results[key]
                    continue
                prob = self.category_vars[big][small].get()
                if random.randint(1, 100) <= prob:
                    cn, en = random.choice(list(items.items()))
                    current_result_dict[key] = {'cn': cn, 'en': en, 'weight': 1.0}
        return current_result_dict

    def generate_prompts(self, is_batch=False):
        if not is_batch: self.save_state_for_undo()
        self.last_results = self.get_random_result_dict()
        self.render_tags()
        if not is_batch: self.log_to_history(self.last_results, "生成")

    def render_tags(self):
        for w in self.tags_container.scrollable_content.winfo_children(): w.destroy()
        row_frame = tk.Frame(self.tags_container.scrollable_content, bg="#f0f2f5")
        row_frame.pack(side=tk.TOP, fill=tk.X, pady=2)
        cur_w, max_w = 0, 750
        for key in sorted(self.last_results.keys()):
            data = self.last_results[key]
            cn, en, weight = data['cn'], data['en'], data['weight']
            mode = self.display_mode.get()
            txt = f"{cn}\n{en}" if mode == "mixed" else (cn if mode == "cn" else en)
            bg = "white"
            if weight > 1: bg = "#ffeaa7"
            if weight < 1: bg = "#dfe6e9"
            tag = tk.Frame(row_frame, bg=bg, relief=tk.RIDGE, bd=1)
            tag.pack(side=tk.LEFT, padx=3, pady=2)
            tk.Label(tag, text=txt, bg=bg, font=("Arial", 9)).pack(side=tk.LEFT, padx=5)
            cf = tk.Frame(tag, bg=bg)
            cf.pack(side=tk.RIGHT, padx=2)
            tk.Label(cf, text=f"{weight:.1f}", font=("Arial", 8, "bold"), bg=bg).pack(side=tk.TOP)
            bf = tk.Frame(cf, bg=bg)
            bf.pack(side=tk.BOTTOM)

            def mod_w(k=key, d=0.1):
                self.last_results[k]['weight'] = round(max(0.1, min(3.0, self.last_results[k]['weight'] + d)), 1)
                self.render_tags()

            tk.Button(bf, text="+", width=1, command=lambda k=key: mod_w(k, 0.1), font=("Arial", 6), bg="#e17055",
                      fg="white", relief=tk.FLAT).pack(side=tk.LEFT)
            tk.Button(bf, text="-", width=1, command=lambda k=key: mod_w(k, -0.1), font=("Arial", 6), bg="#74b9ff",
                      fg="white", relief=tk.FLAT).pack(side=tk.LEFT)
            cur_w += len(str(txt)) * 7 + 60
            if cur_w > max_w: cur_w, row_frame = 0, tk.Frame(self.tags_container.scrollable_content,
                                                             bg="#f0f2f5"); row_frame.pack(side=tk.TOP, fill=tk.X,
                                                                                           pady=2)

    def toggle_all_sections(self, expand):
        for _, (f, b) in self.content_frames.items():
            if expand:
                f.pack(side=tk.TOP, fill=tk.BOTH, expand=True); b.config(text="▼")
            else:
                f.pack_forget(); b.config(text="▶")

    def perform_undo(self, e):
        if self.undo_stack: self.last_results = self.undo_stack.pop(); self.render_tags()

    def save_state_for_undo(self):
        self.undo_stack.append(copy.deepcopy(self.last_results))
        if len(self.undo_stack) > 20: self.undo_stack.pop(0)

    def log_to_history(self, res, p):
        s = self.build_str(res)
        idx = len(self.history_data_list)
        self.history_data_list.append(copy.deepcopy(res))
        tn = f"h_{idx}"
        self.history_text.insert(tk.END, f"[{p}] ", "dim")
        self.history_text.insert(tk.END, s + "\n", tn)
        self.history_text.tag_bind(tn, "<Button-1>", lambda e, i=idx: self.restore_hist(i))
        self.history_text.tag_bind(tn, "<Enter>",
                                   lambda e, t=tn: self.history_text.tag_add("hover", f"{t}.first", f"{t}.last"))
        self.history_text.tag_bind(tn, "<Leave>",
                                   lambda e, t=tn: self.history_text.tag_remove("hover", f"{t}.first", f"{t}.last"))
        self.history_text.see(tk.END)

    def restore_hist(self, i):
        self.save_state_for_undo()
        self.last_results = copy.deepcopy(self.history_data_list[i])
        self.render_tags()
        self.notebook.select(self.tab_preview)

    def build_str(self, res):
        l = []
        for k in sorted(res.keys()):
            d = res[k];
            t = d['en']
            if d['weight'] != 1: t = f"({t}:{d['weight']})"
            l.append(t)
        return ", ".join(l)

    def run_batch_generation(self):
        try:
            c = int(self.batch_count.get())
        except:
            c = 5
        self.notebook.select(self.tab_history)
        self.history_text.insert(tk.END, f"\n=== 批量 {c} ===\n", "sys_msg")
        for i in range(c): r = self.get_random_result_dict(); self.log_to_history(r, f"#{i + 1}")
        self.history_text.see(tk.END)

    def copy_positive(self):
        self.master_window.clipboard_clear()
        self.master_window.clipboard_append(self.build_str(self.last_results))
        self.log_system_message("内容已复制到剪贴板")

    def clear_all(self):
        self.save_state_for_undo()
        self.last_results = {}
        self.render_tags()
        self.log_system_message("提示词已清空")

    def unlock_all(self):
        for big in self.prob_lock_vars:
            for small in self.prob_lock_vars[big]: self.prob_lock_vars[big][small].set(False)
        for big in self.prompt_lock_vars:
            for small in self.prompt_lock_vars[big]: self.prompt_lock_vars[big][small].set(False)
        self.log_system_message("所有锁定已重置 (请加载预设或手动点击刷新UI状态)")

    def save_preset(self):
        preset_data = {
            "probabilities": {}, "file_enabled": {}, "prob_locks": {}, "prompt_locks": {},
            "display_mode": self.display_mode.get()
        }
        for big in self.category_vars:
            preset_data["probabilities"][big] = {}
            preset_data["prob_locks"][big] = {}
            preset_data["prompt_locks"][big] = {}
            if big in self.file_enabled_vars:
                preset_data["file_enabled"][big] = self.file_enabled_vars[big]
            for small in self.category_vars[big]:
                preset_data["probabilities"][big][small] = self.category_vars[big][small].get()
                preset_data["prob_locks"][big][small] = self.prob_lock_vars[big][small].get()
                preset_data["prompt_locks"][big][small] = self.prompt_lock_vars[big][small].get()

        filepath = filedialog.asksaveasfilename(initialdir=self.preset_folder, title="保存预设",
                                                defaultextension=".json", filetypes=[("JSON Files", "*.json")])
        if filepath:
            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(preset_data, f, ensure_ascii=False, indent=2)
                self.log_system_message(f"预设已保存: {os.path.basename(filepath)}")
            except Exception as e:
                self.log_system_message(f"保存失败: {e}")

    def load_preset(self):
        filepath = filedialog.askopenfilename(initialdir=self.preset_folder, title="加载预设",
                                              filetypes=[("JSON Files", "*.json")])
        if not filepath: return
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                preset_data = json.load(f)
            if "display_mode" in preset_data:
                self.display_mode.set(preset_data["display_mode"])
                self.update_display_mode_btn_color()

            probs = preset_data.get("probabilities", {})
            for big in probs:
                if big in self.category_vars:
                    for small in probs[big]:
                        if small in self.category_vars[big]:
                            self.category_vars[big][small].set(probs[big][small])

            file_en = preset_data.get("file_enabled", {})
            for big, enabled in file_en.items():
                if big in self.file_enabled_vars:
                    self.file_enabled_vars[big] = enabled
                    if big in self.file_btn_refs:
                        self.update_file_btn_style(self.file_btn_refs[big], enabled)
                    self.update_category_visuals(big, enabled)

            self.render_tags()
            self.log_system_message("预设已加载")
        except Exception as e:
            self.log_system_message(f"加载失败: {e}")

    def export_history(self):
        filepath = filedialog.asksaveasfilename(initialdir=".", title="导出历史记录", defaultextension=".txt",
                                                filetypes=[("Text Files", "*.txt")])
        if filepath:
            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(self.history_text.get(1.0, tk.END))
                self.log_system_message("历史记录已导出")
            except Exception as e:
                self.log_system_message(f"导出失败: {e}")