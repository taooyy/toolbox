这是一个非常好的重构请求。将单文件脚本重构为标准的 Python 项目结构，有助于代码的可维护性、扩展性和可读性。

根据你提供的 `b.py` 文件内容，我制定了以下标准的 Python 项目结构。我们将遵循 **MVC (Model-View-Controller)** 的变体思想，将逻辑（Engine）、配置（Config）、界面（GUI）和工具（Utils）分离。

### 📁 项目目录结构

```text
ToolboxProject/
├── main.py                  # 程序入口
├── requirements.txt         # 依赖库列表
├── README.md                # 项目说明
└── src/                     # 源代码目录
    ├── __init__.py
    ├── utils/               # 工具模块
    │   ├── __init__.py
    │   └── paths.py         # 路径处理工具
    ├── config/              # 配置模块
    │   ├── __init__.py
    │   └── manager.py       # 配置管理类
    ├── core/                # 核心业务逻辑 (Model/Controller)
    │   ├── __init__.py
    │   ├── unpack_engine.py # 解压引擎
    │   └── icon_engine.py   # 图标转换引擎
    └── gui/                 # 图形用户界面 (View)
        ├── __init__.py
        └── app.py           # 主窗口与UI逻辑
```

-----

### 1\. `requirements.txt` (依赖管理)

首先定义项目依赖，方便环境配置。

```text
customtkinter
Pillow
```

*(注意：`tkinter` 是 Python 内置库，无需安装；`winrar`/`bandizip` 是外部软件，需要用户自行安装)*

-----

### 2\. `src/utils/paths.py` (路径工具)

将全局的路径获取逻辑提取出来。

```python
import os

def get_base_roots() -> dict:
    """
    获取基础路径配置，自动检测 D 盘或 C 盘。
    """
    drive = "D:\\" if os.path.exists("D:\\") else "C:\\"
    base_tool_dir = os.path.join(drive, "工具箱")

    paths = {
        "config_dir": os.path.join(base_tool_dir, "config"),
        "icon_out_dir": os.path.join(base_tool_dir, "Icon图片"),
        "config_file": os.path.join(base_tool_dir, "config", "app_config.json")
    }

    # 自动创建目录
    for p in [paths["config_dir"], paths["icon_out_dir"]]:
        if not os.path.exists(p):
            try:
                os.makedirs(p)
            except OSError:
                pass

    return paths
```

-----

### 3\. `src/config/manager.py` (配置管理)

将 `ConfigManager` 类独立出来。

```python
import os
import json
from src.utils.paths import get_base_roots

class ConfigManager:
    def __init__(self):
        self.paths = get_base_roots()
        self.config_file = self.paths["config_file"]
        self.default_config = {
            "engine": "WinRAR",
            "winrar_path": r"C:\Program Files\WinRAR\WinRAR.exe",
            "bandizip_path": r"C:\Program Files\Bandizip\Bandizip.exe",
            "max_workers": 4,
            "last_unpack_src": "",
            "last_unpack_dst": "",
            "last_output_mode": "当前目录(散)",
            "delete_source": False,
            "icon_output_path": self.paths["icon_out_dir"],
            "icon_auto_crop": True
        }

    def load_config(self) -> dict:
        if not os.path.exists(self.config_file):
            return self.default_config.copy()
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                config = self.default_config.copy()
                config.update(data)
                return config
        except (json.JSONDecodeError, IOError):
            return self.default_config.copy()

    def save_config(self, data: dict):
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except IOError as e:
            print(f"Error saving config: {e}")
```

-----

### 4\. `src/core/unpack_engine.py` (解压引擎)

解压逻辑独立，增加了类型提示。

```python
import os
import threading
import subprocess
import re
from collections import deque
from typing import Callable, List, Tuple

class UnpackEngine:
    def __init__(self, log_cb: Callable, prog_cb: Callable, fin_cb: Callable):
        self.log_callback = log_cb
        self.progress_callback = prog_cb
        self.finish_callback = fin_cb
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()
        self.stats = {"success": 0, "fail": 0, "total": 0}
        self.password_pool = deque()

    def start_task(self, config: dict, manual_password: str):
        self._stop_event.clear()
        self._pause_event.set()
        self.stats = {"success": 0, "fail": 0, "total": 0}
        threading.Thread(target=self._run_process, args=(config, manual_password), daemon=True).start()

    def pause(self):
        self._pause_event.clear()
        self.log_callback("⏸️ 任务已暂停...", "warn")

    def resume(self):
        self._pause_event.set()
        self.log_callback("▶️ 任务继续", "info")

    def stop(self):
        self._stop_event.set()
        self._pause_event.set()
        self.log_callback("⏹️ 正在停止...", "error")

    def _smart_parse_content(self, text: str) -> List[str]:
        candidates = set()
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        # 优化正则：匹配密码、code、pwd等关键字
        pattern = re.compile(r"(?:密码|pass|pwd|code|解压)[^:：\s]*[:：]\s*([^\s\u4e00-\u9fa5]+)", re.IGNORECASE)
        for line in lines:
            match = pattern.search(line)
            if match:
                candidates.add(match.group(1).strip().rstrip('。，.'))
            clean_line = line.strip(" []【】")
            if 3 < len(clean_line) < 50 and "http" not in clean_line.lower():
                candidates.add(clean_line)
        return list(candidates)

    def _load_txt_passwords(self, source_folder: str) -> List[str]:
        found_pwds = set()
        self.log_callback("🔎 扫描密码...", "info")
        try:
            for root, _, files in os.walk(source_folder):
                for f in files:
                    if f.lower().endswith(('.txt', '.nfo')):
                        try:
                            path = os.path.join(root, f)
                            try:
                                with open(path, 'r', encoding='utf-8') as tf:
                                    content = tf.read()
                            except UnicodeDecodeError:
                                with open(path, 'r', encoding='gbk') as tf:
                                    content = tf.read()
                            for p in self._smart_parse_content(content):
                                found_pwds.add(p)
                        except Exception:
                            continue
        except Exception:
            pass
        return list(found_pwds)

    # === 🔥 新增：分卷首卷判断逻辑 ===
    def _is_main_volume(self, filename: str) -> bool:
        """
        判断文件是否为压缩包的主文件（首卷）。
        如果是分卷的第二部分（如 part2.rar, .z01, .002），则返回 False。
        """
        name_lower = filename.lower()
        
        # 1. 处理 .partN.rar 格式 (例如 test.part1.rar)
        # 提取 .part 后面的数字
        part_match = re.search(r'\.part(\d+)\.rar$', name_lower)
        if part_match:
            # 只有当数字是 1 时，才是主卷
            return int(part_match.group(1)) == 1

        # 2. 处理 .z01, .z02, .r01 等旧式分卷
        # 这些文件的后缀本身就是分卷号，主文件通常是 .zip 或 .rar
        # 如果遇到 .z01 或 .r01 结尾，直接忽略，因为 os.walk 会扫到同名的 .zip/.rar
        if re.search(r'\.[z|r]\d+$', name_lower):
            return False

        # 3. 处理 .001, .002 格式 (例如 data.7z.001)
        # 只有 .001 是主卷
        num_ext_match = re.search(r'\.(\d{3})$', name_lower)
        if num_ext_match:
            return num_ext_match.group(1) == '001'

        # 4. 其他常规后缀 (.zip, .rar, .7z) 默认都是主卷
        return True
    # ===================================

    def _run_process(self, cfg: dict, manual_password: str):
        unique_pwds = [p.strip() for p in manual_password.split()] if manual_password else []
        # 只有在非指定密码模式下才去扫描txt
        if not manual_password: 
            for p in self._load_txt_passwords(cfg['source_folder']):
                if p not in unique_pwds:
                    unique_pwds.append(p)
        self.password_pool = deque(unique_pwds)

        # 增加 .001 支持
        valid_ext = ('.rar', '.zip', '.7z', '.tar', '.gz', '.001')
        tasks = []
        
        if not os.path.exists(cfg['source_folder']):
            self.finish_callback(self.stats, aborted=True)
            return

        self.log_callback("🔍 扫描文件中...", "info")
        
        for root, _, files in os.walk(cfg['source_folder']):
            for f in files:
                # 1. 基本后缀检查
                if f.lower().endswith(valid_ext):
                    # 2. 🔥 智能过滤：跳过分卷的非首卷文件
                    if self._is_main_volume(f):
                        tasks.append((os.path.join(root, f), cfg))
                    else:
                        # 可选：打印跳过信息，或者静默跳过
                        # self.log_callback(f"分卷跳过: {f}", "info")
                        pass

        self.stats["total"] = len(tasks)
        if self.stats["total"] == 0:
            self.log_callback("⚠️ 未发现可处理的压缩包", "warn")
            self.finish_callback(self.stats)
            return

        self.log_callback(f"🚀 发现 {len(tasks)} 个主压缩包，开始处理...", "info")
        
        max_workers = cfg.get("max_workers", 4)
        semaphore = threading.Semaphore(max_workers)
        threads = []

        for i, (fpath, task_cfg) in enumerate(tasks):
            if self._stop_event.is_set():
                break
            self._pause_event.wait()
            semaphore.acquire()
            t = threading.Thread(target=self._unpack_wrapper, args=(fpath, task_cfg, semaphore))
            threads.append(t)
            t.start()
            self.progress_callback((i + 1) / len(tasks))

        for t in threads:
            t.join()
        self.finish_callback(self.stats, aborted=self._stop_event.is_set())

    def _unpack_wrapper(self, fpath: str, cfg: dict, semaphore: threading.Semaphore):
        try:
            if self._stop_event.is_set():
                return
            self._pause_event.wait()
            if self._try_unpack_with_pool(fpath, cfg):
                self.stats["success"] += 1
            else:
                self.stats["fail"] += 1
        finally:
            semaphore.release()

    def _try_unpack_with_pool(self, fpath: str, cfg: dict) -> bool:
        fname = os.path.basename(fpath)
        
        # 修正：对于 .001 或 .part1.rar 文件，在生成文件夹名时要去掉这些后缀
        # 简单处理：如果是 .part1.rar，去掉 .part1.rar；如果是 .7z.001，去掉 .001
        base = os.path.splitext(fname)[0] # 默认去掉最后一个后缀
        
        # 针对特殊分卷名的文件夹命名优化
        if ".part" in fname.lower() and fname.lower().endswith(".rar"):
            # A.part1.rar -> A
            base = re.sub(r'\.part\d+$', '', base, flags=re.IGNORECASE)
        elif fname.lower().endswith(".001"):
            # A.7z.001 -> A.7z (base已经是 A.7z 了) -> 如果想纯名可以是 A
            if base.lower().endswith(".7z"):
                base = base[:-3]
        elif fname.lower().endswith(".tar.gz"):
             base = fname[:-7]

        # 临时将优化后的 base 存入 cfg 传给 execute (这里稍微 hack 一下，或者修改 execute 逻辑)
        # 更好的方式是在 _execute_unpack 内部重新计算 dest
        
        current_candidates = list(self.password_pool) if self.password_pool else [""]
        for pwd in current_candidates:
            if self._stop_event.is_set():
                return False
            # 注意：这里传进去的 base 是为了下面计算路径用的，但 _execute_unpack 里又算了一遍
            # 我们直接在 _execute_unpack 里优化路径计算
            if self._execute_unpack(fpath, cfg, pwd):
                if pwd and len(self.password_pool) > 1 and self.password_pool[0] != pwd:
                    try:
                        self.password_pool.remove(pwd)
                        self.password_pool.appendleft(pwd)
                    except ValueError:
                        pass
                self.log_callback(f"✅ 成功: {fname}", "success")
                if cfg['delete_source']:
                    # 🔥 删除逻辑增强：如果是分卷成功，需要删除所有分卷吗？
                    # 风险较高，建议如果是分卷，只删除当前文件或者不做操作。
                    # 简单起见，目前只删除传入的这个主文件。
                    # 如果要删除所有分卷，需要额外的逻辑去寻找同名分卷。
                    try:
                        os.remove(fpath) 
                    except OSError:
                        pass
                return True
        self.log_callback(f"❌ 失败: {fname}", "error")
        return False

    def _execute_unpack(self, fpath: str, cfg: dict, pwd: str) -> bool:
        fname = os.path.basename(fpath)
        fdir = os.path.dirname(fpath)
        
        # === 路径名优化逻辑 ===
        base = os.path.splitext(fname)[0]
        name_lower = fname.lower()
        if name_lower.endswith(".tar.gz"):
            base = fname[:-7]
        # 处理 part1.rar -> base 应该是文件名本身，不带 part1
        elif ".part" in name_lower and name_lower.endswith(".rar"):
            base = re.sub(r'\.part\d+$', '', base, flags=re.IGNORECASE)
        # 处理 .001
        elif name_lower.endswith(".001"):
             # data.7z.001 -> base=data.7z -> 再去一次后缀 -> data
             base = os.path.splitext(base)[0]
        # ====================

        mode = cfg['output_mode']
        cpath = cfg['custom_output_path']
        dest = fdir
        
        if mode == "current_smart":
            dest = os.path.join(fdir, base)
        elif mode == "custom_direct":
            dest = cpath if cpath else fdir
        elif mode == "custom_smart":
            dest = os.path.join(cpath, base) if cpath else fdir
        
        if not os.path.exists(dest):
            try:
                os.makedirs(dest)
            except OSError:
                pass

        cmd = [cfg['engine_path'], "x", "-y"]
        
        if "WinRAR" in cfg['engine']:
            # WinRAR 只要给第一个分卷，它会自动处理后续的
            cmd.extend(["-ibck", fpath, dest + os.sep, f"-p{pwd}" if pwd else "-p-"])
        else:
            # Bandizip 逻辑类似
            cmd.extend([f"-o:{dest}", fpath])
            if pwd:
                cmd.append(f"-p:{pwd}")

        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=si).returncode == 0
        except Exception:
            return False
```

-----

### 5\. `src/core/icon_engine.py` (图标引擎)

```python
import os
import threading
from typing import Callable, List
from PIL import Image

class IconEngine:
    def __init__(self, log_cb: Callable, prog_cb: Callable, fin_cb: Callable):
        self.log = log_cb
        self.prog = prog_cb
        self.fin = fin_cb

    def start(self, files: List[str], out_dir: str, size_mode: str, custom_size: str, auto_crop: bool):
        threading.Thread(target=self._run, args=(files, out_dir, size_mode, custom_size, auto_crop), daemon=True).start()

    def _run(self, files: List[str], out_dir: str, size_mode: str, custom_size: str, auto_crop: bool):
        target_sizes = []
        max_target_dim = 256  # 默认检测基准

        # === 1. 解析目标尺寸 ===
        if "标准" in size_mode:
            target_sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
            max_target_dim = 256
        elif "自定义" in size_mode:
            try:
                s = int(custom_size)
                target_sizes = [(s, s)]
                max_target_dim = s
            except ValueError:
                self.fin({"success": 0, "fail": len(files), "skipped": []})
                return
        else:
            try:
                s = int(size_mode.split('x')[0])
                target_sizes = [(s, s)]
                max_target_dim = s
            except (ValueError, IndexError):
                target_sizes = [(256, 256)]
                max_target_dim = 256

        if not os.path.exists(out_dir):
            try:
                os.makedirs(out_dir)
            except OSError:
                pass

        stats = {"success": 0, "fail": 0, "skipped": []}
        total = len(files)

        for i, fpath in enumerate(files):
            fname = os.path.basename(fpath)
            try:
                img = Image.open(fpath)

                # === 2. 增加尺寸判断逻辑 ===
                w, h = img.size
                if w < max_target_dim or h < max_target_dim:
                    stats["skipped"].append(f"{fname} (尺寸 {w}x{h} 小于 {max_target_dim})")
                    self.log(f"⚠️ 跳过: {fname} (尺寸不足)", "warn")
                    self.prog((i + 1) / total)
                    continue

                if img.mode != "RGBA":
                    img = img.convert("RGBA")
                if auto_crop:
                    w, h = img.size
                    m = min(w, h)
                    img = img.crop(((w - m) / 2, (h - m) / 2, (w + m) / 2, (h + m) / 2))

                name_no_ext = os.path.splitext(fname)[0]
                save_path = os.path.join(out_dir, f"{name_no_ext}.ico")

                img.save(save_path, format='ICO', sizes=target_sizes)
                stats["success"] += 1
                self.log(f"✅: {fname}", "success")
            except Exception as e:
                stats["fail"] += 1
                self.log(f"❌: {fname}", "error")

            self.prog((i + 1) / total)

        self.fin(stats)
```

-----

### 6\. `src/gui/app.py` (图形界面)

这是最复杂的部分，我们导入前面定义好的模块。

```python
import os
import tkinter as tk
from tkinter import filedialog, Listbox, ttk, messagebox
from datetime import datetime
import customtkinter as ctk
from PIL import Image

# === 新增：设置窗口图标 ===
        # 假设 logo.ico 在项目根目录，或者你可以把它放在 src/assets/ 下
        # 注意：这里需要处理一下路径，防止打包后找不到
        try:
            self.iconbitmap("logo.ico")
        except:
            pass  # 防止开发环境找不到文件报错
        # =======================

from src.config.manager import ConfigManager
from src.core.unpack_engine import UnpackEngine
from src.core.icon_engine import IconEngine

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("全能工具箱 - 生产力增强版")
        self.geometry("1000x750")
        ctk.set_appearance_mode("Light")

        self.cfg_mgr = ConfigManager()
        self.config = self.cfg_mgr.load_config()

        self.unpacker = UnpackEngine(self.log_u, self.prog_u, self.fin_u)
        self.iconer = IconEngine(self.log_i, self.prog_i, self.fin_i)

        self.icon_files = []
        self.u_running = False
        self.u_paused = False
        self.current_preview_img = None

        self._init_layout()
        self.switch_tab("unpack")

    def _init_layout(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Sidebar
        self.sidebar = ctk.CTkFrame(self, width=180, corner_radius=0, fg_color=("gray95", "gray20"))
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        ctk.CTkLabel(self.sidebar, text="📦 工具箱", font=("", 20, "bold")).pack(pady=(30, 20))

        self.btn_nav_unpack = self._nav_btn("解压专家", "unpack")
        self.btn_nav_icon = self._nav_btn("图片转Icon", "icon")
        self.btn_nav_setting = self._nav_btn("全局设置", "setting")

        # Main Area
        self.main_area = ctk.CTkFrame(self, fg_color="transparent")
        self.main_area.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        self.main_area.grid_rowconfigure(0, weight=1)
        self.main_area.grid_columnconfigure(0, weight=1)

        self.frame_unpack = self._ui_unpack()
        self.frame_icon = self._ui_icon()
        self.frame_setting = self._ui_setting()

    def _nav_btn(self, text, tag):
        btn = ctk.CTkButton(self.sidebar, text=text, height=45, fg_color="transparent",
                            text_color=("gray10", "white"), anchor="w", font=("", 14),
                            command=lambda: self.switch_tab(tag))
        btn.pack(fill="x", padx=10, pady=5)
        return btn

    def switch_tab(self, tag):
        for f in [self.frame_unpack, self.frame_icon, self.frame_setting]:
            f.grid_forget()
        for b in [self.btn_nav_unpack, self.btn_nav_icon, self.btn_nav_setting]:
            b.configure(fg_color="transparent")

        if tag == "unpack":
            self.frame_unpack.grid(row=0, column=0, sticky="nsew")
            self.btn_nav_unpack.configure(fg_color=("gray85", "gray30"))
        elif tag == "icon":
            self.frame_icon.grid(row=0, column=0, sticky="nsew")
            self.btn_nav_icon.configure(fg_color=("gray85", "gray30"))
            self._refresh_preview_list()
        elif tag == "setting":
            self.frame_setting.grid(row=0, column=0, sticky="nsew")
            self.btn_nav_setting.configure(fg_color=("gray85", "gray30"))

    # ==========================
    # Tab 1: 解压
    # ==========================
    def _ui_unpack(self):
        frame = ctk.CTkFrame(self.main_area, fg_color="transparent")
        st_box = ctk.CTkFrame(frame, height=50)
        st_box.pack(fill="x", pady=(0, 10))
        self.lbl_u_status = ctk.CTkLabel(st_box, text="准备就绪", font=("", 16, "bold"), text_color="#3B8ED0")
        self.lbl_u_status.pack(side="left", padx=20, pady=10)
        self.bar_u = ctk.CTkProgressBar(st_box)
        self.bar_u.set(0)
        self.bar_u.pack(side="left", fill="x", expand=True, padx=20)

        cfg_box = ctk.CTkFrame(frame)
        cfg_box.pack(fill="x", pady=5)

        r1 = ctk.CTkFrame(cfg_box, fg_color="transparent")
        r1.pack(fill="x", padx=10, pady=5)
        self.entry_u_src = ctk.CTkEntry(r1, placeholder_text="源文件夹")
        self.entry_u_src.pack(side="left", fill="x", expand=True)
        self.entry_u_src.insert(0, self.config.get("last_unpack_src", ""))
        ctk.CTkButton(r1, text="📂", width=40, command=lambda: self._browse_dir(self.entry_u_src)).pack(side="left", padx=5)
        
        self.om_u_mode = ctk.CTkOptionMenu(r1, values=["当前目录(散)", "当前+智能文件夹", "指定目录(混)",
                                                       "指定+智能文件夹"], width=140)
        self.om_u_mode.pack(side="left")
        self.om_u_mode.set(self.config.get("last_output_mode", "当前目录(散)"))

        r2 = ctk.CTkFrame(cfg_box, fg_color="transparent")
        r2.pack(fill="x", padx=10, pady=5)
        self.entry_u_pwd = ctk.CTkEntry(r2, placeholder_text="密码(空格分隔)")
        self.entry_u_pwd.pack(side="left", fill="x", expand=True)
        self.entry_u_dst = ctk.CTkEntry(r2, placeholder_text="输出位置")
        self.entry_u_dst.pack(side="left", fill="x", expand=True, padx=5)
        self.entry_u_dst.insert(0, self.config.get("last_unpack_dst", ""))
        ctk.CTkButton(r2, text="📂", width=40, command=lambda: self._browse_dir(self.entry_u_dst)).pack(side="left", padx=5)

        self.var_del = ctk.BooleanVar(value=self.config.get("delete_source", False))
        ctk.CTkCheckBox(cfg_box, text="解压后删除源文件", variable=self.var_del).pack(anchor="w", padx=15, pady=10)

        self.txt_u_log = ctk.CTkTextbox(frame, font=("Consolas", 12))
        self.txt_u_log.pack(fill="both", expand=True, pady=10)

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

    def log_u(self, m, l):
        self.after(0, lambda: self._log_insert(self.txt_u_log, m))

    def prog_u(self, v):
        self.after(0, lambda: self.bar_u.set(v))

   def fin_u(self, s, aborted=False):  # <--- 修改点：把 a 改为 aborted
        def _f():
            self.u_running = False
            self._toggle_u_btns(False)
            # 下面所有的 a 也要改成 aborted
            self.bar_u.set(0 if aborted else 1.0)
            t = "已取消" if aborted else f"完成! 成功{s['success']}"
            c = "#FF4D4D" if aborted else "#3B8ED0"
            self.lbl_u_status.configure(text=t, text_color=c)
            if not aborted: 
                self._log_insert(self.txt_u_log, "=" * 20 + "\n" + t)

        self.after(0, _f)

    # ==========================
    # Tab 2: 图标
    # ==========================
    def _ui_icon(self):
        frame = ctk.CTkFrame(self.main_area, fg_color="transparent")
        frame.grid_columnconfigure((0, 1, 2), weight=1, uniform="icon_cols")
        frame.grid_rowconfigure(0, weight=1)

        # 左栏
        left = ctk.CTkFrame(frame)
        left.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        ctk.CTkLabel(left, text="待处理图片", font=("", 14, "bold")).pack(pady=10)
        self.lst_icon = Listbox(left, bd=0, highlightthickness=0, font=("", 10), selectbackground="#3B8ED0")
        self.lst_icon.pack(fill="both", expand=True, padx=5, pady=5)
        btns = ctk.CTkFrame(left, fg_color="transparent")
        btns.pack(fill="x", pady=5)
        ctk.CTkButton(btns, text="➕ 添加", width=80, command=self.add_imgs).pack(side="left", padx=5)
        ctk.CTkButton(btns, text="🗑️ 清空", width=60, fg_color="gray",
                      command=lambda: [self.lst_icon.delete(0, "end"), self.icon_files.clear()]).pack(side="right",
                                                                                                      padx=5)

        # 中栏
        mid = ctk.CTkFrame(frame)
        mid.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        ctk.CTkLabel(mid, text="转换配置", font=("", 14, "bold")).pack(pady=15)
        ctk.CTkLabel(mid, text="生成尺寸:", text_color="gray").pack(anchor="w", padx=20)
        self.cb_vals = ["标准多尺寸 (推荐)", "256x256", "128x128", "64x64", "48x48", "32x32", "16x16",
                        "自定义 (手动输入)"]
        self.cb_size = ttk.Combobox(mid, values=self.cb_vals, state="readonly")
        self.cb_size.pack(fill="x", padx=20, pady=5)
        self.cb_size.set("标准多尺寸 (推荐)")
        self.cb_size.bind("<<ComboboxSelected>>", self._on_icon_combo)
        self.entry_i_cust = ctk.CTkEntry(mid, placeholder_text="输入数字 px")
        self.entry_i_cust.pack(fill="x", padx=20, pady=(5, 15))
        self.entry_i_cust.configure(state="disabled")
        self.var_crop = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(mid, text="智能居中裁剪", variable=self.var_crop).pack(anchor="w", padx=20, pady=5)
        ctk.CTkFrame(mid, height=2, fg_color="gray80").pack(fill="x", padx=10, pady=20)
        self.lbl_i_status = ctk.CTkLabel(mid, text="等待开始...", text_color="gray")
        self.lbl_i_status.pack(pady=5)
        self.bar_i = ctk.CTkProgressBar(mid)
        self.bar_i.set(0)
        self.bar_i.pack(fill="x", padx=20, pady=5)
        self.btn_i_run = ctk.CTkButton(mid, text="⚡ 开始转换", height=50, font=("", 14, "bold"), command=self.run_icon)
        self.btn_i_run.pack(fill="x", padx=20, pady=20)

        # 右栏
        right = ctk.CTkFrame(frame)
        right.grid(row=0, column=2, sticky="nsew", padx=5, pady=5)
        ctk.CTkLabel(right, text="结果预览", font=("", 14, "bold")).pack(pady=10)
        self.preview_box = ctk.CTkFrame(right, height=150, fg_color=("gray90", "gray30"))
        self.preview_box.pack(fill="x", padx=10, pady=5)
        self.preview_box.pack_propagate(False)
        self.lbl_preview_img = ctk.CTkLabel(self.preview_box, text="点击下方文件预览")
        self.lbl_preview_img.place(relx=0.5, rely=0.5, anchor="center")
        self.lst_out = Listbox(right, bd=0, highlightthickness=0, font=("", 9), selectbackground="#2CC985")
        self.lst_out.pack(fill="both", expand=True, padx=10, pady=5)
        self.lst_out.bind("<<ListboxSelect>>", self._on_preview_click)
        ctk.CTkButton(right, text="🔄 刷新列表", height=30, fg_color="#3B8ED0", command=self._refresh_preview_list).pack(
            fill="x", padx=10, pady=10)

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
        files = [f for f in os.listdir(out_dir) if f.lower().endswith(".ico")]
        files.sort(key=lambda x: os.path.getmtime(os.path.join(out_dir, x)), reverse=True)
        for f in files: self.lst_out.insert("end", f)

    def _on_preview_click(self, event):
        sel = self.lst_out.curselection()
        if not sel: return
        fname = self.lst_out.get(sel)
        fpath = os.path.join(self.config["icon_output_path"], fname)

        try:
            img = Image.open(fpath)
            img.thumbnail((128, 128))
            ctk_img = ctk.CTkImage(img, size=img.size)
            self.current_preview_img = ctk_img 
            self.lbl_preview_img.configure(image=ctk_img, text="")
        except Exception:
            self.lbl_preview_img.configure(image=None, text="预览失败")

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

    # ==========================
    # Tab 3: 全局设置
    # ==========================
    def _ui_setting(self):
        frame = ctk.CTkScrollableFrame(self.main_area, fg_color="transparent")
        self._set_grp(frame, "解压引擎",
                      [("engine", "类型", ["WinRAR", "Bandizip"]), ("winrar_path", "WinRAR.exe", "file"),
                       ("bandizip_path", "Bandizip.exe", "file"), ("max_workers", "线程数", None)])
        self._set_grp(frame, "图片转换", [("icon_output_path", "Icon输出位置", "dir")])
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
        self.config.update({"engine": self.v_engine.get(), "winrar_path": self.e_winrar_path.get(),
                            "bandizip_path": self.e_bandizip_path.get(),
                            "icon_output_path": self.e_icon_output_path.get()})
        try:
            self.config["max_workers"] = int(self.e_max_workers.get())
        except:
            pass
        self.cfg_mgr.save_config(self.config)
        self._refresh_preview_list()
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
```

-----

### 7\. `main.py` (项目入口)

最后，这是整个项目的入口文件。

```python
from src.gui.app import App

if __name__ == "__main__":
    app = App()
    app.mainloop()
```

### 如何运行

1.  创建一个文件夹，例如 `ToolboxProject`。
2.  按照上述目录结构创建文件，并将对应的代码复制进去。
3.  在终端运行 `pip install customtkinter Pillow` 安装依赖。
4.  在根目录下运行 `python main.py` 启动程序。