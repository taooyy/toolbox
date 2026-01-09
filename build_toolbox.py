import PyInstaller.__main__
import os
import shutil

# 1. 定义图标名称 (确保你根目录下有 logo.ico，如果没有就删掉 --icon 这一行)
ICON_FILE = "icon.ico"
HAS_ICON = os.path.exists(ICON_FILE)

# 2. 构建 PyInstaller 命令参数
args = [
    'main.py',  # 入口文件
    '--name=Toolbox',  # exe 名字
    '--noconsole',  # 不显示黑窗口
    '--onefile',  # 单文件模式
    '--clean',  # 清理缓存

    # === 关键修复 1: 强制收集 customtkinter ===
    '--collect-all=customtkinter',

    # === 关键修复 2: 包含 src 源码目录 ===
    '--add-data=src;src',

    # === 关键修复 3: 显式声明隐藏导入 ===
    '--hidden-import=PIL',
    '--hidden-import=PIL.Image',
    '--hidden-import=PIL.ImageTk',
    '--hidden-import=customtkinter',
    '--hidden-import=tkinter',
]

# 如果有图标，添加图标参数
if HAS_ICON:
    args.append(f'--icon={ICON_FILE}')
    # 将图标也作为资源打包进去 (可选，用于程序内部引用)
    args.append(f'--add-data={ICON_FILE};.')

print("🚀 开始打包... 请耐心等待，可能需要几分钟。")

# 3. 运行 PyInstaller
PyInstaller.__main__.run(args)

print("\n✅ 打包完成！")
print(f"请在 dist 文件夹中查找 Toolbox.exe")