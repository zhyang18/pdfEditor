"""
PDF 核心文档模型与底层物理操作封装模块。
基于 pymupdf 引擎提供文档的加载、高清晰度渲染、页面重排、旋转、删除、插入图片与文本、压缩等功能。
"""

import os
import shutil
import tempfile
import json
from typing import Optional, List, Tuple
import pymupdf
from PySide6.QtGui import QImage
from core.image_layer import ImageLayerManager, ImageLayer


class PdfDocument:
    """
    PDF 核心文档实体类。
    封装底层 pymupdf.Document 对象，提供文档生命周期管理与页面修改能力。
    """

    def __init__(self) -> None:
        """
        初始化 PDF 文档实例。
        创建空状态的文档对象，记录文件路径与修改标记，初始化图片图层管理器。
        """
        self._doc: Optional[pymupdf.Document] = None
        self._base_doc_bytes: Optional[bytes] = None
        self._file_path: Optional[str] = None
        self._is_modified: bool = False
        self.image_layers: ImageLayerManager = ImageLayerManager()

    def _sync_base_doc_bytes(self) -> None:
        """
        同步底层纯净 PDF 文档的内存字节快照。
        """
        if self._doc is not None and not self._doc.is_closed:
            try:
                self._base_doc_bytes = self._doc.tobytes(garbage=3, deflate=True)
            except Exception:
                pass

    @property
    def file_path(self) -> Optional[str]:
        """
        获取当前打开的 PDF 文件绝对路径。

        @return 文件路径字符串；若为新创建未保存文档则返回 None
        """
        return self._file_path

    @property
    def is_modified(self) -> bool:
        """
        获取当前文档是否有未保存的修改。

        @return 若有未保存修改返回 True，否则返回 False
        """
        return self._is_modified

    def set_modified(self, modified: bool = True) -> None:
        """
        设置文档修改状态标记。

        @param modified 是否已被修改，默认为 True
        """
        self._is_modified = modified

    @property
    def is_open(self) -> bool:
        """
        判断当前是否有 PDF 文档处于打开状态。

        @return 若文档有效且未关闭返回 True，否则返回 False
        """
        return self._doc is not None and not self._doc.is_closed

    @property
    def page_count(self) -> int:
        """
        获取当前文档的总页数。

        @return 总页数整数值；未打开文档时返回 0
        """
        if not self.is_open or self._doc is None:
            return 0
        return len(self._doc)

    def open(self, file_path: str, password: Optional[str] = None) -> bool:
        """
        从指定本地文件路径打开 PDF 文档。

        @param file_path 目标 PDF 文件的绝对路径
        @param password PDF 文档的解锁密码（若文档被加密时传入）
        @return 打开是否成功
        """
        self.close()
        if not os.path.isfile(file_path):
            return False

        try:
            doc = pymupdf.open(file_path)
            if doc.is_encrypted:
                if password is not None:
                    auth_result = doc.authenticate(password)
                    if auth_result == 0:
                        doc.close()
                        return False
                else:
                    doc.close()
                    return False
            self._doc = doc
            self._file_path = os.path.abspath(file_path)
            self._is_modified = False
            self.image_layers.clear()

            # 尝试从 Catalog 还原已存储的可编辑图层数据
            try:
                cat_xref = doc.pdf_catalog()
                val = doc.xref_get_key(cat_xref, "PdfEditorLayers")
                if val and val[0] == "string" and val[1]:
                    layers_data = json.loads(val[1])
                    self.image_layers.deserialize(layers_data)
            except Exception:
                pass

            self._sync_base_doc_bytes()
            return True
        except Exception:
            self._doc = None
            self._file_path = None
            return False

    def create_empty(self) -> None:
        """
        在内存中创建一个全新的空白 PDF 文档，并默认插入一个 A4 页面。
        """
        self.close()
        self._doc = pymupdf.open()
        # 默认插入一张标准 A4 页面 (595 x 842 pt)
        self._doc.new_page(width=595.0, height=842.0)
        self._file_path = None
        self._is_modified = True
        self.image_layers.clear()
        self._sync_base_doc_bytes()

    def get_page_size(self, page_index: int) -> Optional[Tuple[float, float]]:
        """
        获取指定页面的尺寸规格（点数 pt）。

        @param page_index 页面索引（从 0 开始）
        @return 包含 (width, height) 的浮点元组；若索引无效则返回 None
        """
        if not self.is_open or self._doc is None or not (0 <= page_index < len(self._doc)):
            return None
        rect = self._doc[page_index].rect
        return (rect.width, rect.height)

    def render_page_pixmap(self, page_index: int, dpi: int = 150) -> Optional[QImage]:
        """
        将指定页面渲染为高保真 QImage 位图对象，用于 UI 界面显示与缩略图。

        @param page_index 页面索引（从 0 开始）
        @param dpi 渲染分辨率（点/英寸），默认为 150 DPI
        @return 渲染生成的 QImage 对象；若失败或页面越界返回 None
        """
        if not self.is_open or self._doc is None or not (0 <= page_index < len(self._doc)):
            return None

        try:
            page = self._doc[page_index]
            zoom = dpi / 72.0
            matrix = pymupdf.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=matrix, alpha=False)

            # 将 pymupdf.Pixmap 转换为 PySide6.QtGui.QImage
            image = QImage(
                pix.samples,
                pix.width,
                pix.height,
                pix.stride,
                QImage.Format_RGB888
            )
            # 必须 copy 一份独立内存，避免 pix 被垃圾回收后野指针崩溃
            return image.copy()
        except Exception:
            return None

    def move_page(self, from_index: int, to_index: int) -> bool:
        """
        移动指定页面到目标位置，改变页码顺序。
        采用基于页面索引全排列的重构方案，确保与列表索引严格对应。

        @param from_index 原始页面索引（从 0 开始）
        @param to_index 目标页面索引（从 0 开始）
        @return 页面移动是否成功
        """
        if not self.is_open or self._doc is None:
            return False
        total = len(self._doc)
        if not (0 <= from_index < total and 0 <= to_index < total):
            return False
        if from_index == to_index:
            return True

        try:
            order = list(range(total))
            item = order.pop(from_index)
            order.insert(to_index, item)
            self._doc.select(order)
            self._is_modified = True
            self._sync_base_doc_bytes()
            return True
        except Exception:
            return False

    def reorder_pages(self, new_order: List[int]) -> bool:
        """
        按指定索引序列批量重排所有页面。

        @param new_order 新的页面索引列表，其元素必须包含所有当前页面的 0-based 索引
        @return 重排是否成功
        """
        if not self.is_open or self._doc is None:
            return False
        if sorted(new_order) != list(range(len(self._doc))):
            return False

        try:
            self._doc.select(new_order)
            self._is_modified = True
            self._sync_base_doc_bytes()
            return True
        except Exception:
            return False

    def rotate_page(self, page_index: int, angle: int) -> bool:
        """
        旋转指定页面（顺时针增加指定角度）。

        @param page_index 目标页面索引（从 0 开始）
        @param angle 旋转度数，通常为 90、180 或 270 度
        @return 旋转操作是否成功
        """
        if not self.is_open or self._doc is None or not (0 <= page_index < len(self._doc)):
            return False

        try:
            page = self._doc[page_index]
            current_rot = page.rotation
            new_rot = (current_rot + angle) % 360
            page.set_rotation(new_rot)
            self._is_modified = True
            self._sync_base_doc_bytes()
            return True
        except Exception:
            return False

    def delete_page(self, page_index: int) -> bool:
        """
        删除指定索引的单个页面。

        @param page_index 待删除的页面索引（从 0 开始）
        @return 删除是否成功（若文档仅剩 1 页则禁止删除返回 False）
        """
        if not self.is_open or self._doc is None or not (0 <= page_index < len(self._doc)):
            return False
        if len(self._doc) <= 1:
            return False

        try:
            self._doc.delete_page(page_index)
            self._is_modified = True
            self._sync_base_doc_bytes()
            return True
        except Exception:
            return False

    def delete_pages(self, page_indices: List[int]) -> bool:
        """
        批量删除指定的多个页面。

        @param page_indices 待删除的页面索引列表
        @return 删除是否成功（必须至少保留 1 页）
        """
        if not self.is_open or self._doc is None or not page_indices:
            return False

        total = len(self._doc)
        valid_indices = sorted(list(set(idx for idx in page_indices if 0 <= idx < total)), reverse=True)
        if len(valid_indices) >= total:
            return False

        try:
            for idx in valid_indices:
                self._doc.delete_page(idx)
            self._is_modified = True
            self._sync_base_doc_bytes()
            return True
        except Exception:
            return False

    def insert_blank_page(self, page_index: int, width: float = 595.0, height: float = 842.0) -> bool:
        """
        在指定位置插入一张空白页面。

        @param page_index 插入的目标索引（若等于总页数则追加在末尾）
        @param width 页面宽度（点数 pt），默认 595.0 (A4)
        @param height 页面高度（点数 pt），默认 842.0 (A4)
        @return 插入是否成功
        """
        if not self.is_open or self._doc is None:
            return False
        total = len(self._doc)
        if not (0 <= page_index <= total):
            return False

        try:
            self._doc.new_page(pno=page_index, width=width, height=height)
            self._is_modified = True
            self._sync_base_doc_bytes()
            return True
        except Exception:
            return False

    def insert_image(
        self,
        page_index: int,
        image_path: str,
        rect: Tuple[float, float, float, float],
        keep_proportion: bool = True
    ) -> bool:
        """
        在指定页面的矩形区域内插入图片。

        @param page_index 目标页面索引（从 0 开始）
        @param image_path 本地图片文件绝对路径
        @param rect 目标矩形区域元组 (x0, y0, x1, y1)
        @param keep_proportion 是否保持图像原始宽高比，默认为 True
        @return 插入图片是否成功
        """
        if not self.is_open or self._doc is None or not (0 <= page_index < len(self._doc)):
            return False
        if not os.path.isfile(image_path):
            return False

        try:
            page = self._doc[page_index]
            fitz_rect = pymupdf.Rect(*rect)
            page.insert_image(fitz_rect, filename=image_path, keep_proportion=keep_proportion)
            self._is_modified = True
            return True
        except Exception:
            return False

    def insert_text(
        self,
        page_index: int,
        rect: Tuple[float, float, float, float],
        text: str,
        font_size: float = 12.0,
        color: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    ) -> bool:
        """
        在指定页面的矩形框内插入文本内容。

        @param page_index 目标页面索引（从 0 开始）
        @param rect 文本边框矩形 (x0, y0, x1, y1)
        @param text 待写入的文本字符串
        @param font_size 字体字号大小（点数），默认为 12.0
        @param color 字体 RGB 归一化颜色元组 (r, g, b)，取值范围 0.0~1.0，默认为黑色
        @return 插入文本是否成功
        """
        if not self.is_open or self._doc is None or not (0 <= page_index < len(self._doc)):
            return False
        if not text.strip():
            return False

        try:
            page = self._doc[page_index]
            fitz_rect = pymupdf.Rect(*rect)
            # 采用内置中文字体支持中文排版
            page.insert_textbox(
                fitz_rect,
                text,
                fontsize=font_size,
                color=color,
                fontname="china-s"
            )
            self._is_modified = True
            return True
        except Exception:
            return False

    def add_text_watermark(
        self,
        text: str,
        font_size: float = 36.0,
        color: Tuple[float, float, float] = (0.75, 0.75, 0.75),
        opacity: float = 0.3,
        angle: float = 45.0,
        page_indices: Optional[List[int]] = None
    ) -> bool:
        """
        为文档页面批量添加倾斜文本水印。
        使用高精度仿射变换矩阵实现任意实数角度居中倾斜，优先选用系统无衬线中文字体保证中文渲染效果。

        @param text 水印文本内容
        @param font_size 水印字号大小，默认为 36.0
        @param color 水印 RGB 归一化颜色元组 (r, g, b)，默认为浅灰色
        @param opacity 水印填充不透明度 (0.0~1.0)，默认为 0.3
        @param angle 倾斜旋转度数，默认为 45.0 度
        @param page_indices 目标页面索引列表；若为 None 则应用到所有页面
        @return 添加水印是否成功
        """
        if not self.is_open or self._doc is None or not text.strip():
            return False

        targets = page_indices if page_indices is not None else list(range(len(self._doc)))
        try:
            # 常见 Windows 系统中文字体文件列表
            system_font_candidates = [
                "C:/Windows/Fonts/simhei.ttf",
                "C:/Windows/Fonts/msyh.ttc",
                "C:/Windows/Fonts/simsun.ttc",
            ]
            available_font_path = None
            for p in system_font_candidates:
                if os.path.isfile(p):
                    available_font_path = p
                    break

            for idx in targets:
                if 0 <= idx < len(self._doc):
                    page = self._doc[idx]
                    rect = page.rect
                    cx = rect.width / 2.0
                    cy = rect.height / 2.0

                    # 尝试引入系统高质量中文字体，若不可用则回退至 china-s
                    font_alias = "china-s"
                    if available_font_path is not None:
                        try:
                            page.insert_font(fontname="f_wm", fontfile=available_font_path)
                            font_alias = "f_wm"
                        except Exception:
                            font_alias = "china-s"

                    # 根据字号估算文本跨度并居中
                    est_half_width = (len(text) * font_size * 0.7) / 2.0
                    start_point = pymupdf.Point(cx - est_half_width, cy + font_size / 3.0)
                    center_point = pymupdf.Point(cx, cy)
                    rot_matrix = pymupdf.Matrix(float(angle))

                    # 优先使用 morph 以页面中心为锚点执行任意角度精准旋转
                    try:
                        page.insert_text(
                            start_point,
                            text,
                            fontsize=font_size,
                            color=color,
                            fill_opacity=opacity,
                            fontname=font_alias,
                            morph=(center_point, rot_matrix)
                        )
                    except Exception:
                        # 降级尝试平铺插入
                        page.insert_text(
                            start_point,
                            text,
                            fontsize=font_size,
                            color=color,
                            fill_opacity=opacity,
                            fontname="china-s"
                        )

            self._is_modified = True
            return True
        except Exception:
            return False

    def extract_pages(self, page_indices: List[int], output_path: str) -> bool:
        """
        提取指定页面并独立保存为新的 PDF 文件。

        @param page_indices 待提取的页面索引列表
        @param output_path 目标输出 PDF 文件的保存路径
        @return 提取并保存是否成功
        """
        if not self.is_open or self._doc is None or not page_indices:
            return False

        try:
            new_doc = pymupdf.open()
            for idx in page_indices:
                if 0 <= idx < len(self._doc):
                    new_doc.insert_pdf(self._doc, from_page=idx, to_page=idx)
            new_doc.save(output_path, garbage=4, deflate=True)
            new_doc.close()
            return True
        except Exception:
            return False

    def split_document(self, split_after_page: int, output_path_1: str, output_path_2: str) -> bool:
        """
        在指定页面之后将当前文档拆分为两个独立的 PDF 文件。
        例如当前文档共 5 页（索引 0~4），split_after_page 为 2（即第 2 页，1-based），
        则第一部分包含第 1~2 页（索引 0~1），第二部分包含第 3~5 页（索引 2~4）。

        @param split_after_page 拆分分界页码（1-based，即在该页之后截断，有效范围为 1 <= split_after_page < page_count）
        @param output_path_1 第一部分输出文件的保存路径
        @param output_path_2 第二部分输出文件的保存路径
        @return 拆分并保存是否全部成功
        """
        if not self.is_open or self._doc is None:
            return False

        total = len(self._doc)
        if split_after_page < 1 or split_after_page >= total:
            return False
        if not output_path_1 or not output_path_2:
            return False

        try:
            # 第一部分：页面索引 0 至 split_after_page - 1
            doc1 = pymupdf.open()
            doc1.insert_pdf(self._doc, from_page=0, to_page=split_after_page - 1)
            doc1.save(output_path_1, garbage=4, deflate=True)
            doc1.close()

            # 第二部分：页面索引 split_after_page 至 total - 1
            doc2 = pymupdf.open()
            doc2.insert_pdf(self._doc, from_page=split_after_page, to_page=total - 1)
            doc2.save(output_path_2, garbage=4, deflate=True)
            doc2.close()

            return True
        except Exception:
            return False

    def save(self, target_path: Optional[str] = None) -> bool:
        """
        保存当前 PDF 文档。
        若存在活动的可编辑图片图层，将图片对象与图层元数据融合写入目标 PDF 中，并保持内存图层完好以便继续编辑、撤销与删除。
        若指定 target_path 则执行另存为；若未指定则覆盖原打开文件（使用安全临时文件替换）。

        @param target_path 可选的目标另存为文件路径
        @return 保存是否成功
        """
        if not self.is_open or self._doc is None:
            return False

        save_path = target_path if target_path is not None else self._file_path
        if not save_path:
            return False

        save_path = os.path.abspath(save_path)
        try:
            active_layers = self.image_layers.get_all_layers()
            # 若有图片图层且有纯净底本镜像，从底本输出带图片的全新文档
            if active_layers and self._base_doc_bytes is not None:
                export_doc = pymupdf.open(stream=self._base_doc_bytes, filetype="pdf")
                for layer in active_layers:
                    if 0 <= layer.page_index < len(export_doc):
                        page = export_doc[layer.page_index]
                        rect = pymupdf.Rect(*layer.rect)
                        page.insert_image(rect, filename=layer.image_path)

                # 将图层元数据写入 Catalog 字典
                try:
                    payload = json.dumps(self.image_layers.serialize(), ensure_ascii=False)
                    cat_xref = export_doc.pdf_catalog()
                    export_doc.xref_set_key(cat_xref, "PdfEditorLayers", pymupdf.get_pdf_str(payload))
                except Exception:
                    pass

                # 执行原子替换保存
                dir_name = os.path.dirname(save_path)
                with tempfile.NamedTemporaryFile(dir=dir_name, delete=False, suffix=".tmp") as tmp:
                    temp_name = tmp.name
                export_doc.save(temp_name, garbage=4, deflate=True, clean=True)
                export_doc.close()
                shutil.move(temp_name, save_path)

                self._file_path = save_path
                self._is_modified = False
                return True
            else:
                # 常规无图片图层的保存
                if self._file_path and os.path.samefile(save_path, self._file_path) if os.path.exists(save_path) else False:
                    dir_name = os.path.dirname(save_path)
                    with tempfile.NamedTemporaryFile(dir=dir_name, delete=False, suffix=".tmp") as tmp:
                        temp_name = tmp.name
                    self._doc.save(temp_name, garbage=4, deflate=True, clean=True)
                    self._doc.close()
                    shutil.move(temp_name, save_path)
                    self._doc = pymupdf.open(save_path)
                    self._file_path = save_path
                    self._is_modified = False
                    return True
                else:
                    self._doc.save(save_path, garbage=4, deflate=True, clean=True)
                    self._file_path = save_path
                    self._is_modified = False
                    return True
        except Exception:
            return False

    def close(self) -> None:
        """
        安全关闭当前打开的 PDF 文档并释放底层资源。
        """
        if self._doc is not None and not self._doc.is_closed:
            try:
                self._doc.close()
            except Exception:
                pass
        self._doc = None
        self._base_doc_bytes = None
        self._file_path = None
        self._is_modified = False
        self.image_layers.clear()
