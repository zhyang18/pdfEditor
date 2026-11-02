"""
页面缩略图侧边栏面板组件。
支持默认单列大图显示、根据容器宽度自动合理分列（支持 1 列、2 列、3 列等多列响应式网格布局）、
多列与单列下流畅拖拽边缘自动平滑滚动及精准滚动插入到列表底部、以及右键页面操作上下文菜单。
"""

from typing import Optional, Tuple
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QListWidget, QListWidgetItem,
    QAbstractItemView, QMenu, QLabel, QHBoxLayout, QPushButton,
    QApplication, QStyledItemDelegate, QStyleOptionViewItem, QStyle,
    QListView
)
from PySide6.QtGui import (
    QIcon, QPixmap, QDrag, QCursor, QPainter, QColor, QPen, QBrush,
    QResizeEvent, QMouseEvent, QDragEnterEvent, QDragMoveEvent,
    QDragLeaveEvent, QDropEvent
)
from PySide6.QtCore import (
    Qt, Signal, QSize, QPoint, QRect, QMimeData, QTimer, QModelIndex
)
from core.pdf_document import PdfDocument
from assets.icons import IconLibrary


class ThumbnailDelegate(QStyledItemDelegate):
    """
    高清晰度自适应缩略图卡片项渲染委托。
    根据当前视口宽度及响应式多列布局结果绘制合适尺寸的缩略图卡片，
    并负责渲染现代卡片外框、真实页面缩略图、拟真纸张边缘、页码标签及拖拽指示标记。
    """

    def __init__(self, parent: Optional["ThumbnailListWidget"] = None) -> None:
        """
        初始化缩略图自适应委托。

        @param parent 关联的缩略图列表控件
        """
        super().__init__(parent)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        """
        根据当前分列计算后的合适卡片尺寸返回期望大小。

        @param option 视图项渲染选项
        @param index 数据模型索引
        @return 自适应计算后的卡片尺寸 QSize
        """
        parent_widget = self.parent()
        if isinstance(parent_widget, ThumbnailListWidget):
            return parent_widget.card_size
        return QSize(150, 200)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        """
        自适应绘制缩略图卡片、纸张图层、页码及多列拖拽目标指示标记。

        @param painter 绘图对象
        @param option 视图项渲染选项
        @param index 数据模型索引
        """
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        # 计算卡片绘制区域（扣除网格单元内的安全边距）
        card_rect = option.rect.adjusted(3, 3, -3, -3)

        # 判断主题深浅模式
        is_dark = option.palette.window().color().lightness() < 128
        is_selected = bool(option.state & QStyle.State_Selected)
        is_hover = bool(option.state & QStyle.State_MouseOver)

        parent_widget = self.parent()
        is_drop_target = (
            isinstance(parent_widget, ThumbnailListWidget)
            and parent_widget.is_dragging
            and parent_widget.drop_target_row == index.row()
        )

        # 1. 绘制卡片背景与边框
        if is_selected:
            bg_color = QColor("#1E3A8A") if is_dark else QColor("#EFF6FF")
            border_color = QColor("#3B82F6") if is_dark else QColor("#2563EB")
            border_width = 2
        elif is_drop_target:
            bg_color = QColor("#1E3A8A") if is_dark else QColor("#F0FDF4")
            border_color = QColor("#10B981") if is_dark else QColor("#059669")
            border_width = 2
        elif is_hover:
            bg_color = QColor("#334155") if is_dark else QColor("#F8FAFC")
            border_color = QColor("#475569") if is_dark else QColor("#CBD5E1")
            border_width = 1
        else:
            bg_color = QColor("#1E293B") if is_dark else QColor("#FFFFFF")
            border_color = QColor("#334155") if is_dark else QColor("#E2E8F0")
            border_width = 1

        painter.setPen(QPen(border_color, border_width))
        painter.setBrush(QBrush(bg_color))
        painter.drawRoundedRect(card_rect, 6, 6)

        # 2. 绘制页面缩略图
        thumb_area = QRect(
            card_rect.left() + 6,
            card_rect.top() + 6,
            card_rect.width() - 12,
            max(10, card_rect.height() - 32)
        )

        pixmap = index.data(Qt.UserRole + 1)
        if not isinstance(pixmap, QPixmap) or pixmap.isNull():
            icon = index.data(Qt.DecorationRole)
            if isinstance(icon, QIcon) and not icon.isNull():
                pixmap = icon.pixmap(thumb_area.size())

        if isinstance(pixmap, QPixmap) and not pixmap.isNull():
            scaled = pixmap.scaled(
                thumb_area.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            # 水平垂直居中
            draw_x = thumb_area.left() + (thumb_area.width() - scaled.width()) // 2
            draw_y = thumb_area.top() + (thumb_area.height() - scaled.height()) // 2
            draw_rect = QRect(draw_x, draw_y, scaled.width(), scaled.height())

            # 绘制拟真纸张轮廓边框
            paper_border = QColor("#475569") if is_dark else QColor("#CBD5E1")
            painter.setPen(QPen(paper_border, 1))
            painter.drawRect(draw_rect.adjusted(-1, -1, 1, 1))
            painter.drawPixmap(draw_rect, scaled)

        # 3. 绘制页码文本
        text_rect = QRect(
            card_rect.left(),
            card_rect.bottom() - 22,
            card_rect.width(),
            18
        )
        page_text = index.data(Qt.DisplayRole) or f"第 {index.row() + 1} 页"

        font = painter.font()
        font.setPointSize(9 if card_rect.width() < 140 else 10)
        font.setBold(is_selected)
        painter.setFont(font)

        if is_selected:
            text_color = QColor("#93C5FD") if is_dark else QColor("#2563EB")
        elif is_drop_target:
            text_color = QColor("#6EE7B7") if is_dark else QColor("#059669")
        else:
            text_color = QColor("#94A3B8") if is_dark else QColor("#475569")

        painter.setPen(text_color)
        painter.drawText(text_rect, Qt.AlignCenter, page_text)

        # 4. 绘制拖拽目标插入指示标记（单列画横线，多列画竖线与圆点）
        if is_drop_target and isinstance(parent_widget, ThumbnailListWidget):
            indicator_color = QColor("#2563EB") if not is_dark else QColor("#60A5FA")
            painter.setPen(QPen(indicator_color, 3, Qt.SolidLine, Qt.RoundCap))
            painter.setBrush(QBrush(indicator_color))

            if parent_widget.current_columns > 1:
                # 多列网格模式：根据前/后在卡片左边缘或右边缘绘制垂直插入指示线
                if parent_widget.drop_position_before:
                    x = card_rect.left()
                else:
                    x = card_rect.right()
                painter.drawLine(x, card_rect.top(), x, card_rect.bottom())
                painter.drawEllipse(QPoint(x, card_rect.top() + 2), 3, 3)
                painter.drawEllipse(QPoint(x, card_rect.bottom() - 2), 3, 3)
            else:
                # 单列模式：根据上/下在卡片顶部或底部绘制水平插入指示线
                if parent_widget.drop_position_before:
                    y = card_rect.top()
                else:
                    y = card_rect.bottom()
                painter.drawLine(card_rect.left(), y, card_rect.right(), y)
                painter.drawEllipse(QPoint(card_rect.left() + 2, y), 3, 3)
                painter.drawEllipse(QPoint(card_rect.right() - 2, y), 3, 3)

        painter.restore()


class ThumbnailListWidget(QListWidget):
    """
    支持默认单列大图显示、根据容器宽度智能分列与拖拽边缘平滑自动滚动的缩略图列表控件。
    默认侧边栏宽度下保持为 1 列表显示；主动拉宽时自动判定最佳分列数（支持多列），
    并在拖拽调整页码顺序时靠近视口边缘触发多级平滑自动滚动，完美支持多列模式下拖动滚动并插入到列表底部。
    """

    page_moved = Signal(int, int)  # 信号参数：(from_index, to_index)
    MIME_PAGE = "application/x-pdf-page-index"
    AUTO_SCROLL_MARGIN = 80  # 视口上下边缘触发自动滚动的阈值区域（像素，扩大感应区提升丝滑度）

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        初始化缩略图列表控件。

        @param parent 包含该控件的父窗口组件
        """
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setViewMode(QListWidget.IconMode)
        self.setResizeMode(QListWidget.Adjust)
        self.setSpacing(6)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)

        # 布局分列与尺寸状态（默认保持单列 1 列表显示）
        self._current_columns: int = 1
        self._card_size: QSize = QSize(160, 200)
        self._base_aspect_ratio: float = 1.414

        # 安装自定义自适应渲染委托
        self.thumbnail_delegate = ThumbnailDelegate(self)
        self.setItemDelegate(self.thumbnail_delegate)

        self._drag_start_item: Optional[QListWidgetItem] = None
        self._drag_start_pos: QPoint = QPoint()

        # 拖拽与自动滚动状态控制
        self._is_layouting: bool = False
        self._is_dragging: bool = False
        self._drop_target_row: int = -1
        self._drop_position_before: bool = True
        self._last_drag_pos: QPoint = QPoint()
        self._auto_scroll_speed: int = 0
        self._auto_scroll_timer: QTimer = QTimer(self)
        self._auto_scroll_timer.setInterval(20)
        self._auto_scroll_timer.timeout.connect(self._on_auto_scroll_timer)

    @property
    def current_columns(self) -> int:
        """
        获取当前响应式计算的最佳分列数。

        @return 当前列数（如 1, 2, 3...）
        """
        return self._current_columns

    @property
    def card_size(self) -> QSize:
        """
        获取当前卡片绘制的推荐尺寸。

        @return 卡片尺寸 QSize
        """
        return self._card_size

    @property
    def is_dragging(self) -> bool:
        """
        获取当前是否处于拖拽操作进行中。

        @return 是否处于拖拽状态
        """
        return self._is_dragging

    @property
    def drop_target_row(self) -> int:
        """
        获取当前拖拽悬停的目标行索引。

        @return 目标行索引；若无悬停则为 -1
        """
        return self._drop_target_row

    @property
    def drop_position_before(self) -> bool:
        """
        获取当前拖拽指示是插入在目标项之前还是之后。

        @return True 为之前（左方/上方），False 为之后（右方/下方）
        """
        return self._drop_position_before

    def _calc_layout_geometry(self) -> Tuple[int, QSize, QSize]:
        """
        根据当前视口宽度及文档实际几何纵横比，自动判定合适的大小宽度与最佳分列数。
        默认侧边栏宽度（< 360px）下始终保持为单列（1 列表）显示；
        仅当用户主动将容器拉宽达到充足空间时，才合理分列为 2 列、3 列或 4 列。

        @return 包含 (列数, 卡片总尺寸, 网格单元尺寸) 的元组
        """
        vp_w = self.viewport().width()
        if vp_w <= 0:
            vp_w = 260

        # 规则 1：默认侧边栏宽度（通常在 240px ~ 350px 区间）始终保持单列 (cols = 1) 显示
        # 规则 2：宽度 >= 360px 时合理升级为 2 列
        # 规则 3：宽度 >= 560px 时合理升级为 3 列
        # 规则 4：宽度 >= 760px 时合理升级为 4 列及以上
        if vp_w < 360:
            cols = 1
        elif vp_w < 560:
            cols = 2
        elif vp_w < 760:
            cols = 3
        else:
            cols = max(3, (vp_w - 20) // 180)

        usable_w = max(100, vp_w - 20)
        grid_w = max(90, usable_w // cols)
        card_w = grid_w - 6

        # 依据页面实际几何纵横比计算缩略图高度
        thumb_w = max(50, card_w - 12)
        thumb_h = int(thumb_w * self._base_aspect_ratio)
        max_h = int(thumb_w * 2.0)
        min_h = int(thumb_w * 0.35)
        thumb_h = max(min_h, min(thumb_h, max_h))

        card_h = thumb_h + 30
        grid_h = card_h + 6
        return cols, QSize(card_w, card_h), QSize(grid_w, grid_h)

    def update_grid_layout(self) -> None:
        """
        重新计算并应用响应式多列网格几何参数。
        """
        cols, card_size, grid_size = self._calc_layout_geometry()
        self._current_columns = cols
        self._card_size = card_size
        self.setGridSize(grid_size)

        for i in range(self.count()):
            item = self.item(i)
            if item is not None:
                item.setSizeHint(card_size)

        if not self._is_layouting:
            self._is_layouting = True
            try:
                self.scheduleDelayedItemsLayout()
            finally:
                self._is_layouting = False

    def resizeEvent(self, event: QResizeEvent) -> None:
        """
        响应控件尺寸调整事件，重新计算合适卡片宽度与列数分列并重绘。

        @param event 尺寸变化事件
        """
        super().resizeEvent(event)
        self.update_grid_layout()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """
        捕获鼠标按下事件并记录拖拽起始项与位置。
        支持从 itemAt、indexAt 及当前选中项多重解析起始项，避免边缘点击漏识别。

        @param event 鼠标按下事件
        """
        if event.button() == Qt.LeftButton:
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            self._drag_start_pos = pos
            item = self.itemAt(pos)
            if item is None:
                idx = self.indexAt(pos)
                if idx.isValid():
                    item = self.item(idx.row())
            if item is None:
                item = self.currentItem()
            self._drag_start_item = item
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """
        捕获鼠标释放事件，在未触发 QDrag 时重置拖拽起始项。

        @param event 鼠标释放事件
        """
        if not self._is_dragging:
            self._drag_start_item = None
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """
        捕获鼠标移动事件，达到拖拽距离阈值时启动 QDrag 操作。

        @param event 鼠标移动事件
        """
        if event.buttons() & Qt.LeftButton and self._drag_start_item is not None:
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            distance = (pos - self._drag_start_pos).manhattanLength()
            if distance >= QApplication.startDragDistance():
                self._start_custom_drag()
                return
        super().mouseMoveEvent(event)

    def _start_custom_drag(self) -> None:
        """
        构建包含被拖动项页码与缩略图半透明预览的 QDrag 对象并启动拖拽事件循环。
        """
        if self._drag_start_item is None:
            return

        from_row = self.row(self._drag_start_item)
        if from_row < 0:
            return

        self._is_dragging = True
        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setData(self.MIME_PAGE, str(from_row).encode("utf-8"))
        mime_data.setText(str(from_row))
        drag.setMimeData(mime_data)

        # 制作半透明拖拽跟随图标
        pixmap = self._drag_start_item.data(Qt.UserRole + 1)
        if isinstance(pixmap, QPixmap) and not pixmap.isNull():
            drag_pixmap = pixmap.scaled(100, 140, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        else:
            drag_pixmap = self._drag_start_item.icon().pixmap(100, 140)

        drag.setPixmap(drag_pixmap)
        drag.setHotSpot(QPoint(drag_pixmap.width() // 2, drag_pixmap.height() // 2))

        try:
            drag.exec(Qt.MoveAction)
        finally:
            self._is_dragging = False
            self._drag_start_item = None
            self._drop_target_row = -1
            self._stop_auto_scroll()
            self.viewport().update()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """
        拖拽进入事件校验，仅响应带有有效页码信息的移动拖拽。

        @param event 拖拽进入事件
        """
        if event.mimeData().hasFormat(self.MIME_PAGE) or event.mimeData().text().isdigit():
            self._is_dragging = True
            event.acceptProposedAction()
        else:
            event.ignore()

    def _resolve_drop_target(self, pos: QPoint) -> Tuple[int, bool]:
        """
        精确计算拖拽位置对应的目标项索引以及前后插入方位。
        在多列与单列模式下均可精准识别末尾空白、行末空列与视口底部，确保可平滑插入到列表最底部。

        @param pos 视口坐标系下的鼠标位置
        @return 包含 (目标行索引, 是否插入在之后) 的元组
        """
        if self.count() == 0:
            return 0, False

        vbar = self.verticalScrollBar()
        is_at_bottom = (vbar is None or not vbar.isVisible() or vbar.value() >= vbar.maximum() - 25)

        last_item = self.item(self.count() - 1)
        last_rect = self.visualItemRect(last_item) if last_item else QRect()

        # 1. 优先检测是否处于列表底部空白区域或最后一排未填满的空列（直接定位为插入到列表最底部）
        if last_rect.isValid():
            # 鼠标在最后一项下方，或者鼠标在最后一项所在行但位于最后一项右侧空白处
            if pos.y() >= last_rect.bottom() or (pos.y() >= last_rect.top() and pos.x() >= last_rect.right()):
                return self.count() - 1, True
            # 当滚动条已触底且鼠标位置在最后一项的中心高度以下
            if is_at_bottom and pos.y() >= last_rect.center().y():
                return self.count() - 1, True

        # 2. 精确命中项（先通过 itemAt，若无再通过 indexAt 兜底）
        target_item = self.itemAt(pos)
        if target_item is None:
            idx = self.indexAt(pos)
            if idx.isValid():
                target_item = self.item(idx.row())

        if target_item is not None:
            row = self.row(target_item)
            rect = self.visualItemRect(target_item)
            if self._current_columns > 1:
                insert_after = (pos.x() >= rect.center().x())
            else:
                insert_after = (pos.y() >= rect.center().y())
            return row, insert_after

        # 3. 顶部空白检测
        first_item = self.item(0)
        first_rect = self.visualItemRect(first_item) if first_item else QRect()
        if first_rect.isValid() and pos.y() <= first_rect.top():
            return 0, False

        # 4. 未直接命中项时（网格空隙），寻找几何距离最近的可见项
        best_row = 0
        min_dist = float("inf")
        insert_after = False

        for i in range(self.count()):
            item = self.item(i)
            if item is None:
                continue
            rect = self.visualItemRect(item)
            if not rect.isValid():
                continue
            dist = (rect.center() - pos).manhattanLength()
            if dist < min_dist:
                min_dist = dist
                best_row = i
                if self._current_columns > 1:
                    insert_after = (pos.x() > rect.center().x())
                else:
                    insert_after = (pos.y() > rect.center().y())

        if best_row == self.count() - 1 and (insert_after or is_at_bottom):
            return self.count() - 1, True

        return best_row, insert_after

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        """
        拖拽移动过程实时高亮悬停目标项、绘制多列指示标记，并检测视口边缘触发平滑自动滚动。

        @param event 拖拽移动事件
        """
        if not (event.mimeData().hasFormat(self.MIME_PAGE) or event.mimeData().text().isdigit()):
            event.ignore()
            return

        self._is_dragging = True
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        self._last_drag_pos = pos

        # 精确解析目标项与前后方位（支持多列底部空白与行末空列识别）
        target_row, insert_after = self._resolve_drop_target(pos)
        self._drop_target_row = target_row
        self._drop_position_before = (not insert_after)

        # 视口边缘感应区自动滚动逻辑（多列与单列下均可顺畅向下滚动直至最底端）
        vp_h = self.viewport().height()
        margin = max(10, min(self.AUTO_SCROLL_MARGIN, vp_h // 3))

        if pos.y() < margin:
            depth = max(0, margin - pos.y())
            ratio = min(1.0, depth / float(margin))
            self._auto_scroll_speed = -int(6 + ratio * 32)
            if not self._auto_scroll_timer.isActive():
                self._auto_scroll_timer.start()
        elif pos.y() > (vp_h - margin):
            depth = max(0, pos.y() - (vp_h - margin))
            ratio = min(1.0, depth / float(margin))
            self._auto_scroll_speed = int(6 + ratio * 32)
            if not self._auto_scroll_timer.isActive():
                self._auto_scroll_timer.start()
        else:
            self._stop_auto_scroll()

        self.viewport().update()
        event.acceptProposedAction()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        """
        拖拽离开事件处理，停止自动滚动并清除高亮标记。

        @param event 拖拽离开事件
        """
        self._stop_auto_scroll()
        self._drop_target_row = -1
        self.viewport().update()
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        """
        处理释放拖拽事件，精确计算目标行索引并发射 page_moved 信号，确保可平滑插入到列表最底部。

        @param event 拖拽释放事件
        """
        self._stop_auto_scroll()
        self._is_dragging = False
        self._drop_target_row = -1

        has_page_mime = event.mimeData().hasFormat(self.MIME_PAGE) or event.mimeData().text().isdigit()
        if not has_page_mime:
            event.ignore()
            return

        if event.mimeData().hasFormat(self.MIME_PAGE):
            from_row = int(bytes(event.mimeData().data(self.MIME_PAGE)).decode("utf-8"))
        else:
            from_row = int(event.mimeData().text())

        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        target_row, insert_after = self._resolve_drop_target(pos)

        # 依据标准列表重排公式精准映射插入目标索引：
        # 1. 插在 target_row 之后：若 from_row < target_row 则为 target_row；若 from_row > target_row 则为 target_row + 1
        # 2. 插在 target_row 之前：若 from_row < target_row 则为 target_row - 1；若 from_row > target_row 则为 target_row
        if insert_after:
            to_row = target_row if from_row < target_row else target_row + 1
        else:
            to_row = target_row - 1 if from_row < target_row else target_row

        to_row = max(0, min(to_row, self.count() - 1))
        event.accept()
        self.viewport().update()

        if from_row != to_row:
            self.page_moved.emit(from_row, to_row)

    def _on_auto_scroll_timer(self) -> None:
        """
        自动滚动定时器回调，执行视口平滑位移并实时更新当前拖拽悬停项与指示线。
        即便触底亦保持目标更新，支持多列下稳定悬停与释放。
        """
        vbar = self.verticalScrollBar()
        if vbar is None:
            self._stop_auto_scroll()
            return

        old_val = vbar.value()
        new_val = max(vbar.minimum(), min(vbar.maximum(), old_val + self._auto_scroll_speed))
        if new_val != old_val:
            vbar.setValue(new_val)

        # 基于最后一次记录的光标位置解析目标项，避免调用 setCurrentItem 触发干扰性强制滚屏
        target_row, insert_after = self._resolve_drop_target(self._last_drag_pos)
        self._drop_target_row = target_row
        self._drop_position_before = (not insert_after)

        self.viewport().update()

    def _stop_auto_scroll(self) -> None:
        """
        停止视口平滑自动滚动定时器并重置滚动速度。
        """
        if self._auto_scroll_timer.isActive():
            self._auto_scroll_timer.stop()
        self._auto_scroll_speed = 0


class ThumbnailPanel(QWidget):
    """
    左侧缩略图导航与页面编排面板。
    提供页面缩略图自适应合适宽度展示、默认单列/拉宽智能多列分列显示、拖拽多页边缘平滑自动滚动重排与右键管理。
    """

    page_selected = Signal(int)
    page_order_changed = Signal(int, int)
    page_rotated = Signal(int, int)
    page_deleted = Signal(int)
    page_inserted = Signal(int)
    page_extracted = Signal(int)
    split_requested = Signal(int)
    reorder_requested = Signal(int)

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
        记录真实物理纵横比与高清晰度位图，并触发自适应分列排版（默认单列）。

        @param pdf_doc 当前活动的 PDF 文档实体
        """
        self.list_widget.clear()
        if not pdf_doc.is_open:
            return

        total_pages = pdf_doc.page_count
        aspect_ratios = []
        for i in range(total_pages):
            page_size = pdf_doc.get_page_size(i)
            if page_size is not None and page_size[0] > 0:
                aspect = float(page_size[1]) / float(page_size[0])
            else:
                aspect = 1.414
            aspect_ratios.append(aspect)

        if aspect_ratios:
            self.list_widget._base_aspect_ratio = aspect_ratios[0]

        for i in range(total_pages):
            aspect_ratio = aspect_ratios[i]
            qimage = pdf_doc.render_page_pixmap(i, dpi=120)
            if qimage is not None:
                pixmap = QPixmap.fromImage(qimage)
                scaled_pixmap = pixmap.scaled(
                    130, max(20, int(130 * aspect_ratio)),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                item = QListWidgetItem(QIcon(scaled_pixmap), f"第 {i + 1} 页")
                item.setTextAlignment(Qt.AlignHCenter | Qt.AlignBottom)
                item.setData(Qt.UserRole, i)
                item.setData(Qt.UserRole + 1, pixmap)
                item.setData(Qt.UserRole + 2, aspect_ratio)
                self.list_widget.addItem(item)

        # 触发响应式分列排版（默认宽度下保持为 1 列表显示）
        self.list_widget.update_grid_layout()

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
        设置当前高亮选中的页面项，并平滑滚动使其在视口可见。

        @param page_index 页面索引（从 0 开始）
        """
        if 0 <= page_index < self.list_widget.count():
            self.list_widget.blockSignals(True)
            self.list_widget.setCurrentRow(page_index)
            item = self.list_widget.item(page_index)
            if item is not None:
                self.list_widget.scrollToItem(item, QAbstractItemView.EnsureVisible)
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

    def _show_context_menu(self, pos: QPoint) -> None:
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
