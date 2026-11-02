"""
页面缩略图侧边栏面板组件。
支持高清晰度页面缩略图预览、流畅鼠标拖拽实时调整页码排序，以及右键页面操作上下文菜单。
"""

from typing import Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QListWidget, QListWidgetItem,
    QAbstractItemView, QMenu, QLabel, QHBoxLayout, QPushButton,
    QApplication
)
from PySide6.QtGui import QIcon, QPixmap, QDrag, QCursor
from PySide6.QtCore import Qt, Signal, QSize, QPoint, QMimeData
from core.pdf_document import PdfDocument
from assets.icons import IconLibrary


class ThumbnailListWidget(QListWidget):
    """
    支持鼠标拖拽实时调整页码顺序的自定义缩略图列表控件。
    基于 QDrag 提供跟随光标的半透明预览和精准目标行位移检测。
    """

    page_moved = Signal(int, int)  # 信号参数：(from_index, to_index)
    MIME_PAGE = "application/x-pdf-page-index"

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        初始化缩略图列表控件。

        @param parent 包含该控件的父窗口组件
        """
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setViewMode(QListWidget.IconMode)
        self.setIconSize(QSize(130, 180))
        self.setGridSize(QSize(150, 220))
        self.setResizeMode(QListWidget.Adjust)
        self.setSpacing(8)
        self.setAcceptDrops(True)

        self._drag_start_item: Optional[QListWidgetItem] = None
        self._drag_start_pos: QPoint = QPoint()

    def mousePressEvent(self, event) -> None:
        """
        捕获鼠标按下事件并记录拖拽起始项与位置。

        @param event 鼠标按下事件
        """
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.pos()
            self._drag_start_item = self.itemAt(event.pos())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        """
        捕获鼠标移动事件，达到拖拽距离阈值时启动 QDrag 操作。

        @param event 鼠标移动事件
        """
        if event.buttons() & Qt.LeftButton and self._drag_start_item is not None:
            distance = (event.pos() - self._drag_start_pos).manhattanLength()
            if distance >= QApplication.startDragDistance():
                self._start_custom_drag()
                return
        super().mouseMoveEvent(event)

    def _start_custom_drag(self) -> None:
        """
        构建包含被拖动项页码与缩略图半透明预览的 QDrag 对象并启动拖拽。
        """
        if self._drag_start_item is None:
            return

        from_row = self.row(self._drag_start_item)
        if from_row < 0:
            return

        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setData(self.MIME_PAGE, str(from_row).encode("utf-8"))
        mime_data.setText(str(from_row))
        drag.setMimeData(mime_data)

        # 制作半透明拖拽跟随图标
        icon_pixmap = self._drag_start_item.icon().pixmap(90, 120)
        drag.setPixmap(icon_pixmap)
        drag.setHotSpot(QPoint(icon_pixmap.width() // 2, icon_pixmap.height() // 2))

        drag.exec(Qt.MoveAction)
        self._drag_start_item = None

    def dragEnterEvent(self, event) -> None:
        """
        拖拽进入事件校验，仅响应带有有效页码信息的移动拖拽。

        @param event 拖拽进入事件
        """
        if event.mimeData().hasFormat(self.MIME_PAGE) or event.mimeData().text().isdigit():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        """
        拖拽移动过程实时高亮悬停目标项。

        @param event 拖拽移动事件
        """
        if event.mimeData().hasFormat(self.MIME_PAGE) or event.mimeData().text().isdigit():
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            target_item = self.itemAt(pos)
            if target_item is not None:
                self.setCurrentItem(target_item)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        """
        处理释放拖拽事件，精确计算目标行索引并发射 page_moved 信号。

        @param event 拖拽释放事件
        """
        has_page_mime = event.mimeData().hasFormat(self.MIME_PAGE) or event.mimeData().text().isdigit()
        if not has_page_mime:
            event.ignore()
            return

        if event.mimeData().hasFormat(self.MIME_PAGE):
            from_row = int(bytes(event.mimeData().data(self.MIME_PAGE)).decode("utf-8"))
        else:
            from_row = int(event.mimeData().text())

        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        target_item = self.itemAt(pos)

        if target_item is not None:
            to_row = self.row(target_item)
        else:
            # 若释放在空白处，根据垂直位置判断放置在首部或尾部
            if self.count() > 0 and pos.y() > self.rect().center().y():
                to_row = self.count() - 1
            else:
                to_row = 0

        to_row = max(0, min(to_row, self.count() - 1))
        event.accept()

        if from_row != to_row:
            self.page_moved.emit(from_row, to_row)


class ThumbnailPanel(QWidget):
    """
    左侧缩略图导航与页面编排面板。
    提供页面缩略图渲染、拖拽顺序调整、页码快速跳转与右键管理菜单。
    """

    page_selected = Signal(int)
    page_order_changed = Signal(int, int)
    page_rotated = Signal(int, int)
    page_deleted = Signal(int)
    page_inserted = Signal(int)
    page_extracted = Signal(int)
    split_requested = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        初始化页面缩略图面板。

        @param parent 包含该面板的父组件
        """
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self) -> None:
        """
        初始化界面布局与子控件。
        """
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # 顶部标题栏与快捷操作
        header_layout = QHBoxLayout()
        title_label = QLabel("页面导航与排序 (可拖拽)")
        title_label.setStyleSheet("font-weight: 600; color: #334155;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        self.up_btn = QPushButton()
        self.up_btn.setIcon(IconLibrary.get_icon("move_up", 16))
        self.up_btn.setToolTip("将选中页向上移动")
        self.up_btn.clicked.connect(self._on_move_up_clicked)
        header_layout.addWidget(self.up_btn)

        self.down_btn = QPushButton()
        self.down_btn.setIcon(IconLibrary.get_icon("move_down", 16))
        self.down_btn.setToolTip("将选中页向下移动")
        self.down_btn.clicked.connect(self._on_move_down_clicked)
        header_layout.addWidget(self.down_btn)

        self.split_btn = QPushButton("拆开")
        self.split_btn.setIcon(IconLibrary.get_icon("split", 14))
        self.split_btn.setToolTip("以当前选中页为分界点，将当前 PDF 拆开为两个文件")
        self.split_btn.setStyleSheet("padding: 2px 6px; font-size: 11px; font-weight: bold; color: #7C3AED;")
        self.split_btn.clicked.connect(self._on_split_clicked)
        self.btn_split = self.split_btn
        header_layout.addWidget(self.split_btn)

        layout.addLayout(header_layout)

        # 缩略图列表控件
        self.list_widget = ThumbnailListWidget(self)
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        self.list_widget.page_moved.connect(self._on_page_moved)
        self.list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.list_widget)

    def load_thumbnails(self, pdf_doc: PdfDocument) -> None:
        """
        根据当前 PDF 文档全量刷新渲染缩略图列表。

        @param pdf_doc 当前活动的 PDF 文档实体
        """
        self.list_widget.clear()
        if not pdf_doc.is_open:
            return

        total_pages = pdf_doc.page_count
        for i in range(total_pages):
            # 使用 120 DPI 高清晰度渲染缩略图基图，确保微缩文字清晰可辨
            qimage = pdf_doc.render_page_pixmap(i, dpi=120)
            if qimage is not None:
                pixmap = QPixmap.fromImage(qimage)
                scaled_pixmap = pixmap.scaled(
                    130, 180,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                item = QListWidgetItem(QIcon(scaled_pixmap), f"第 {i + 1} 页")
                item.setTextAlignment(Qt.AlignHCenter | Qt.AlignBottom)
                item.setData(Qt.UserRole, i)
                self.list_widget.addItem(item)

        if total_pages > 0:
            self.list_widget.setCurrentRow(0)

    @property
    def current_page_index(self) -> int:
        """
        获取当前高亮选中的页面索引。

        @return 页面索引（从 0 开始）；若未选中返回 -1
        """
        return self.list_widget.currentRow()

    def set_current_page(self, page_index: int) -> None:
        """
        设置当前高亮选中的页面项。

        @param page_index 页面索引（从 0 开始）
        """
        if 0 <= page_index < self.list_widget.count():
            self.list_widget.blockSignals(True)
            self.list_widget.setCurrentRow(page_index)
            self.list_widget.blockSignals(False)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        """
        缩略图项点击处理函数，触发页面跳转信号。

        @param item 被点击的列表项
        """
        row = self.list_widget.row(item)
        if row >= 0:
            self.page_selected.emit(row)

    def _on_page_moved(self, from_row: int, to_row: int) -> None:
        """
        拖拽调整顺序处理函数。

        @param from_row 原始行索引
        @param to_row 目标行索引
        """
        self.page_order_changed.emit(from_row, to_row)

    def _on_move_up_clicked(self) -> None:
        """
        点击“上移”按钮，将当前选中页向上移动一位。
        """
        curr = self.list_widget.currentRow()
        if curr > 0:
            self.page_order_changed.emit(curr, curr - 1)

    def _on_move_down_clicked(self) -> None:
        """
        点击“下移”按钮，将当前选中页向下移动一位。
        """
        curr = self.list_widget.currentRow()
        if 0 <= curr < self.list_widget.count() - 1:
            self.page_order_changed.emit(curr, curr + 1)

    def _on_split_clicked(self) -> None:
        """
        点击面板顶部的“拆开”按钮，在当前选中的页面之后拆开 PDF。
        """
        curr = self.list_widget.currentRow()
        split_point = curr + 1 if curr >= 0 else 1
        self.split_requested.emit(split_point)

    def _show_context_menu(self, pos) -> None:
        """
        弹出缩略图右键快捷管理菜单。

        @param pos 鼠标右键点击的相对坐标
        """
        item = self.list_widget.itemAt(pos)
        if item is None:
            return

        row = self.list_widget.row(item)
        menu = QMenu(self)

        action_up = menu.addAction(IconLibrary.get_icon("move_up", 16), "向上移动此页")
        action_down = menu.addAction(IconLibrary.get_icon("move_down", 16), "向下移动此页")
        menu.addSeparator()

        action_rot_right = menu.addAction(IconLibrary.get_icon("rotate_right", 16), "顺时针旋转 90°")
        action_rot_left = menu.addAction(IconLibrary.get_icon("rotate_left", 16), "逆时针旋转 90°")
        menu.addSeparator()

        action_insert = menu.addAction(IconLibrary.get_icon("insert_page", 16), "在此页后插入空白页")
        action_extract = menu.addAction(IconLibrary.get_icon("to_word", 16), "提取此页另存为...")
        action_split = menu.addAction(IconLibrary.get_icon("split", 16), "在此页之后拆分 PDF...")
        menu.addSeparator()

        action_delete = menu.addAction(IconLibrary.get_icon("delete_page", 16), "删除此页")

        action_up.setEnabled(row > 0)
        action_down.setEnabled(row < self.list_widget.count() - 1)
        action_split.setEnabled(self.list_widget.count() > 1 and row < self.list_widget.count() - 1)
        action_delete.setEnabled(self.list_widget.count() > 1)

        selected_action = menu.exec(self.list_widget.mapToGlobal(pos))
        if selected_action == action_up:
            self.page_order_changed.emit(row, row - 1)
        elif selected_action == action_down:
            self.page_order_changed.emit(row, row + 1)
        elif selected_action == action_rot_right:
            self.page_rotated.emit(row, 90)
        elif selected_action == action_rot_left:
            self.page_rotated.emit(row, 270)
        elif selected_action == action_insert:
            self.page_inserted.emit(row + 1)
        elif selected_action == action_extract:
            self.page_extracted.emit(row)
        elif selected_action == action_split:
            self.split_requested.emit(row + 1)
        elif selected_action == action_delete:
            self.page_deleted.emit(row)
