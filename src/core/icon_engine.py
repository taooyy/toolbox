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
        max_target_dim = 256
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
            except Exception:
                stats["fail"] += 1
                self.log(f"❌: {fname}", "error")
            self.prog((i + 1) / total)
        self.fin(stats)

