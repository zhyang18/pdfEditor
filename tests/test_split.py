"""
PDF 拆分功能与交互对话框单元测试模块。
验证底层无损拆分逻辑、页码区间切片准确度、异常边界处理以及 SplitDialog 的联动与路径校验。
"""

import os
import unittest
import tempfile
import pymupdf

from PySide6.QtWidgets import QApplication

os.environ["QT_QPA_PLATFORM"] = "offscreen"

app = QApplication.instance()
if app is None:
    app = QApplication([])

from core.pdf_document import PdfDocument
from ui.dialogs.split_dialog import SplitDialog


class TestPdfSplitFunctionality(unittest.TestCase):
    """
    PDF 拆分引擎与 UI 对话框测试用例集合。
    """

    def setUp(self) -> None:
        """
        初始化测试临时目录与真实测试文档。
        """
        self.test_dir = tempfile.mkdtemp()
        self.sample_pdf = os.path.join(self.test_dir, "multi_page_doc.pdf")

        # 生成包含 5 页的真实测试 PDF 文档
        doc = pymupdf.open()
        for i in range(5):
            page = doc.new_page(width=595.0, height=842.0)
            page.insert_text(pymupdf.Point(60, 120), f"Split Content Page {i + 1}", fontsize=20)
        doc.save(self.sample_pdf)
        doc.close()

    def tearDown(self) -> None:
        """
        清理测试过程中创建的所有临时文件。
        """
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_split_document_core_success(self) -> None:
        """
        测试底层 PdfDocument.split_document 正常拆分功能。
        验证将 5 页文档在第 2 页后拆分，生成 2 页和 3 页两个独立文件。
        """
        pdf_doc = PdfDocument()
        self.assertTrue(pdf_doc.open(self.sample_pdf))
        self.assertEqual(pdf_doc.page_count, 5)

        out1 = os.path.join(self.test_dir, "part1.pdf")
        out2 = os.path.join(self.test_dir, "part2.pdf")

        # 在第 2 页后切开（即 Part 1: 页 1~2; Part 2: 页 3~5）
        success = pdf_doc.split_document(2, out1, out2)
        self.assertTrue(success)

        # 验证两个输出文件物理存在
        self.assertTrue(os.path.exists(out1))
        self.assertTrue(os.path.exists(out2))

        # 验证第一部分内容与页数
        doc1 = pymupdf.open(out1)
        self.assertEqual(len(doc1), 2)
        self.assertIn("Page 1", doc1[0].get_text())
        self.assertIn("Page 2", doc1[1].get_text())
        doc1.close()

        # 验证第二部分内容与页数
        doc2 = pymupdf.open(out2)
        self.assertEqual(len(doc2), 3)
        self.assertIn("Page 3", doc2[0].get_text())
        self.assertIn("Page 4", doc2[1].get_text())
        self.assertIn("Page 5", doc2[2].get_text())
        doc2.close()

        pdf_doc.close()

    def test_split_document_boundary_cases(self) -> None:
        """
        测试 PdfDocument.split_document 的边界条件与异常入参防御。
        """
        pdf_doc = PdfDocument()
        self.assertTrue(pdf_doc.open(self.sample_pdf))

        out1 = os.path.join(self.test_dir, "b1.pdf")
        out2 = os.path.join(self.test_dir, "b2.pdf")

        # 分界页码小于 1 应当失败
        self.assertFalse(pdf_doc.split_document(0, out1, out2))
        self.assertFalse(pdf_doc.split_document(-1, out1, out2))

        # 分界页码等于或大于总页数 5 应当失败
        self.assertFalse(pdf_doc.split_document(5, out1, out2))
        self.assertFalse(pdf_doc.split_document(6, out1, out2))

        # 输出路径为空应当失败
        self.assertFalse(pdf_doc.split_document(2, "", out2))
        self.assertFalse(pdf_doc.split_document(2, out1, ""))

        pdf_doc.close()

        # 未打开文档执行拆分应当返回 False
        unopened_doc = PdfDocument()
        self.assertFalse(unopened_doc.split_document(1, out1, out2))

    def test_split_dialog_interaction(self) -> None:
        """
        测试 SplitDialog 界面组件交互、联动与校验逻辑。
        """
        pdf_doc = PdfDocument()
        self.assertTrue(pdf_doc.open(self.sample_pdf))

        dialog = SplitDialog(pdf_doc, initial_split_page=3)

        # 验证控件初始状态
        self.assertEqual(dialog.slider.minimum(), 1)
        self.assertEqual(dialog.slider.maximum(), 4)
        self.assertEqual(dialog.slider.value(), 3)
        self.assertEqual(dialog.spin_box.value(), 3)

        # 验证动态卡片文字说明
        self.assertIn("第 1 ~ 3 页", dialog.lbl_part1_summary.text())
        self.assertIn("共 3 页", dialog.lbl_part1_summary.text())
        self.assertIn("第 4 ~ 5 页", dialog.lbl_part2_summary.text())
        self.assertIn("共 2 页", dialog.lbl_part2_summary.text())

        # 验证改变滑块数值后微调框与说明联动
        dialog.slider.setValue(1)
        self.assertEqual(dialog.spin_box.value(), 1)
        self.assertIn("第 1 ~ 1 页", dialog.lbl_part1_summary.text())
        self.assertIn("第 2 ~ 5 页", dialog.lbl_part2_summary.text())

        # 验证路径冲突校验
        # 两个目标路径相同应当被拦截
        same_path = os.path.join(self.test_dir, "same.pdf")
        self.assertFalse(dialog._validate_paths(same_path, same_path))

        # 目标路径覆盖源文档应当被拦截
        self.assertFalse(dialog._validate_paths(self.sample_pdf, same_path))

        # 有效路径验证通过并执行拆分
        p1 = os.path.join(self.test_dir, "valid_part1.pdf")
        p2 = os.path.join(self.test_dir, "valid_part2.pdf")
        self.assertTrue(dialog._validate_paths(p1, p2))

        dialog.edit_path1.setText(p1)
        dialog.edit_path2.setText(p2)
        dialog._on_start_split()
        self.assertTrue(os.path.exists(p1))
        self.assertTrue(os.path.exists(p2))

        dialog.close()
        pdf_doc.close()

    def test_split_single_page_doc(self) -> None:
        """
        测试单页文档在拆分对话框中的防御处理。
        """
        single_path = os.path.join(self.test_dir, "single_page.pdf")
        doc = pymupdf.open()
        doc.new_page(width=595.0, height=842.0)
        doc.save(single_path)
        doc.close()

        pdf_doc = PdfDocument()
        self.assertTrue(pdf_doc.open(single_path))
        self.assertEqual(pdf_doc.page_count, 1)

        dialog = SplitDialog(pdf_doc)
        # 单页文档不具备拆分条件，不包含滑块
        self.assertFalse(hasattr(dialog, "slider"))
        dialog.close()
        pdf_doc.close()
