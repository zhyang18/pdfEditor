"""
PyInstaller 独立自包含 Windows EXE 自动化打包编译脚本。
将 PDF 编辑器及其所有依赖项、C扩展、动态链接库、QSS样式表与高清矢量图标
全部打包为完全自包含的独立程序。

针对启动速度深度优化：
1. 默认采用便携免安装绿色目录模式 (--onedir)，免除单文件运行时往临时目录解压 200MB+ 文件的巨大耗时与杀毒软件扫描瓶颈；
2. 集成 PyInstaller 原生 C 级 Bootloader 启动画面 (--splash)，在双击 EXE 文件的第一毫秒由操作系统直接弹出启动窗口，彻底解决启动真空期；
3. 裁剪排除未使用的庞大 Qt 子模块（QtQuick、QtQml、QtNetwork 等），缩减体积并加速动态链接库载入；
4. 保留 --onefile 命令行参数切换能力，满足不同场景的分发交付需求。
"""

import os
import sys
import PyInstaller.__main__


def build(onefile: bool = False) -> int:
    """
    执行 PyInstaller 打包构建。

    @param onefile 是否打包为单文件独立 EXE（默认为 False，即打包为便携绿色目录以获取秒级冷启动；若传入 True 则打包为单个 exe）
    @return PyInstaller 构建进程返回值，0 表示打包成功
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    entry_script = os.path.join(base_dir, "app.py")
    icon_path = os.path.join(base_dir, "assets", "app.ico")
    assets_dir = os.path.join(base_dir, "assets")
    splash_path = os.path.join(base_dir, "assets", "splash.png")

    # 若启动封面图不存在，则自动调用生成器创建
    if not os.path.isfile(splash_path):
        try:
            from assets.generate_splash import generate_splash_image
            generate_splash_image(splash_path)
        except Exception as e:
            print(f"警告：自动生成启动过渡封面图失败：{e}")

    # 构建 PyInstaller 命令行参数列表，-y 表示自动覆盖旧的 dist 目录
    args = [
        entry_script,
        "--name=PdfEditor",
        "--noconsole",
        "--clean",
        "-y",
        f"--icon={icon_path}",
        f"--add-data={assets_dir};assets",
        "--collect-data=pymupdf",
        # 排除未使用的 AI 布局模型与体积庞大的无用子模块
        "--exclude-module=pymupdf.layout",
        "--exclude-module=PySide6.QtQuick",
        "--exclude-module=PySide6.QtQml",
        "--exclude-module=PySide6.QtSql",
        "--exclude-module=PySide6.QtNetwork",
        "--exclude-module=PySide6.QtTest",
        "--exclude-module=PySide6.QtBluetooth",
        "--exclude-module=PySide6.QtSensors",
        "--exclude-module=PySide6.QtSerialPort",
        "--exclude-module=PySide6.QtPositioning",
        "--exclude-module=PySide6.QtWebChannel",
        "--exclude-module=PySide6.QtWebEngineCore",
        "--exclude-module=PySide6.QtWebEngineWidgets",
        "--exclude-module=PySide6.QtRemoteObjects",
        "--exclude-module=PySide6.QtScxml",
        "--exclude-module=PySide6.Qt3DCore",
        "--exclude-module=tkinter",
        "--exclude-module=matplotlib",
        "--exclude-module=scipy",
        # 显式保留核心依赖与扩展
        "--hidden-import=PySide6.QtSvg",
        "--hidden-import=pymupdf",
        "--hidden-import=pdf2docx",
        "--hidden-import=docx",
        "--hidden-import=win32com",
        "--hidden-import=pythoncom",
        "--hidden-import=comtypes",
    ]

    manifest_path = os.path.join(base_dir, "app.manifest")
    if os.path.isfile(manifest_path):
        args.append(f"--manifest={manifest_path}")

    # 若启动封面图就绪，注入原生 C 级 Bootloader Splash 选项并设定主屏幕物理居中
    if os.path.isfile(splash_path):
        args.append(f"--splash={splash_path}")
        args.append("--splash-center=primary")

    if onefile:
        args.append("--onefile")
    else:
        args.append("--onedir")

    print(f"==================================================")
    print(f" 开始打包 PDF 编辑器自包含独立版本")
    print(f" 打包模式: {'单文件独立 EXE (--onefile)' if onefile else '便携绿色目录 (--onedir, 推荐秒开)'}")
    print(f" C 级启动画面: {'已启用 (双击瞬间原生秒弹)' if os.path.isfile(splash_path) else '未启用'}")
    print(f"==================================================")

    try:
        PyInstaller.__main__.run(args)
        if onefile:
            target_exe = os.path.join(base_dir, "dist", "PdfEditor.exe")
            if os.path.isfile(target_exe):
                size_mb = os.path.getsize(target_exe) / (1024 * 1024)
                print(f"\n[√] 单文件 EXE 打包完成！生成文件：{target_exe} ({size_mb:.2f} MB)")
                print("提示：单文件 EXE 每次启动需要在后台向 Temp 解压，启动时间较长；若追求秒开请使用便携目录或 Inno Setup 安装包。")
        else:
            dist_dir = os.path.join(base_dir, "dist", "PdfEditor")
            target_exe = os.path.join(dist_dir, "PdfEditor.exe")
            print(f"\n[√] 便携绿色目录打包完成！输出目录：{dist_dir}")
            print(f"启动文件：{target_exe}")
            print("优势：免运行时解压，直接由操作系统内存映射加载，且双击瞬间由 Bootloader 原生秒弹启动加载页！")
            print("如需向最终用户交付单一文件安装包，可使用随附的 installer.iss 配合 Inno Setup 进行封装。")
        return 0
    except Exception as e:
        print(f"\n[×] 打包过程中出现错误：{e}")
        return 1


if __name__ == "__main__":
    # 若命令行显式传入 --onefile 则打包为单文件，默认采用秒开的便携绿色目录 (--onedir)
    is_onefile = "--onefile" in sys.argv
    sys.exit(build(onefile=is_onefile))
