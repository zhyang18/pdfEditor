"""
PDF 编辑器应用程序入口主脚本。
负责全局环境初始化、高分屏 DPI 自适应配置、应用级元数据定义、
PyInstaller C 级 Bootloader 原生启动画面对接与主窗口生命周期启动。
"""

import sys
import os
import time

# 禁用未使用的 pymupdf AI 布局分析模型检测，避免缺少 onnx/yaml 资源时的报错
if "pymupdf.layout" not in sys.modules:
    sys.modules["pymupdf.layout"] = None

# 尝试对接 PyInstaller C 级 Bootloader 原生启动画面模块
try:
    import pyi_splash
    HAS_PYI_SPLASH = True
except ImportError:
    HAS_PYI_SPLASH = False


def recenter_pyi_splash() -> None:
    """
    通过 Windows 64 位原生 API 纠正并锁定 PyInstaller Bootloader 启动画面位置。
    无论在何种 DPI 缩放（100%、125%、150%、200%）与屏幕分辨率下，
    均始终将启动画面几何中心精准锁定在当前主屏幕正中央，彻底杜绝突跳与位移。
    """
    if sys.platform != "win32":
        return

    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32

        # 显式配置 64 位 API 参数类型，避免 64 位 HWND 指针被 32 位截断导致调用失败
        user32.SetWindowPos.argtypes = [
            wintypes.HWND,
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT
        ]
        user32.SetWindowPos.restype = wintypes.BOOL

        user32.GetWindowRect.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.RECT)
        ]
        user32.GetWindowRect.restype = wintypes.BOOL

        current_pid = os.getpid()
        target_hwnds = []

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        def enum_cb(hwnd: wintypes.HWND, lparam: wintypes.LPARAM) -> bool:
            if not user32.IsWindowVisible(hwnd):
                return True
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == current_pid:
                cls_buf = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, cls_buf, 256)
                cls_name = cls_buf.value
                if "TkTopLevel" in cls_name or "Splash" in cls_name or "Toplevel" in cls_name:
                    target_hwnds.append(hwnd)
            return True

        user32.EnumWindows(WNDENUMPROC(enum_cb), 0)

        for hwnd in target_hwnds:
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            curr_w = rect.right - rect.left
            curr_h = rect.bottom - rect.top
            if curr_w <= 0 or curr_h <= 0:
                continue

            # 获取主屏幕系统物理分辨率与居中坐标
            screen_w = user32.GetSystemMetrics(0)  # SM_CXSCREEN
            screen_h = user32.GetSystemMetrics(1)  # SM_CYSCREEN
            center_x = (screen_w - curr_w) // 2
            center_y = (screen_h - curr_h) // 2

            # 仅移动窗口中心至屏幕中央，保持当前尺寸不变 (0x0001 = SWP_NOSIZE, 0x0004 = SWP_NOACTIVATE)
            user32.SetWindowPos(
                hwnd,
                wintypes.HWND(0),
                center_x,
                center_y,
                0,
                0,
                0x0001 | 0x0004
            )
    except Exception:
        pass


# 在载入任何重型 Qt 图形库之前，先行执行一次居中校准
recenter_pyi_splash()

from PySide6.QtWidgets import QApplication, QWidget, QGraphicsOpacityEffect
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont, QPen
from PySide6.QtCore import Qt, QRectF, QTimer, QPropertyAnimation
from assets.icons import IconLibrary

# Qt 模块载入完成后再次锁定居中
recenter_pyi_splash()


class FluentSplashScreen(QWidget):
    """
    现代 Fluent 极简风格的高清应用程序启动过渡窗口。
    用于在源码直接运行模式下提供毫秒级无延迟即时视觉响应。
    """

    def __init__(self) -> None:
        """
        初始化启动画面，配置无边框、置顶与半透明窗口属性，并居中置于主屏幕。
        """
        super().__init__(None, Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.SplashScreen)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self._status_text = "正在就绪工作区..."
        self._card_width = 400
        self._card_height = 230
        self.resize(self._card_width, self._card_height)
        self._center_on_screen()

        # 预渲染应用图标
        app_icon = IconLibrary.get_icon("to_word", 52)
        self._icon_pixmap = app_icon.pixmap(52, 52)
        self._anim = None

    def _center_on_screen(self) -> None:
        """
        将启动窗口几何居中于当前主屏幕可用可视区域。
        """
        screen = QApplication.primaryScreen()
        if screen is not None:
            geo = screen.availableGeometry()
            x = geo.x() + (geo.width() - self._card_width) // 2
            y = geo.y() + (geo.height() - self._card_height) // 2
            self.move(x, y)

    def paintEvent(self, event) -> None:
        """
        执行 Fluent 启动卡片与状态文字的高清矢量绘制。

        @param event 绘制事件
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        width = self.width()
        height = self.height()

        # 绘制背景卡片（圆角矩形，纯白底色与精致浅灰描边）
        card_rect = QRectF(2, 2, width - 4, height - 4)
        painter.setBrush(QColor(255, 255, 255))
        painter.setPen(QPen(QColor(226, 232, 240), 1.5))
        painter.drawRoundedRect(card_rect, 14, 14)

        # 绘制主应用图标
        painter.drawPixmap(int((width - 52) / 2), 30, self._icon_pixmap)

        # 绘制主标题
        title_font = QFont("Microsoft YaHei", 15, QFont.Bold)
        painter.setFont(title_font)
        painter.setPen(QColor(15, 23, 42))
        painter.drawText(QRectF(0, 96, width, 30), Qt.AlignCenter, "PDF 编辑器")

        # 绘制副标题
        sub_font = QFont("Microsoft YaHei", 9)
        painter.setFont(sub_font)
        painter.setPen(QColor(100, 116, 139))
        painter.drawText(QRectF(0, 130, width, 22), Qt.AlignCenter, "现代轻量 · 高性能矢量渲染")

        # 绘制底部状态提示
        status_font = QFont("Microsoft YaHei", 8)
        painter.setFont(status_font)
        painter.setPen(QColor(148, 163, 184))
        painter.drawText(QRectF(0, 180, width, 20), Qt.AlignCenter, self._status_text)

        painter.end()

    def update_status(self, text: str) -> None:
        """
        动态更新启动画面底部的状态提示文字并即时重绘刷新。

        @param text 待展示的状态描述文字
        """
        self._status_text = text
        self.update()
        QApplication.processEvents()

    def finish(self, main_window: QWidget) -> None:
        """
        平滑渐隐关闭启动过渡画面并将焦点移交给主窗口。

        @param main_window 主窗口控件实例
        """
        main_window.show()
        main_window.raise_()
        main_window.activateWindow()

        # 添加 160ms 优雅淡出动画，确保平滑自然过渡
        effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(effect)

        anim = QPropertyAnimation(effect, b"opacity")
        anim.setDuration(160)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.finished.connect(self.close)
        self._anim = anim
        anim.start()


def create_splash_screen() -> FluentSplashScreen:
    """
    创建并返回 FluentSplashScreen 实例的工厂函数。

    @return 构造就绪的启动过渡窗口对象
    """
    return FluentSplashScreen()


def main() -> int:
    """
    应用程序主函数，初始化 Qt 环境并启动主事件循环。
    支持 PyInstaller C 级 Bootloader 原生启动画面与本地开发启动画面的无缝协同，
    并在全流程中始终将启动画面居中锁定在当前主屏幕正中央。

    @return 操作系统进程退出代码，0 表示正常退出
    """
    # 启用高分屏抗锯齿与自适应缩放策略
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("PdfEditor")
    app.setApplicationDisplayName("PDF 编辑器")
    app.setOrganizationName("PdfEditorPro")

    # 全局加载 Qt 官方标准中文语言翻译包（汉化标准对话框、右键菜单、文件选择器等）
    from PySide6.QtCore import QTranslator, QLibraryInfo
    from core.utils import ResourceUtils
    qt_translator = QTranslator(app)
    qm_path = ResourceUtils.get_asset_path("qtbase_zh_CN.qm")
    if os.path.isfile(qm_path):
        qt_translator.load(qm_path)
        app.installTranslator(qt_translator)
    else:
        trans_dir = QLibraryInfo.path(QLibraryInfo.TranslationsPath)
        if qt_translator.load("qtbase_zh_CN.qm", trans_dir):
            app.installTranslator(qt_translator)

    # 在 Qt 激活全局高分屏上下文后，立即执行居中校准锁定
    recenter_pyi_splash()

    # 设置应用全局图标
    app_icon = IconLibrary.get_icon("to_word", 48)
    app.setWindowIcon(app_icon)

    is_headless = os.environ.get("QT_QPA_PLATFORM") == "offscreen"
    if is_headless:
        # 无头离屏测试环境：关闭 splash 并不做任何延时展示
        if HAS_PYI_SPLASH:
            try:
                pyi_splash.close()
            except Exception:
                pass
        from ui.main_window import MainWindow
        window = MainWindow()
        window.show()
        if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
            arg_file = sys.argv[1]
            if arg_file.lower().endswith(".pdf"):
                window.load_pdf(arg_file)
        return app.exec()

    # 1. 独立可执行程序模式：由 PyInstaller C Bootloader 在双击瞬间已原生弹出 Splash
    if HAS_PYI_SPLASH:
        try:
            pyi_splash.update_text("正在载入核心引擎与文档组件...")
            recenter_pyi_splash()
        except Exception:
            pass

        from ui.main_window import MainWindow

        try:
            pyi_splash.update_text("正在构建工作区...")
            recenter_pyi_splash()
        except Exception:
            pass

        window = MainWindow()
        window.show()

        try:
            pyi_splash.close()
        except Exception:
            pass

        if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
            arg_file = sys.argv[1]
            if arg_file.lower().endswith(".pdf"):
                window.load_pdf(arg_file)

        return app.exec()

    # 2. 本地源码直接运行模式（无 pyi_splash）：使用轻量 Python FluentSplashScreen
    start_time = time.perf_counter()
    splash = FluentSplashScreen()
    splash.show()
    # show() 之后再次校准绝对居中，杜绝系统 DPI 缩放影响
    splash._center_on_screen()
    splash.repaint()
    app.processEvents()

    splash.update_status("正在就绪核心引擎与界面组件...")
    from ui.main_window import MainWindow

    splash.update_status("正在构建工作区...")
    window = MainWindow()

    elapsed_ms = (time.perf_counter() - start_time) * 1000
    min_splash_ms = 700

    def launch_main_window() -> None:
        """
        展示主窗口并平滑关闭启动过渡画面。
        """
        splash.finish(window)

        if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
            arg_file = sys.argv[1]
            if arg_file.lower().endswith(".pdf"):
                window.load_pdf(arg_file)

    if elapsed_ms < min_splash_ms:
        remaining_ms = int(min_splash_ms - elapsed_ms)
        splash.update_status("正在启动...")
        QTimer.singleShot(remaining_ms, launch_main_window)
    else:
        launch_main_window()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
