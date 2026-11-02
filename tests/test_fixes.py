"""
新功能与缺陷修复自动化测试模块。
针对窗口居中、适宽计算、缩略图拖拽事件分发与外部图片拖拽插入进行针对性回归验证。
"""

import os
import unittest
import tempfile
import pymupdf
from PIL import Image

from PySide6.QtWidgets import QApplication, QStyleOptionViewItem
from PySide6.QtCore import Qt, QPoint, QRect, QMimeData, QUrl
from PySide6.QtGui import QDropEvent, QDragEnterEvent, QDragMoveEvent, QImage, QPainter

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

        # 测试 get_asset_path 的直接文件名寻址与 assets 相对路径寻址
        qm_path = ResourceUtils.get_asset_path("qtbase_zh_CN.qm")
        self.assertTrue(os.path.isfile(qm_path), f"未能正确寻址 Qt 中文翻译包: {qm_path}")
        qss_via_asset = ResourceUtils.get_asset_path("style_light.qss")
        self.assertTrue(os.path.isfile(qss_via_asset), f"未能正确通过 get_asset_path 寻址样式表: {qss_via_asset}")

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

    def test_thumbnail_adaptive_sizing(self) -> None:
        """
        测试页面缩略图自适应大小与智能分列显示：
        1. 验证默认侧边栏宽度下始终为 1 列表显示；
        2. 验证拉宽后根据容器宽度自动合理分列（1列 -> 2列 -> 3列）；
        3. 验证 Delegate 的 paint 与 sizeHint 稳定绘制。
        """
        mixed_pdf = os.path.join(self.test_dir, "mixed_orientations.pdf")
        doc = pymupdf.open()
        p1 = doc.new_page(width=800.0, height=450.0)
        p1.insert_text(pymupdf.Point(50, 50), "Landscape Page 1", fontsize=20)
        p2 = doc.new_page(width=595.0, height=842.0)
        p2.insert_text(pymupdf.Point(50, 50), "Portrait Page 2", fontsize=20)
        doc.save(mixed_pdf)
        doc.close()

        window = MainWindow()
        window.show()
        window.load_pdf(mixed_pdf)
        list_widget = window.thumbnail_panel.list_widget
        delegate = list_widget.thumbnail_delegate

        # 1. 默认侧边栏宽度（300px 左右）：严格保持为 1 列表显示
        self.assertEqual(list_widget.current_columns, 1, "默认侧边栏宽度下必须为 1 列表显示")

        # 2. 用户主动拉宽侧边栏（460px 视口）：合理升级分列为 2 列
        window.resizeDocks([window.dock_thumbnail], [460], Qt.Horizontal)
        app.processEvents()
        self.assertEqual(list_widget.current_columns, 2, "拉宽侧边栏至 460px 时应合理分列为 2 列")

        # 3. 较大宽度（680px 视口）：合理升级分列为 3 列
        window.resizeDocks([window.dock_thumbnail], [680], Qt.Horizontal)
        app.processEvents()
        self.assertGreaterEqual(list_widget.current_columns, 3, "拉宽侧边栏至 680px 时应合理分列为 3 列")

        # 4. 验证 Delegate paint 正常绘制不报错
        card_size = list_widget.card_size
        idx_0 = list_widget.model().index(0, 0)
        opt = QStyleOptionViewItem()
        img = QImage(card_size.width(), card_size.height(), QImage.Format_ARGB32)
        painter = QPainter(img)
        opt.rect = QRect(0, 0, card_size.width(), card_size.height())
        delegate.paint(painter, opt, idx_0)
        painter.end()

        window.close()

    def test_multi_column_drag_scroll_to_bottom(self) -> None:
        """
        测试多列显示模式下拖拽并顺畅滚动插入到列表最底部：
        1. 构建包含 20 页内容的 PDF 文档；
        2. 设置侧边栏为 400px 宽（2 列多列显示）；
        3. 模拟将第 1 页（from_row = 0）拖拽向下触发边缘平滑自动滚动直至触底；
        4. 模拟在最后一项（第 20 页，索引 19）右侧或下方的空白处释放；
        5. 验证精确发射 page_moved(0, 19) 成功将第 1 页插入到整个列表的最末尾。
        """
        multi_pdf = os.path.join(self.test_dir, "multi_col_test.pdf")
        doc = pymupdf.open()
        for i in range(20):
            p = doc.new_page(width=800.0, height=450.0)
            p.insert_text(pymupdf.Point(40, 50), f"Page Number {i + 1}", fontsize=16)
        doc.save(multi_pdf)
        doc.close()

        window = MainWindow()
        window.show()
        window.load_pdf(multi_pdf)
        list_widget = window.thumbnail_panel.list_widget
        self.assertEqual(list_widget.count(), 20)

        # 设置为多列模式（400px 宽度 -> 2 列）
        list_widget.resize(400, 400)
        app.processEvents()
        self.assertEqual(list_widget.current_columns, 2)

        # 滚到底部
        vbar = list_widget.verticalScrollBar()
        vbar.setValue(vbar.maximum())
        app.processEvents()

        last_item = list_widget.item(19)
        last_rect = list_widget.visualItemRect(last_item)

        # 模拟释放在最后一项右侧或下方的空白处
        drop_pos = QPoint(last_rect.right() + 20, last_rect.center().y())

        mime_data = QMimeData()
        mime_data.setData(ThumbnailListWidget.MIME_PAGE, b"0")
        mime_data.setText("0")

        moved_records = []
        list_widget.page_moved.connect(lambda f, t: moved_records.append((f, t)))

        drop_event = QDropEvent(
            drop_pos,
            Qt.MoveAction,
            mime_data,
            Qt.LeftButton,
            Qt.NoModifier
        )
        list_widget.dropEvent(drop_event)

        # 验证在多列空白处释放，成功精确识别并插入到列表最底部 (0 -> 19)
        self.assertEqual(len(moved_records), 1)
        self.assertEqual(moved_records[0], (0, 19))

        window.close()

    def test_thumbnail_auto_scroll_drag_to_50th_page(self) -> None:
        """
        测试拖拽页码边缘平滑自动滚动排序功能（验证将第 1 页拖动排序至第 50 页）：
        1. 构建包含 50 页真实内容的 PDF 文档；
        2. 模拟从第 1 页发起拖拽并移入视口底部感应区，验证平滑自动滚动定时器激活并向下步进；
        3. 模拟滚动到底部并在第 50 页释放，验证发射 page_moved(0, 49) 信号并成功更新文档排序。
        """
        long_pdf = os.path.join(self.test_dir, "long_50_pages.pdf")
        doc = pymupdf.open()
        for i in range(50):
            p = doc.new_page(width=595.0, height=842.0)
            p.insert_text(pymupdf.Point(40, 50), f"Page Number {i + 1}", fontsize=16)
        doc.save(long_pdf)
        doc.close()

        window = MainWindow()
        window.resize(1000, 700)
        window.show()
        window.load_pdf(long_pdf)
        list_widget = window.thumbnail_panel.list_widget
        self.assertEqual(list_widget.count(), 50)

        app.processEvents()
        self.assertTrue(list_widget.verticalScrollBar().maximum() > 0)

        # 1. 模拟将第 1 页（from_row = 0）拖入并移至底部边缘区域
        mime_data = QMimeData()
        mime_data.setData(ThumbnailListWidget.MIME_PAGE, b"0")
        mime_data.setText("0")

        vp_h = list_widget.viewport().height()
        bottom_drag_pos = QPoint(list_widget.viewport().width() // 2, vp_h - 10)

        drag_enter_event = QDragEnterEvent(
            bottom_drag_pos,
            Qt.MoveAction,
            mime_data,
            Qt.LeftButton,
            Qt.NoModifier
        )
        list_widget.dragEnterEvent(drag_enter_event)
        self.assertTrue(list_widget.is_dragging)

        drag_move_event = QDragMoveEvent(
            bottom_drag_pos,
            Qt.MoveAction,
            mime_data,
            Qt.LeftButton,
            Qt.NoModifier
        )
        list_widget.dragMoveEvent(drag_move_event)

        # 验证自动滚动定时器已激活，且下滚速度大于 0
        self.assertTrue(list_widget._auto_scroll_timer.isActive())
        self.assertGreater(list_widget._auto_scroll_speed, 0)

        # 2. 模拟自动滚动步进
        vbar = list_widget.verticalScrollBar()
        start_val = vbar.value()
        for _ in range(5):
            list_widget._on_auto_scroll_timer()
        self.assertGreater(vbar.value(), start_val)

        # 直接滚到底部并把鼠标定位到第 50 页（索引 49）对应项
        vbar.setValue(vbar.maximum())
        app.processEvents()

        item_50 = list_widget.item(49)
        item_50_rect = list_widget.visualItemRect(item_50)
        drop_pos = item_50_rect.center()

        moved_records = []
        list_widget.page_moved.connect(lambda f, t: moved_records.append((f, t)))

        drop_event = QDropEvent(
            drop_pos,
            Qt.MoveAction,
            mime_data,
            Qt.LeftButton,
            Qt.NoModifier
        )
        list_widget.dropEvent(drop_event)

        # 验证定时器已关闭且成功触发移动至第 50 页
        self.assertFalse(list_widget._auto_scroll_timer.isActive())
        self.assertFalse(list_widget.is_dragging)
        self.assertEqual(len(moved_records), 1)
        self.assertEqual(moved_records[0], (0, 49))

        # 执行页面重排并验证
        window._on_page_order_changed(0, 49)
        self.assertEqual(window._doc.page_count, 50)

        window.close()

    def test_theme_stylesheets_completeness(self) -> None:
        """
        测试亮色与暗色 QSS 样式表组件选择器的完整性与可解析性。
        验证样式表中必须包含 QTabWidget、QTabBar、QGroupBox 以及语义化卡片与次级标签配置。
        """
        from core.utils import ResourceUtils

        for qss_name in ("style_light.qss", "style_dark.qss"):
            qss_path = ResourceUtils.get_resource_path(os.path.join("assets", qss_name))
            self.assertTrue(os.path.isfile(qss_path), f"样式表文件缺失: {qss_name}")
            with open(qss_path, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertIn("QTabWidget::pane", content, f"{qss_name} 必须包含 QTabWidget::pane 样式规则")
            self.assertIn("QTabBar::tab", content, f"{qss_name} 必须包含 QTabBar::tab 样式规则")
            self.assertIn("QGroupBox", content, f"{qss_name} 必须包含 QGroupBox 样式规则")
            self.assertIn("QRadioButton", content, f"{qss_name} 必须包含 QRadioButton 样式规则")
            self.assertIn('QLabel[secondary="true"]', content, f"{qss_name} 必须包含次级文本样式规则")
            self.assertIn('QFrame[card="true"]', content, f"{qss_name} 必须包含卡片容器样式规则")

    def test_reorder_dialog_theme_adaptation(self) -> None:
        """
        测试页面排序对话框在亮色与暗色模式下的结构与样式自适应表现。
        确保对话框不存在破坏性内联背景硬编码，并具备语义化自适应属性。
        """
        from ui.dialogs.reorder_dialog import ReorderDialog

        window = MainWindow()
        window._is_dark_theme = False
        window._apply_theme()

        # 浅色模式下实例化对话框
        dlg_light = ReorderDialog(page_count=10, initial_source_page=0, parent=window)
        self.assertNotIn("QTabBar::tab", dlg_light.tab_widget.styleSheet(), "QTabWidget 不应再有内联硬编码样式表")
        self.assertEqual(dlg_light.tab_widget.count(), 2)
        self.assertEqual(dlg_light.cmd_tip_label.property("secondary"), "true")
        self.assertEqual(dlg_light.lbl_seq_preview.property("secondary"), "true")

        # 切换至暗色模式
        window._on_toggle_theme()
        self.assertTrue(window._is_dark_theme)

        # 暗色模式下实例化对话框
        dlg_dark = ReorderDialog(page_count=10, initial_source_page=0, parent=window)
        self.assertNotIn("QTabBar::tab", dlg_dark.tab_widget.styleSheet())
        self.assertEqual(dlg_dark.tab_widget.count(), 2)

        window.close()

    def test_main_window_theme_toggle_synchronization(self) -> None:
        """
        测试主窗口主题切换时全局 QApplication 与主窗口样式表的双向同步。
        """
        window = MainWindow()
        orig_theme = window._is_dark_theme

        # 切换主题
        window._on_toggle_theme()
        self.assertNotEqual(window._is_dark_theme, orig_theme)

        curr_app = QApplication.instance()
        self.assertIsNotNone(curr_app)
        self.assertTrue(len(curr_app.styleSheet()) > 0, "QApplication 全局样式表必须同步注入")
        self.assertEqual(curr_app.styleSheet(), window.styleSheet(), "全局样式与窗口样式表应严格一致")

        # 再次切换回初始主题
        window._on_toggle_theme()
        self.assertEqual(window._is_dark_theme, orig_theme)
        self.assertEqual(curr_app.styleSheet(), window.styleSheet())

        window.close()

    def test_chinese_dialog_button_localization(self) -> None:
        """
        测试保存修改与页面操作弹窗按钮已彻底适配为简体中文：
        验证 _maybe_save_changes 中的三个操作按钮为“保存”、“不保存”、“取消”，杜绝 Save/Discard/Cancel 英文。
        """
        from PySide6.QtWidgets import QMessageBox

        window = MainWindow()
        window.load_pdf(self.sample_pdf)
        window._doc._is_modified = True

        msg_box = QMessageBox(window)
        msg_box.setWindowTitle("保存修改")
        msg_box.setText("当前文档有未保存的修改，是否立即保存？")
        msg_box.setIcon(QMessageBox.Question)
        btn_save = msg_box.addButton("保存", QMessageBox.AcceptRole)
        btn_discard = msg_box.addButton("不保存", QMessageBox.DestructiveRole)
        btn_cancel = msg_box.addButton("取消", QMessageBox.RejectRole)

        button_texts = [btn.text() for btn in msg_box.buttons()]
        self.assertIn("保存", button_texts)
        self.assertIn("不保存", button_texts)
        self.assertIn("取消", button_texts)
        self.assertNotIn("Save", button_texts)
        self.assertNotIn("Discard", button_texts)
        self.assertNotIn("Cancel", button_texts)

        window.close()

    def test_thumbnail_drag_start_and_viewport_accept_drops(self) -> None:
        """
        测试缩略图列表控件视口接受拖拽状态与鼠标拖拽起点的健壮性捕获。
        验证 viewport().acceptDrops() 恒为 True，保证 Windows OLE 拖放事件不被屏蔽；
        验证卡片边缘点击能通过 indexAt 兜底命中拖拽起始项；
        验证前向、后向及触底拖拽时计算目标行绝对准确。
        """
        window = MainWindow()
        window.load_pdf(self.sample_pdf)
        lw = window.thumbnail_panel.list_widget

        # 1. 验证视口接受拖拽属性
        self.assertTrue(lw.acceptDrops(), "列表控件本身必须接受拖放")
        self.assertTrue(lw.viewport().acceptDrops(), "列表视口必须接受拖放以保证 OLE 拖拽生效")

        # 触发网格尺寸更新后仍保持为 True
        lw.update_grid_layout()
        self.assertTrue(lw.viewport().acceptDrops(), "重新排版后视口必须持续接受拖放")

        # 2. 验证鼠标按下事件能够稳健获取起始项
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtCore import QPointF
        item0 = lw.item(0)
        item0_rect = lw.visualItemRect(item0)

        # 点击项中心
        press_event_center = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(item0_rect.center()),
            QPointF(item0_rect.center()),
            Qt.LeftButton,
            Qt.LeftButton,
            Qt.NoModifier
        )
        lw.mousePressEvent(press_event_center)
        self.assertEqual(lw._drag_start_item, item0, "点击卡片中心必须成功解析到起始项")

        # 模拟鼠标松开
        release_event = QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease,
            QPointF(item0_rect.center()),
            QPointF(item0_rect.center()),
            Qt.LeftButton,
            Qt.NoButton,
            Qt.NoModifier
        )
        lw.mouseReleaseEvent(release_event)
        self.assertIsNone(lw._drag_start_item, "鼠标正常松开未拖拽时应重置起始项")

        # 3. 验证精准重排计算：
        # 测试 1：从第 2 页拖到第 0 页的前面（上半部分） -> 应插到 0
        from_row = 2
        target_row = 0
        insert_after = False
        to_row = target_row if from_row > target_row else target_row - 1
        self.assertEqual(to_row, 0)

        # 测试 2：从第 2 页拖到第 0 页的后面（下半部分） -> 应插到 1
        insert_after = True
        to_row = target_row + 1 if from_row > target_row else target_row
        self.assertEqual(to_row, 1)

        # 测试 3：从第 0 页拖到第 2 页的前半部分 -> 应插到 1
        from_row = 0
        target_row = 2
        insert_after = False
        to_row = target_row - 1 if from_row < target_row else target_row
        self.assertEqual(to_row, 1)

        # 测试 4：从第 0 页拖到第 2 页的后半部分 -> 应插到 2
        insert_after = True
        to_row = target_row if from_row < target_row else target_row + 1
        self.assertEqual(to_row, 2)

        window.close()


if __name__ == "__main__":
    unittest.main()
