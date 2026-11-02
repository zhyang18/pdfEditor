"""
多 PDF 文件合并核心服务模块。
支持按用户自定义顺序、自定义页面区间切片并将多个 PDF 文件拼接合并为一个整体文档。
"""

import os
from dataclasses import dataclass
from typing import List, Optional, Callable
import pymupdf
from core.utils import PageRangeParser


@dataclass
class MergeItem:
    """
    单个待合并 PDF 文件的配置项数据结构。
    """
    file_path: str
    page_range: str = "all"


class PdfMerger:
    """
    多 PDF 文件合并器类。
    提供文件顺序拼接、指定页提取拼合以及进度回调支持。
    """

    def __init__(self) -> None:
        """
        初始化 PDF 合并器实例。
        """
        pass

    def merge_files(
        self,
        items: List[MergeItem],
        output_path: str,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> bool:
        """
        按照指定顺序与页面区间将多个 PDF 文件合并为一个新文件。

        @param items 待合并文件项列表，按列表先后次序拼装
        @param output_path 最终合并生成的 PDF 文件保存路径
        @param progress_callback 进度回调函数，接收 (current_index, total_count, current_filename)
        @return 合并是否成功完成
        """
        if not items:
            return False

        merged_doc = pymupdf.open()
        total_items = len(items)

        try:
            for idx, item in enumerate(items):
                if not os.path.isfile(item.file_path):
                    continue

                if progress_callback is not None:
                    try:
                        filename = os.path.basename(item.file_path)
                        progress_callback(idx + 1, total_items, filename)
                    except Exception:
                        pass

                src_doc = pymupdf.open(item.file_path)
                page_count = len(src_doc)
                if page_count == 0:
                    src_doc.close()
                    continue

                # 解析需提取的页码区间
                target_pages = PageRangeParser.parse_page_ranges(item.page_range, page_count)
                for page_idx in target_pages:
                    merged_doc.insert_pdf(src_doc, from_page=page_idx, to_page=page_idx)

                src_doc.close()

            if len(merged_doc) == 0:
                merged_doc.close()
                return False

            merged_doc.save(output_path, garbage=4, deflate=True)
            merged_doc.close()
            return True
        except Exception:
            if not merged_doc.is_closed:
                merged_doc.close()
            return False
