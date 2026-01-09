import json
import os
import shutil
from typing import Callable, Dict, Any


class JsonEngine:
    def __init__(self, log_cb: Callable):
        self.log = log_cb
        self.current_data = {}
        self.current_file_path = ""

    def new_file(self):
        """重置为空数据"""
        self.current_data = {}
        self.current_file_path = ""
        self.log("📄 新建空白项目", "info")

    def load_file(self, filepath: str) -> bool:
        """加载并清洗 JSON 数据"""
        if not os.path.exists(filepath):
            self.log("❌ 文件不存在", "error")
            return False

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)

            # === 核心：脏数据清洗 ===
            # 目标结构: { "key": { ... }, "key2": { ... } }
            cleaned_data = {}
            dirty_count = 0

            if isinstance(raw_data, dict):
                for k, v in raw_data.items():
                    if isinstance(v, dict):
                        cleaned_data[str(k)] = v
                    else:
                        dirty_count += 1
            else:
                self.log("❌ JSON 根节点必须是对象 (Dict)", "error")
                return False

            self.current_data = cleaned_data
            self.current_file_path = filepath

            msg = f"📂 加载成功: {os.path.basename(filepath)}"
            if dirty_count > 0:
                msg += f" (已清洗 {dirty_count} 条无效数据)"
            self.log(msg, "success")
            return True

        except json.JSONDecodeError:
            self.log("❌ 文件格式错误，非有效 JSON", "error")
            return False
        except Exception as e:
            self.log(f"❌ 加载失败: {str(e)}", "error")
            return False

    def save_file(self, filepath: str = None) -> bool:
        """保存文件"""
        target = filepath if filepath else self.current_file_path
        if not target:
            self.log("⚠️ 未指定保存路径", "warn")
            return False

        try:
            # 备份
            if os.path.exists(target):
                shutil.copy(target, target + ".bak")

            with open(target, 'w', encoding='utf-8') as f:
                json.dump(self.current_data, f, indent=4, ensure_ascii=False)

            self.current_file_path = target
            self.log(f"💾 保存成功: {os.path.basename(target)}", "success")
            return True
        except Exception as e:
            self.log(f"❌ 保存失败: {str(e)}", "error")
            return False

    def add_types(self, types_str: str):
        """批量新建类型 (逗号或换行分隔)"""
        if not types_str.strip(): return

        # 支持逗号、换行、空格分隔
        keys = types_str.replace('\n', ',').replace(' ', ',').split(',')
        added = 0
        for k in keys:
            k = k.strip()
            if k and k not in self.current_data:
                self.current_data[k] = {}
                added += 1

        if added > 0:
            self.log(f"✅ 批量新增 {added} 个类型", "success")
        else:
            self.log("⚠️ 未新增类型 (可能已存在或输入为空)", "warn")

    def add_kv(self, type_key: str, key: str, value: str):
        """向指定类型添加数据"""
        if type_key not in self.current_data:
            self.log(f"❌ 类型 '{type_key}' 不存在", "error")
            return

        self.current_data[type_key][key] = value
        self.log(f"✅ 添加数据 [{type_key}] {key} : {value}", "success")

    def delete_item(self, type_key: str, item_key: str = None):
        """删除类型或类型下的具体键值"""
        if type_key in self.current_data:
            if item_key is None:
                # 删除整个类型
                del self.current_data[type_key]
                self.log(f"🗑️ 已删除类型: {type_key}", "success")
            elif item_key in self.current_data[type_key]:
                # 删除具体条目
                del self.current_data[type_key][item_key]
                self.log(f"🗑️ 已删除条目: [{type_key}] {item_key}", "success")

    def swap_kv(self, type_key: str):
        """交换指定类型下的键值对"""
        if type_key not in self.current_data:
            self.log(f"❌ 类型 '{type_key}' 不存在", "error")
            return

        original_dict = self.current_data[type_key]
        new_dict = {}
        skipped = 0

        for k, v in original_dict.items():
            # 只有当值是字符串或数字时才能作为 Key
            if isinstance(v, (str, int, float)):
                new_dict[str(v)] = k
            else:
                skipped += 1

        self.current_data[type_key] = new_dict
        msg = f"🔄 类型 '{type_key}' 键值翻转完成"
        if skipped > 0:
            msg += f" (跳过 {skipped} 个复杂值)"
        self.log(msg, "success")

    def add_batch_data(self, type_key: str, raw_text: str, mode: str = "auto"):
        """
        批量添加数据
        :param type_key: 目标分类 Key
        :param raw_text: 输入的原始文本
        :param mode: 解析模式 "auto" (自动识别) 或 "lines" (双行块结构)
        """
        if type_key not in self.current_data:
            self.log(f"❌ 类型 '{type_key}' 不存在，请先新建类型", "error")
            return

        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        success_count = 0

        # --- 模式 A：双行模式 (奇数行Key, 偶数行Value) ---
        if mode == "lines":
            if len(lines) % 2 != 0:
                self.log("⚠️ 双行模式下，有效行数必须是偶数 (Key + Value 成对出现)", "warn")

            for i in range(0, len(lines) - 1, 2):
                k = lines[i]
                v = lines[i + 1]
                self.current_data[type_key][k] = v
                success_count += 1

        # --- 模式 B：自动智能分割 (修复冒号干扰问题) ---
        else:
            for line in lines:
                k, v = None, None
                found_chinese = False

                # 1. 【最高优先级】中英文边界切割
                # 能够解决: "tag: subtag (source) 翻译" 这种 Key 内部带冒号的情况
                for i, char in enumerate(line):
                    if '\u4e00' <= char <= '\u9fa5':
                        # 找到第一个中文字符，直接切割
                        raw_k = line[:i]
                        v = line[i:]

                        # 清理 Key 尾部可能残留的分隔符 (比如 "girl: 女孩" 切割后 key是 "girl: ")
                        k = raw_k.rstrip(":：=,， ").strip()
                        found_chinese = True
                        break

                # 2. 如果没有中文，才尝试使用符号分割 (纯英文/数字情况)
                if not found_chinese:
                    if ":" in line:
                        k, v = line.split(":", 1)
                    elif "：" in line:
                        k, v = line.split("：", 1)
                    elif "=" in line:
                        k, v = line.split("=", 1)
                    elif "," in line:
                        k, v = line.split(",", 1)
                    elif "，" in line:
                        k, v = line.split("，", 1)
                    else:
                        # 兜底：按空格切分 (处理 "1girl solo")
                        parts = line.split(None, 1)
                        if len(parts) == 2:
                            k, v = parts
                        elif len(parts) == 1:
                            k, v = parts[0], ""

                # 3. 数据清洗与保存
                if k is not None:
                    k = k.strip()
                    v = v.strip() if v else ""
                    if k:
                        self.current_data[type_key][k] = v
                        success_count += 1

        if success_count > 0:
            self.log(f"✅ 在 [{type_key}] 下成功添加 {success_count} 条数据", "success")
        else:
            self.log("⚠️ 未识别到有效数据，请检查格式", "warn")

    def get_preview_data(self) -> Dict:
        return self.current_data