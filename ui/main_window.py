"""
PDF 编辑器主窗口模块。
整合主工具栏、左侧缩略图导航器、主画布工作区、状态栏，并处理全局快捷键、撤销重做状态和拖拽打开文件。
"""

import os
from typing import Optional, List
from PySide6.QtWidgets import (
    QMainWindow, QDockWidget, QFileDialog, QMessageBox,
    QLabel, QSlider, QHBoxLayout, QWidget, QSpinBox,
    QProgressDialog, QApplication, QDialog
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QKeySequence, QShortcut, QActionGroup, QResizeEvent

from core.pdf_document import PdfDocument
from core.history_manager import HistoryManager, Command
from core.utils import FileUtils, ResourceUtils, PageReorderHelper
from ui.toolbar import PdfToolBar
from ui.thumbnail_panel import ThumbnailPanel
from ui.canvas_view import PdfCanvasView
from assets.icons import IconLibrary


class PageMoveCommand(Command):
    """
    页面顺序移动可撤销命令。
    记录源位置与目标位置并在撤销时反向移动。
    """

    def __init__(self, pdf_doc: PdfDocument, from_idx: int, to_idx: int, main_window: "MainWindow") -> None:
        """
        初始化页面移动命令。

        @param pdf_doc 目标 PDF 文档对象
        @param from_idx 原始索引
        @param to_idx 目标索引
        @param main_window 主窗口实例
        """
        super().__init__(f"移动第 {from_idx + 1} 页到第 {to_idx + 1} 页")
        self._doc = pdf_doc
        self._from_idx = from_idx
        self._to_idx = to_idx
        self._main_window = main_window

    def execute(self) -> bool:
        """
        执行页面移动。

        @return 是否移动成功
        """
        success = self._doc.move_page(self._from_idx, self._to_idx)
        if success:
            self._main_window.thumbnail_panel.move_thumbnail_item(self._from_idx, self._to_idx)
            self._main_window.thumbnail_panel.set_current_page(self._to_idx)
            self._main_window.canvas_view.display_page(self._doc, self._to_idx)
            self._main_window._update_status_bar()
        return success

    def undo(self) -> bool:
        """
        反向移动恢复原状。

        @return 撤销是否成功
        """
        success = self._doc.move_page(self._to_idx, self._from_idx)
        if success:
            self._main_window.thumbnail_panel.move_thumbnail_item(self._to_idx, self._from_idx)
            self._main_window.thumbnail_panel.set_current_page(self._from_idx)
            self._main_window.canvas_view.display_page(self._doc, self._from_idx)
            self._main_window._update_status_bar()
        return success


class PageReorderCommand(Command):
    """
    页面批量重排与定向移动可撤销命令。
    基于置换与逆置换数学映射，支持重排操作与撤销 (Undo) 完美双向还原。
    """

    def __init__(
        self,
        pdf_doc: PdfDocument,
        new_order: List[int],
        description: str,
        main_window: "MainWindow"
    ) -> None:
        """
        初始化页面重排命令。

        @param pdf_doc 目标 PDF 文档对象
        @param new_order 重排后的 0-based 页面索引列表
        @param description 命令动作文本说明
        @param main_window 主窗口实例
        """
        super().__init__(description)
        self._doc = pdf_doc
        self._new_order = list(new_order)
        self._inverse_order = PageReorderHelper.calculate_inverse_permutation(new_order)
        self._main_window = main_window

    def execute(self) -> bool:
        """
        执行页面重排。

        @return 是否重排成功
        """
        success = self._doc.reorder_pages(self._new_order)
        if success:
            self._main_window.refresh_views(0)
            self._main_window.lbl_status.setText(f"已成功执行：{self.description}")
        return success

    def undo(self) -> bool:
        """
        撤销页面重排，按逆置换无损恢复原始页面排列。

        @return 撤销是否成功
        """
        success = self._doc.reorder_pages(self._inverse_order)
        if success:
            self._main_window.refresh_views(0)
            self._main_window.lbl_status.setText(f"已撤销操作：{self.description}")
        return success


class MoveOrResizeImageCommand(Command):
    """
    图片移动或放缩可撤销命令。
    记录操作前后的外接矩形并在撤销/重做时双向恢复。
    """

    def __init__(
        self,
        main_window: "MainWindow",
        layer_id: str,
        old_rect: tuple,
        new_rect: tuple
    ) -> None:
        """
        初始化图片几何调整命令。

        @param main_window 主窗口实例
        @param layer_id 目标图片图层 ID
        @param old_rect 原始矩形 (x0, y0, x1, y1)
        @param new_rect 变更后矩形 (x0, y0, x1, y1)
        """
        super().__init__("调整图片位置或尺寸")
        self._main_window = main_window
        self._layer_id = layer_id
        self._old_rect = old_rect
        self._new_rect = new_rect

    def execute(self) -> bool:
        """
        执行应用新几何尺寸。

        @return 是否成功应用
        """
        doc = self._main_window._doc
        if doc.image_layers.update_layer_rect(self._layer_id, self._new_rect):
            self._main_window.canvas_view.update_image_item_geometry(self._layer_id, self._new_rect)
            doc.set_modified(True)
            self._main_window._update_status_bar()
            return True
        return False

    def undo(self) -> bool:
        """
        撤销恢复为原始几何尺寸。

        @return 是否成功撤销
        """
        doc = self._main_window._doc
        if doc.image_layers.update_layer_rect(self._layer_id, self._old_rect):
            self._main_window.canvas_view.update_image_item_geometry(self._layer_id, self._old_rect)
            doc.set_modified(True)
            self._main_window._update_status_bar()
            return True
        return False


class DeleteImageCommand(Command):
    """
    删除图片可撤销命令。
    支持按下 Delete 键或右键删除图片后，随时通过 Ctrl+Z 完美撤销恢复。
    """

    def __init__(self, main_window: "MainWindow", layer_data: dict) -> None:
        """
        初始化删除图片命令。

        @param main_window 主窗口实例
        @param layer_data 被删除图层的全量属性字典
        """
        super().__init__("删除图片")
        self._main_window = main_window
        self._layer_data = layer_data
        self._layer_id = layer_data["id"]

    def execute(self) -> bool:
        """
        执行删除操作：从文档图层管理器与画板场景中移除。

        @return 是否删除成功
        """
        doc = self._main_window._doc
        removed = doc.image_layers.remove_layer(self._layer_id)
        if removed is not None:
            self._main_window.canvas_view.remove_image_item(self._layer_id)
            doc.set_modified(True)
            self._main_window._update_status_bar()
            return True
        return False

    def undo(self) -> bool:
        """
        撤销恢复操作：将图片重新添加回文档图层并加载在画布上。

        @return 是否撤销成功
        """
        from core.image_layer import ImageLayer
        doc = self._main_window._doc
        layer = ImageLayer.from_dict(self._layer_data)
        doc.image_layers.add_layer(
            page_index=layer.page_index,
            image_path=layer.image_path,
            rect=layer.rect,
            layer_id=layer.id
        )
        if self._main_window.canvas_view.current_page_index == layer.page_index:
            self._main_window.canvas_view.load_image_item_for_layer(layer)
        doc.set_modified(True)
        self._main_window._update_status_bar()
        return True


class InsertImageCommand(Command):
    """
    插入图片可撤销命令。
    支持在当前页插入图片后，按 Ctrl+Z 撤回插入。
    """

    def __init__(self, main_window: "MainWindow", layer_data: dict) -> None:
        """
        初始化插入图片命令。

        @param main_window 主窗口实例
        @param layer_data 插入图层的全量属性字典
        """
        super().__init__("插入图片")
        self._main_window = main_window
        self._layer_data = layer_data
        self._layer_id = layer_data["id"]

    def execute(self) -> bool:
        """
        执行插入图片。

        @return 是否执行成功
        """
        from core.image_layer import ImageLayer
        doc = self._main_window._doc
        layer = doc.image_layers.get_layer(self._layer_id)
        if layer is None:
            layer = ImageLayer.from_dict(self._layer_data)
            doc.image_layers.add_layer(
                page_index=layer.page_index,
                image_path=layer.image_path,
                rect=layer.rect,
                layer_id=layer.id
            )
        if self._main_window.canvas_view.current_page_index == layer.page_index:
            self._main_window.canvas_view.load_image_item_for_layer(layer)
        doc.set_modified(True)
        self._main_window._update_status_bar()
        return True

    def undo(self) -> bool:
        """
        撤销插入图片。

        @return 是否撤销成功
        """
        doc = self._main_window._doc
        removed = doc.image_layers.remove_layer(self._layer_id)
        if removed is not None:
            self._main_window.canvas_view.remove_image_item(self._layer_id)
            doc.set_modified(True)
            self._main_window._update_status_bar()
            return True
        return False


class MainWindow(QMainWindow):
    """
    PDF 编辑器主窗口类。
    负责各视图间的信号协同、文件状态提示、生命周期管理与弹窗触发。
    """

    def __init__(self) -> None:
        """
        初始化主窗口、核心文档对象、历史管理器与界面布局，并居中显示。
        """
        super().__init__()
        self.setWindowTitle("PDF 编辑器 - 极简清爽专业版")
        self.resize(1200, 800)
        self.setAcceptDrops(True)

        self._doc = PdfDocument()
        self._history = HistoryManager()
        self._history.add_on_change_listener(self._on_history_changed)
        self._is_dark_theme = False

        self._init_ui()
        self._setup_shortcuts()
        self._apply_theme()
        self._center_on_screen()
        self._update_status_bar()

    def _center_on_screen(self) -> None:
        """
        将主窗口居中于当前主屏幕可用可视区域。
        """
        screen = self.screen() or QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.x() + max(0, (geo.width() - self.width()) // 2)
            y = geo.y() + max(0, (geo.height() - self.height()) // 2)
            self.move(x, y)

    def _init_ui(self) -> None:
        """
        初始化窗口各功能部件与信号槽连接。
        """
        # 0. 顶部主菜单栏（确保各项功能永不被工具栏折叠）
        self._init_menu_bar()

        # 1. 顶部工具栏
        self.toolbar = PdfToolBar(self)
        self.addToolBar(self.toolbar)

        # 连接工具栏信号
        self.toolbar.open_requested.connect(self._on_open_file)
        self.toolbar.save_requested.connect(self._on_save_file)
        self.toolbar.save_as_requested.connect(self._on_save_as_file)
        self.toolbar.print_requested.connect(self._on_print_document)
        self.toolbar.undo_requested.connect(self._on_undo)
        self.toolbar.redo_requested.connect(self._on_redo)
        self.toolbar.reorder_dialog_requested.connect(self._on_open_reorder_dialog)
        self.toolbar.rotate_right_requested.connect(lambda: self._on_rotate_page(90))
        self.toolbar.rotate_left_requested.connect(lambda: self._on_rotate_page(270))
        self.toolbar.insert_page_requested.connect(self._on_insert_blank_page)
        self.toolbar.delete_page_requested.connect(self._on_delete_page)
        self.toolbar.insert_image_requested.connect(self._on_insert_image)
        self.toolbar.delete_image_requested.connect(self._on_delete_selected_image)
        self.toolbar.bake_image_requested.connect(self._on_bake_image)
        self.toolbar.cancel_image_requested.connect(self._on_cancel_image)
        self.toolbar.watermark_requested.connect(self._on_add_watermark)
        self.toolbar.merge_requested.connect(self._on_open_merge_dialog)
        self.toolbar.split_requested.connect(self._on_split_pdf)
        self.toolbar.export_word_requested.connect(self._on_export_to_word)
        self.toolbar.import_word_requested.connect(self._on_import_from_word)
        self.toolbar.compress_requested.connect(self._on_compress_document)
        self.toolbar.zoom_in_requested.connect(self._on_zoom_in)
        self.toolbar.zoom_out_requested.connect(self._on_zoom_out)
        self.toolbar.fit_page_requested.connect(self._on_fit_page)
        self.toolbar.fit_width_requested.connect(self._on_fit_width)
        self.toolbar.theme_toggle_requested.connect(self._on_toggle_theme)

        # 2. 中央画布视口
        self.canvas_view = PdfCanvasView(self)
        self.setCentralWidget(self.canvas_view)
        self.canvas_view.zoom_changed.connect(self._on_canvas_zoom_changed)
        self.canvas_view.image_burned.connect(self._on_image_burned)
        self.canvas_view.image_dropped_from_external.connect(self._on_image_dropped_from_external)
        self.canvas_view.image_transformed.connect(self._on_image_transformed)
        self.canvas_view.image_delete_requested.connect(self._on_image_delete_requested)
        self.canvas_view.image_selection_changed.connect(self._on_image_selection_changed)
        self.canvas_view.page_turn_requested.connect(self._on_canvas_page_turn_requested)

        # 3. 左侧缩略图停靠面板
        self.dock_thumbnail = QDockWidget("页面缩略图", self)
        self.dock_thumbnail.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        self.thumbnail_panel = ThumbnailPanel(self)
        self.dock_thumbnail.setWidget(self.thumbnail_panel)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.dock_thumbnail)

        # 连接缩略图信号
        self.thumbnail_panel.page_selected.connect(self._on_page_selected)
        self.thumbnail_panel.page_order_changed.connect(self._on_page_order_changed)
        self.thumbnail_panel.page_rotated.connect(self._on_thumbnail_rotate)
        self.thumbnail_panel.page_deleted.connect(self._on_thumbnail_delete)
        self.thumbnail_panel.page_inserted.connect(self._on_thumbnail_insert)
        self.thumbnail_panel.page_extracted.connect(self._on_thumbnail_extract)
        self.thumbnail_panel.split_requested.connect(self._on_split_pdf_at_page)
        self.thumbnail_panel.reorder_requested.connect(self._on_open_reorder_dialog)

        # 4. 底部状态栏
        self.status_bar = self.statusBar()
        self._init_status_bar()

        # 5. 工具栏初始自适应布局
        self.toolbar.adapt_to_width(self.width())

    def _init_menu_bar(self) -> None:
        """
        初始化主窗口现代 Fluent 风格多级菜单栏。
        提供文件、编辑、页面、工具与视图的直观固定入口，确保各项功能永不被工具栏折叠遮挡。
        """
        menubar = self.menuBar()

        # 1. 文件菜单
        menu_file = menubar.addMenu("文件(&F)")
        act_open = menu_file.addAction(IconLibrary.get_icon("open", 16), "打开本地文档...(&O)")
        act_open.setShortcut("Ctrl+O")
        act_open.triggered.connect(self._on_open_file)

        act_save = menu_file.addAction(IconLibrary.get_icon("save", 16), "保存(&S)")
        act_save.setShortcut("Ctrl+S")
        act_save.triggered.connect(self._on_save_file)

        act_save_as = menu_file.addAction(IconLibrary.get_icon("save_as", 16), "另存为...(&A)")
        act_save_as.setShortcut("Ctrl+Shift+S")
        act_save_as.triggered.connect(self._on_save_as_file)

        act_print = menu_file.addAction(IconLibrary.get_icon("print", 16), "打印...(&P)")
        act_print.setShortcut("Ctrl+P")
        act_print.triggered.connect(self._on_print_document)

        menu_file.addSeparator()
        act_exit = menu_file.addAction("退出(&X)")
        act_exit.setShortcut("Ctrl+Q")
        act_exit.triggered.connect(self.close)

        # 2. 编辑菜单
        menu_edit = menubar.addMenu("编辑(&E)")
        self.menu_act_undo = menu_edit.addAction(IconLibrary.get_icon("undo", 16), "撤销(&U)")
        self.menu_act_undo.setShortcut("Ctrl+Z")
        self.menu_act_undo.setEnabled(False)
        self.menu_act_undo.triggered.connect(self._on_undo)

        self.menu_act_redo = menu_edit.addAction(IconLibrary.get_icon("redo", 16), "重做(&R)")
        self.menu_act_redo.setShortcut("Ctrl+Y")
        self.menu_act_redo.setEnabled(False)
        self.menu_act_redo.triggered.connect(self._on_redo)

        menu_edit.addSeparator()
        act_insert_img = menu_edit.addAction(IconLibrary.get_icon("insert_image", 16), "插入图片...(&I)")
        act_insert_img.triggered.connect(self._on_insert_image)

        self.menu_act_del_img = menu_edit.addAction(IconLibrary.get_icon("delete_page", 16), "删除选中图片(&D)")
        self.menu_act_del_img.setShortcut("Delete")
        self.menu_act_del_img.setEnabled(False)
        self.menu_act_del_img.triggered.connect(self._on_delete_selected_image)

        # 3. 页面菜单（核心入口！）
        menu_page = menubar.addMenu("页面(&P)")
        act_split_page = menu_page.addAction(IconLibrary.get_icon("split", 16), "✂️ 拆开当前 PDF (一分为二)...(&K)")
        act_split_page.setShortcut("Ctrl+K")
        act_split_page.triggered.connect(self._on_split_pdf)

        menu_page.addSeparator()
        act_reorder = menu_page.addAction(IconLibrary.get_icon("reorder", 16), "批量重排页面顺序...(&R)")
        act_reorder.triggered.connect(self._on_open_reorder_dialog)

        act_rot_r = menu_page.addAction(IconLibrary.get_icon("rotate_right", 16), "顺时针旋转 90°")
        act_rot_r.triggered.connect(lambda: self._on_rotate_page(90))

        act_rot_l = menu_page.addAction(IconLibrary.get_icon("rotate_left", 16), "逆时针旋转 90°")
        act_rot_l.triggered.connect(lambda: self._on_rotate_page(270))

        menu_page.addSeparator()
        act_insert_p = menu_page.addAction(IconLibrary.get_icon("insert_page", 16), "插入空白 A4 页")
        act_insert_p.triggered.connect(self._on_insert_blank_page)

        act_del_p = menu_page.addAction(IconLibrary.get_icon("delete_page", 16), "删除当前页")
        act_del_p.triggered.connect(self._on_delete_page)

        # 4. 工具菜单
        menu_tools = menubar.addMenu("工具(&T)")
        act_split_tool = menu_tools.addAction(IconLibrary.get_icon("split", 16), "✂️ 拆开 PDF 文档...")
        act_split_tool.triggered.connect(self._on_split_pdf)

        act_merge = menu_tools.addAction(IconLibrary.get_icon("merge", 16), "多文件合并向导...(&M)")
        act_merge.triggered.connect(self._on_open_merge_dialog)

        menu_tools.addSeparator()
        act_export_word = menu_tools.addAction(IconLibrary.get_icon("to_word", 16), "导出 Word 文档 (.docx)...")
        act_export_word.triggered.connect(self._on_export_to_word)

        act_import_word = menu_tools.addAction(IconLibrary.get_icon("from_word", 16), "导入 Word 并转换为 PDF...")
        act_import_word.triggered.connect(self._on_import_from_word)

        menu_tools.addSeparator()
        act_compress = menu_tools.addAction(IconLibrary.get_icon("compress", 16), "压缩瘦身优化...")
        act_compress.triggered.connect(self._on_compress_document)

        act_watermark = menu_tools.addAction(IconLibrary.get_icon("watermark", 16), "添加文本水印...")
        act_watermark.triggered.connect(self._on_add_watermark)

        menu_tools.addSeparator()
        act_print_tool = menu_tools.addAction(IconLibrary.get_icon("print", 16), "打印当前文档...(&P)")
        act_print_tool.triggered.connect(self._on_print_document)

        # 5. 视图菜单
        menu_view = menubar.addMenu("视图(&V)")
        act_zin = menu_view.addAction(IconLibrary.get_icon("zoom_in", 16), "放大(&I)")
        act_zin.setShortcut("Ctrl++")
        act_zin.triggered.connect(self._on_zoom_in)

        act_zout = menu_view.addAction(IconLibrary.get_icon("zoom_out", 16), "缩小(&O)")
        act_zout.setShortcut("Ctrl+-")
        act_zout.triggered.connect(self._on_zoom_out)

        act_fit_p = menu_view.addAction(IconLibrary.get_icon("fit_page", 16), "适应整页")
        act_fit_p.triggered.connect(self._on_fit_page)

        act_fit_w = menu_view.addAction(IconLibrary.get_icon("fit_width", 16), "适应页面宽度")
        act_fit_w.triggered.connect(self._on_fit_width)

        menu_view.addSeparator()

        # 工具栏显示自适应样式单选组
        menu_tb_style = menu_view.addMenu("工具栏显示样式(&T)")
        self._tb_action_group = QActionGroup(self)
        self._tb_action_group.setExclusive(True)

        act_tb_auto = menu_tb_style.addAction("📐 自动随窗口大小自适应 (推荐)")
        act_tb_auto.setCheckable(True)
        act_tb_auto.setChecked(True)
        self._tb_action_group.addAction(act_tb_auto)
        act_tb_auto.triggered.connect(lambda: self.toolbar.set_adaptive_mode(PdfToolBar.MODE_AUTO))

        act_tb_full = menu_tb_style.addAction("🔤 完整图标与文本 (宽屏)")
        act_tb_full.setCheckable(True)
        self._tb_action_group.addAction(act_tb_full)
        act_tb_full.triggered.connect(lambda: self.toolbar.set_adaptive_mode(PdfToolBar.MODE_FULL))

        act_tb_hybrid = menu_tb_style.addAction("🔀 紧凑精炼混合模式")
        act_tb_hybrid.setCheckable(True)
        self._tb_action_group.addAction(act_tb_hybrid)
        act_tb_hybrid.triggered.connect(lambda: self.toolbar.set_adaptive_mode(PdfToolBar.MODE_HYBRID))

        act_tb_icon = menu_tb_style.addAction("🖼️ 纯图标模式 (超紧凑)")
        act_tb_icon.setCheckable(True)
        self._tb_action_group.addAction(act_tb_icon)
        act_tb_icon.triggered.connect(lambda: self.toolbar.set_adaptive_mode(PdfToolBar.MODE_ICON))

        menu_view.addSeparator()
        act_theme = menu_view.addAction(IconLibrary.get_icon("theme_toggle", 16), "切换浅色/暗色主题")
        act_theme.triggered.connect(self._on_toggle_theme)

    def _init_status_bar(self) -> None:
        """
        初始化状态栏组件：状态说明、页码跳转、缩放比例控制器。
        """
        self.lbl_status = QLabel("就绪")
        self.status_bar.addWidget(self.lbl_status, 1)

        # 页码指示器与跳转
        self.lbl_page_info = QLabel("第 0 / 0 页")
        self.lbl_page_info.setStyleSheet("font-weight: 500; margin-right: 8px;")
        self.status_bar.addPermanentWidget(self.lbl_page_info)

        # 页码直接跳转 SpinBox
        self.spin_page_jump = QSpinBox()
        self.spin_page_jump.setRange(1, 1)
        self.spin_page_jump.setEnabled(False)
        self.spin_page_jump.setToolTip("输入页码并按回车直接跳转")
        self.spin_page_jump.valueChanged.connect(self._on_page_jump_changed)
        self.status_bar.addPermanentWidget(self.spin_page_jump)

        # 缩放指示
        self.lbl_zoom = QLabel("100%")
        self.lbl_zoom.setStyleSheet("margin-left: 12px; margin-right: 6px;")
        self.status_bar.addPermanentWidget(self.lbl_zoom)

        # 文件物理大小信息
        self.lbl_file_size = QLabel("")
        self.lbl_file_size.setStyleSheet("color: #64748B; margin-left: 8px;")
        self.status_bar.addPermanentWidget(self.lbl_file_size)

    def _setup_shortcuts(self) -> None:
        """
        配置常用快捷键，提升操作效率。
        """
        QShortcut(QKeySequence.Open, self, self._on_open_file)
        QShortcut(QKeySequence.Save, self, self._on_save_file)
        QShortcut(QKeySequence.SaveAs, self, self._on_save_as_file)
        QShortcut(QKeySequence.Print, self, self._on_print_document)
        QShortcut(QKeySequence.Undo, self, self._on_undo)
        QShortcut(QKeySequence.Redo, self, self._on_redo)
        QShortcut(QKeySequence.ZoomIn, self, self._on_zoom_in)
        QShortcut(QKeySequence.ZoomOut, self, self._on_zoom_out)
        QShortcut(QKeySequence("Ctrl+K"), self, self._on_split_pdf)
        QShortcut(QKeySequence.Delete, self, self._on_delete_selected_image)

    def refresh_views(self, target_page: Optional[int] = None) -> None:
        """
        同步刷新缩略图列表、主画板显示及状态栏信息。

        @param target_page 刷新后需要展示的目标页面索引；若为 None 则保持当前页
        """
        if not self._doc.is_open or self._doc.page_count == 0:
            self.thumbnail_panel.load_thumbnails(self._doc)
            self.canvas_view.display_page(self._doc, 0)
            self._update_status_bar()
            return

        total = self._doc.page_count
        current = self.canvas_view.current_page_index
        if target_page is not None:
            new_page = max(0, min(target_page, total - 1))
        else:
            new_page = max(0, min(current, total - 1))

        self.thumbnail_panel.load_thumbnails(self._doc)
        self.thumbnail_panel.set_current_page(new_page)
        self.canvas_view.display_page(self._doc, new_page)
        self._update_status_bar()

    def _update_status_bar(self) -> None:
        """
        根据当前文档状态更新状态栏各指示器内容。
        """
        if not self._doc.is_open or self._doc.page_count == 0:
            self.lbl_page_info.setText("未加载文档")
            self.spin_page_jump.setEnabled(False)
            self.lbl_file_size.setText("")
            self.setWindowTitle("PDF 编辑器 - 极简清爽专业版")
            return

        total = self._doc.page_count
        curr = self.canvas_view.current_page_index + 1
        self.lbl_page_info.setText(f"第 {curr} / {total} 页")

        self.spin_page_jump.blockSignals(True)
        self.spin_page_jump.setEnabled(True)
        self.spin_page_jump.setRange(1, total)
        self.spin_page_jump.setValue(curr)
        self.spin_page_jump.blockSignals(False)

        path = self._doc.file_path
        size_str = FileUtils.get_file_size_str(path) if path else "未保存新文档"
        self.lbl_file_size.setText(f"大小: {size_str}")

        mod_flag = " *" if self._doc.is_modified else ""
        doc_name = os.path.basename(path) if path else "未命名文档"
        self.setWindowTitle(f"{doc_name}{mod_flag} - PDF 编辑器")

    def _on_open_file(self) -> None:
        """
        弹出文件选择对话框并打开指定 PDF 文件。
        """
        if not self._maybe_save_changes():
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "打开 PDF 文档",
            "",
            "PDF 文件 (*.pdf);;所有文件 (*.*)"
        )
        if not file_path:
            return

        self.load_pdf(file_path)

    def load_pdf(self, file_path: str) -> None:
        """
        载入指定路径的 PDF 文档并刷新视图。

        @param file_path 目标 PDF 文件路径
        """
        success = self._doc.open(file_path)
        if success:
            self._history.clear()
            self.refresh_views(0)
            self.canvas_view.fit_page()
            self.lbl_status.setText(f"成功打开：{os.path.basename(file_path)}")
        else:
            QMessageBox.critical(self, "错误", "无法打开该 PDF 文件，可能文件已损坏或为加密受保护文件。")

    def _on_save_file(self) -> None:
        """
        保存当前修改。若为新文档则触发另存为。
        """
        if not self._doc.is_open:
            return

        if not self._doc.file_path:
            self._on_save_as_file()
            return

        success = self._doc.save()
        if success:
            self._update_status_bar()
            self.lbl_status.setText("文档保存成功！")
        else:
            QMessageBox.critical(self, "保存失败", "保存文件时发生错误，请检查文件是否被其他程序占用。")

    def _on_save_as_file(self) -> None:
        """
        弹出另存为文件对话框保存至新路径。
        """
        if not self._doc.is_open:
            return

        out_path, _ = QFileDialog.getSaveFileName(
            self,
            "另存为 PDF 文件",
            "文档_副本.pdf",
            "PDF 文件 (*.pdf)"
        )
        if not out_path:
            return

        success = self._doc.save(out_path)
        if success:
            self._update_status_bar()
            self.lbl_status.setText(f"另存为成功：{os.path.basename(out_path)}")
        else:
            QMessageBox.critical(self, "另存为失败", "无法保存到目标路径。")

    def _on_undo(self) -> None:
        """
        响应撤销操作。
        """
        self._history.undo()

    def _on_redo(self) -> None:
        """
        响应重做操作。
        """
        self._history.redo()

    def _on_history_changed(self) -> None:
        """
        撤销/重做栈改变时联动更新工具栏按钮与菜单栏状态。
        """
        can_undo = self._history.can_undo()
        can_redo = self._history.can_redo()
        self.toolbar.update_undo_redo_state(can_undo, can_redo)
        if hasattr(self, "menu_act_undo"):
            self.menu_act_undo.setEnabled(can_undo)
        if hasattr(self, "menu_act_redo"):
            self.menu_act_redo.setEnabled(can_redo)
        desc = self._history.get_undo_description()
        if desc:
            self.lbl_status.setText(f"已执行操作：{desc}")

    def _on_page_selected(self, page_index: int) -> None:
        """
        响应左侧缩略图点击跳转。

        @param page_index 目标页面索引
        """
        self.canvas_view.display_page(self._doc, page_index)
        self._update_status_bar()

    def _on_canvas_page_turn_requested(self, new_page_index: int, scroll_to_bottom: bool = False) -> None:
        """
        响应画板视口滑轮或键盘滑动手势触发的翻页请求，同步更新缩略图和状态栏。

        @param new_page_index 目标页面索引（从 0 开始）
        @param scroll_to_bottom 翻页后是否将新页面视口滚动到底部
        """
        if not self._doc.is_open or not (0 <= new_page_index < self._doc.page_count):
            return

        self.canvas_view.display_page(self._doc, new_page_index)
        self.thumbnail_panel.set_current_page(new_page_index)
        self._update_status_bar()

        if scroll_to_bottom:
            QTimer.singleShot(0, self.canvas_view.scroll_to_bottom)
        else:
            QTimer.singleShot(0, self.canvas_view.scroll_to_top)

    def _on_page_order_changed(self, from_idx: int, to_idx: int) -> None:
        """
        响应缩略图拖拽或上移下移按钮调整页面排序。

        @param from_idx 源页面索引
        @param to_idx 目标页面索引
        """
        if not self._doc.is_open or from_idx == to_idx:
            return

        cmd = PageMoveCommand(self._doc, from_idx, to_idx, self)
        self._history.push(cmd)

    def _on_open_reorder_dialog(self, initial_source_page: Optional[int] = None) -> None:
        """
        弹出批量页码重排与定向移动输入对话框（按需懒加载）。
        通过 PageReorderCommand 将重排操作纳入撤销/重做历史栈。

        @param initial_source_page 初始预设的源页面 0-based 索引（可选，默认为空）
        """
        if not self._doc.is_open or self._doc.page_count < 2:
            QMessageBox.information(self, "提示", "当前文档页面不足 2 页，无需重排。")
            return

        # 过滤 QAction.triggered 信号默认传递的 checked: bool 参数
        if isinstance(initial_source_page, bool):
            initial_source_page = None

        from ui.dialogs.reorder_dialog import ReorderDialog
        dlg = ReorderDialog(
            page_count=self._doc.page_count,
            initial_source_page=initial_source_page,
            parent=self
        )
        if dlg.exec():
            new_order = dlg.new_order
            desc = dlg.operation_description or "批量重排页面顺序"
            cmd = PageReorderCommand(self._doc, new_order, desc, self)
            self._history.push(cmd)

    def _on_rotate_page(self, angle: int) -> None:
        """
        旋转当前查看的页面。

        @param angle 顺时针旋转角度
        """
        if not self._doc.is_open:
            return

        curr = self.canvas_view.current_page_index
        success = self._doc.rotate_page(curr, angle)
        if success:
            self.refresh_views(curr)

    def _on_thumbnail_rotate(self, page_index: int, angle: int) -> None:
        """
        响应右键菜单指定页面旋转。
        采用增量式单页局部刷新，彻底避免重载整个缩略图列表。

        @param page_index 目标页面索引
        @param angle 旋转角度
        """
        success = self._doc.rotate_page(page_index, angle)
        if success:
            self.thumbnail_panel.rotate_page_thumbnail(page_index, angle)
            if self.canvas_view.current_page_index == page_index:
                self.canvas_view.display_page(self._doc, page_index)
            self._update_status_bar()

    def _on_insert_blank_page(self) -> None:
        """
        在当前页后面插入一张标准 A4 空白页。
        """
        if not self._doc.is_open:
            # 若未打开文档，则创建一个新文档
            self._doc.create_empty()
            self.refresh_views(0)
            return

        curr = self.canvas_view.current_page_index
        target_idx = curr + 1
        success = self._doc.insert_blank_page(target_idx)
        if success:
            self.thumbnail_panel.insert_thumbnail_item(target_idx)
            self.thumbnail_panel.set_current_page(target_idx)
            self.canvas_view.display_page(self._doc, target_idx)
            self._update_status_bar()
            self.lbl_status.setText(f"已在第 {target_idx + 1} 页插入空白页！")

    def _on_thumbnail_insert(self, target_index: int) -> None:
        """
        响应缩略图右键插入空白页。

        @param target_index 插入索引
        """
        success = self._doc.insert_blank_page(target_index)
        if success:
            self.thumbnail_panel.insert_thumbnail_item(target_index)
            self.thumbnail_panel.set_current_page(target_index)
            self.canvas_view.display_page(self._doc, target_index)
            self._update_status_bar()

    def _on_delete_page(self) -> None:
        """
        删除当前查看的页面。
        """
        if not self._doc.is_open:
            return
        if self._doc.page_count <= 1:
            QMessageBox.warning(self, "提示", "当前文档仅剩 1 页，无法继续删除！")
            return

        curr = self.canvas_view.current_page_index
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("确认删除")
        msg_box.setText(f"确定要删除当前第 {curr + 1} 页吗？此操作不可逆。")
        msg_box.setIcon(QMessageBox.Question)
        btn_confirm = msg_box.addButton("确定删除", QMessageBox.AcceptRole)
        btn_cancel = msg_box.addButton("取消", QMessageBox.RejectRole)
        msg_box.setDefaultButton(btn_cancel)
        msg_box.exec()
        if msg_box.clickedButton() == btn_confirm:
            success = self._doc.delete_page(curr)
            if success:
                self.thumbnail_panel.delete_thumbnail_item(curr)
                new_idx = max(0, min(curr, self._doc.page_count - 1))
                self.thumbnail_panel.set_current_page(new_idx)
                self.canvas_view.display_page(self._doc, new_idx)
                self._update_status_bar()
                self.lbl_status.setText("页面已成功删除！")

    def _on_thumbnail_delete(self, page_index: int) -> None:
        """
        响应缩略图右键删除特定页。

        @param page_index 待删除页索引
        """
        if self._doc.page_count <= 1:
            QMessageBox.warning(self, "提示", "当前文档仅剩 1 页，无法继续删除！")
            return

        success = self._doc.delete_page(page_index)
        if success:
            self.thumbnail_panel.delete_thumbnail_item(page_index)
            new_idx = max(0, min(page_index, self._doc.page_count - 1))
            self.thumbnail_panel.set_current_page(new_idx)
            self.canvas_view.display_page(self._doc, new_idx)
            self._update_status_bar()

    def _on_thumbnail_extract(self, page_index: int) -> None:
        """
        响应缩略图右键提取特定页面。

        @param page_index 提取页索引
        """
        out_path, _ = QFileDialog.getSaveFileName(
            self,
            f"提取第 {page_index + 1} 页另存为",
            f"页面_{page_index + 1}.pdf",
            "PDF 文件 (*.pdf)"
        )
        if not out_path:
            return

        success = self._doc.extract_pages([page_index], out_path)
        if success:
            QMessageBox.information(self, "成功", f"第 {page_index + 1} 页已成功提取导出至：\n{out_path}")
        else:
            QMessageBox.critical(self, "错误", "提取页面保存失败。")

    def _on_insert_image(self) -> None:
        """
        弹出图片选择对话框，并在当前页画布上添加悬浮图片图层供用户拖拽与调整大小。
        记录 InsertImageCommand 进入撤销重做栈。
        """
        if not self._doc.is_open:
            QMessageBox.information(self, "提示", "请先打开或创建一个 PDF 文档再插入图片。")
            return

        img_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择要插入的图片",
            "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.webp);;所有文件 (*.*)"
        )
        if not img_path:
            return

        layer = self.canvas_view.add_floating_image(img_path)
        if layer is not None:
            cmd = InsertImageCommand(self, layer.to_dict())
            self._history.push(cmd)
            self.toolbar.set_image_editing_mode(True)
            self._update_status_bar()
            self.lbl_status.setText("图片已插入！可随时鼠标拖动位置、拉动 8 个边角把手缩放，或按 Delete 键删除，随时可按 Ctrl+Z 撤消。")

    def _on_image_dropped_from_external(self, image_path: str) -> None:
        """
        外部图片直接拖拽释放到画板后的槽函数，联动工具栏与状态栏提示。

        @param image_path 拖拽释放的本地图片文件路径
        """
        self.toolbar.set_image_editing_mode(True)
        self._update_status_bar()
        self.lbl_status.setText(f"已从外部拖入图片：{os.path.basename(image_path)}！可自由拖动位置或拉伸缩放，随时按 Delete 键删除或 Ctrl+Z 撤消。")

    def _on_image_transformed(self, layer_id: str, old_rect: tuple, new_rect: tuple) -> None:
        """
        处理画板上图片移动或拉伸放缩完成事件，封装为可撤销命令并推入历史栈。

        @param layer_id 目标图层唯一 ID
        @param old_rect 变更前的绝对场景物理坐标矩形 (x0, y0, x1, y1)
        @param new_rect 变更后的绝对场景物理坐标矩形 (x0, y0, x1, y1)
        """
        cmd = MoveOrResizeImageCommand(self, layer_id, old_rect, new_rect)
        self._history.execute_command(cmd)

    def _on_image_delete_requested(self, layer_id: str) -> None:
        """
        处理图片删除请求（来自右键菜单或 Delete 快捷键），封装为可撤销命令并推入历史栈。

        @param layer_id 待删除图层唯一 ID
        """
        layer = self._doc.image_layers.get_layer(layer_id)
        if layer is not None:
            cmd = DeleteImageCommand(self, layer.to_dict())
            self._history.execute_command(cmd)
            self.lbl_status.setText("已删除选中图片，可按 Ctrl+Z 撤消。")

    def _on_delete_selected_image(self) -> None:
        """
        删除当前画板上选中的图片图层（响应工具栏【删除图片】按钮或全局 Delete 快捷键）。
        """
        item = self.canvas_view.get_selected_image_item()
        if item is not None and item.layer_id:
            self._on_image_delete_requested(item.layer_id)

    def _on_image_selection_changed(self, has_selected: bool) -> None:
        """
        画板图片图层选中状态变更响应，动态启用或禁用工具栏与菜单栏中的【删除图片】项。

        @param has_selected 当前是否有图片被鼠标选中
        """
        self.toolbar.set_image_selected(has_selected)
        if hasattr(self, "menu_act_del_img"):
            self.menu_act_del_img.setEnabled(has_selected)

    def _on_bake_image(self) -> None:
        """
        确认固化当前悬浮图片，将其永久烧录进 PDF 页面。
        """
        success = self.canvas_view.bake_active_image(self._doc)
        if success:
            self.toolbar.set_image_editing_mode(False)
            self.refresh_views(self.canvas_view.current_page_index)
            self.lbl_status.setText("图片已成功固化烧录到当前 PDF 页面！")
        else:
            QMessageBox.critical(self, "错误", "固化写入图片时发生错误。")

    def _on_cancel_image(self) -> None:
        """
        放弃当前未固化的图片图层。
        """
        self.canvas_view.cancel_active_image()
        self.toolbar.set_image_editing_mode(False)
        self.lbl_status.setText("已放弃图片插入。")

    def _on_image_burned(self, page_idx: int, path: str, rect: tuple) -> None:
        """
        图片烧录成功回调事件。

        @param page_idx 目标页
        @param path 本地图片路径
        @param rect 坐标矩形
        """
        self._doc.set_modified(True)
        self._update_status_bar()

    def _on_add_watermark(self) -> None:
        """
        弹出水印配置对话框并为页面添加水印（按需懒加载）。
        """
        if not self._doc.is_open:
            QMessageBox.information(self, "提示", "请先打开 PDF 文档再添加水印。")
            return

        from ui.dialogs.watermark_dialog import WatermarkDialog
        dlg = WatermarkDialog(self._doc.page_count, self)
        if dlg.exec():
            text, size, opacity, angle, pages = dlg.get_watermark_params()
            success = self._doc.add_text_watermark(
                text=text,
                font_size=size,
                opacity=opacity,
                angle=angle,
                page_indices=pages
            )
            if success:
                self.refresh_views(self.canvas_view.current_page_index)
                self.lbl_status.setText("水印已成功添加到文档！")
            else:
                QMessageBox.critical(self, "错误", "添加水印失败。")

    def _on_open_merge_dialog(self) -> None:
        """
        弹出独立的多文件合并向导对话框（按需懒加载）。
        """
        from ui.dialogs.merge_dialog import MergeDialog
        dlg = MergeDialog(self)
        if dlg.exec():
            self.lbl_status.setText("多文件合并已完成！")

    def _on_split_pdf(self) -> None:
        """
        弹出拆分 PDF 对话框，以当前浏览页码作为默认拆分分界点。
        """
        if not self._doc.is_open:
            QMessageBox.information(self, "提示", "请先打开一个 PDF 文档后再进行拆分。")
            return
        if self._doc.page_count < 2:
            QMessageBox.information(self, "提示", "当前文档只有 1 页，无法拆分为两个独立的 PDF 文件。")
            return

        from ui.dialogs.split_dialog import SplitDialog
        current_page = max(1, min(self.canvas_view.current_page_index + 1, self._doc.page_count - 1))
        dlg = SplitDialog(self._doc, initial_split_page=current_page, parent=self)
        if dlg.exec():
            self.lbl_status.setText("PDF 拆分已成功完成！")

    def _on_split_pdf_at_page(self, split_after_page: int) -> None:
        """
        从缩略图右键快捷触发在指定页码之后拆分 PDF。

        @param split_after_page 选定的分界截断页码（1-based）
        """
        if not self._doc.is_open:
            return
        if self._doc.page_count < 2:
            QMessageBox.information(self, "提示", "当前文档只有 1 页，无法拆分为两个独立的 PDF 文件。")
            return

        from ui.dialogs.split_dialog import SplitDialog
        dlg = SplitDialog(self._doc, initial_split_page=split_after_page, parent=self)
        if dlg.exec():
            self.lbl_status.setText(f"已在第 {split_after_page} 页之后拆分 PDF！")

    def _on_print_document(self) -> None:
        """
        触发 PDF 文档打印向导流程。
        校验当前文档打开状态，展示打印配置对话框，并在确认后启动高保真光栅化打印调度与进度反馈。
        """
        if not self._doc.is_open or self._doc.page_count == 0:
            QMessageBox.information(self, "提示", "请先打开需要打印的 PDF 文档。")
            return

        from ui.dialogs.print_dialog import PrintDialog
        from core.pdf_printer import PdfPrinter

        current_page = self.canvas_view.current_page_index
        dialog = PrintDialog(self._doc, current_page_index=current_page, parent=self)
        if dialog.exec() != QDialog.Accepted:
            return

        config = dialog.get_print_configuration()
        if config is None or not config.page_indices:
            return

        total_pages = len(config.page_indices)
        progress = QProgressDialog("正在准备打印任务...", "取消", 0, total_pages, self)
        progress.setWindowTitle("正在打印")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(200)
        progress.setValue(0)

        is_canceled = False

        def progress_callback(current_idx: int, total: int) -> bool:
            """
            打印进度更新与中断检测回调函数。

            @param current_idx 当前正在光栅化发送的页码序号（从 1 开始）
            @param total 待打印的总页数
            @return 若用户请求取消返回 False，否则返回 True 继续打印
            """
            nonlocal is_canceled
            if progress.wasCanceled():
                is_canceled = True
                return False
            progress.setValue(current_idx)
            progress.setLabelText(f"正在发送第 {current_idx} / {total} 页到打印机...")
            QApplication.processEvents()
            return True

        self.lbl_status.setText(f"正在向打印机 '{config.printer_name}' 发送任务...")
        QApplication.processEvents()

        success, message = PdfPrinter.print_document(
            self._doc,
            config,
            progress_callback=progress_callback
        )
        progress.close()

        if success:
            self.lbl_status.setText(f"打印成功：{message}")
            QMessageBox.information(self, "打印完成", message)
        else:
            if is_canceled:
                self.lbl_status.setText("用户取消了打印任务")
            else:
                self.lbl_status.setText(f"打印失败：{message}")
                QMessageBox.critical(self, "打印失败", message)

    def _on_export_to_word(self) -> None:
        """
        将当前 PDF 高保真转换为 Word (.docx) 文件。
        """
        if not self._doc.is_open or not self._doc.file_path:
            QMessageBox.information(self, "提示", "请先打开一个本地已保存的 PDF 文档再导出 Word。")
            return

        src_pdf = self._doc.file_path
        base_name = os.path.splitext(os.path.basename(src_pdf))[0]
        dst_docx, _ = QFileDialog.getSaveFileName(
            self,
            "导出 Word 文档",
            f"{base_name}.docx",
            "Word 文档 (*.docx)"
        )
        if not dst_docx:
            return

        from ui.dialogs.word_dialog import WordConvertDialog
        dlg = WordConvertDialog(mode="pdf_to_word", src_path=src_pdf, dst_path=dst_docx, parent=self)
        dlg.exec()
        if dlg.is_success:
            self.lbl_status.setText(f"Word 导出成功：{os.path.basename(dst_docx)}")

    def _on_import_from_word(self) -> None:
        """
        选择 Word 文件，将其转换为 PDF 并自动载入编辑器。
        """
        if not self._maybe_save_changes():
            return

        word_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择待导入的 Word 文档",
            "",
            "Word 文档 (*.docx *.doc);;所有文件 (*.*)"
        )
        if not word_path:
            return

        base_name = os.path.splitext(os.path.basename(word_path))[0]
        target_pdf, _ = QFileDialog.getSaveFileName(
            self,
            "设置转换后生成的 PDF 保存路径",
            f"{base_name}_转换.pdf",
            "PDF 文件 (*.pdf)"
        )
        if not target_pdf:
            return

        from ui.dialogs.word_dialog import WordConvertDialog
        dlg = WordConvertDialog(mode="word_to_pdf", src_path=word_path, dst_path=target_pdf, parent=self)
        dlg.exec()
        if dlg.is_success and os.path.isfile(target_pdf):
            self.load_pdf(target_pdf)
            self.lbl_status.setText(f"Word 已成功转换为 PDF 并载入！")

    def _on_compress_document(self) -> None:
        """
        压缩优化当前 PDF 文档，清除冗余对象并重新压缩。
        """
        if not self._doc.is_open or not self._doc.file_path:
            QMessageBox.information(self, "提示", "请先打开本地 PDF 文档再进行压缩。")
            return

        src_path = self._doc.file_path
        orig_size = os.path.getsize(src_path)
        base_name = os.path.splitext(os.path.basename(src_path))[0]

        out_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存瘦身压缩后的 PDF 文件",
            f"{base_name}_瘦身.pdf",
            "PDF 文件 (*.pdf)"
        )
        if not out_path:
            return

        success = self._doc.save(out_path)
        if success and os.path.isfile(out_path):
            new_size = os.path.getsize(out_path)
            orig_str = FileUtils.format_file_size(orig_size)
            new_str = FileUtils.format_file_size(new_size)
            saved_bytes = max(0, orig_size - new_size)
            saved_str = FileUtils.format_file_size(saved_bytes)

            QMessageBox.information(
                self,
                "压缩完成",
                f"PDF 瘦身压缩成功！\n原始大小：{orig_str}\n压缩后大小：{new_str}\n共节省空间：{saved_str}"
            )
            self.lbl_status.setText(f"已压缩保存至：{os.path.basename(out_path)}")
        else:
            QMessageBox.critical(self, "错误", "压缩失败。")

    def _on_zoom_in(self) -> None:
        """
        放大主画板。
        """
        self.canvas_view.zoom_in()

    def _on_zoom_out(self) -> None:
        """
        缩小主画板。
        """
        self.canvas_view.zoom_out()

    def _on_fit_page(self) -> None:
        """
        适应整个页面。
        """
        self.canvas_view.fit_page()

    def _on_fit_width(self) -> None:
        """
        适应页面宽度。
        """
        self.canvas_view.fit_width()

    def _on_canvas_zoom_changed(self, zoom_percent: int) -> None:
        """
        画板缩放比例更新槽函数。

        @param zoom_percent 缩放百分比整数
        """
        self.lbl_zoom.setText(f"{zoom_percent}%")

    def _on_page_jump_changed(self, val: int) -> None:
        """
        状态栏页码直接跳转。

        @param val 目标页码 (1-based)
        """
        target_idx = val - 1
        if 0 <= target_idx < self._doc.page_count:
            self.canvas_view.display_page(self._doc, target_idx)
            self.thumbnail_panel.set_current_page(target_idx)
            self._update_status_bar()

    def _on_toggle_theme(self) -> None:
        """
        切换浅色现代 Fluent 主题与暗色夜间主题。
        """
        self._is_dark_theme = not self._is_dark_theme
        self._apply_theme()
        theme_name = "暗色模式" if self._is_dark_theme else "清爽浅色模式"
        self.lbl_status.setText(f"已切换至{theme_name}")

    def _apply_theme(self) -> None:
        """
        从本地 QSS 样式表文件加载并注入应用程序全局及主窗口样式。
        基于 ResourceUtils 自包含寻址与动态资源路径映射，自动适配单文件 EXE 临时解压区。
        """
        style_file = "style_dark.qss" if self._is_dark_theme else "style_light.qss"
        content = ResourceUtils.load_stylesheet(style_file)
        if content:
            app = QApplication.instance()
            if app is not None:
                app.setStyleSheet(content)
            self.setStyleSheet(content)

    def _maybe_save_changes(self) -> bool:
        """
        检查文档是否有未保存修改，若有则弹出提示询问用户是否保存。

        @return 若用户同意继续操作返回 True，若用户点击取消则返回 False
        """
        if not self._doc.is_open or not self._doc.is_modified:
            return True

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("保存修改")
        msg_box.setText("当前文档有未保存的修改，是否立即保存？")
        msg_box.setIcon(QMessageBox.Question)
        btn_save = msg_box.addButton("保存", QMessageBox.AcceptRole)
        btn_discard = msg_box.addButton("不保存", QMessageBox.DestructiveRole)
        btn_cancel = msg_box.addButton("取消", QMessageBox.RejectRole)
        msg_box.setDefaultButton(btn_save)

        msg_box.exec()
        clicked = msg_box.clickedButton()
        if clicked == btn_save:
            self._on_save_file()
            return True
        elif clicked == btn_discard:
            return True
        else:
            return False

    IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif", ".tif", ".tiff")

    def resizeEvent(self, event: QResizeEvent) -> None:
        """
        响应主窗口尺寸改变事件，实时联动工具栏执行动态自适应伸缩布局。

        @param event 窗口尺寸改变事件
        """
        super().resizeEvent(event)
        if hasattr(self, "toolbar") and self.toolbar is not None:
            self.toolbar.adapt_to_width(event.size().width())

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """
        处理文件拖拽进入窗口事件，支持 PDF、Word 以及图片格式。

        @param event 拖拽进入事件
        """
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                path = urls[0].toLocalFile().lower()
                if (
                    path.endswith(".pdf")
                    or path.endswith(".docx")
                    or path.endswith(".doc")
                    or any(path.endswith(ext) for ext in self.IMAGE_EXTS)
                ):
                    event.acceptProposedAction()
                    return
        super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        """
        处理文件在窗口内释放事件，根据文件格式分别执行 PDF 打开、Word 转换或当前页图片插入。

        @param event 拖拽释放事件
        """
        urls = event.mimeData().urls()
        if not urls:
            return

        file_path = urls[0].toLocalFile()
        lower = file_path.lower()

        # 1. 拖入图片
        if any(lower.endswith(ext) for ext in self.IMAGE_EXTS):
            if self._doc.is_open:
                layer = self.canvas_view.add_floating_image(file_path)
                if layer is not None:
                    cmd = InsertImageCommand(self, layer.to_dict())
                    self._history.push(cmd)
                    self._on_image_dropped_from_external(file_path)
            else:
                QMessageBox.information(self, "提示", "请先打开一个 PDF 文档，然后再拖入图片进行插入。")
            return

        # 2. 拖入 PDF
        if lower.endswith(".pdf"):
            if self._maybe_save_changes():
                self.load_pdf(file_path)
            return

        # 3. 拖入 Word
        if lower.endswith(".docx") or lower.endswith(".doc"):
            reply = QMessageBox.question(
                self,
                "导入 Word 文档",
                f"检测到拖入 Word 文件：\n{os.path.basename(file_path)}\n是否立即将其转换为 PDF 并在此编辑？",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                base_name = os.path.splitext(os.path.basename(file_path))[0]
                target_pdf, _ = QFileDialog.getSaveFileName(
                    self,
                    "设置转换后生成的 PDF 保存路径",
                    f"{base_name}_转换.pdf",
                    "PDF 文件 (*.pdf)"
                )
                if target_pdf:
                    from ui.dialogs.word_dialog import WordConvertDialog
                    dlg = WordConvertDialog(mode="word_to_pdf", src_path=file_path, dst_path=target_pdf, parent=self)
                    dlg.exec()
                    if dlg.is_success and os.path.isfile(target_pdf):
                        self.load_pdf(target_pdf)

    def closeEvent(self, event) -> None:
        """
        窗口关闭拦截事件，确保未保存的改动得到妥善提醒。
        在无头离屏测试环境下自动释放文档并退出，避免模态弹窗挂起。

        @param event 关闭事件
        """
        if hasattr(self, "thumbnail_panel") and hasattr(self.thumbnail_panel, "worker"):
            self.thumbnail_panel.worker.stop()

        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            self._doc.close()
            event.accept()
            return

        if self._maybe_save_changes():
            self._doc.close()
            event.accept()
        else:
            event.ignore()
