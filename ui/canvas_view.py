"""
PDF 主画板与交互式编辑视口模块。
基于 QGraphicsView 与 QGraphicsScene 实现动态高保真矢量自适应重采样渲染，
确保在任意缩放倍率（包括适宽、适页、25%~500% 任意放大缩小）与高分屏环境下，文字与图元始终极致清晰锐利。
"""

from typing import Optional, Tuple, Dict
import os
import time
from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsItem,
    QGraphicsPixmapItem, QGraphicsRectItem, QWidget, QApplication,
    QMenu
)
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QPixmap, QWheelEvent,
    QMouseEvent, QCursor, QTransform, QKeyEvent, QContextMenuEvent
)
from PySide6.QtCore import Qt, Signal, QRectF, QPointF, QTimer
from core.pdf_document import PdfDocument
from core.image_layer import ImageLayer


class ResizableImageItem(QGraphicsRectItem):
    """
    可自由拖拽移动与八向拉伸放缩的图片图层项。
    在用户向 PDF 插入图片时浮现在当前页上，支持直观的鼠标交互定位与尺寸修改。
    提供超大命中热区（Hit Area）、四角等比例拉伸与全区域脏矩形消除，彻底杜绝拖动轨迹残影。
    """

    HANDLE_SIZE = 10.0          # 边部视觉把手边长
    CORNER_HANDLE_SIZE = 12.0   # 四角视觉把手边长（更醒目）
    HIT_AREA_SIZE = 26.0        # 交互触发判定热区（超大容错区域，极大提升四角抓取灵敏度）

    def __init__(
        self,
        pixmap: QPixmap,
        image_path: str,
        initial_rect: Optional[QRectF] = None,
        layer_id: str = "",
        parent: Optional[QGraphicsItem] = None
    ) -> None:
        """
        初始化可拉伸图片图层项。

        @param pixmap 待插入图片的 QPixmap 图像
        @param image_path 本地图片的原始绝对路径
        @param initial_rect 初始矩形范围，若为 None 则使用 pixmap 原始像素尺寸
        @param layer_id 图层唯一标识符
        @param parent 父图元项
        """
        super().__init__(parent)
        self.layer_id = layer_id
        self._pixmap = pixmap
        self._image_path = image_path
        if initial_rect is not None:
            self.setRect(initial_rect)
        else:
            self.setRect(0, 0, pixmap.width(), pixmap.height())

        self.setFlags(
            QGraphicsItem.ItemIsMovable |
            QGraphicsItem.ItemIsSelectable |
            QGraphicsItem.ItemSendsGeometryChanges |
            QGraphicsItem.ItemIsFocusable
        )
        self.setAcceptHoverEvents(True)
        self._active_handle: Optional[str] = None
        self._drag_start_pos: QPointF = QPointF()
        self._orig_rect: QRectF = QRectF()
        self._scene_rect_before_drag: Optional[Tuple[float, float, float, float]] = None

    @property
    def image_path(self) -> str:
        """
        获取当前图片对应的本地绝对路径。

        @return 本地图片路径
        """
        return self._image_path

    def get_scene_rect(self) -> Tuple[float, float, float, float]:
        """
        获取图元在场景绝对物理点数坐标系下的矩形 (x0, y0, x1, y1)。

        @return 物理点数坐标元组
        """
        pos = self.pos()
        r = self.rect()
        return (pos.x() + r.left(), pos.y() + r.top(), pos.x() + r.right(), pos.y() + r.bottom())

    def boundingRect(self) -> QRectF:
        """
        获取该图元的物理外接矩形边界（包含放缩把手与描边外扩区域）。
        确保在图元移动、放缩时脏矩形区域能被 100% 完整擦除，彻底杜绝拖拽残影与轨迹。

        @return 包含把手外扩的绝对外接边界 QRectF
        """
        r = self.rect()
        margin = self.HIT_AREA_SIZE / 2.0 + 4.0
        return r.adjusted(-margin, -margin, margin, margin)

    def _get_handle_visual_rects(self) -> dict[str, QRectF]:
        """
        计算 8 个放缩锚点的视觉绘制矩形坐标。

        @return 键为方位名、值为绘制矩形 QRectF 的字典
        """
        r = self.rect()
        s_edge = self.HANDLE_SIZE
        s_corner = self.CORNER_HANDLE_SIZE
        h_edge = s_edge / 2.0
        h_corner = s_corner / 2.0

        return {
            "top_left": QRectF(r.left() - h_corner, r.top() - h_corner, s_corner, s_corner),
            "top": QRectF(r.center().x() - h_edge, r.top() - h_edge, s_edge, s_edge),
            "top_right": QRectF(r.right() - h_corner, r.top() - h_corner, s_corner, s_corner),
            "right": QRectF(r.right() - h_edge, r.center().y() - h_edge, s_edge, s_edge),
            "bottom_right": QRectF(r.right() - h_corner, r.bottom() - h_corner, s_corner, s_corner),
            "bottom": QRectF(r.center().x() - h_edge, r.bottom() - h_edge, s_edge, s_edge),
            "bottom_left": QRectF(r.left() - h_corner, r.bottom() - h_corner, s_corner, s_corner),
            "left": QRectF(r.left() - h_edge, r.center().y() - h_edge, s_edge, s_edge),
        }

    def _get_handle_hit_rects(self) -> dict[str, QRectF]:
        """
        计算 8 个放缩锚点的交互触发判定热区（扩大容错范围）。

        @return 键为方位名、值为触发判定矩形 QRectF 的字典
        """
        r = self.rect()
        s = self.HIT_AREA_SIZE
        half = s / 2.0

        return {
            "top_left": QRectF(r.left() - half, r.top() - half, s, s),
            "top": QRectF(r.center().x() - half, r.top() - half, s, s),
            "top_right": QRectF(r.right() - half, r.top() - half, s, s),
            "right": QRectF(r.right() - half, r.center().y() - half, s, s),
            "bottom_right": QRectF(r.right() - half, r.bottom() - half, s, s),
            "bottom": QRectF(r.center().x() - half, r.bottom() - half, s, s),
            "bottom_left": QRectF(r.left() - half, r.bottom() - half, s, s),
            "left": QRectF(r.left() - half, r.center().y() - half, s, s),
        }

    def _detect_handle_at(self, pos: QPointF) -> Optional[str]:
        """
        根据当前鼠标坐标精准检测是否命中放缩把手，优先判定四角热区。

        @param pos 图元本地坐标系下的鼠标点
        @return 命中的把手名称（如 'top_left'、'bottom_right' 等）；若未命中返回 None
        """
        hit_rects = self._get_handle_hit_rects()
        # 1. 优先检测四角关键锚点，给予最大触发容错
        corners = ("top_left", "bottom_right", "top_right", "bottom_left")
        for corner in corners:
            if hit_rects[corner].contains(pos):
                return corner

        # 2. 其次检测四边缘中心点
        edges = ("top", "bottom", "left", "right")
        for edge in edges:
            if hit_rects[edge].contains(pos):
                return edge

        return None

    def hoverMoveEvent(self, event) -> None:
        """
        响应鼠标悬浮事件，根据悬停的放缩锚点切换对应的鼠标指针图标。

        @param event 悬停移动事件
        """
        pos = event.pos()
        handle = self._detect_handle_at(pos)

        if handle in ("top_left", "bottom_right"):
            self.setCursor(QCursor(Qt.SizeFDiagCursor))
        elif handle in ("top_right", "bottom_left"):
            self.setCursor(QCursor(Qt.SizeBDiagCursor))
        elif handle in ("top", "bottom"):
            self.setCursor(QCursor(Qt.SizeVerCursor))
        elif handle in ("left", "right"):
            self.setCursor(QCursor(Qt.SizeHorCursor))
        else:
            self.setCursor(QCursor(Qt.SizeAllCursor))
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """
        响应鼠标按下事件，判断是选中了放缩把手还是准备拖拽移动，并记录初始位置矩形。

        @param event 鼠标按下事件
        """
        self._scene_rect_before_drag = self.get_scene_rect()
        pos = event.pos()
        handle = self._detect_handle_at(pos)

        if handle is not None:
            self._active_handle = handle
            self._drag_start_pos = event.scenePos()
            self._orig_rect = self.rect()
            event.accept()
        else:
            self._active_handle = None
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """
        响应鼠标拖曳事件，执行实时尺寸拉伸或移动。
        拉动四角时自动保持等比例缩放（按住 Ctrl 可自由拉伸），边缘支持单向尺寸调节。

        @param event 鼠标移动事件
        """
        if self._active_handle is not None:
            delta = event.scenePos() - self._drag_start_pos
            orig = self._orig_rect
            r = QRectF(orig)

            # 是否允许自由非等比例拉伸（按住 Ctrl 键时）
            free_ratio = bool(event.modifiers() & Qt.ControlModifier)

            # 四角拉伸（默认等比例自适应缩放）
            if self._active_handle == "bottom_right":
                new_w = max(24.0, orig.width() + delta.x())
                new_h = max(24.0, orig.height() + delta.y())
                if not free_ratio and orig.width() > 0 and orig.height() > 0:
                    scale = max(new_w / orig.width(), new_h / orig.height())
                    new_w = orig.width() * scale
                    new_h = orig.height() * scale
                r.setWidth(new_w)
                r.setHeight(new_h)

            elif self._active_handle == "bottom_left":
                new_w = max(24.0, orig.width() - delta.x())
                new_h = max(24.0, orig.height() + delta.y())
                if not free_ratio and orig.width() > 0 and orig.height() > 0:
                    scale = max(new_w / orig.width(), new_h / orig.height())
                    new_w = orig.width() * scale
                    new_h = orig.height() * scale
                r.setLeft(orig.right() - new_w)
                r.setHeight(new_h)

            elif self._active_handle == "top_right":
                new_w = max(24.0, orig.width() + delta.x())
                new_h = max(24.0, orig.height() - delta.y())
                if not free_ratio and orig.width() > 0 and orig.height() > 0:
                    scale = max(new_w / orig.width(), new_h / orig.height())
                    new_w = orig.width() * scale
                    new_h = orig.height() * scale
                r.setWidth(new_w)
                r.setTop(orig.bottom() - new_h)

            elif self._active_handle == "top_left":
                new_w = max(24.0, orig.width() - delta.x())
                new_h = max(24.0, orig.height() - delta.y())
                if not free_ratio and orig.width() > 0 and orig.height() > 0:
                    scale = max(new_w / orig.width(), new_h / orig.height())
                    new_w = orig.width() * scale
                    new_h = orig.height() * scale
                r.setLeft(orig.right() - new_w)
                r.setTop(orig.bottom() - new_h)

            # 四边缘中心拉伸（自由单轴尺寸调节）
            elif self._active_handle == "right":
                r.setWidth(max(24.0, orig.width() + delta.x()))
            elif self._active_handle == "left":
                new_w = max(24.0, orig.width() - delta.x())
                r.setLeft(orig.right() - new_w)
            elif self._active_handle == "bottom":
                r.setHeight(max(24.0, orig.height() + delta.y()))
            elif self._active_handle == "top":
                new_h = max(24.0, orig.height() - delta.y())
                r.setTop(orig.bottom() - new_h)

            self.prepareGeometryChange()
            self.setRect(r)
            self.update()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """
        响应鼠标释放事件，结束拉伸或移动操作，若产生位移变化则触发画板历史记录。

        @param event 鼠标释放事件
        """
        self._active_handle = None
        super().mouseReleaseEvent(event)

        current_scene_rect = self.get_scene_rect()
        if self._scene_rect_before_drag is not None and self.scene() is not None:
            old_r = self._scene_rect_before_drag
            new_r = current_scene_rect
            dx = abs(new_r[0] - old_r[0]) + abs(new_r[1] - old_r[1])
            dw = abs((new_r[2] - new_r[0]) - (old_r[2] - old_r[0]))
            dh = abs((new_r[3] - new_r[1]) - (old_r[3] - old_r[1]))
            if (dx > 1.0 or dw > 1.0 or dh > 1.0) and self.layer_id:
                views = self.scene().views()
                if views and hasattr(views[0], "notify_image_transformed"):
                    views[0].notify_image_transformed(self.layer_id, old_r, new_r)

        self._scene_rect_before_drag = None

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """
        键盘按键事件：选中图片后按 Delete 或 Backspace 键请求删除此图片。

        @param event 键盘按键事件
        """
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            if self.layer_id and self.scene() is not None:
                views = self.scene().views()
                if views and hasattr(views[0], "notify_image_delete_requested"):
                    views[0].notify_image_delete_requested(self.layer_id)
                    event.accept()
                    return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """
        右键上下文菜单：提供删除当前选中的图片操作。

        @param event 右键上下文菜单事件
        """
        menu = QMenu()
        act_delete = menu.addAction("删除此图片 (Delete)")
        chosen = menu.exec(event.screenPos())
        if chosen == act_delete and self.layer_id and self.scene() is not None:
            views = self.scene().views()
            if views and hasattr(views[0], "notify_image_delete_requested"):
                views[0].notify_image_delete_requested(self.layer_id)
        event.accept()

    def paint(self, painter: QPainter, option, widget=None) -> None:
        """
        绘制图片图层及其选中高亮边框和 8 个控制把手。
        开启高质量平滑插值绘制，确保图片拉大缩小时无失真。

        @param painter 绘图工具对象
        @param option 绘图选项参数
        @param widget 目标组件
        """
        r = self.rect()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        # 绘制原始图片
        painter.drawPixmap(r.toRect(), self._pixmap)

        # 选中状态下绘制蓝色控制外框与锚点
        if self.isSelected():
            pen = QPen(QColor(37, 99, 235), 1.5, Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(r)

            # 绘制 8 个把手（白底、深蓝描边、微圆角）
            handle_pen = QPen(QColor(37, 99, 235), 1.5)
            handle_brush = QBrush(QColor(255, 255, 255))
            dot_brush = QBrush(QColor(37, 99, 235))

            painter.setPen(handle_pen)
            painter.setBrush(handle_brush)
            visual_handles = self._get_handle_visual_rects()

            for name, handle_rect in visual_handles.items():
                painter.setPen(handle_pen)
                painter.setBrush(handle_brush)
                painter.drawRoundedRect(handle_rect, 2.0, 2.0)

                # 四角关键把手在中心额外绘制一个小蓝色实心原点，增强视觉聚焦与交互提示
                if "top" in name and ("left" in name or "right" in name) or "bottom" in name and ("left" in name or "right" in name):
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(dot_brush)
                    center = handle_rect.center()
                    painter.drawEllipse(center, 1.5, 1.5)


class PdfCanvasView(QGraphicsView):
    """
    PDF 动态超清自适应画板视口。
    基于 QGraphicsView 与 QGraphicsScene 实现动态高保真矢量重采样渲染，
    无论放大到几倍或缩小，均自动以 1:1 像素密度实时重新光栅化，杜绝拉伸发糊与走样。
    """

    zoom_changed = Signal(int)
    image_burned = Signal(int, str, tuple)  # 信号：(page_index, image_path, (x0, y0, x1, y1))
    image_dropped_from_external = Signal(str)  # 信号：外部拖入图片文件路径
    image_transformed = Signal(str, tuple, tuple)  # 信号：图片移动/缩放 (layer_id, old_rect, new_rect)
    image_delete_requested = Signal(str)  # 信号：请求删除图片 (layer_id)
    image_selection_changed = Signal(bool)  # 信号：是否有选中图片
    page_turn_requested = Signal(int, bool)  # 信号：画板上下滑动翻页请求 (目标页索引, 是否滚动到目标页底部)

    IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif", ".tif", ".tiff")

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        初始化 PDF 画板视口与高保真动态渲染引擎。

        @param parent 包含该视口的父组件
        """
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.scene.selectionChanged.connect(self._on_scene_selection_changed)

        # 开启全局抗锯齿与像素平滑渲染提示
        self.setRenderHints(
            QPainter.Antialiasing |
            QPainter.SmoothPixmapTransform |
            QPainter.TextAntialiasing
        )
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setBackgroundBrush(QBrush(QColor(241, 245, 249)))
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setAcceptDrops(True)

        self._current_page_item: Optional[QGraphicsPixmapItem] = None
        self._image_items: Dict[str, ResizableImageItem] = {}
        self._active_image_item: Optional[ResizableImageItem] = None
        self._current_page_index: int = 0
        self._current_pdf_doc: Optional[PdfDocument] = None
        self._page_size_pt: Tuple[float, float] = (595.0, 842.0)
        self._rendered_dpi: int = 150
        self._zoom_factor: float = 1.0
        self._fit_mode: str = "page"  # "page" (整页自适应), "width" (宽适自适应), "manual" (用户手动缩放)
        self._last_wheel_page_turn_time: float = 0.0

        # 防抖动态高清重采样定时器 (100毫秒)，确保平滑缩放与高清锐化兼得
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self._update_high_res_render)

    def _on_scene_selection_changed(self) -> None:
        """
        响应场景中图元选中变化，更新选中状态并分发信号。
        """
        selected_items = self.scene.selectedItems()
        has_image_selected = any(isinstance(item, ResizableImageItem) for item in selected_items)
        self.image_selection_changed.emit(has_image_selected)

    def notify_image_transformed(self, layer_id: str, old_rect: tuple, new_rect: tuple) -> None:
        """
        图元移动或缩放完成通知。

        @param layer_id 图层唯一标识符
        @param old_rect 原始坐标 (x0, y0, x1, y1)
        @param new_rect 变更后坐标 (x0, y0, x1, y1)
        """
        self.image_transformed.emit(layer_id, old_rect, new_rect)

    def notify_image_delete_requested(self, layer_id: str) -> None:
        """
        图元请求删除通知。

        @param layer_id 待删除的图层唯一标识符
        """
        self.image_delete_requested.emit(layer_id)

    def get_selected_image_item(self) -> Optional[ResizableImageItem]:
        """
        获取当前画板中被用户选中的图片图元。

        @return 若存在选中的 ResizableImageItem 则返回该图元；否则返回 None
        """
        for item in self.scene.selectedItems():
            if isinstance(item, ResizableImageItem):
                return item
        return None

    @property
    def current_page_index(self) -> int:
        """
        获取当前显示的页面索引。

        @return 页面索引（从 0 开始）
        """
        return self._current_page_index

    @property
    def active_image_item(self) -> Optional[ResizableImageItem]:
        """
        获取当前处于待烧录状态的悬浮图片图元对象。

        @return 若存在待固化图片则返回该对象，否则返回 None
        """
        return self._active_image_item

    def _calculate_optimal_dpi(self) -> int:
        """
        根据当前视口绝对缩放矩阵与屏幕物理像素比 (DPR)，动态换算呈现 1:1 像素清晰所需的最佳 DPI。

        @return 最优渲染 DPI 整数，范围限制在 72 至 600 之间
        """
        # 获取当前 View 的绝对水平变换放大率
        view_scale = self.transform().m11()
        if view_scale <= 0.001:
            view_scale = 1.0

        # 获取屏幕物理像素比（针对 125%、150%、200% 等高分屏自适应）
        dpr = 1.0
        screen = self.screen() or QApplication.primaryScreen()
        if screen:
            dpr = screen.devicePixelRatio()

        # 1 pt = 1/72 inch，因此最佳 DPI = 72 * view_scale * dpr
        target_dpi = int(72.0 * view_scale * dpr)
        # 下限 72 DPI，上限 250 DPI，足以满足视网膜清晰锐度并防止低配机器极端大图占用过多内存
        return max(72, min(target_dpi, 250))

    def _schedule_high_res_render(self) -> None:
        """
        触发防抖高清重采样定时器，在用户缩放或调整尺寸停顿 100ms 后执行清晰光栅化。
        """
        self._render_timer.start(100)

    def _update_high_res_render(self) -> None:
        """
        防抖定时器触发槽函数：在用户缩放停止后，以当前最佳 DPI 重新渲染矢量页面并无缝贴合。
        """
        if self._current_pdf_doc is None or not self._current_pdf_doc.is_open:
            return
        if self._current_page_item is None:
            return

        target_dpi = self._calculate_optimal_dpi()
        # 若与当前已渲染 DPI 差异不大（小于 12 DPI），无需重复计算
        if abs(target_dpi - self._rendered_dpi) < 12:
            return

        qimage = self._current_pdf_doc.render_page_pixmap(self._current_page_index, dpi=target_dpi)
        if qimage is None:
            return

        pixmap = QPixmap.fromImage(qimage)
        w_pt, h_pt = self._page_size_pt

        # 无缝更新 Pixmap 与局部变换矩阵，严格保持场景几何大小恒定不变
        self._current_page_item.setPixmap(pixmap)
        sx = w_pt / float(pixmap.width())
        sy = h_pt / float(pixmap.height())
        self._current_page_item.setTransform(QTransform().scale(sx, sy))
        self._rendered_dpi = target_dpi

    def display_page(self, pdf_doc: PdfDocument, page_index: int) -> None:
        """
        渲染并呈现指定页面的高清视图。
        以 PDF 物理点数建立场景坐标，并以最佳 DPI 光栅化生成高清图元。

        @param pdf_doc 当前活动的 PDF 文档实体
        @param page_index 页面索引（从 0 开始）
        """
        if not pdf_doc.is_open or not (0 <= page_index < pdf_doc.page_count):
            self.scene.clear()
            self._current_page_item = None
            self._active_image_item = None
            self._current_pdf_doc = None
            return

        self._current_pdf_doc = pdf_doc
        self._current_page_index = page_index

        page_size = pdf_doc.get_page_size(page_index)
        if page_size is not None and page_size[0] > 0 and page_size[1] > 0:
            self._page_size_pt = page_size
        else:
            self._page_size_pt = (595.0, 842.0)

        w_pt, h_pt = self._page_size_pt

        self.scene.clear()
        self._image_items.clear()
        self._active_image_item = None

        best_dpi = self._calculate_optimal_dpi()
        qimage = pdf_doc.render_page_pixmap(page_index, dpi=best_dpi)
        if qimage is None:
            return

        pixmap = QPixmap.fromImage(qimage)
        self._current_page_item = self.scene.addPixmap(pixmap)
        self._current_page_item.setTransformationMode(Qt.SmoothTransformation)

        # 映射图元为 PDF 物理点数 (w_pt, h_pt)
        sx = w_pt / float(pixmap.width())
        sy = h_pt / float(pixmap.height())
        self._current_page_item.setTransform(QTransform().scale(sx, sy))

        self.scene.setSceneRect(0, 0, w_pt, h_pt)
        self._rendered_dpi = best_dpi

        # 还原呈现当前页登记的所有可编辑图片图层
        if pdf_doc is not None and hasattr(pdf_doc, "image_layers"):
            for layer in pdf_doc.image_layers.get_layers_for_page(page_index):
                self.load_image_item_for_layer(layer)

    def load_image_item_for_layer(self, layer: ImageLayer) -> Optional[ResizableImageItem]:
        """
        根据图片图层数据对象在场景中创建并挂载可交互图片图元。

        @param layer 目标图片图层实体对象
        @return 生成的 ResizableImageItem 对象；若加载失败返回 None
        """
        if not os.path.isfile(layer.image_path):
            return None

        pixmap = QPixmap(layer.image_path)
        if pixmap.isNull():
            return None

        x0, y0, x1, y1 = layer.rect
        w = max(24.0, x1 - x0)
        h = max(24.0, y1 - y0)

        item = ResizableImageItem(
            pixmap=pixmap,
            image_path=layer.image_path,
            initial_rect=QRectF(0, 0, w, h),
            layer_id=layer.id
        )
        item.setPos(x0, y0)
        self.scene.addItem(item)
        self._image_items[layer.id] = item
        return item

    def remove_image_item(self, layer_id: str) -> bool:
        """
        从当前画板场景中移除指定 ID 的图片图元。

        @param layer_id 目标图层 ID
        @return 移除是否成功
        """
        item = self._image_items.pop(layer_id, None)
        if item is not None:
            self.scene.removeItem(item)
            if self._active_image_item == item:
                self._active_image_item = None
            return True
        return False

    def update_image_item_geometry(self, layer_id: str, rect: tuple) -> bool:
        """
        通过图层 ID 直接更新画布上图片图元的位置与几何尺寸。

        @param layer_id 目标图层 ID
        @param rect 目标物理矩形坐标 (x0, y0, x1, y1)
        @return 是否成功更新
        """
        item = self._image_items.get(layer_id)
        if item is not None:
            x0, y0, x1, y1 = rect
            w = max(24.0, x1 - x0)
            h = max(24.0, y1 - y0)
            item.prepareGeometryChange()
            item.setPos(x0, y0)
            item.setRect(QRectF(0, 0, w, h))
            item.update()
            return True
        return False

    def add_floating_image(self, image_path: str, pos: Optional[QPointF] = None) -> Optional[ImageLayer]:
        """
        在当前显示的页面添加一个待调整与固化的悬浮图片图层。

        @param image_path 本地图片文件绝对路径
        @param pos 放置的目标场景坐标；若为 None 则居中放置在页面中央
        @return 成功添加的图片图层对象，失败则返回 None
        """
        if self._current_page_item is None or self._current_pdf_doc is None:
            return None

        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            return None

        w_pt, h_pt = self._page_size_pt
        # 初始尺寸自适应页面点数的 35%
        init_w = w_pt * 0.35
        aspect = float(pixmap.height()) / float(pixmap.width()) if pixmap.width() > 0 else 1.0
        init_h = init_w * aspect

        if pos is not None:
            # 放置在指定鼠标场景坐标处（居中对其点）
            x = pos.x() - init_w / 2.0
            y = pos.y() - init_h / 2.0
            # 限制在页面物理点数范围内
            x = max(0.0, min(x, w_pt - init_w))
            y = max(0.0, min(y, h_pt - init_h))
        else:
            # 居中放置
            x = (w_pt - init_w) / 2.0
            y = (h_pt - init_h) / 2.0

        if hasattr(self._current_pdf_doc, "image_layers"):
            layer = self._current_pdf_doc.image_layers.add_layer(
                self._current_page_index,
                image_path,
                (x, y, x + init_w, y + init_h)
            )
            item = self.load_image_item_for_layer(layer)
            if item is not None:
                item.setSelected(True)
                self._active_image_item = item
                self._current_pdf_doc.set_modified(True)
                return layer
        return None

    def bake_active_image(self, pdf_doc: PdfDocument) -> bool:
        """
        将当前悬浮图片图层的真实坐标与尺寸固化写入 PDF 页面中。
        由于场景坐标与 PDF 物理点数严格等价，实现 1:1 零误差精准写入。

        @param pdf_doc 当前活动的 PDF 文档对象
        @return 固化是否成功完成
        """
        if self._active_image_item is None or not pdf_doc.is_open:
            return False

        item = self._active_image_item
        img_scene_pos = item.pos()
        img_rect = item.rect()

        # 计算在场景中的绝对范围（即精确 PDF 点数坐标）
        scene_x0 = img_scene_pos.x() + img_rect.left()
        scene_y0 = img_scene_pos.y() + img_rect.top()
        scene_x1 = img_scene_pos.x() + img_rect.right()
        scene_y1 = img_scene_pos.y() + img_rect.bottom()

        pdf_rect = (scene_x0, scene_y0, scene_x1, scene_y1)
        image_path = item.image_path
        page_idx = self._current_page_index

        # 执行固化写入
        success = pdf_doc.insert_image(page_idx, image_path, pdf_rect)
        if success:
            layer_id = getattr(item, "layer_id", "")
            if layer_id and hasattr(pdf_doc, "image_layers"):
                pdf_doc.image_layers.remove_layer(layer_id)
            self.scene.removeItem(item)
            self._image_items.pop(layer_id, None)
            self._active_image_item = None
            # 重新渲染该页呈现合并效果
            self.display_page(pdf_doc, page_idx)
            self.image_burned.emit(page_idx, image_path, pdf_rect)
            return True
        return False

    def cancel_active_image(self) -> None:
        """
        取消并放弃当前尚未固化的悬浮图片图层。
        """
        if self._active_image_item is not None:
            self.scene.removeItem(self._active_image_item)
            self._active_image_item = None

    def zoom_in(self) -> None:
        """
        放大画板视图，进入自定义缩放模式，并调度高清矢量重采样。
        """
        self._fit_mode = "manual"
        self.scale(1.2, 1.2)
        self._zoom_factor = self.transform().m11()
        self.zoom_changed.emit(int(self._zoom_factor * 100))
        self._schedule_high_res_render()

    def zoom_out(self) -> None:
        """
        缩小画板视图，进入自定义缩放模式，并调度高清重采样。
        """
        self._fit_mode = "manual"
        self.scale(1.0 / 1.2, 1.0 / 1.2)
        self._zoom_factor = self.transform().m11()
        self.zoom_changed.emit(int(self._zoom_factor * 100))
        self._schedule_high_res_render()

    def _apply_fit_page(self, schedule_render: bool = True) -> None:
        """
        执行画板适应整页的核心几何缩放与居中计算。

        @param schedule_render 是否在完成几何变换后调度高清矢量重采样
        """
        if self._current_page_item is None:
            return

        w_pt, h_pt = self._page_size_pt
        if w_pt <= 0 or h_pt <= 0:
            return

        available_w = max(100, self.viewport().width() - 32)
        available_h = max(100, self.viewport().height() - 32)
        scale_val = min(available_w / w_pt, available_h / h_pt)

        self.resetTransform()
        self.scale(scale_val, scale_val)
        self._zoom_factor = scale_val
        self.zoom_changed.emit(int(self._zoom_factor * 100))

        if self.horizontalScrollBar():
            hbar = self.horizontalScrollBar()
            hbar.setValue((hbar.maximum() + hbar.minimum()) // 2)
        if self.verticalScrollBar():
            vbar = self.verticalScrollBar()
            vbar.setValue((vbar.maximum() + vbar.minimum()) // 2)

        if schedule_render:
            self._schedule_high_res_render()

    def fit_page(self) -> None:
        """
        使画板完整适应当前整个页面，开启窗口自适应联动，并调度高清矢量重采样。
        """
        self._fit_mode = "page"
        self._apply_fit_page(schedule_render=True)

    def _apply_fit_width(self, schedule_render: bool = True) -> None:
        """
        执行画板适应宽度的核心几何缩放与居中计算。

        @param schedule_render 是否在完成几何变换后调度高清矢量重采样
        """
        if self._current_page_item is None:
            return

        w_pt, h_pt = self._page_size_pt
        if w_pt <= 0:
            return

        available_w = max(100, self.viewport().width() - 36)
        scale_val = available_w / w_pt

        self.resetTransform()
        self.scale(scale_val, scale_val)
        self._zoom_factor = scale_val
        self.zoom_changed.emit(int(self._zoom_factor * 100))

        if self.horizontalScrollBar():
            hbar = self.horizontalScrollBar()
            hbar.setValue((hbar.maximum() + hbar.minimum()) // 2)
        if self.verticalScrollBar():
            self.verticalScrollBar().setValue(0)

        if schedule_render:
            self._schedule_high_res_render()

    def fit_width(self) -> None:
        """
        使画板适应视口宽度，开启窗口宽度自适应联动，并调度高清重采样。
        """
        self._fit_mode = "width"
        self._apply_fit_width(schedule_render=True)

    def get_fit_mode(self) -> str:
        """
        获取当前画板的自适应缩放模式标识。

        @return 缩放模式标识（page、width 或 manual）
        """
        return self._fit_mode

    def resizeEvent(self, event) -> None:
        """
        响应视口尺寸改变事件，联动更新整页或宽适自适应缩放并触发高清重采样。

        @param event 尺寸改变事件
        """
        super().resizeEvent(event)
        if self._current_page_item is not None:
            if self._fit_mode == "page":
                self._apply_fit_page(schedule_render=False)
            elif self._fit_mode == "width":
                self._apply_fit_width(schedule_render=False)
            self._schedule_high_res_render()

    def dragEnterEvent(self, event) -> None:
        """
        处理拖拽进入画板事件，检测是否为图片文件。

        @param event 拖拽进入事件
        """
        if event.mimeData().hasUrls() and self._current_page_item is not None:
            for url in event.mimeData().urls():
                file_path = url.toLocalFile().lower()
                if any(file_path.endswith(ext) for ext in self.IMAGE_EXTENSIONS):
                    event.acceptProposedAction()
                    return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        """
        处理拖拽悬停移动事件。

        @param event 拖拽移动事件
        """
        if event.mimeData().hasUrls() and self._current_page_item is not None:
            for url in event.mimeData().urls():
                file_path = url.toLocalFile().lower()
                if any(file_path.endswith(ext) for ext in self.IMAGE_EXTENSIONS):
                    event.acceptProposedAction()
                    return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        """
        处理文件在画板释放事件，若是图片则在鼠标释放位置直接插入悬浮图片。

        @param event 拖拽释放事件
        """
        if event.mimeData().hasUrls() and self._current_page_item is not None:
            for url in event.mimeData().urls():
                local_path = os.path.normpath(url.toLocalFile())
                if any(local_path.lower().endswith(ext) for ext in self.IMAGE_EXTENSIONS):
                    pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
                    # 将鼠标视图坐标映射为画板场景坐标
                    scene_pos = self.mapToScene(pos)
                    added = self.add_floating_image(local_path, pos=scene_pos)
                    if added:
                        self.image_dropped_from_external.emit(local_path)
                        event.acceptProposedAction()
                        return
        super().dropEvent(event)

    def scroll_to_top(self) -> None:
        """
        将视口垂直滚动条直接滚动至顶部。
        """
        vbar = self.verticalScrollBar()
        if vbar is not None:
            vbar.setValue(vbar.minimum())

    def scroll_to_bottom(self) -> None:
        """
        将视口垂直滚动条直接滚动至底部。
        """
        vbar = self.verticalScrollBar()
        if vbar is not None:
            vbar.setValue(vbar.maximum())

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """
        处理画板视口键盘按键事件。
        支持 PageUp 向上滑动翻页，PageDown 向下滑动翻页；
        若有选中的图片，按 Delete / Backspace 键请求删除此图片。

        @param event 键盘按键事件对象
        """
        # 1. 选中图片按 Delete / Backspace 请求删除
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            item = self.get_selected_image_item()
            if item is not None and item.layer_id:
                self.image_delete_requested.emit(item.layer_id)
                event.accept()
                return

        # 2. 键盘上下滑动翻页支持
        if event.key() == Qt.Key_PageUp:
            if self._current_pdf_doc is not None and self._current_page_index > 0:
                self.page_turn_requested.emit(self._current_page_index - 1, True)
                event.accept()
                return
        elif event.key() == Qt.Key_PageDown:
            if self._current_pdf_doc is not None and self._current_page_index < self._current_pdf_doc.page_count - 1:
                self.page_turn_requested.emit(self._current_page_index + 1, False)
                event.accept()
                return

        super().keyPressEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        """
        处理滚轮事件：
        1. 按住 Ctrl 键时执行平滑自适应高保真矢量缩放；
        2. 未按 Ctrl 键时支持自然上下滑动翻页与内容滚动：
           - 当页面整页完整显示在视口内无多余滚动条时，向上滑动滚轮翻到上一页，向下滑动滚轮翻到下一页；
           - 当页面超出视口存在垂直滚动条时：
             - 若滚动条到达最顶部且用户继续向上滑动，顺畅翻到上一页并定位到上一页底部；
             - 若滚动条到达最底部且用户继续向下滑动，顺畅翻到下一页并定位到下一页顶部；
             - 处于页面中间时执行平滑垂直滚动。

        @param event 滚轮事件对象
        """
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            event.accept()
            return

        delta_y = event.angleDelta().y()
        if delta_y == 0:
            super().wheelEvent(event)
            return

        # 若未加载文档或只有 1 页，执行默认滚动
        if self._current_pdf_doc is None or not self._current_pdf_doc.is_open or self._current_pdf_doc.page_count <= 1:
            super().wheelEvent(event)
            return

        vbar = self.verticalScrollBar()
        vbar_val = vbar.value() if vbar is not None else 0
        vbar_min = vbar.minimum() if vbar is not None else 0
        vbar_max = vbar.maximum() if vbar is not None else 0

        # 计算当前页面在当前缩放比例下的实际视口像素高度
        _, h_pt = self._page_size_pt
        scale_y = abs(self.transform().m22())
        page_view_height = h_pt * scale_y
        viewport_height = self.viewport().height()

        # 判断整页是否已完整容纳于视口内（或页面超大处于局部放大状态）
        page_fits_in_view = (page_view_height <= viewport_height + 60)
        at_top = (vbar_val <= vbar_min + 5)
        at_bottom = (vbar_val >= vbar_max - 5)

        target_page: Optional[int] = None
        scroll_to_bottom = False

        if (page_fits_in_view or at_top) and delta_y > 0:
            # 向上滑动 -> 翻到上一页
            if self._current_page_index > 0:
                target_page = self._current_page_index - 1
                scroll_to_bottom = not page_fits_in_view

        elif (page_fits_in_view or at_bottom) and delta_y < 0:
            # 向下滑动 -> 翻到下一页
            if self._current_page_index < self._current_pdf_doc.page_count - 1:
                target_page = self._current_page_index + 1
                scroll_to_bottom = False

        if target_page is not None:
            # 引入 180ms 翻页冷却时间，防止机械滚轮或触控板误触发连跳多页
            now = time.monotonic()
            if now - self._last_wheel_page_turn_time >= 0.18:
                self._last_wheel_page_turn_time = now
                self.page_turn_requested.emit(target_page, scroll_to_bottom)
                event.accept()
                return
            else:
                # 处于冷却期内的多余微小惯性抖动直接消费
                event.accept()
                return

        super().wheelEvent(event)
