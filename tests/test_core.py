"""
核心模块自动化单元测试套件。
针对文件工具、页码解析器、PDF 文档增删改查、页面重排、图片插入、多文件合并与 Word 转换进行全方位验证。
"""

import os
import unittest
import tempfile
import pymupdf
from PIL import Image

from core.utils import FileUtils, PageRangeParser
from core.pdf_document import PdfDocument
from core.pdf_merger import PdfMerger, MergeItem
from core.word_converter import WordConverter
from core.history_manager import HistoryManager, Command


class TestCoreServices(unittest.TestCase):
    """
    核心业务逻辑自动化测试类。
    测试 PDF 与 Word 的各项关键功能接口。
    """

    def setUp(self) -> None:
        """
        初始化每个测试用例的前置环境，创建临时测试工作目录。
        """
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        """
        清理测试用例生成的临时目录与测试文件。
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

    def _create_sample_pdf(self, file_path: str, pages: int = 3) -> None:
        """
        创建一个具有指定页数的真实测试 PDF 文件。

        @param file_path 待创建的目标 PDF 文件路径
        @param pages 需要生成的页面总数
        """
        doc = pymupdf.open()
        for i in range(pages):
            page = doc.new_page(width=595.0, height=842.0)
            page.insert_text(pymupdf.Point(50, 100), f"Test Page {i + 1}", fontsize=24)
        doc.save(file_path)
        doc.close()

    def _create_sample_image(self, file_path: str) -> None:
        """
        创建一个真实的测试图片文件。

        @param file_path 待生成的本地图片文件路径
        """
        img = Image.new("RGB", (200, 200), color=(37, 99, 235))
        img.save(file_path, "PNG")

    def test_file_utils(self) -> None:
        """
        测试文件大小格式化与物理文件尺寸读取函数。
        """
        self.assertEqual(FileUtils.format_file_size(0), "0 B")
        self.assertEqual(FileUtils.format_file_size(1024), "1.00 KB")
        self.assertEqual(FileUtils.format_file_size(1048576), "1.00 MB")

    def test_page_range_parser(self) -> None:
        """
        测试页码区间文本字符串的解析准确性。
        """
        self.assertEqual(PageRangeParser.parse_page_ranges("all", 5), [0, 1, 2, 3, 4])
        self.assertEqual(PageRangeParser.parse_page_ranges("1-3, 5", 5), [0, 1, 2, 4])
        self.assertEqual(PageRangeParser.parse_page_ranges("4-2", 5), [1, 2, 3])
        self.assertEqual(PageRangeParser.parse_page_ranges("10-20", 5), [])

    def test_pdf_document_operations(self) -> None:
        """
        测试 PDF 文档的打开、页面移动重排、页面旋转、插入图片与保存功能。
        """
        pdf_path = os.path.join(self.test_dir, "sample.pdf")
        self._create_sample_pdf(pdf_path, pages=4)

        pdf_doc = PdfDocument()
        opened = pdf_doc.open(pdf_path)
        self.assertTrue(opened)
        self.assertEqual(pdf_doc.page_count, 4)

        # 测试页面重排 (将最后一页移动到最前)
        move_success = pdf_doc.move_page(3, 0)
        self.assertTrue(move_success)
        self.assertTrue(pdf_doc.is_modified)

        # 测试批量重排
        reorder_success = pdf_doc.reorder_pages([3, 2, 1, 0])
        self.assertTrue(reorder_success)

        # 测试页面旋转
        rotate_success = pdf_doc.rotate_page(0, 90)
        self.assertTrue(rotate_success)

        # 测试插入空白页
        insert_page_success = pdf_doc.insert_blank_page(1)
        self.assertTrue(insert_page_success)
        self.assertEqual(pdf_doc.page_count, 5)

        # 测试插入图片
        img_path = os.path.join(self.test_dir, "test.png")
        self._create_sample_image(img_path)
        insert_img_success = pdf_doc.insert_image(0, img_path, (100, 100, 300, 300))
        self.assertTrue(insert_img_success)

        # 测试保存到新路径
        saved_path = os.path.join(self.test_dir, "saved.pdf")
        save_success = pdf_doc.save(saved_path)
        self.assertTrue(save_success)
        self.assertTrue(os.path.isfile(saved_path))

        # 重新加载验证
        pdf_doc.close()
        check_doc = PdfDocument()
        self.assertTrue(check_doc.open(saved_path))
        self.assertEqual(check_doc.page_count, 5)
        check_doc.close()

    def test_pdf_merger(self) -> None:
        """
        测试多个 PDF 文件的合并功能及页码切片拼装。
        """
        file1 = os.path.join(self.test_dir, "part1.pdf")
        file2 = os.path.join(self.test_dir, "part2.pdf")
        merged_file = os.path.join(self.test_dir, "merged.pdf")

        self._create_sample_pdf(file1, pages=3)
        self._create_sample_pdf(file2, pages=2)

        merger = PdfMerger()
        items = [
            MergeItem(file_path=file1, page_range="1-2"),
            MergeItem(file_path=file2, page_range="all"),
        ]

        result = merger.merge_files(items, merged_file)
        self.assertTrue(result)
        self.assertTrue(os.path.isfile(merged_file))

        # 验证总页数为 2 + 2 = 4 页
        doc = pymupdf.open(merged_file)
        self.assertEqual(len(doc), 4)
        doc.close()

    def test_word_conversion(self) -> None:
        """
        测试 PDF 导出为 Word 以及 Word 转换回 PDF 流程。
        """
        pdf_path = os.path.join(self.test_dir, "for_word.pdf")
        self._create_sample_pdf(pdf_path, pages=2)

        docx_path = os.path.join(self.test_dir, "output.docx")
        # 测试 PDF 转 Word
        to_word_success = WordConverter.pdf_to_word(pdf_path, docx_path)
        self.assertTrue(to_word_success)
        self.assertTrue(os.path.isfile(docx_path))

        # 测试 Word 转 PDF
        back_pdf_path = os.path.join(self.test_dir, "back_to.pdf")
        to_pdf_success = WordConverter.word_to_pdf(docx_path, back_pdf_path)
        self.assertTrue(to_pdf_success)
        self.assertTrue(os.path.isfile(back_pdf_path))


if __name__ == "__main__":
    unittest.main()
