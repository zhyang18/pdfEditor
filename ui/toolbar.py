"""
顶部现代 Fluent 风格主工具栏组件。
整合文件读写、页面结构调整、任意页图片插入、Word 转换、多文件合并与画板缩放控制按钮。
全面支持根据窗口尺寸（尤其是 1024 宽、窄屏及超宽屏等各种环境）自适应调整按钮大小、文本与图标展示形态，确保所有功能永不折叠与截断。
"""

from typing import Optional, Dict, Tuple
from PySide6.QtWidgets import (
    QToolBar, QWidget, QToolButton, QLabel
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QAction, QResizeEvent
from assets.icons import IconLibrary


class PdfToolBar(QToolBar):
    """
    主界面现代功能工具栏。
    提供动作分组、SVG 矢量图标渲染、根据窗口尺寸智能自适应缩放与信号转发。
    """

    MODE_AUTO = "auto"
    MODE_FULL = "full"
    MODE_HYBRID = "hybrid"
    MODE_ICON = "icon"

    open_requested = Signal()
    save_requested = Signal()
    save_as_requested = Signal()
    print_requested = Signal()

    undo_requested = Signal()
    redo_requested = Signal()

    reorder_dialog_requested = Signal()
    rotate_right_requested = Signal()
    rotate_left_requested = Signal()
    insert_page_requested = Signal()
    delete_page_requested = Signal()

    insert_image_requested = Signal()
    delete_image_requested = Signal()
    bake_image_requested = Signal()
    cancel_image_requested = Signal()
    watermark_requested = Signal()

    merge_requested = Signal()
    split_requested = Signal()
    export_word_requested = Signal()
    import_word_requested = Signal()
    compress_requested = Signal()

    zoom_in_requested = Signal()
    zoom_out_requested = Signal()
    fit_page_requested = Signal()
    fit_width_requested = Signal()
    theme_toggle_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        初始化主工具栏实例并装配各组功能按钮与自适应属性。

        @param parent 包含该工具栏的父窗口组件
        """
        super().__init__("主操作栏", parent)
        self.setMovable(False)
        self.setFloatable(False)
        self._adaptive_mode: str = self.MODE_AUTO
        self._current_layout_mode: str = ""
        self._action_meta: Dict[QAction, Tuple[str, str, bool]] = {}

        self._init_actions()
        self._setup_action_meta()

    def _init_actions(self) -> None:
        """
        创建并组织各功能分区按钮。
        """
        # 1. 文件组
        self.act_open = self.addAction(IconLibrary.get_icon("open", 20), "打开")
        self.act_open.setToolTip("打开本地 PDF 文件 (Ctrl+O)")
        self.act_open.triggered.connect(self.open_requested.emit)

        self.act_save = self.addAction(IconLibrary.get_icon("save", 20), "保存")
        self.act_save.setToolTip("保存当前修改 (Ctrl+S)")
        self.act_save.triggered.connect(self.save_requested.emit)

        self.act_save_as = self.addAction(IconLibrary.get_icon("save_as", 20), "另存为")
        self.act_save_as.setToolTip("另存为新文件 (Ctrl+Shift+S)")
        self.act_save_as.triggered.connect(self.save_as_requested.emit)

        self.act_print = self.addAction(IconLibrary.get_icon("print", 20), "打印")
        self.act_print.setToolTip("打印当前文档 (Ctrl+P)")
        self.act_print.triggered.connect(self.print_requested.emit)

        self.addSeparator()

        # 2. 撤销/重做
        self.act_undo = self.addAction(IconLibrary.get_icon("undo", 18), "撤销")
        self.act_undo.setToolTip("撤销上一步操作 (Ctrl+Z)")
        self.act_undo.setEnabled(False)
        self.act_undo.triggered.connect(self.undo_requested.emit)

        self.act_redo = self.addAction(IconLibrary.get_icon("redo", 18), "重做")
        self.act_redo.setToolTip("重做已撤销操作 (Ctrl+Y)")
        self.act_redo.setEnabled(False)
        self.act_redo.triggered.connect(self.redo_requested.emit)

        self.addSeparator()

        # 3. 页面编排与旋转
        self.act_reorder = self.addAction(IconLibrary.get_icon("reorder", 18), "重排顺序")
        self.act_reorder.setToolTip("批量输入并重排页面顺序")
        self.act_reorder.triggered.connect(self.reorder_dialog_requested.emit)

        self.act_rot_right = self.addAction(IconLibrary.get_icon("rotate_right", 18), "旋转")
        self.act_rot_right.setToolTip("将当前页顺时针旋转 90°")
        self.act_rot_right.triggered.connect(self.rotate_right_requested.emit)

        self.act_insert_page = self.addAction(IconLibrary.get_icon("insert_page", 18), "插入空白页")
        self.act_insert_page.setToolTip("在当前页后插入一张标准 A4 空白页")
        self.act_insert_page.triggered.connect(self.insert_page_requested.emit)

        self.act_delete_page = self.addAction(IconLibrary.get_icon("delete_page", 18), "删除页")
        self.act_delete_page.setToolTip("删除当前正在查看的页面")
        self.act_delete_page.triggered.connect(self.delete_page_requested.emit)

        self.addSeparator()

        # 4. 图片插入与编辑
        self.act_insert_img = self.addAction(IconLibrary.get_icon("insert_image", 18), "插入图片")
        self.act_insert_img.setToolTip("选择图片并在当前页任意位置自由拖拽摆放、调整大小")
        self.act_insert_img.triggered.connect(self.insert_image_requested.emit)

        self.act_delete_img = self.addAction(IconLibrary.get_icon("delete_page", 18), "删除图片")
        self.act_delete_img.setToolTip("删除当前选中的图片 (Delete)")
        self.act_delete_img.setEnabled(False)
        self.act_delete_img.triggered.connect(self.delete_image_requested.emit)

        self.act_bake_img = self.addAction(IconLibrary.get_icon("save", 18), "固化图片")
        self.act_bake_img.setToolTip("确认并将当前图片写入保存到 PDF 页面")
        self.act_bake_img.setVisible(False)
        self.act_bake_img.triggered.connect(self.bake_image_requested.emit)

        self.act_cancel_img = self.addAction(IconLibrary.get_icon("delete_page", 18), "放弃图片")
        self.act_cancel_img.setToolTip("放弃当前未固化的图片")
        self.act_cancel_img.setVisible(False)
        self.act_cancel_img.triggered.connect(self.cancel_image_requested.emit)

        self.act_watermark = self.addAction(IconLibrary.get_icon("watermark", 18), "添加水印")
        self.act_watermark.setToolTip("为页面批量添加文本水印")
        self.act_watermark.triggered.connect(self.watermark_requested.emit)

        self.addSeparator()

        # 5. 格式转换与多文件合并
        self.act_merge = self.addAction(IconLibrary.get_icon("merge", 18), "多文件合并")
        self.act_merge.setToolTip("合并多个 PDF 文件并支持切片提取")
        self.act_merge.triggered.connect(self.merge_requested.emit)

        self.act_split = self.addAction(IconLibrary.get_icon("split", 18), "拆开(拆分)")
        self.act_split.setToolTip("在任意指定位置将当前 PDF 拆开为前后两个独立文件 (Ctrl+K)")
        self.act_split.triggered.connect(self.split_requested.emit)

        self.act_to_word = self.addAction(IconLibrary.get_icon("to_word", 18), "导出 Word")
        self.act_to_word.setToolTip("将当前 PDF 高保真转换为 Word (.docx)")
        self.act_to_word.triggered.connect(self.export_word_requested.emit)

        self.act_from_word = self.addAction(IconLibrary.get_icon("from_word", 18), "导入 Word")
        self.act_from_word.setToolTip("导入 Word (.docx/.doc) 并转换为 PDF 编辑")
        self.act_from_word.triggered.connect(self.import_word_requested.emit)

        self.act_compress = self.addAction(IconLibrary.get_icon("compress", 18), "压缩瘦身")
        self.act_compress.setToolTip("优化结构与压缩流对象，减小 PDF 文件大小")
        self.act_compress.triggered.connect(self.compress_requested.emit)

        self.addSeparator()

        # 6. 视图控制与主题
        self.act_zoom_in = self.addAction(IconLibrary.get_icon("zoom_in", 18), "放大")
        self.act_zoom_in.triggered.connect(self.zoom_in_requested.emit)

        self.act_zoom_out = self.addAction(IconLibrary.get_icon("zoom_out", 18), "缩小")
        self.act_zoom_out.triggered.connect(self.zoom_out_requested.emit)

        self.act_fit_page = self.addAction(IconLibrary.get_icon("fit_page", 18), "整页")
        self.act_fit_page.triggered.connect(self.fit_page_requested.emit)

        self.act_fit_width = self.addAction(IconLibrary.get_icon("fit_width", 18), "宽适")
        self.act_fit_width.triggered.connect(self.fit_width_requested.emit)

        self.act_theme = self.addAction(IconLibrary.get_icon("theme_toggle", 18), "切换主题")
        self.act_theme.setToolTip("在浅色现代风格与暗色夜间风格之间切换")
        self.act_theme.triggered.connect(self.theme_toggle_requested.emit)

    def _setup_action_meta(self) -> None:
        """
        初始化登记各 Action 的完整文案、精炼文案与核心频次优先级，用于响应式自适应切换。
        """
        self._action_meta = {
            self.act_open: ("打开", "打开", True),
            self.act_save: ("保存", "保存", True),
            self.act_save_as: ("另存为", "另存", True),
            self.act_print: ("打印", "打印", True),
            self.act_undo: ("撤销", "撤销", True),
            self.act_redo: ("重做", "重做", True),
            self.act_reorder: ("重排顺序", "重排", False),
            self.act_rot_right: ("旋转", "旋转", False),
            self.act_insert_page: ("插入空白页", "加页", False),
            self.act_delete_page: ("删除页", "删页", False),
            self.act_insert_img: ("插入图片", "插图", False),
            self.act_delete_img: ("删除图片", "删图", False),
            self.act_bake_img: ("固化图片", "固化", False),
            self.act_cancel_img: ("放弃图片", "放弃", False),
            self.act_watermark: ("添加水印", "水印", False),
            self.act_merge: ("多文件合并", "合并", True),
            self.act_split: ("拆开(拆分)", "拆分", True),
            self.act_to_word: ("导出 Word", "转Word", False),
            self.act_from_word: ("导入 Word", "导Word", False),
            self.act_compress: ("压缩瘦身", "压缩", False),
            self.act_zoom_in: ("放大", "放大", False),
            self.act_zoom_out: ("缩小", "缩小", False),
            self.act_fit_page: ("整页", "整页", False),
            self.act_fit_width: ("宽适", "宽适", False),
            self.act_theme: ("切换主题", "主题", False),
        }

    def adapt_to_width(self, width: int) -> None:
        """
        根据当前窗口或工具栏物理可用宽度，动态自适应调节按钮排布模式、尺寸与样式。

        @param width 工具栏当前可用物理宽度像素值
        """
        if width <= 0:
            return

        # 判定目标展示模式：根据可用宽度阶梯智能自适应
        if self._adaptive_mode == self.MODE_AUTO:
            if width >= 1850:
                target_mode = self.MODE_FULL
            elif width >= 1350:
                target_mode = self.MODE_HYBRID
            else:
                target_mode = self.MODE_ICON
        else:
            target_mode = self._adaptive_mode

        self._apply_layout_mode(target_mode, width)

    def _apply_layout_mode(self, mode: str, width: int) -> None:
        """
        应用指定的工具栏布局模式，调整所有按钮文本、图标样式与宽度。

        @param mode 目标布局模式（full、hybrid、icon）
        @param width 当前宽度数值
        """
        needs_style_refresh = (self._current_layout_mode != mode)
        self._current_layout_mode = mode

        if mode == self.MODE_FULL:
            self.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            for act, (full_text, _, _) in self._action_meta.items():
                act.setText(full_text)
                w = self.widgetForAction(act)
                if isinstance(w, QToolButton):
                    w.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
                    w.setMinimumWidth(0)
                    w.setMaximumWidth(16777215)
            self.setProperty("adaptive_style", "full")

        elif mode == self.MODE_HYBRID:
            self.setToolButtonStyle(Qt.ToolButtonIconOnly)
            for act, (full_text, compact_text, is_core) in self._action_meta.items():
                act.setText(compact_text if is_core else full_text)
                w = self.widgetForAction(act)
                if isinstance(w, QToolButton):
                    if is_core:
                        w.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
                    else:
                        w.setToolButtonStyle(Qt.ToolButtonIconOnly)
                    w.setMinimumWidth(0)
                    w.setMaximumWidth(16777215)
            self.setProperty("adaptive_style", "compact")

        else:  # MODE_ICON
            self.setToolButtonStyle(Qt.ToolButtonIconOnly)
            visible_acts = [act for act in self.actions() if act.isVisible()]
            count = max(1, len(visible_acts))
            avail_w = max(240, width - 60)
            btn_w = max(28, min(38, int(avail_w / count)))
            for act in self.actions():
                w = self.widgetForAction(act)
                if isinstance(w, QToolButton):
                    w.setToolButtonStyle(Qt.ToolButtonIconOnly)
                    w.setMinimumWidth(btn_w if act.isVisible() else 0)
                    w.setMaximumWidth(42)
            self.setProperty("adaptive_style", "icon")

        if needs_style_refresh:
            self.style().unpolish(self)
            self.style().polish(self)
            for act in self.actions():
                w = self.widgetForAction(act)
                if isinstance(w, QToolButton):
                    w.style().unpolish(w)
                    w.style().polish(w)

    def set_adaptive_mode(self, mode: str) -> None:
        """
        设置工具栏的响应式展示自适应模式。

        @param mode 自适应模式枚举字符串（auto、full、hybrid、icon）
        """
        self._adaptive_mode = mode
        self.adapt_to_width(self.width())

    def get_adaptive_mode(self) -> str:
        """
        获取当前工具栏配置的自适应模式标识。

        @return 当前模式标识字符串
        """
        return self._adaptive_mode

    def resizeEvent(self, event: QResizeEvent) -> None:
        """
        响应工具栏尺寸变化事件，实时联动执行智能自适应伸缩布局。

        @param event 尺寸改变事件
        """
        super().resizeEvent(event)
        self.adapt_to_width(event.size().width())

    def set_image_editing_mode(self, editing: bool) -> None:
        """
        根据是否正处于图片悬浮拖动状态，动态切换“固化”与“放弃”按钮的显示。

        @param editing 是否正处于图片放置调整状态
        """
        self.act_bake_img.setVisible(editing)
        self.act_cancel_img.setVisible(editing)
        self.act_insert_img.setEnabled(not editing)

    def update_undo_redo_state(self, can_undo: bool, can_redo: bool) -> None:
        """
        更新撤销与重做按钮的可用启用状态。

        @param can_undo 是否可撤销
        @param can_redo 是否可重做
        """
        self.act_undo.setEnabled(can_undo)
        self.act_redo.setEnabled(can_redo)

    def set_image_selected(self, selected: bool) -> None:
        """
        根据当前画布是否有图片被选中，动态启用或禁用“删除图片”按钮。

        @param selected 是否有图片图元处于选中状态
        """
        self.act_delete_img.setEnabled(selected)
