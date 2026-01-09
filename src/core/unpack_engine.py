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
        base = os.path.splitext(fname)[0]  # 默认去掉最后一个后缀

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