import os


def get_base_roots() -> dict:
    """
    获取基础路径配置，自动检测 D 盘或 C 盘。
    """
    # 检测盘符
    drive = "D:\\" if os.path.exists("D:\\") else "C:\\"
    base_tool_dir = os.path.join(drive, "工具箱")

    paths = {
        "config_dir": os.path.join(base_tool_dir, "config"),
        "icon_out_dir": os.path.join(base_tool_dir, "Icon图片"),

        # === 关键修复点：必须有下面这一行 ===
        "json_dir": os.path.join(base_tool_dir, "json"),
        # ===================================

        "config_file": os.path.join(base_tool_dir, "config", "app_config.json")
    }

    # 自动创建目录 (确保也创建 json_dir)
    for p in [paths["config_dir"], paths["icon_out_dir"], paths["json_dir"]]:
        if not os.path.exists(p):
            try:
                os.makedirs(p)
            except OSError:
                pass

    return paths