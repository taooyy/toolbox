import os
import tkinter as tk
from tkinter import filedialog, Listbox, ttk, messagebox
from datetime import datetime
import customtkinter as ctk
from PIL import Image
from src.gui.prompt_panel import PromptPanel

# === 设置窗口图标 (防止开发环境报错) ===
try:
    # self.iconbitmap("logo.ico")
    pass
except:
    pass

# === 引入各模块 ===
from src.config.manager import ConfigManager
from src.core.unpack_engine import UnpackEngine
from src.core.icon_engine import IconEngine
from src.core.json_engine import JsonEngine


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("全能工具箱")
        self.geometry("650x500")
        ctk.set_appearance_mode("Light")

        # 1. 加载配置
        self.cfg_mgr = ConfigManager()
        self.config = self.cfg_mgr.load_config()

        # 2. 初始化各引擎
        self.unpacker = UnpackEngine(self.log_u, self.prog_u, self.fin_u)
        self.iconer = IconEngine(self.log_i, self.prog_i, self.fin_i)
        self.jsoner = JsonEngine(self.log_j)

        # 3. 运行时变量初始化
        self.icon_files = []
        self.u_running = False
        self.u_paused = False
        self.current_preview_img = None

        # 4. 初始化界面
        self._init_layout()

        # 默认显示解压页
        self.switch_tab("unpack")

    def _init_layout(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # === 侧边栏 Sidebar ===
        self.sidebar = ctk.CTkFrame(self, width=180, corner_radius=0, fg_color=("gray95", "gray20"))
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        ctk.CTkLabel(self.sidebar, text="📦 工具箱", font=("", 20, "bold")).pack(pady=(30, 20))

        self.btn_nav_unpack = self._nav_btn("解压专家", "unpack")
        self.btn_nav_icon = self._nav_btn("图片转Icon", "icon")
        self.btn_nav_json = self._nav_btn("JSON工厂", "json")
        # [新增] 抽卡机按钮
        self.btn_nav_prompt = self._nav_btn("AI 提示词抽卡", "prompt")
        self.btn_nav_setting = self._nav_btn("全局设置", "setting")

        # === 主区域 Main Area ===
        self.main_area = ctk.CTkFrame(self, fg_color="transparent")
        self.main_area.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        self.main_area.grid_rowconfigure(0, weight=1)
        self.main_area.grid_columnconfigure(0, weight=1)

        # 预加载所有页面 Frame
        self.frame_unpack = self._ui_unpack()
        self.frame_icon = self._ui_icon()
        self.frame_json = self._ui_json()
        self.frame_setting = self._ui_setting()
        # [新增] 预加载 Prompt Frame
        self.frame_prompt = self._ui_prompt()

    def _nav_btn(self, text, tag):
        btn = ctk.CTkButton(self.sidebar, text=text, height=45, fg_color="transparent",
                            text_color=("gray10", "white"), anchor="w", font=("", 14),
                            command=lambda: self.switch_tab(tag))
        btn.pack(fill="x", padx=10, pady=5)
        return btn

    def switch_tab(self, tag):
        # 隐藏所有页面
        # [修改] 增加 frame_prompt
        for f in [self.frame_unpack, self.frame_icon, self.frame_setting, self.frame_json, self.frame_prompt]:
            f.grid_forget()

        # 重置按钮样式
        # [修改] 增加 btn_nav_prompt
        for b in [self.btn_nav_unpack, self.btn_nav_icon, self.btn_nav_setting, self.btn_nav_json,
                    self.btn_nav_prompt]:
            b.configure(fg_color="transparent")

        # 显示选中页面并高亮按钮
        if tag == "unpack":
            self.frame_unpack.grid(row=0, column=0, sticky="nsew")
            self.btn_nav_unpack.configure(fg_color=("gray85", "gray30"))
        elif tag == "icon":
            self.frame_icon.grid(row=0, column=0, sticky="nsew")
            self.btn_nav_icon.configure(fg_color=("gray85", "gray30"))
            self._refresh_preview_list()
        elif tag == "json":
            self.frame_json.grid(row=0, column=0, sticky="nsew")
            self.btn_nav_json.configure(fg_color=("gray85", "gray30"))
        elif tag == "prompt":  # [新增]
            self.frame_prompt.grid(row=0, column=0, sticky="nsew")
            self.btn_nav_prompt.configure(fg_color=("gray85", "gray30"))
            # 切换到此 Tab 时，让 prompt panel 获取焦点，以便快捷键生效
            self.frame_prompt.focus_set()
        elif tag == "setting":
            self.frame_setting.grid(row=0, column=0, sticky="nsew")
            self.btn_nav_setting.configure(fg_color=("gray85", "gray30"))

    # =========================================================================
    # Tab 1: 解压专家
    # =========================================================================
    def _ui_unpack(self):
        frame = ctk.CTkFrame(self.main_area, fg_color="transparent")

        # 状态栏
        st_box = ctk.CTkFrame(frame, height=50)
        st_box.pack(fill="x", pady=(0, 10))
        self.lbl_u_status = ctk.CTkLabel(st_box, text="准备就绪", font=("", 16, "bold"), text_color="#3B8ED0")
        self.lbl_u_status.pack(side="left", padx=20, pady=10)
        self.bar_u = ctk.CTkProgressBar(st_box)
        self.bar_u.set(0)
        self.bar_u.pack(side="left", fill="x", expand=True, padx=20)

        # 配置区
        cfg_box = ctk.CTkFrame(frame)
        cfg_box.pack(fill="x", pady=5)

        # 第一行：源路径 + 模式
        r1 = ctk.CTkFrame(cfg_box, fg_color="transparent")
        r1.pack(fill="x", padx=10, pady=5)
        self.entry_u_src = ctk.CTkEntry(r1, placeholder_text="源文件夹")
        self.entry_u_src.pack(side="left", fill="x", expand=True)
        self.entry_u_src.insert(0, self.config.get("last_unpack_src", ""))
        ctk.CTkButton(r1, text="📂", width=40, command=lambda: self._browse_dir(self.entry_u_src)).pack(side="left",
                                                                                                       padx=5)

        self.om_u_mode = ctk.CTkOptionMenu(r1, values=["当前目录(散)", "当前+智能文件夹", "指定目录(混)",
                                                       "指定+智能文件夹"], width=140)
        self.om_u_mode.pack(side="left")
        self.om_u_mode.set(self.config.get("last_output_mode", "当前目录(散)"))

        # 第二行：密码 + 输出路径
        r2 = ctk.CTkFrame(cfg_box, fg_color="transparent")
        r2.pack(fill="x", padx=10, pady=5)
        self.entry_u_pwd = ctk.CTkEntry(r2, placeholder_text="密码(空格分隔)")
        self.entry_u_pwd.pack(side="left", fill="x", expand=True)
        self.entry_u_dst = ctk.CTkEntry(r2, placeholder_text="输出位置")
        self.entry_u_dst.pack(side="left", fill="x", expand=True, padx=5)
        self.entry_u_dst.insert(0, self.config.get("last_unpack_dst", ""))
        ctk.CTkButton(r2, text="📂", width=40, command=lambda: self._browse_dir(self.entry_u_dst)).pack(side="left",
                                                                                                       padx=5)

        self.var_del = ctk.BooleanVar(value=self.config.get("delete_source", False))
        ctk.CTkCheckBox(cfg_box, text="解压后删除源文件 (仅主文件)", variable=self.var_del).pack(anchor="w", padx=15,
                                                                                                 pady=10)

        # 日志区
        self.txt_u_log = ctk.CTkTextbox(frame, font=("Consolas", 12))
        self.txt_u_log.pack(fill="both", expand=True, pady=10)

        # 按钮区
        btn_box = ctk.CTkFrame(frame, fg_color="transparent")
        btn_box.pack(fill="x", pady=5)
        btn_box.grid_columnconfigure((0, 1, 2), weight=1)
        self.btn_u_start = ctk.CTkButton(btn_box, text="▶ 开始", height=45, fg_color="#2CC985", command=self.run_unpack)
        self.btn_u_start.grid(row=0, column=0, sticky="ew", padx=5)
        self.btn_u_pause = ctk.CTkButton(btn_box, text="⏸ 暂停", height=45, fg_color="#E1AD01", state="disabled",
                                         command=self.pause_unpack)
        self.btn_u_pause.grid(row=0, column=1, sticky="ew", padx=5)
        self.btn_u_stop = ctk.CTkButton(btn_box, text="⏹ 停止", height=45, fg_color="#FF4D4D", state="disabled",
                                        command=self.stop_unpack)
        self.btn_u_stop.grid(row=0, column=2, sticky="ew", padx=5)

        return frame

    def run_unpack(self):
        if self.u_running: return
        self.config.update({
            "last_unpack_src": self.entry_u_src.get(),
            "last_unpack_dst": self.entry_u_dst.get(),
            "last_output_mode": self.om_u_mode.get(),
            "delete_source": self.var_del.get()
        })
        self.cfg_mgr.save_config(self.config)

        mode_map = {"当前目录(散)": "current", "当前+智能文件夹": "current_smart", "指定目录(混)": "custom_direct",
                    "指定+智能文件夹": "custom_smart"}
        cfg = self.config.copy()
        cfg.update({
            "source_folder": self.entry_u_src.get(),
            "output_mode": mode_map.get(self.om_u_mode.get(), "current"),
            "custom_output_path": self.entry_u_dst.get(),
            "engine_path": self.config["winrar_path"] if self.config["engine"] == "WinRAR" else self.config[
                "bandizip_path"]
        })

        self.u_running = True
        self.u_paused = False
        self._toggle_u_btns(True)
        self.txt_u_log.delete("1.0", "end")
        self.lbl_u_status.configure(text="运行中...", text_color="#2CC985")

        self.unpacker.start_task(cfg, self.entry_u_pwd.get())

    def pause_unpack(self):
        if not self.u_running: return
        if not self.u_paused:
            self.u_paused = True
            self.btn_u_pause.configure(text="▶ 继续")
            self.lbl_u_status.configure(text="已暂停", text_color="#E1AD01")
            self.unpacker.pause()
        else:
            self.u_paused = False
            self.btn_u_pause.configure(text="⏸ 暂停")
            self.lbl_u_status.configure(text="运行中...", text_color="#2CC985")
            self.unpacker.resume()

    def stop_unpack(self):
        if not self.u_running: return
        self.unpacker.stop()
        self.btn_u_stop.configure(state="disabled")

    def _toggle_u_btns(self, r):
        self.btn_u_start.configure(state="disabled" if r else "normal")
        self.btn_u_pause.configure(state="normal" if r else "disabled")
        self.btn_u_stop.configure(state="normal" if r else "disabled")

    # --- Callbacks ---
    def log_u(self, m, l):
        self.after(0, lambda: self._log_insert(self.txt_u_log, m))

    def prog_u(self, v):
        self.after(0, lambda: self.bar_u.set(v))

    def fin_u(self, s, aborted=False):
        def _f():
            self.u_running = False
            self._toggle_u_btns(False)
            self.bar_u.set(0 if aborted else 1.0)
            t = "已取消" if aborted else f"完成! 成功 {s['success']} / 失败 {s['fail']}"
            c = "#FF4D4D" if aborted else "#3B8ED0"
            self.lbl_u_status.configure(text=t, text_color=c)
            if not aborted:
                self._log_insert(self.txt_u_log, "=" * 20 + "\n" + t)

        self.after(0, _f)

    # =========================================================================
    # Tab 2: 图片转 Icon
    # =========================================================================
    def _ui_icon(self):
        """
        [界面重构] 图片转 Icon 页面 (响应式按钮版)
        Row 2: 采用 Grid 布局，按钮宽度随窗口自适应
        """
        frame = ctk.CTkFrame(self.main_area, fg_color="transparent")

        # === 主网格配置 ===
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)  # Row 1: Input List (Expand)
        frame.grid_rowconfigure(1, weight=0)  # Row 2: Settings (Fixed Height)
        frame.grid_rowconfigure(2, weight=1)  # Row 3: Output (Expand)

        # =====================================================
        # 1. 第一行：待处理图片
        # =====================================================
        row1 = ctk.CTkFrame(frame)
        row1.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        row1.grid_columnconfigure(0, weight=1)
        row1.grid_rowconfigure(1, weight=1)

        # 1.1 顶部工具条
        r1_bar = ctk.CTkFrame(row1, fg_color="transparent")
        r1_bar.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))

        ctk.CTkLabel(r1_bar, text="📥 待处理图片", font=("", 14, "bold")).pack(side="left")

        ctk.CTkButton(r1_bar, text="🗑️ 清空列表", width=80, height=28, fg_color="#FF4D4D", hover_color="#D63031",
                      command=lambda: [self.lst_icon.delete(0, "end"), self.icon_files.clear()]).pack(side="right",
                                                                                                      padx=5)
        ctk.CTkButton(r1_bar, text="➕ 添加图片", width=100, height=28, fg_color="#3B8ED0",
                      command=self.add_imgs).pack(side="right", padx=5)

        # 1.2 输入列表
        self.lst_icon = Listbox(row1, bd=0, highlightthickness=0, font=("Consolas", 10), selectbackground="#3B8ED0")
        self.lst_icon.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

        # =====================================================
        # 2. 第二行：配置与控制 (Grid 响应式布局)
        # =====================================================
        row2 = ctk.CTkFrame(frame)
        row2.grid(row=1, column=0, sticky="ew", padx=5, pady=5)

        # [关键修改] 设置列权重：左侧配置区占4份，右侧按钮占1份
        # 这样当窗口变宽时，按钮也会按比例变宽
        row2.grid_columnconfigure(0, weight=4)
        row2.grid_columnconfigure(1, weight=1)
        row2.grid_rowconfigure(0, weight=1)

        # 2.1 左侧：配置项 (Grid Column 0)
        cfg_panel = ctk.CTkFrame(row2, fg_color="transparent")
        cfg_panel.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        # 第一排：尺寸设置
        line1 = ctk.CTkFrame(cfg_panel, fg_color="transparent")
        line1.pack(fill="x", pady=2)
        ctk.CTkLabel(line1, text="生成尺寸:", text_color="gray", font=("", 12)).pack(side="left", padx=(0, 5))

        self.cb_vals = [
            "标准多尺寸 (推荐)",
            "转换/导出为 SVG",
            "256x256", "128x128", "64x64", "48x48", "32x32", "16x16",
            "自定义 (手动输入)"
        ]
        self.cb_size = ttk.Combobox(line1, values=self.cb_vals, state="readonly", width=18)
        self.cb_size.pack(side="left", padx=5)
        self.cb_size.set("标准多尺寸 (推荐)")
        self.cb_size.bind("<<ComboboxSelected>>", self._on_icon_combo)

        self.entry_i_cust = ctk.CTkEntry(line1, placeholder_text="px", width=60, height=28)
        self.entry_i_cust.pack(side="left", padx=5)
        self.entry_i_cust.configure(state="disabled")

        # [已修复] 变量初始化
        self.var_crop = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(line1, text="智能居中裁剪", variable=self.var_crop, font=("", 12)).pack(side="left", padx=15)

        # 第二排：进度条与状态
        line2 = ctk.CTkFrame(cfg_panel, fg_color="transparent")
        line2.pack(fill="x", pady=(8, 0))

        self.bar_i = ctk.CTkProgressBar(line2, height=12)
        self.bar_i.set(0)
        self.bar_i.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.lbl_i_status = ctk.CTkLabel(line2, text="准备就绪", text_color="gray", font=("", 11))
        self.lbl_i_status.pack(side="left")

        # 2.2 右侧：大按钮 (Grid Column 1)
        # [关键修改] 移除固定 width，使用 sticky="ew" 水平填充
        self.btn_i_run = ctk.CTkButton(row2, text="⚡ 开始转换", height=50,
                                       fg_color="#2CC985", hover_color="#26AF73",
                                       font=("", 15, "bold"), command=self.run_icon)
        self.btn_i_run.grid(row=0, column=1, sticky="ew", padx=(0, 15), pady=15)

        # =====================================================
        # 3. 第三行：输出结果
        # =====================================================
        row3 = ctk.CTkFrame(frame)
        row3.grid(row=2, column=0, sticky="nsew", padx=5, pady=5)
        row3.grid_columnconfigure(0, weight=1)
        row3.grid_rowconfigure(1, weight=1)

        # 3.1 头部
        r3_bar = ctk.CTkFrame(row3, fg_color="transparent")
        r3_bar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 5))
        ctk.CTkLabel(r3_bar, text="📤 结果预览", font=("", 14, "bold")).pack(side="left")
        ctk.CTkButton(r3_bar, text="🔄 刷新", width=60, height=24, fg_color="transparent", border_width=1,
                      text_color=("gray10", "gray90"), command=self._refresh_preview_list).pack(side="right")

        # 3.2 左侧：输出列表
        self.lst_out = Listbox(row3, bd=0, highlightthickness=0, font=("Consolas", 10), selectbackground="#2CC985")
        self.lst_out.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self.lst_out.bind("<<ListboxSelect>>", self._on_preview_click)

        # 3.3 右侧：预览图容器
        preview_container = ctk.CTkFrame(row3, fg_color="transparent")
        preview_container.grid(row=1, column=1, sticky="ns", padx=(0, 10), pady=(0, 10))

        self.preview_box = ctk.CTkFrame(preview_container, width=160, height=160, fg_color=("gray90", "gray30"))
        self.preview_box.pack(pady=0)
        self.preview_box.pack_propagate(False)

        self.lbl_preview_img = ctk.CTkLabel(self.preview_box, text="点击文件\n预览图标", font=("", 10))
        self.lbl_preview_img.place(relx=0.5, rely=0.5, anchor="center")

        return frame

    def _on_icon_combo(self, e):
        if "自定义" in self.cb_size.get():
            self.entry_i_cust.configure(state="normal")
            self.entry_i_cust.focus()
        else:
            self.entry_i_cust.delete(0, "end")
            self.entry_i_cust.configure(state="disabled")

    def add_imgs(self):
        fs = filedialog.askopenfilenames(filetypes=[("Img", "*.png *.jpg *.jpeg *.bmp")])
        for f in fs:
            if f not in self.icon_files:
                self.icon_files.append(f)
                self.lst_icon.insert("end", os.path.basename(f))

    def run_icon(self):
        if not self.icon_files: return
        self.btn_i_run.configure(state="disabled")
        self.iconer.start(self.icon_files, self.config["icon_output_path"],
                          self.cb_size.get(), self.entry_i_cust.get(), self.var_crop.get())

    def _refresh_preview_list(self):
        out_dir = self.config["icon_output_path"]
        self.lst_out.delete(0, "end")
        if not os.path.exists(out_dir):
            self.lst_out.insert("end", "输出目录不存在")
            return
        # === [修改] 增加 .svg 到文件过滤器 ===
        files = [f for f in os.listdir(out_dir) if f.lower().endswith((".ico", ".svg"))]
        files.sort(key=lambda x: os.path.getmtime(os.path.join(out_dir, x)), reverse=True)
        for f in files: self.lst_out.insert("end", f)

    def _on_preview_click(self, event):
        sel = self.lst_out.curselection()
        if not sel: return
        fname = self.lst_out.get(sel)
        fpath = os.path.join(self.config["icon_output_path"], fname)

        # === 1. 准备数据 (先不操作 UI) ===
        new_img = None
        msg_text = ""

        # SVG 处理
        if fname.lower().endswith(".svg"):
            msg_text = "SVG 矢量图\n(请在浏览器中查看)"
        # 图片处理
        else:
            try:
                pil_img = Image.open(fpath)
                pil_img.thumbnail((128, 128))
                # 创建 CTkImage
                new_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=pil_img.size)
            except Exception:
                msg_text = "预览失败\n(文件可能损坏)"

        # === 2. 更新全局引用 (防止垃圾回收) ===
        # 这一步非常重要，必须在 UI 更新前完成
        self.current_preview_img = new_img

        # === 3. 安全更新 UI (重建策略) ===
        try:
            # 尝试正常更新（大多数时候走这里）
            self.lbl_preview_img.configure(image=new_img, text=msg_text)
        except Exception:
            # !!! 这里的 Exception 就是你遇到的 "pyimage1 doesn't exist" !!!
            # 如果控件已经损坏，不要试图修复它，直接销毁并重建
            try:
                self.lbl_preview_img.destroy()
            except:
                pass

            # 原地创建一个新的 Label
            self.lbl_preview_img = ctk.CTkLabel(self.preview_box, text=msg_text, image=new_img)
            # 恢复布局位置 (必须与 _ui_icon 中的布局一致)
            self.lbl_preview_img.place(relx=0.5, rely=0.5, anchor="center")

    def log_i(self, m, l):
        self.after(0, lambda: self.lbl_i_status.configure(text=m))

    def prog_i(self, v):
        self.after(0, lambda: self.bar_i.set(v))

    def fin_i(self, stats):
        def _f():
            self.btn_i_run.configure(state="normal")
            self.lbl_i_status.configure(text=f"完成! 成功 {stats['success']}")
            self._refresh_preview_list()

            if stats["skipped"]:
                msg = f"以下 {len(stats['skipped'])} 个文件因尺寸过小被跳过:\n\n"
                msg += "\n".join(stats["skipped"][:10])
                if len(stats["skipped"]) > 10:
                    msg += f"\n... 以及其他 {len(stats['skipped']) - 10} 个"
                msg += "\n\n(提示: 请选择更小的目标尺寸或使用更大的原图)"
                messagebox.showwarning("部分跳过", msg)
            elif stats["success"] > 0:
                messagebox.showinfo("完成", f"成功转换 {stats['success']} 个图标")

        self.after(0, _f)

    # =========================================================================
    # Tab 3: JSON 工厂 (新版: 批量输入 + 智能解析)
    # =========================================================================
    def _ui_json(self):
        """
        [最终修正版] JSON 工厂
        1. 包含了您提供的所有按钮、提示文本(Hint)和布局细节。
        2. 右侧面板升级为 ScrollableFrame，确保小屏幕下能滚动查看底部按钮。
        """
        frame = ctk.CTkFrame(self.main_area, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=3)  # 左侧预览占宽
        frame.grid_columnconfigure(1, weight=1)  # 右侧操作占窄
        frame.grid_rowconfigure(0, weight=1)

        # =====================================================
        # 左侧：预览区域 (完全保持您提供的代码)
        # =====================================================
        left_panel = ctk.CTkFrame(frame, fg_color="transparent")
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        # 顶部工具栏
        toolbar = ctk.CTkFrame(left_panel)
        toolbar.pack(fill="x", pady=(0, 10))
        ctk.CTkButton(toolbar, text="📄 新建", width=60, fg_color="gray", command=self.json_new).pack(side="left",
                                                                                                     padx=5, pady=5)
        ctk.CTkButton(toolbar, text="📂 打开", width=60, command=self.json_open).pack(side="left", padx=5)
        ctk.CTkButton(toolbar, text="💾 保存", width=60, fg_color="#2CC985", command=self.json_save).pack(side="left",
                                                                                                         padx=5)
        self.lbl_j_path = ctk.CTkLabel(toolbar, text="未打开文件", text_color="gray")
        self.lbl_j_path.pack(side="left", padx=10)

        # Treeview 预览
        tree_frame = ctk.CTkFrame(left_panel)
        tree_frame.pack(fill="both", expand=True)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", background="#2b2b2b", fieldbackground="#2b2b2b", foreground="white", rowheight=25,
                        borderwidth=0)
        style.configure("Treeview.Heading", background="#3a3a3a", foreground="white", relief="flat")
        style.map("Treeview", background=[("selected", "#3B8ED0")])

        self.tree = ttk.Treeview(tree_frame, columns=("val"), show="tree headings", selectmode="browse")
        self.tree.heading("#0", text="Key / Type", anchor="w")
        self.tree.heading("val", text="Value", anchor="w")
        self.tree.column("#0", width=200)
        self.tree.column("val", width=300)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)

        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        # 底部日志
        self.lbl_j_status = ctk.CTkLabel(left_panel, text="准备就绪", anchor="w", text_color="gray")
        self.lbl_j_status.pack(fill="x", pady=5)

        # =====================================================
        # 右侧：操作面板 (升级为 ScrollableFrame 以支持滚动)
        # =====================================================
        # [修改点] 这里改为 CTkScrollableFrame
        right_panel = ctk.CTkScrollableFrame(frame, label_text="🛠️ 操作面板")
        right_panel.grid(row=0, column=1, sticky="nsew", padx=(5, 0))

        # 辅助函数：模拟 _grp_box (防止 self._grp_box 未定义或布局不兼容)
        def create_group_box(parent, title):
            grp = ctk.CTkFrame(parent)
            grp.pack(fill="x", pady=5, padx=5)
            ctk.CTkLabel(grp, text=title, font=("", 13, "bold"), anchor="w").pack(fill="x", padx=10, pady=5)
            return grp

        # 1. 批量新建类型
        grp1 = create_group_box(right_panel, "1. 批量新建类型")

        self.txt_j_types = ctk.CTkTextbox(grp1, height=60, font=("", 12))
        self.txt_j_types.pack(fill="x", padx=10, pady=5)
        self.txt_j_types.insert("1.0", "类型1, 类型2")
        ctk.CTkButton(grp1, text="➕ 批量添加", height=30, command=self.json_add_types).pack(fill="x", padx=10, pady=5)

        # 2. 批量数据录入
        grp2 = create_group_box(right_panel, "2. 批量录入")

        self.entry_j_type = ctk.CTkEntry(grp2, placeholder_text="在此输入或从左侧选择类型")
        self.entry_j_type.pack(fill="x", padx=10, pady=(5, 0))

        # 添加复选框控制模式
        self.var_double_line = ctk.BooleanVar(value=False)
        cb_mode = ctk.CTkCheckBox(grp2, text="启用双行模式 (奇数行标题 / 偶数行内容)",
                                  variable=self.var_double_line, font=("", 11))
        cb_mode.pack(anchor="w", padx=15, pady=5)

        # [恢复漏掉的 Hint]
        hint = (
            "默认模式: 自动识别 冒号/等号/逗号 (Key:Value)\n"
            "双行模式: 专门用于处理 Prompt 等长文本\n"
            "   第一行: 名称 (Key)\n"
            "   第二行: 内容 (Value)"
        )
        ctk.CTkLabel(grp2, text=hint, font=("Consolas", 11), text_color="gray", justify="left").pack(anchor="w",
                                                                                                     padx=15, pady=5)

        self.txt_j_data = ctk.CTkTextbox(grp2, height=150, font=("Consolas", 11))
        self.txt_j_data.pack(fill="x", padx=10, pady=5)

        demo_text = "普通模式示例:\nkey1: value1\nkey2=value2\n\n双行模式示例(需勾选上方):\n角色名\n{{tag1, tag2, tag3}}\n服装\nwhite dress, blue bow"
        self.txt_j_data.insert("1.0", demo_text)

        # [恢复漏掉的按钮布局]
        btn_row = ctk.CTkFrame(grp2, fg_color="transparent")
        btn_row.pack(fill="x", padx=5, pady=5)
        ctk.CTkButton(btn_row, text="批量添加", width=60, fg_color="#3B8ED0",
                      command=self.json_run_batch).pack(side="left", padx=5, expand=True)
        ctk.CTkButton(btn_row, text="删除", width=60, fg_color="#FF4D4D",
                      command=self.json_del).pack(side="left", padx=5, expand=True)

        # 3. 高级操作
        grp3 = create_group_box(right_panel, "3. 高级操作")
        # [恢复漏掉的说明文本]
        ctk.CTkLabel(grp3, text="将指定类型下的 Key 和 Value 互换", font=("", 10), text_color="gray").pack(pady=(0, 5))
        ctk.CTkButton(grp3, text="🔄 交换键值对", fg_color="#E1AD01", command=self.json_swap).pack(fill="x",
                                                                                                             padx=10,
                                                                                                             pady=5)

        return frame

    def _grp_box(self, parent, title):
        f = ctk.CTkFrame(parent)
        f.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(f, text=title, font=("", 14, "bold")).pack(anchor="w", padx=10, pady=5)
        return f

    # --- JSON Callbacks ---

    def log_j(self, msg, level="info"):
        color = "#2CC985" if level == "success" else "#FF4D4D" if level == "error" else "#3B8ED0"
        self.lbl_j_status.configure(text=msg, text_color=color)
        if level == "error": messagebox.showerror("错误", msg)

    def _render_tree(self, keep_state=True, force_open=None):
        """
        渲染左侧树形列表
        :param keep_state: True=保留当前的展开/折叠状态
        :param force_open: 一个列表，包含本次需要强制展开的类型名 (用于新增操作)
        """
        if force_open is None:
            force_open = []

        opened_types = set()
        if keep_state:
            for item_id in self.tree.get_children():
                # 记录所有已展开的父节点 text
                if self.tree.item(item_id, "open"):
                    opened_types.add(self.tree.item(item_id, "text"))

        # 清空视图
        for item in self.tree.get_children():
            self.tree.delete(item)

        # 获取最新数据
        data = self.jsoner.get_preview_data()

        for type_key, items in data.items():
            # 决定是否展开:
            # 1. 如果 keep_state=False (新文件)，默认全展开
            # 2. 如果在 force_open 列表中 (刚新增的)，强制展开
            # 3. 如果 keep_state=True，检查是否在 opened_types 记录中
            is_open = True

            if keep_state:
                # 只有当 (既不在历史记录里) 且 (也不在强制展开列表里) 时，才折叠
                if (str(type_key) not in opened_types) and (str(type_key) not in force_open):
                    is_open = False

            parent_id = self.tree.insert("", "end", text=str(type_key), open=is_open)

            if isinstance(items, dict):
                for k, v in items.items():
                    display_val = str(v)
                    if len(display_val) > 100:
                        display_val = display_val[:100] + "..."
                    self.tree.insert(parent_id, "end", text=str(k), values=(display_val,))

    def _on_tree_select(self, event):
        sel_id = self.tree.selection()
        if not sel_id: return

        item = self.tree.item(sel_id[0])
        parent_id = self.tree.parent(sel_id[0])

        self.entry_j_type.delete(0, "end")
        self.txt_j_data.delete("1.0", "end")

        if parent_id:
            type_name = self.tree.item(parent_id)['text']
            key = item['text']
            val = item['values'][0]
            self.entry_j_type.insert(0, type_name)
            self.txt_j_data.insert("1.0", f"{key}: {val}")
        else:
            self.entry_j_type.insert(0, item['text'])

    def json_new(self):
        self.jsoner.new_file()
        self._render_tree()
        self._render_tree(keep_state=False)  # <--- 修改这里：新文件默认全展开
        self.lbl_j_path.configure(text="新文件")

    def json_open(self):
        init_dir = self.config.get("json_work_dir", "D:\\")
        f = filedialog.askopenfilename(initialdir=init_dir, filetypes=[("JSON", "*.json")])
        if f:
            if self.jsoner.load_file(f):
                self.lbl_j_path.configure(text=os.path.basename(f))
                self._render_tree(keep_state=False)  # <--- 修改这里：打开新文件默认全展开
                self._render_tree()

    def json_save(self):
        if not self.jsoner.current_file_path:
            init_dir = self.config.get("json_work_dir", "D:\\")
            f = filedialog.asksaveasfilename(initialdir=init_dir, defaultextension=".json",
                                             filetypes=[("JSON", "*.json")])
            if not f: return
            self.jsoner.save_file(f)
            self.lbl_j_path.configure(text=os.path.basename(f))
        else:
            self.jsoner.save_file()

    def json_add_types(self):
        raw = self.txt_j_types.get("1.0", "end")

        # 1. 执行添加逻辑 (Core)
        self.jsoner.add_types(raw)

        # 2. 解析出刚才添加的 Key 列表 (用于强制展开)
        # 这里的解析逻辑与 Engine 保持一致：逗号/换行/空格 分隔
        new_keys = []
        if raw.strip():
            # 简单的分割逻辑提取 keys
            candidates = raw.replace('\n', ',').replace(' ', ',').split(',')
            new_keys = [k.strip() for k in candidates if k.strip()]

        # 3. 渲染并强制展开这些新 Key
        self._render_tree(keep_state=True, force_open=new_keys)

        self._try_autosave()

    def json_run_batch(self):
        t = self.entry_j_type.get()
        raw_text = self.txt_j_data.get("1.0", "end")

        if not t:
            self.log_j("❌ 请先指定或选择一个类型", "error")
            return

        if not raw_text.strip():
            self.log_j("⚠️ 数据为空，未执行操作", "warn")
            return
        # --- 修改：根据复选框状态传递 mode 参数 ---
        mode = "lines" if self.var_double_line.get() else "auto"
        self.jsoner.add_batch_data(t, raw_text, mode=mode)
        # --------------------------------------
        self._render_tree()
        self._try_autosave()

    def json_del(self):
        sel_id = self.tree.selection()
        if not sel_id:
            self.log_j("⚠️ 请先在左侧列表中选择要删除的项目", "warn")
            return

        item = self.tree.item(sel_id[0])
        parent_id = self.tree.parent(sel_id[0])

        if parent_id:
            t = self.tree.item(parent_id)['text']
            k = item['text']
            if messagebox.askyesno("删除确认", f"确定删除条目?\n[{t}] {k}"):
                self.jsoner.delete_item(t, k)
        else:
            t = item['text']
            if messagebox.askyesno("删除确认", f"⚠️ 高风险操作\n确定删除整个类型 [{t}] 及其下所有数据吗?"):
                self.jsoner.delete_item(t)

        self._render_tree()
        self.entry_j_type.delete(0, "end")
        self.txt_j_data.delete("1.0", "end")
        self._try_autosave()

    def json_swap(self):
        t = self.entry_j_type.get()
        if not t:
            self.log_j("❌ 请先选中或输入一个类型名", "error")
            return

        if messagebox.askyesno("交换确认", f"确定交换 [{t}] 下所有的键和值吗？\n如果值重复，可能会丢失数据。"):
            self.jsoner.swap_kv(t)
            self._render_tree()
            self._try_autosave()

    # =========================================================================
    # Tab 4: AI抽卡机
    # =========================================================================

    # 增加 _ui_prompt 初始化逻辑
    def _ui_prompt(self):
        container = ctk.CTkFrame(self.main_area, fg_color="transparent")
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        # [修改] 传递 self.config
        # 注意：这里我们保存 panel 的引用，方便后续销毁重建
        self.prompt_panel_instance = PromptPanel(container, self.config)

        return container

    # =========================================================================
    # Tab 5: 全局设置
    # =========================================================================
    def _ui_setting(self):
        frame = ctk.CTkScrollableFrame(self.main_area, fg_color="transparent")

        self._set_grp(frame, "解压引擎",
                      [("engine", "类型", ["WinRAR", "Bandizip"]), ("winrar_path", "WinRAR.exe", "file"),
                       ("bandizip_path", "Bandizip.exe", "file"), ("max_workers", "线程数", None)])

        self._set_grp(frame, "图片转换", [("icon_output_path", "Icon输出位置", "dir")])
        # [新增] AI 抽卡机设置组
        self._set_grp(frame, "AI 提示词抽卡", [
            ("prompt_data_path", "Data 数据源目录", "dir"),
            ("prompt_preset_path", "Presets 预设目录", "dir")
        ])
        self._set_grp(frame, "JSON 编辑器", [("json_work_dir", "默认工作目录", "dir")])

        ctk.CTkButton(frame, text="💾 保存所有设置", height=45, fg_color="#6C5CE7", font=("", 14, "bold"),
                      command=self.save_settings).pack(pady=30, padx=20, fill="x")
        return frame

    def _set_grp(self, p, title, items):
        grp = ctk.CTkFrame(p)
        grp.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(grp, text=title, font=("", 14, "bold")).pack(anchor="w", padx=15, pady=10)
        for k, lbl, typ in items:
            row = ctk.CTkFrame(grp, fg_color="transparent")
            row.pack(fill="x", padx=15, pady=5)
            ctk.CTkLabel(row, text=lbl, width=90, anchor="w", text_color="gray30").pack(side="left")
            if isinstance(typ, list):
                v = ctk.StringVar(value=self.config.get(k, typ[0]));
                setattr(self, f"v_{k}", v)
                ctk.CTkOptionMenu(row, values=typ, variable=v).pack(side="left", fill="x", expand=True)
            else:
                e = ctk.CTkEntry(row);
                e.pack(side="left", fill="x", expand=True)
                e.insert(0, str(self.config.get(k, "")));
                setattr(self, f"e_{k}", e)
                if typ in ["file", "dir"]: ctk.CTkButton(row, text="Browse", width=60,
                                                         command=lambda x=e, t=typ: self._browse(x, t)).pack(
                    side="left", padx=5)

    def save_settings(self):
        self.config.update({
            "engine": self.v_engine.get(),
            "winrar_path": self.e_winrar_path.get(),
            "bandizip_path": self.e_bandizip_path.get(),
            "icon_output_path": self.e_icon_output_path.get(),
            "json_work_dir": self.e_json_work_dir.get(),
            # [新增] 保存抽卡机路径
            "prompt_data_path": self.e_prompt_data_path.get(),
            "prompt_preset_path": self.e_prompt_preset_path.get()
        })
        try:
            self.config["max_workers"] = int(self.e_max_workers.get())
        except:
            pass
        # 2. 持久化保存
        self.cfg_mgr.save_config(self.config)

        # 3. 刷新 UI
        self._refresh_preview_list()  # 刷新 Icon 列表

        # [新增] 强制刷新 PromptPanel 以应用新路径
        # 逻辑：销毁旧的 Panel 实例，使用新 Config 创建一个新的
        if hasattr(self, 'frame_prompt'):
            for widget in self.frame_prompt.winfo_children():
                widget.destroy()

            # 重新实例化 (传入更新后的 self.config)
            self.prompt_panel_instance = PromptPanel(self.frame_prompt, self.config)
            # 注意：PromptPanel 内部会自动 pack，不需要这里再 pack

        messagebox.showinfo("提示", "设置已保存")

    def _browse(self, e, t):
        p = filedialog.askdirectory() if t == "dir" else filedialog.askopenfilename(filetypes=[("Exe", "*.exe")])
        if p: e.delete(0, "end"); e.insert(0, p)

    def _browse_dir(self, e):
        p = filedialog.askdirectory()
        if p: e.delete(0, "end"); e.insert(0, p)

    def _log_insert(self, txtbox, msg):
        t = datetime.now().strftime("%H:%M:%S")
        txtbox.configure(state="normal")
        txtbox.insert("end", f"[{t}] {msg}\n")
        txtbox.see("end")
        txtbox.configure(state="disabled")

    def _try_autosave(self):
        """尝试自动保存 (仅当文件路径存在时执行)"""
        # 如果当前有文件路径，则静默保存
        if self.jsoner.current_file_path:
            if self.jsoner.save_file():
                # 在状态栏追加显示保存状态
                current_text = self.lbl_j_status.cget("text")
                # 避免重复追加
                if "自动保存" not in current_text:
                    self.lbl_j_status.configure(text=f"{current_text} (已自动保存)", text_color="#2CC985")
        else:
            # 如果是新文件未保存过，提示用户
            self.log_j("⚠️ 数据已修改 (未自动保存，请先手动保存一次文件)", "warn")