"""
UI 组件与主窗口自动化集成测试套件。
在无头 (offscreen) 模式下测试主窗口实例化、缩略图联动、画板渲染、图片悬浮图层添加与固化等流程。
"""

import os
import unittest
import tempfile
import pymupdf
from PIL import Image

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

# 设置离屏测试平台
os.environ["QT_QPA_PLATFORM"] = "offscreen"

app = QApplication.instance()
if app is None:
    app = QApplication([])

from ui.main_window import MainWindow
from ui.dialogs.merge_dialog import MergeDialog
from ui.dialogs.reorder_dialog import ReorderDialog
from ui.dialogs.watermark_dialog import WatermarkDialog


class TestUiComponents(unittest.TestCase):
    """
    图形用户界面集成测试类。
    验证主窗口与其对话框控件在实际数据加载下的稳健性。
    """

    def setUp(self) -> None:
        """
        初始化每个 UI 测试用例的前置环境，生成临时测试文件。
        """
        self.test_dir = tempfile.mkdtemp()
        self.sample_pdf = os.path.join(self.test_dir, "ui_sample.pdf")
        self.sample_img = os.path.join(self.test_dir, "ui_img.png")

        # 创建真实 PDF
        doc = pymupdf.open()
        for i in range(3):
            page = doc.new_page(width=595.0, height=842.0)
            page.insert_text(pymupdf.Point(50, 100), f"UI Page {i + 1}", fontsize=20)
        doc.save(self.sample_pdf)
        doc.close()

        # 创建真实图片
        img = Image.new("RGB", (100, 100), color=(16, 185, 129))
        img.save(self.sample_img, "PNG")

    def tearDown(self) -> None:
        """
        清理临时测试文件。
        """
        if os.path.exists(self.test_dir):
            for root, dirs, files in os.walk(self.test_dir, topdown=False):
                for f in files:
                    try:
                        os.remove(os.path.join(root, f))
                    except Exception:
                        pass
                for d in dirs:
                    try:
                        os.rmdir(os.path.join(root, d))
                    except Exception:
                        pass
            try:
                os.rmdir(self.test_dir)
            except Exception:
                pass

    def test_main_window_lifecycle(self) -> None:
        """
        测试主窗口加载 PDF、切换页面、旋转、插入图片与保存生命周期。
        """
        window = MainWindow()
        window.load_pdf(self.sample_pdf)

        # 检查页面是否成功加载
        self.assertEqual(window.thumbnail_panel.list_widget.count(), 3)
        self.assertEqual(window.canvas_view.current_page_index, 0)

        # 测试页面顺序调整
        window._on_page_order_changed(2, 0)
        self.assertEqual(window.canvas_view.current_page_index, 0)

        # 测试撤销与重做
        self.assertTrue(window._history.can_undo())
        window._on_undo()
        self.assertTrue(window._history.can_redo())
        window._on_redo()

        # 测试在页面上添加悬浮图片并固化
        added = window.canvas_view.add_floating_image(self.sample_img)
        self.assertTrue(added)
        self.assertIsNotNone(window.canvas_view.active_image_item)

        # 固化图片
        bake_success = window.canvas_view.bake_active_image(window._doc)
        self.assertTrue(bake_success)
        self.assertIsNone(window.canvas_view.active_image_item)

        # 测试旋转页面
        window._on_rotate_page(90)

        # 保存并验证
        save_target = os.path.join(self.test_dir, "saved_ui.pdf")
        self.assertTrue(window._doc.save(save_target))
        self.assertTrue(os.path.isfile(save_target))

        window.close()

    def test_dialogs_instantiation(self) -> None:
        """
        测试多文件合并对话框、重排对话框及水印对话框的实例化。
        """
        merge_dlg = MergeDialog()
        self.assertIsNotNone(merge_dlg)
        merge_dlg.close()

        reorder_dlg = ReorderDialog(3)
        self.assertEqual(reorder_dlg._page_count, 3)
        reorder_dlg.close()

        watermark_dlg = WatermarkDialog(3)
        params = watermark_dlg.get_watermark_params()
        self.assertEqual(params[0], "机密文件 请勿外传")
        watermark_dlg.close()

    def test_window_adaptive_resizing(self) -> None:
        """
        测试主窗口在不同尺寸拉伸缩放时的自适应响应：
        1. 验证 1024 宽窄屏下工具栏自适应为纯图标模式，且所有按钮完整呈现、无截断溢出；
        2. 验证大屏下工具栏自适应展开为全量图文模式；
        3. 验证主画布视口在窗口尺寸变更时 PDF 页面显示大小自适应缩放。
        """
        window = MainWindow()
        window.show()
        window.load_pdf(self.sample_pdf)
        app.processEvents()

        # 1. 验证 1024 宽度自适应
        window.resize(1024, 700)
        app.processEvents()
        self.assertEqual(window.toolbar.get_adaptive_mode(), "auto")
        self.assertEqual(window.toolbar._current_layout_mode, "icon")

        # 检查所有常驻按钮均可见，且最右侧按钮右边界未超出 1024
        for act in window.toolbar.actions():
            w = window.toolbar.widgetForAction(act)
            if w is not None and act.isVisible():
                self.assertLess(w.pos().x() + w.width(), 1024)

        # 2. 验证大屏 1920 宽度自适应
        window.resize(1920, 1080)
        app.processEvents()
        self.assertEqual(window.toolbar._current_layout_mode, "full")

        # 3. 验证画板自适应缩放（fit_page 模式）
        zoom_large = window.canvas_view._zoom_factor
        window.resize(1000, 600)
        app.processEvents()
        zoom_small = window.canvas_view._zoom_factor
        self.assertLess(zoom_small, zoom_large)

        window.close()


if __name__ == "__main__":
    unittest.main()
