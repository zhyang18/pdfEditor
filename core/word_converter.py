"""
Word 文档与 PDF 文档双向互转核心服务模块。
提供 PDF 导出为 Word (.docx) 以及 Word 导入转为 PDF 的高保真转换能力。
"""

import os
from typing import Optional, Callable
import pymupdf


class WordConverter:
    """
    Word 与 PDF 双向格式转换器。
    提供 PDF 转 Word (.docx) 及 Word (.docx/.doc) 转 PDF 的静态工具方法。
    """

    @staticmethod
    def pdf_to_word(
        pdf_path: str,
        docx_path: str,
        start_page: int = 0,
        end_page: Optional[int] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> bool:
        """
        将指定 PDF 文档或指定页码区间转换为 Word (.docx) 格式。

        @param pdf_path 源 PDF 文件的本地绝对路径
        @param docx_path 目标输出 Word 文档的保存路径
        @param start_page 起始页面索引（从 0 开始），默认为 0
        @param end_page 结束页面索引（不包含该页）；若为 None 则转换到文档末尾
        @param progress_callback 转换进度回调函数，接收 (progress_percent, status_message)
        @return 转换是否成功完成
        """
        if not os.path.isfile(pdf_path):
            return False

        try:
            from pdf2docx import Converter

            if progress_callback is not None:
                progress_callback(10, "正在解析 PDF 文档结构与流式段落...")

            cv = Converter(pdf_path)
            cv.convert(docx_path, start=start_page, end=end_page)
            cv.close()

            if progress_callback is not None:
                progress_callback(100, "Word 文档转换完成！")

            return os.path.isfile(docx_path)
        except Exception:
            return False

    @staticmethod
    def word_to_pdf(
        word_path: str,
        pdf_path: str,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> bool:
        """
        将指定 Word 文档 (.docx/.doc) 转换为 PDF 格式。
        优先采用 Windows 原生 Office/WPS COM 组件进行高保真矢量转换；
        若无可用 Office 办公软件环境，则自动调用纯 Python 解析渲染引擎进行备用转换。

        @param word_path 源 Word 文档的本地绝对路径
        @param pdf_path 目标输出 PDF 文件的保存路径
        @param progress_callback 转换进度回调函数，接收 (progress_percent, status_message)
        @return 转换是否成功完成
        """
        if not os.path.isfile(word_path):
            return False

        abs_word = os.path.abspath(word_path)
        abs_pdf = os.path.abspath(pdf_path)

        # 方案一：优先使用系统原生 Office / WPS COM 接口
        try:
            import pythoncom
            import win32com.client

            pythoncom.CoInitialize()
            if progress_callback is not None:
                progress_callback(20, "正在启动 Word 渲染排版服务...")

            word_app = None
            try:
                word_app = win32com.client.DispatchEx("Word.Application")
            except Exception:
                try:
                    word_app = win32com.client.DispatchEx("KWps.Application")
                except Exception:
                    word_app = None

            if word_app is not None:
                word_app.Visible = False
                doc = word_app.Documents.Open(abs_word, ReadOnly=True)

                if progress_callback is not None:
                    progress_callback(60, "正在导出高保真 PDF 数据流...")

                # 17 代表 wdFormatPDF
                doc.SaveAs(abs_pdf, FileFormat=17)
                doc.Close(SaveChanges=False)
                word_app.Quit()
                pythoncom.CoUninitialize()

                if os.path.isfile(abs_pdf):
                    if progress_callback is not None:
                        progress_callback(100, "PDF 转换成功！")
                    return True
        except Exception:
            pass

        # 方案二：备用纯 Python 解析回退方案
        try:
            if progress_callback is not None:
                progress_callback(30, "正在解析 Word 文本段落与样式...")

            import docx

            doc = docx.Document(abs_word)
            pdf_doc = pymupdf.open()
            page = pdf_doc.new_page(width=595.0, height=842.0)

            margin_x = 54.0
            margin_y = 54.0
            current_y = margin_y
            page_height = 842.0 - margin_y
            rect_width = 595.0 - 2 * margin_x

            for p in doc.paragraphs:
                text = p.text.strip()
                if not text:
                    current_y += 14.0
                    continue

                if current_y > page_height:
                    page = pdf_doc.new_page(width=595.0, height=842.0)
                    current_y = margin_y

                font_size = 12.0
                if p.style.name.startswith("Heading 1"):
                    font_size = 18.0
                elif p.style.name.startswith("Heading 2"):
                    font_size = 15.0

                text_rect = pymupdf.Rect(margin_x, current_y, margin_x + rect_width, current_y + font_size * 2.5)
                page.insert_textbox(text_rect, text, fontsize=font_size, fontname="china-s")
                current_y += font_size * 2.2

            if progress_callback is not None:
                progress_callback(80, "正在写入 PDF 文件...")

            pdf_doc.save(abs_pdf, garbage=4, deflate=True)
            pdf_doc.close()

            if progress_callback is not None:
                progress_callback(100, "PDF 转换成功！")

            return os.path.isfile(abs_pdf)
        except Exception:
            return False
