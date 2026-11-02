"""
PDF 打印调度与渲染服务模块。
负责物理打印机与虚拟打印机枚举、打印任务配置管理、带图层高精度页面光栅化渲染及 QPrinter 绘制作业调度。
"""

import os
from typing import Optional, List, Tuple, Callable
from dataclasses import dataclass, field
from PySide6.QtPrintSupport import QPrinter, QPrinterInfo
from PySide6.QtGui import QPainter, QImage, QPageLayout
from PySide6.QtCore import QRectF, Qt
from core.pdf_document import PdfDocument


@dataclass
class PrintConfiguration:
    """
    打印任务参数配置实体类。
    封装目标打印机名称、目标打印页码索引、打印份数、颜色模式、页面方向与缩放模式等关键参数。
    """
    printer_name: str
    page_indices: List[int] = field(default_factory=list)
    copies: int = 1
    collate: bool = True
    color_mode: str = "color"
    orientation: str = "auto"
    scale_mode: str = "fit"


class PdfPrinter:
    """
    PDF 文档打印服务类。
    提供系统可用打印机检测、打印页面高保真图层合成渲染与向系统打印队列发送光栅化打印作业的能力。
    """

    @staticmethod
    def get_available_printers() -> List[str]:
        """
        获取当前操作系统中安装并可用的所有真实物理打印机与虚拟打印机名称列表。

        @return 真实系统打印机名称字符串列表；若系统未安装任何打印机则返回空列表
        """
        printers = QPrinterInfo.availablePrinterNames()
        return list(printers)

    @staticmethod
    def get_default_printer() -> Optional[str]:
        """
        获取当前系统的默认打印机名称。

        @return 默认打印机名称字符串；若系统未设置默认打印机或无可用打印机则返回 None
        """
        default_name = QPrinterInfo.defaultPrinterName()
        if default_name:
            return default_name
        available = QPrinterInfo.availablePrinterNames()
        if available:
            return available[0]
        return None

    @staticmethod
    def render_printable_page(doc: PdfDocument, page_index: int, dpi: int = 300) -> Optional[QImage]:
        """
        将文档指定页面渲染为包含所有未保存/未烘焙图片图层的高保真位图，确保打印输出所见即所得。

        @param doc 目标核心 PDF 文档实例
        @param page_index 页面索引（从 0 开始）
        @param dpi 渲染物理分辨率（点/英寸），默认为 300 DPI
        @return 渲染合成后的高保真 QImage 对象；若页面索引越界或渲染失败返回 None
        """
        if not doc.is_open or not (0 <= page_index < doc.page_count):
            return None

        # 1. 渲染底层基础页面位图
        base_image = doc.render_page_pixmap(page_index, dpi=dpi)
        if base_image is None or base_image.isNull():
            return None

        # 2. 检查该页面是否存在未固化的上层活动图片图层（如印章、签名）
        layers = doc.image_layers.get_layers_for_page(page_index)
        if not layers:
            return base_image

        page_size = doc.get_page_size(page_index)
        if page_size is None or page_size[0] <= 0 or page_size[1] <= 0:
            return base_image

        # 3. 复制为独立格式以进行 QPainter 叠加绘制
        composite_image = base_image.copy()
        painter = QPainter(composite_image)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        scale_x = composite_image.width() / float(page_size[0])
        scale_y = composite_image.height() / float(page_size[1])

        for layer in layers:
            if not os.path.isfile(layer.image_path):
                continue
            layer_img = QImage(layer.image_path)
            if layer_img.isNull():
                continue

            x0, y0, x1, y1 = layer.rect
            target_rect = QRectF(
                x0 * scale_x,
                y0 * scale_y,
                (x1 - x0) * scale_x,
                (y1 - y0) * scale_y
            )
            painter.drawImage(target_rect, layer_img)

        painter.end()
        return composite_image

    @staticmethod
    def print_document(
        doc: PdfDocument,
        config: PrintConfiguration,
        progress_callback: Optional[Callable[[int, int], bool]] = None
    ) -> Tuple[bool, str]:
        """
        执行 PDF 文档打印作业调度，将指定页码范围渲染并逐页写入 QPrinter。

        @param doc 目标待打印的核心 PDF 文档对象
        @param config 打印参数配置实体
        @param progress_callback 进度更新与取消回调函数，接收 (当前已处理页序号, 总页数)，若返回 False 则表示用户请求取消打印
        @return 包含 (是否成功, 结果描述文本) 的元组
        """
        if not doc.is_open:
            return False, "当前未打开任何 PDF 文档，无法执行打印。"

        if not config.page_indices:
            return False, "待打印页码范围为空，未指定任何有效页面。"

        # 校验打印机有效性
        available_printers = QPrinterInfo.availablePrinterNames()
        if config.printer_name not in available_printers:
            return False, f"系统未找到指定的打印机：'{config.printer_name}'。"

        printer_info = QPrinterInfo.printerInfo(config.printer_name)
        if printer_info.isNull():
            return False, f"无法获取打印机 '{config.printer_name}' 的系统驱动信息。"

        printer = QPrinter(printer_info, QPrinter.HighResolution)
        if not printer.isValid():
            return False, f"打印机 '{config.printer_name}' 处于无效或不可用状态。"

        # 配置打印参数
        printer.setPrinterName(config.printer_name)
        printer.setCopyCount(max(1, config.copies))
        printer.setCollateCopies(config.collate)

        if config.color_mode.lower() == "grayscale":
            printer.setColorMode(QPrinter.GrayScale)
        else:
            printer.setColorMode(QPrinter.Color)

        # 启动 QPainter 打印作业
        painter = QPainter()
        if not painter.begin(printer):
            return False, f"无法启动打印机 '{config.printer_name}' 的绘制引擎，请检查打印机连接或驱动状态。"

        total_pages = len(config.page_indices)
        dpi = printer.resolution() if printer.resolution() > 0 else 300

        try:
            for idx, page_idx in enumerate(config.page_indices):
                # 检查外部取消信号
                if progress_callback is not None:
                    continue_print = progress_callback(idx + 1, total_pages)
                    if not continue_print:
                        painter.end()
                        return False, "用户已取消打印任务。"

                # 渲染当前页面高保真图像
                page_image = PdfPrinter.render_printable_page(doc, page_idx, dpi=dpi)
                if page_image is None or page_image.isNull():
                    painter.end()
                    return False, f"第 {page_idx + 1} 页光栅化渲染失败，打印中止。"

                # 若为黑白/灰度模式，在光栅化层转为纯灰度位图，确保全平台虚拟与物理打印驱动一致
                if config.color_mode.lower() == "grayscale":
                    page_image = page_image.convertToFormat(QImage.Format_Grayscale8).convertToFormat(QImage.Format_RGB32)

                # 处理方向
                if config.orientation == "portrait":
                    printer.setPageOrientation(QPageLayout.Orientation.Portrait)
                elif config.orientation == "landscape":
                    printer.setPageOrientation(QPageLayout.Orientation.Landscape)
                else:
                    # 自动根据页面实际宽高比适配
                    if page_image.width() > page_image.height():
                        printer.setPageOrientation(QPageLayout.Orientation.Landscape)
                    else:
                        printer.setPageOrientation(QPageLayout.Orientation.Portrait)

                # 获取打印机当前可绘制物理像素区域
                target_viewport = painter.viewport()
                vp_width = target_viewport.width()
                vp_height = target_viewport.height()

                if config.scale_mode == "actual":
                    # 实际尺寸居中绘制
                    dest_w = page_image.width()
                    dest_h = page_image.height()
                    dest_x = (vp_width - dest_w) / 2.0
                    dest_y = (vp_height - dest_h) / 2.0
                    draw_rect = QRectF(dest_x, dest_y, dest_w, dest_h)
                else:
                    # 适应纸张边界并保持宽高比居中 (默认模式)
                    scale = min(vp_width / float(page_image.width()), vp_height / float(page_image.height()))
                    dest_w = page_image.width() * scale
                    dest_h = page_image.height() * scale
                    dest_x = (vp_width - dest_w) / 2.0
                    dest_y = (vp_height - dest_h) / 2.0
                    draw_rect = QRectF(dest_x, dest_y, dest_w, dest_h)

                # 在打印机表面绘制页面图像
                painter.drawImage(draw_rect, page_image)

                # 若非最后一页，通知打印机换页出纸
                if idx < total_pages - 1:
                    printer.newPage()

        except Exception as e:
            painter.end()
            return False, f"打印调度过程中发生异常：{str(e)}"

        painter.end()
        return True, f"打印任务已成功发送到 '{config.printer_name}'（共 {total_pages} 页）。"
