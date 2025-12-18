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
            "icon_auto_crop": True,
            # === 新增 JSON 配置 ===
            "json_work_dir": self.paths["json_dir"]
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

