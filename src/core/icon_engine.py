import os
import threading
import base64  # [新增] 用于编码图片数据
from io import BytesIO  # [新增] 用于内存操作
from typing import Callable, List
from PIL import Image


class IconEngine:
    def __init__(self, log_cb: Callable, prog_cb: Callable, fin_cb: Callable):
        self.log = log_cb
        self.prog = prog_cb
        self.fin = fin_cb

    def start(self, files: List[str], out_dir: str, size_mode: str, custom_size: str, auto_crop: bool):
        threading.Thread(target=self._run, args=(files, out_dir, size_mode, custom_size, auto_crop),
                         daemon=True).start()

    def _run(self, files: List[str], out_dir: str, size_mode: str, custom_size: str, auto_crop: bool):
        # === [新增] 判断是否为 SVG 模式 ===
        is_svg_mode = "SVG" in size_mode.upper()

        target_sizes = []
        max_target_dim = 256

        # 如果是 SVG，不需要计算 target_sizes，跳过尺寸逻辑
        if not is_svg_mode:
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

                # SVG 模式下通常不检查最小尺寸，或者你可以保留此检查
                if not is_svg_mode and (w < max_target_dim or h < max_target_dim):
                    stats["skipped"].append(f"{fname} (尺寸 {w}x{h} 小于 {max_target_dim})")
                    self.log(f"⚠️ 跳过: {fname} (尺寸不足)", "warn")
                    self.prog((i + 1) / total)
                    continue

                if img.mode != "RGBA":
                    img = img.convert("RGBA")

                # 自动裁剪逻辑 (SVG 模式也生效)
                if auto_crop:
                    w, h = img.size
                    m = min(w, h)
                    img = img.crop(((w - m) / 2, (h - m) / 2, (w + m) / 2, (h + m) / 2))

                name_no_ext = os.path.splitext(fname)[0]

                # === [修改] 分支处理：保存为 SVG 或 ICO ===
                if is_svg_mode:
                    save_path = os.path.join(out_dir, f"{name_no_ext}.svg")
                    self._save_as_svg(img, save_path)
                else:
                    save_path = os.path.join(out_dir, f"{name_no_ext}.ico")
                    img.save(save_path, format='ICO', sizes=target_sizes)

                stats["success"] += 1
                self.log(f"✅: {fname}", "success")
            except Exception as e:
                stats["fail"] += 1
                self.log(f"❌: {fname} ({str(e)})", "error")

            self.prog((i + 1) / total)

        self.fin(stats)

    # === [新增] SVG 保存辅助函数 ===
    def _save_as_svg(self, img: Image.Image, path: str):
        """将 PIL Image 封装为 SVG 文件"""
        # 1. 将图片转换为 PNG 字节流
        buffered = BytesIO()
        img.save(buffered, format="PNG")

        # 2. 转为 Base64 字符串
        img_str = base64.b64encode(buffered.getvalue()).decode('utf-8')

        # 3. 构造 SVG XML 内容
        w, h = img.size
        svg_content = (
            f'<svg width="{w}" height="{h}" version="1.1" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">\n'
            f'  <image width="{w}" height="{h}" xlink:href="data:image/png;base64,{img_str}"/>\n'
            f'</svg>'
        )

        # 4. 写入文件
        with open(path, "w", encoding="utf-8") as f:
            f.write(svg_content)