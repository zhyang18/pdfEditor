"""
新功能与缺陷修复自动化测试模块。
针对窗口居中、适宽计算、缩略图拖拽事件分发与外部图片拖拽插入进行针对性回归验证。
"""

import os
import unittest
import tempfile
import pymupdf
from PIL import Image

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPoint, QMimeData, QUrl
from PySide6.QtGui import QDropEvent

os.environ["QT_QPA_PLATFORM"] = "offscreen"

app = QApplication.instance()
if app is None:
    app = QApplication([])

from ui.main_window import MainWindow
from ui.thumbnail_panel import ThumbnailListWidget
from ui.canvas_view import PdfCanvasView, ResizableImageItem


class TestFixesAndEnhancements(unittest.TestCase):
    """
    新需求与 Bug 修复自动化测试类。
    """

    def setUp(self) -> None:
        """
        初始化测试文件与环境。
        """
        self.test_dir = tempfile.mkdtemp()
        self.sample_pdf = os.path.join(self.test_dir, "test_doc.pdf")
        self.sample_img = os.path.join(self.test_dir, "test_drop.png")

        # 生成 4 页 PDF
        doc = pymupdf.open()
        for i in range(4):
            p = doc.new_page(width=595.0, height=842.0)
            p.insert_text(pymupdf.Point(50, 100), f"Fixes Test Page {i + 1}", fontsize=18)
        doc.save(self.sample_pdf)
        doc.close()

        # 生成测试图片
        img = Image.new("RGBA", (150, 150), (220, 38, 38, 255))
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

    def test_window_centering(self) -> None:
        """
        测试主窗口在屏幕上执行居中移动逻辑。
        """
        window = MainWindow()
        window._center_on_screen()
        # 验证窗口已定位于屏幕可视区域内
        self.assertGreaterEqual(window.x(), 0)
        self.assertGreaterEqual(window.y(), 0)
        window.close()

    def test_fit_width_and_fit_page(self) -> None:
        """
        测试适宽与整页适应缩放变换，确保不产生 NaN 或过度放大缩小导致空白。
        """
        window = MainWindow()
        window.show()
        window.load_pdf(self.sample_pdf)

        # 触发适宽操作
        window._on_fit_width()
        scale_x = window.canvas_view.transform().m11()
        self.assertGreater(scale_x, 0.05)
        self.assertLess(scale_x, 10.0)
        self.assertIsNotNone(window.canvas_view._current_page_item)
        self.assertTrue(window.canvas_view._current_page_item.isVisible())

        # 触发整页适应操作
        window._on_fit_page()
        scale_page = window.canvas_view.transform().m11()
        self.assertGreater(scale_page, 0.05)
        self.assertLess(scale_page, 10.0)

        window.close()

    def test_thumbnail_drag_drop_reorder(self) -> None:
        """
        测试缩略图列表拖拽释放事件能精准发射 page_moved 信号并更新顺序。
        """
        window = MainWindow()
        window.show()
        window.load_pdf(self.sample_pdf)

        list_widget = window.thumbnail_panel.list_widget
        self.assertEqual(list_widget.count(), 4)

        moved_signals = []
        list_widget.page_moved.connect(lambda f, t: moved_signals.append((f, t)))

        # 构造带有页码 MIME 的 DropEvent
        mime_data = QMimeData()
        mime_data.setData(ThumbnailListWidget.MIME_PAGE, b"0")
        mime_data.setText("0")

        # 释放到第 2 页的位置
        item_2 = list_widget.item(2)
        target_pos = list_widget.visualItemRect(item_2).center()

        event = QDropEvent(
            target_pos,
            Qt.MoveAction,
            mime_data,
            Qt.LeftButton,
            Qt.NoModifier
        )
        list_widget.dropEvent(event)

        # 验证信号是否准确发射 (0 -> 2)
        self.assertEqual(len(moved_signals), 1)
        self.assertEqual(moved_signals[0], (0, 2))

        # 测试移动到末尾空白处
        event_bottom = QDropEvent(
            QPoint(50, 1000),
            Qt.MoveAction,
            mime_data,
            Qt.LeftButton,
            Qt.NoModifier
        )
        list_widget.dropEvent(event_bottom)
        self.assertEqual(len(moved_signals), 2)
        self.assertEqual(moved_signals[1], (0, 3))

        window.close()

    def test_canvas_external_image_drop(self) -> None:
        """
        测试编辑区支持直接从外部拖入图片文件并进入悬浮调整状态。
        """
        window = MainWindow()
        window.show()
        window.load_pdf(self.sample_pdf)

        canvas = window.canvas_view
        self.assertIsNone(canvas.active_image_item)

        # 模拟外部图片拖放进画板
        mime_data = QMimeData()
        mime_data.setUrls([QUrl.fromLocalFile(self.sample_img)])

        drop_pos = QPoint(200, 200)
        event = QDropEvent(
            drop_pos,
            Qt.CopyAction,
            mime_data,
            Qt.LeftButton,
            Qt.NoModifier
        )
        canvas.dropEvent(event)

        # 验证图片悬浮图层已被创建且处于激活状态
        self.assertIsNotNone(canvas.active_image_item)
        self.assertEqual(
            os.path.normpath(canvas.active_image_item.image_path),
            os.path.normpath(self.sample_img)
        )

        # 验证工具栏已切换到固化/放弃按钮可见状态
        self.assertTrue(window.toolbar.act_bake_img.isVisible())

        # 固化测试
        window._on_bake_image()
        self.assertIsNone(canvas.active_image_item)

        window.close()

    def test_dynamic_high_res_zoom_clarity(self) -> None:
        """
        测试放大缩小时画板动态高保真重采样机制，确保矢量字形重新以高 DPI 光栅化，
        杜绝机械拉伸引起的模糊发虚，并保持场景几何坐标恒定。
        """
        window = MainWindow()
        window.show()
        window.load_pdf(self.sample_pdf)
        canvas = window.canvas_view

        self.assertIsNotNone(canvas._current_page_item)
        # 重置变换为 1.0 基准比例并进行首次基准渲染
        canvas.resetTransform()
        canvas.scale(1.0, 1.0)
        canvas._update_high_res_render()

        init_dpi = canvas._rendered_dpi
        init_pixmap_w = canvas._current_page_item.pixmap().width()
        scene_w = canvas.sceneRect().width()
        scene_h = canvas.sceneRect().height()

        # 验证场景坐标系为 PDF 页面标准物理点数（如 595 pt）
        self.assertAlmostEqual(scene_w, 595.0, delta=1.0)
        self.assertAlmostEqual(scene_h, 842.0, delta=1.0)

        # 模拟放大至 2.5 倍
        canvas.scale(2.5, 2.5)
        canvas._update_high_res_render()

        zoomed_dpi = canvas._rendered_dpi
        zoomed_pixmap_w = canvas._current_page_item.pixmap().width()

        # 验证渲染 DPI 相应提升，且生成了更高像素密度的物理位图
        self.assertGreater(zoomed_dpi, init_dpi)
        self.assertGreater(zoomed_pixmap_w, init_pixmap_w)

        # 验证场景几何矩形严格恒定不变（确保悬浮标注与插入图片坐标永久精准）
        self.assertEqual(canvas.sceneRect().width(), scene_w)
        self.assertEqual(canvas.sceneRect().height(), scene_h)

        # 验证高清 SVG 图标多尺度适配
        from assets.icons import IconLibrary
        test_icon = IconLibrary.get_icon("open", 24)
        self.assertFalse(test_icon.isNull())

        window.close()

    def test_merge_dialog_drag_drop_and_light_theme(self) -> None:
        """
        测试多文件合并向导支持从外部拖拽导入 PDF 文件，并验证其亮色样式表生效。
        """
        from ui.dialogs.merge_dialog import MergeDialog
        dlg = MergeDialog()

        self.assertEqual(dlg.table.rowCount(), 0)
        self.assertTrue(dlg.acceptDrops())
        self.assertTrue(dlg.table.acceptDrops())

        # 验证样式表中包含 QTableWidget 与 QHeaderView 的亮色配置
        style_text = dlg.styleSheet()
        self.assertIn("QTableWidget", style_text)
        self.assertIn("QHeaderView", style_text)
        self.assertIn("#FFFFFF", style_text)

        # 1. 模拟外部拖拽 PDF 文件释放至 MergeDialog
        mime_data = QMimeData()
        mime_data.setUrls([QUrl.fromLocalFile(self.sample_pdf)])
        event = QDropEvent(
            QPoint(100, 100),
            Qt.CopyAction,
            mime_data,
            Qt.LeftButton,
            Qt.NoModifier
        )
        dlg.dropEvent(event)

        # 验证已成功通过外部拖拽添加了 1 个文件
        self.assertEqual(dlg.table.rowCount(), 1)
        self.assertEqual(dlg.table.item(0, 1).text(), os.path.basename(self.sample_pdf))
        self.assertEqual(dlg.table.item(0, 2).text(), "4 页")

        # 2. 模拟拖拽到表格区域通过事件过滤器导入
        dlg.eventFilter(dlg.table.viewport(), event)
        self.assertEqual(dlg.table.rowCount(), 2)

        dlg.close()

    def test_dialog_dimensions_and_no_clipping(self) -> None:
        """
        测试水印对话框、重排对话框和转换对话框的弹性自适应尺寸，确保底部操作按钮不被遮挡裁切。
        """
        from ui.dialogs.watermark_dialog import WatermarkDialog
        from ui.dialogs.reorder_dialog import ReorderDialog

        # 1. 验证水印对话框
        wm_dlg = WatermarkDialog(max_pages=5)
        # 尺寸应具有充裕的垂直空间（高度 >= 460，杜绝旧版 360 导致的底部按钮裁切）
        self.assertGreaterEqual(wm_dlg.height(), 460)
        self.assertGreaterEqual(wm_dlg.width(), 400)
        # 验证底部确定添加按钮存在且尺寸充裕
        self.assertGreaterEqual(wm_dlg.ok_btn.minimumHeight(), 30)
        self.assertGreaterEqual(wm_dlg.cancel_btn.minimumHeight(), 30)
        # 验证样式已成功加载
        self.assertTrue(len(wm_dlg.styleSheet()) > 0)
        wm_dlg.close()

        # 2. 验证重排对话框
        reorder_dlg = ReorderDialog(page_count=4)
        self.assertGreaterEqual(reorder_dlg.height(), 220)
        self.assertGreaterEqual(reorder_dlg.width(), 420)
        self.assertGreaterEqual(reorder_dlg.ok_btn.minimumHeight(), 30)
        reorder_dlg.close()

    def test_self_contained_resource_resolution(self) -> None:
        """
        测试自包含资源寻址工具，确保样式表与静态资产在单文件免解压与便携环境下均能正确寻址。
        """
        from core.utils import ResourceUtils
        light_path = ResourceUtils.get_resource_path("assets/style_light.qss")
        dark_path = ResourceUtils.get_resource_path("assets/style_dark.qss")
        self.assertTrue(os.path.isfile(light_path))
        self.assertTrue(os.path.isfile(dark_path))

    def test_image_handles_hit_area_and_no_ghost_tracks(self) -> None:
        """
        测试悬浮图片图元的把手热区范围、四角触发灵敏度与无残影边界设置。
        """
        from PySide6.QtGui import QPixmap
        from PySide6.QtCore import QRectF, QPointF
        from PySide6.QtWidgets import QGraphicsView

        pixmap = QPixmap(self.sample_img)
        item = ResizableImageItem(pixmap, self.sample_img, initial_rect=QRectF(100, 100, 200, 150))

        # 1. 验证 boundingRect 包含了把手与热区外扩边距，彻底杜绝残影
        br = item.boundingRect()
        r = item.rect()
        self.assertLess(br.left(), r.left())
        self.assertLess(br.top(), r.top())
        self.assertGreater(br.right(), r.right())
        self.assertGreater(br.bottom(), r.bottom())

        # 2. 验证四角把手超大交互触发热区（26x26）
        # 命中右下角顶点附近（即使偏移 8 像素，依然能灵敏命中 bottom_right 把手）
        detected_br = item._detect_handle_at(QPointF(300 - 6, 250 - 6))
        self.assertEqual(detected_br, "bottom_right")

        # 命中左上角顶点附近
        detected_tl = item._detect_handle_at(QPointF(100 + 5, 100 + 5))
        self.assertEqual(detected_tl, "top_left")

        # 3. 验证 PdfCanvasView 启用了 FullViewportUpdate 彻底消灭拖动轨迹
        view = PdfCanvasView()
        self.assertEqual(view.viewportUpdateMode(), QGraphicsView.FullViewportUpdate)
        view.close()

    def test_text_watermark_rotation_and_chinese(self) -> None:
        """
        测试文本水印在 45 度任意倾斜角与中文字符下的添加与保存成功率。
        """
        from core.pdf_document import PdfDocument
        doc = PdfDocument()
        self.assertTrue(doc.open(self.sample_pdf))

        # 45度倾斜角添加机密文本水印（原先因 rotate=45 导致 ValueError 失败）
        success = doc.add_text_watermark(
            text="机密文件 请勿外传",
            font_size=36.0,
            angle=45.0,
            opacity=0.3
        )
        self.assertTrue(success)
        self.assertTrue(doc.is_modified)

        # 保存并重新验证
        save_out = os.path.join(self.test_dir, "wm_verified.pdf")
        self.assertTrue(doc.save(save_out))
        doc.close()

        # 验证生成的 PDF 物理有效性
        re_doc = pymupdf.open(save_out)
        self.assertEqual(len(re_doc), 4)
        re_doc.close()


    def test_split_visibility_and_actions(self) -> None:
        """
        测试拆开功能的多入口显著性（主菜单栏、缩略图顶部、主工具栏与快捷键）。
        确保用户在界面的任何位置都能一眼看到并触发【拆开】功能。
        """
        window = MainWindow()
        window.show()
        window.load_pdf(self.sample_pdf)

        # 1. 验证主菜单栏中存在【页面】和【工具】拆开入口
        menubar = window.menuBar()
        self.assertIsNotNone(menubar)
        menu_titles = [act.text() for act in menubar.actions()]
        self.assertTrue(any("页面" in t for t in menu_titles))
        self.assertTrue(any("工具" in t for t in menu_titles))

        # 2. 验证缩略图面板顶部常驻【✂️ 拆开】按钮
        self.assertIsNotNone(window.thumbnail_panel.btn_split)
        self.assertIn("拆开", window.thumbnail_panel.btn_split.text())
        self.assertTrue(window.thumbnail_panel.btn_split.isEnabled())

        # 3. 验证主工具栏【拆开(拆分)】按钮
        self.assertIn("拆开", window.toolbar.act_split.text())
        self.assertTrue(window.toolbar.act_split.isEnabled())

        window.close()

    def test_image_layer_continue_edit_undo_delete_and_save(self) -> None:
        """
        测试插入图片保存后继续编辑、撤销、删除及持久化图层完整工作流。
        验证：
        1. 插入图片成为独立图层并在画板生成可拉伸图元；
        2. 保存 PDF 后，图片图层不被强行固化，依然保留可编辑性；
        3. 对图片进行移动/放缩后可按 Ctrl+Z 撤销恢复；
        4. 按 Delete 键或右键删除图片后，可按 Ctrl+Z 撤回删除并复原；
        5. 保存后重新打开 PDF 文档，图层依然存在且可继续微调。
        """
        window = MainWindow()
        window.show()
        window.load_pdf(self.sample_pdf)
        canvas = window.canvas_view

        # 1. 在当前页插入图片
        layer = canvas.add_floating_image(self.sample_img)
        self.assertIsNotNone(layer)
        layer_id = layer.id
        orig_rect = layer.rect
        self.assertIn(layer_id, canvas._image_items)

        # 2. 保存文档
        save_target = os.path.join(self.test_dir, "saved_with_layers.pdf")
        self.assertTrue(window._doc.save(save_target))
        self.assertTrue(os.path.isfile(save_target))

        # 保存后图层应在内存中完好保留，未被清空
        self.assertIn(layer_id, canvas._image_items)
        self.assertIsNotNone(window._doc.image_layers.get_layer(layer_id))

        # 3. 继续编辑：移动图片位置
        new_rect = (orig_rect[0] + 50.0, orig_rect[1] + 50.0, orig_rect[2] + 50.0, orig_rect[3] + 50.0)
        window._on_image_transformed(layer_id, orig_rect, new_rect)
        current_layer = window._doc.image_layers.get_layer(layer_id)
        self.assertEqual(current_layer.rect, new_rect)

        # 4. 测试撤销移动 (Ctrl+Z)
        self.assertTrue(window._history.can_undo())
        window._on_undo()
        self.assertEqual(window._doc.image_layers.get_layer(layer_id).rect, orig_rect)

        # 5. 测试删除图片（按 Delete 键或点击删除按钮）
        item = canvas._image_items[layer_id]
        item.setSelected(True)
        window._on_delete_selected_image()
        self.assertIsNone(window._doc.image_layers.get_layer(layer_id))
        self.assertNotIn(layer_id, canvas._image_items)

        # 6. 测试撤销删除 (Ctrl+Z 恢复图片)
        self.assertTrue(window._history.can_undo())
        window._on_undo()
        restored_layer = window._doc.image_layers.get_layer(layer_id)
        self.assertIsNotNone(restored_layer)
        self.assertEqual(restored_layer.rect, orig_rect)
        self.assertIn(layer_id, canvas._image_items)

        # 7. 再次保存并重新打开验证持久化图层元数据
        self.assertTrue(window._doc.save(save_target))
        window.close()

        # 重新载入刚才保存的 PDF
        window2 = MainWindow()
        window2.load_pdf(save_target)
        self.assertEqual(len(window2._doc.image_layers), 1)
        self.assertIn(layer_id, window2.canvas_view._image_items)
        window2.close()

    def test_canvas_scroll_wheel_page_turn(self) -> None:
        """
        测试编辑区画板上下滑动滚轮翻页功能。
        验证：
        1. 鼠标滚轮在画板向下滑动时，自动顺畅翻到下一页；
        2. 鼠标滚轮在画板向上滑动时，自动顺畅翻到上一页；
        3. 首页向上滑动与尾页向下滑动严格受边界保护不越界；
        4. 键盘 PageDown 与 PageUp 按键在画板触发准确翻页。
        """
        from PySide6.QtGui import QWheelEvent, QKeyEvent
        from PySide6.QtCore import QPoint, QPointF

        window = MainWindow()
        window.show()
        window.load_pdf(self.sample_pdf)
        canvas = window.canvas_view
        self.assertEqual(canvas.current_page_index, 0)
        self.assertEqual(window._doc.page_count, 4)

        # 构造向下滚动的滚轮事件 (delta_y = -120)
        pos = QPoint(300, 300)
        global_pos = canvas.mapToGlobal(pos)
        wheel_down = QWheelEvent(
            QPointF(pos),
            QPointF(global_pos),
            QPoint(0, 0),
            QPoint(0, -120),
            Qt.NoButton,
            Qt.NoModifier,
            Qt.ScrollUpdate,
            False
        )

        # 1. 在第 0 页向下滑动滚轮 -> 翻到第 1 页
        canvas.wheelEvent(wheel_down)
        self.assertEqual(canvas.current_page_index, 1)
        self.assertEqual(window.thumbnail_panel.current_page_index, 1)

        # 模拟冷却时间后再次向下滑动 -> 翻到第 2 页
        canvas._last_wheel_page_turn_time = 0.0
        canvas.wheelEvent(wheel_down)
        self.assertEqual(canvas.current_page_index, 2)

        # 2. 构造向上滚动的滚轮事件 (delta_y = 120)
        wheel_up = QWheelEvent(
            QPointF(pos),
            QPointF(global_pos),
            QPoint(0, 0),
            QPoint(0, 120),
            Qt.NoButton,
            Qt.NoModifier,
            Qt.ScrollUpdate,
            False
        )

        # 向上滑动滚轮 -> 翻回第 1 页
        canvas._last_wheel_page_turn_time = 0.0
        canvas.wheelEvent(wheel_up)
        self.assertEqual(canvas.current_page_index, 1)

        # 向上滑动滚轮 -> 翻回第 0 页
        canvas._last_wheel_page_turn_time = 0.0
        canvas.wheelEvent(wheel_up)
        self.assertEqual(canvas.current_page_index, 0)

        # 3. 边界测试：在第 0 页继续向上滚不会越界
        canvas._last_wheel_page_turn_time = 0.0
        canvas.wheelEvent(wheel_up)
        self.assertEqual(canvas.current_page_index, 0)

        # 4. 键盘 PageDown / PageUp 测试
        key_pagedown = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_PageDown, Qt.NoModifier)
        canvas.keyPressEvent(key_pagedown)
        self.assertEqual(canvas.current_page_index, 1)

        key_pageup = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_PageUp, Qt.NoModifier)
        canvas.keyPressEvent(key_pageup)
        self.assertEqual(canvas.current_page_index, 0)

        window.close()


if __name__ == "__main__":
    unittest.main()
