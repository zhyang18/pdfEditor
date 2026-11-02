"""
打印功能与自定义页码范围打印自动化测试模块。
覆盖页码范围解析与安全语法校验、PrintDialog 交互与动态响应、带图层高保真光栅化渲染及打印任务调度安全边界。
"""

import os
import unittest
import tempfile
import pymupdf
from PIL import Image

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence

os.environ["QT_QPA_PLATFORM"] = "offscreen"

app = QApplication.instance()
if app is None:
    app = QApplication([])

from core.pdf_document import PdfDocument
from core.pdf_printer import PdfPrinter, PrintConfiguration
from ui.dialogs.print_dialog import PrintDialog
from ui.main_window import MainWindow


class TestPdfPrintFeature(unittest.TestCase):
    """
    PDF 打印与自定义页码打印核心功能自动化测试类。
    """

    def setUp(self) -> None:
        """
        初始化测试临时目录与包含 8 页的基准测试 PDF 文档。
        """
        self.test_dir = tempfile.mkdtemp()
        self.sample_pdf = os.path.join(self.test_dir, "test_doc_8pages.pdf")
        self.sample_stamp = os.path.join(self.test_dir, "test_stamp.png")

        # 真实生成 8 页的测试 PDF 文件
        doc = pymupdf.open()
        for i in range(8):
            p = doc.new_page(width=595.0, height=842.0)
            p.insert_text(pymupdf.Point(50, 100), f"Print Test Page {i + 1}", fontsize=18)
        doc.save(self.sample_pdf)
        doc.close()

        # 生成用于图层测试的真实印章图片
        img = Image.new("RGBA", (120, 120), (220, 38, 38, 200))
        img.save(self.sample_stamp, "PNG")

        self.doc = PdfDocument()
        self.assertTrue(self.doc.open(self.sample_pdf))

    def tearDown(self) -> None:
        """
        清理测试文档与临时文件。
        """
        if self.doc.is_open:
            self.doc.close()

    def test_page_range_validation_custom(self) -> None:
        """
        验证用户自定义输入页码范围（如 '6-8'）的词法解析、合法性校验与越界保护。
        """
        dlg = PrintDialog(self.doc, current_page_index=0)

        # 1. 核心需求：验证输入 '6-8'，应当解析为第 6, 7, 8 页（0-based 索引 [5, 6, 7]）
        valid, indices, msg = dlg._validate_custom_range("6-8")
        self.assertTrue(valid)
        self.assertEqual(indices, [5, 6, 7])
        self.assertIn("6, 7, 8", msg)
        self.assertIn("共 3 页", msg)

        # 2. 验证多区间组合：'1-2, 4, 6-8'
        valid, indices, msg = dlg._validate_custom_range("1-2, 4, 6-8")
        self.assertTrue(valid)
        self.assertEqual(indices, [0, 1, 3, 5, 6, 7])
        self.assertEqual(len(indices), 6)

        # 3. 验证倒序输入：'8-6'，应正确容错为 [5, 6, 7]
        valid, indices, msg = dlg._validate_custom_range("8-6")
        self.assertTrue(valid)
        self.assertEqual(indices, [5, 6, 7])

        # 4. 验证超出总页数（文档共 8 页，输入 9 或 6-10）
        valid, indices, msg = dlg._validate_custom_range("6-10")
        self.assertFalse(valid)
        self.assertIn("超出文档最大总页数", msg)

        valid, indices, msg = dlg._validate_custom_range("9")
        self.assertFalse(valid)
        self.assertIn("超出文档最大总页数", msg)

        # 5. 验证非法输入（包含字母、异常符号）
        valid, indices, msg = dlg._validate_custom_range("6~8")
        self.assertFalse(valid)
        self.assertIn("非法字符", msg)

        valid, indices, msg = dlg._validate_custom_range("abc")
        self.assertFalse(valid)
        self.assertIn("非法字符", msg)

        # 6. 验证页码小于 1
        valid, indices, msg = dlg._validate_custom_range("0-3")
        self.assertFalse(valid)
        self.assertIn("页码必须从 1 开始", msg)

        # 7. 验证空输入
        valid, indices, msg = dlg._validate_custom_range("")
        self.assertFalse(valid)

    def test_print_dialog_ui_flow(self) -> None:
        """
        验证 PrintDialog 对话框内单选按钮切换、输入框联动、即时提示与配置生成流程。
        """
        dlg = PrintDialog(self.doc, current_page_index=2)

        # 初始默认状态：全部页面
        self.assertTrue(dlg.radio_all.isChecked())
        self.assertFalse(dlg.txt_custom_range.isEnabled())
        self.assertEqual(dlg._selected_page_indices, list(range(8)))

        # 切换到当前页（第 3 页，0-based 为 2）
        dlg.radio_current.setChecked(True)
        self.assertEqual(dlg._selected_page_indices, [2])
        self.assertIn("当前第 3 页", dlg.lbl_range_hint.text())

        # 切换到自定义页码
        dlg.radio_custom.setChecked(True)
        self.assertTrue(dlg.txt_custom_range.isEnabled())

        # 输入 '6-8'
        dlg.txt_custom_range.setText("6-8")
        self.assertEqual(dlg._selected_page_indices, [5, 6, 7])
        self.assertIn("共 3 页", dlg.lbl_range_hint.text())

        # 验证预览控制项
        self.assertEqual(dlg._preview_list_index, 0)
        self.assertIn("第 1 / 3 页", dlg.lbl_preview_index.text())
        self.assertIn("原第 6 页", dlg.lbl_preview_index.text())

        # 翻页预览
        dlg._on_next_preview_clicked()
        self.assertEqual(dlg._preview_list_index, 1)
        self.assertIn("原第 7 页", dlg.lbl_preview_index.text())

        # 输入越界页码
        dlg.txt_custom_range.setText("10-12")
        self.assertEqual(dlg._selected_page_indices, [])
        self.assertFalse(dlg.btn_print.isEnabled())

    def test_printable_page_rendering_with_layers(self) -> None:
        """
        验证高保真打印光栅化渲染，包含底层 PDF 页面及未烘焙的图片/印章图层。
        """
        # 在第 6 页（0-based 为 5）添加一层图片图层
        self.doc.image_layers.add_layer(
            page_index=5,
            image_path=self.sample_stamp,
            rect=(100.0, 150.0, 250.0, 300.0)
        )

        # 渲染第 6 页的高清打印位图 (150 DPI)
        img = PdfPrinter.render_printable_page(self.doc, 5, dpi=150)
        self.assertIsNotNone(img)
        self.assertFalse(img.isNull())
        self.assertGreater(img.width(), 500)
        self.assertGreater(img.height(), 700)

    def test_printer_system_enumeration_and_invalid_printer(self) -> None:
        """
        验证系统真实打印机枚举与非法打印机名称时的安全错误捕获。
        """
        # 枚举系统可用打印机（无论物理还是虚拟）
        printers = PdfPrinter.get_available_printers()
        self.assertIsInstance(printers, list)

        # 构造无效打印机名称执行打印，应当安全返回错误且不发生崩溃
        fake_config = PrintConfiguration(
            printer_name="NonExistent_Printer_12345",
            page_indices=[5, 6, 7],
            copies=1
        )
        success, err_msg = PdfPrinter.print_document(self.doc, fake_config)
        self.assertFalse(success)
        self.assertIn("系统未找到指定的打印机", err_msg)

    def test_main_window_print_actions(self) -> None:
        """
        验证主窗口主工具栏按钮、菜单项动作及 Ctrl+P 快捷键绑定。
        """
        from unittest.mock import patch
        from PySide6.QtWidgets import QMessageBox

        win = MainWindow()
        # 1. 验证工具栏存在打印动作
        self.assertTrue(hasattr(win.toolbar, "act_print"))
        self.assertEqual(win.toolbar.act_print.text(), "打印")

        # 2. 验证未打开文档时触发打印的安全提示（通过 mock 拦截模态弹窗以防测试卡死）
        self.assertFalse(win._doc.is_open)
        with patch.object(QMessageBox, "information") as mock_info:
            win._on_print_document()
            mock_info.assert_called_once()

        win.close()

    def test_indicator_checkmark_style(self) -> None:
        """
        验证单选框与复选框选中时的打勾样式表加载与 SVG 资源引用解析。
        """
        from core.utils import ResourceUtils

        # 验证 SVG 勾选资源文件物理存在
        svg_path = ResourceUtils.get_resource_path(os.path.join("assets", "check_white.svg"))
        self.assertTrue(os.path.isfile(svg_path))

        # 验证样式表解析函数能正确将相对路径映射为带有正斜杠的规范绝对路径
        light_style = ResourceUtils.load_stylesheet("style_light.qss")
        self.assertIn("check_white.svg", light_style)
        self.assertNotIn('url("assets/check_white.svg")', light_style)

        # 验证 PrintDialog 实例化后单选框与复选框处于有效可选中状态
        dlg = PrintDialog(self.doc)
        self.assertTrue(dlg.radio_all.isChecked())
        self.assertTrue(dlg.chk_collate.isChecked())
        dlg.close()

    def test_custom_range_hint_full_display_and_scroll(self) -> None:
        """
        验证自定义页码范围提示完整展示所有页码，支持换行与多行滚动显示。
        """
        dlg = PrintDialog(self.doc)
        dlg.radio_custom.setChecked(True)

        # 1. 验证用户输入的 '1-6, 8' 完整展示，不再被人为截断为 '... 等共 N 页'
        dlg.txt_custom_range.setText("1-6, 8")
        hint_text = dlg.lbl_range_hint.text()
        self.assertIn("1, 2, 3, 4, 5, 6, 8", hint_text)
        self.assertNotIn("...", hint_text)
        self.assertIn("共 7 页", hint_text)
        self.assertTrue(dlg.lbl_range_hint.wordWrap())
        self.assertTrue(dlg.scroll_range_hint.widgetResizable())
        self.assertLessEqual(dlg.scroll_range_hint.height(), dlg.scroll_range_hint.maximumHeight())

        dlg.close()

    def test_print_settings_realtime_preview_reactivity(self) -> None:
        """
        验证修改横向/纵向方向、色彩模式与缩放模式时，右侧打印预览实时联动更新。
        """
        dlg = PrintDialog(self.doc)
        dlg.resize(800, 580)
        dlg.show()

        # 1. 验证默认自动方向（纵向页面）预览纸张为高大于宽
        pix_auto = dlg.lbl_preview_image.pixmap()
        self.assertFalse(pix_auto.isNull())
        self.assertGreater(pix_auto.height(), pix_auto.width())

        # 2. 切换为横向（Landscape），验证预览纸张即时切换为横向（宽大于高）
        dlg.combo_orientation.setCurrentIndex(2)
        pix_landscape = dlg.lbl_preview_image.pixmap()
        self.assertFalse(pix_landscape.isNull())
        self.assertGreater(pix_landscape.width(), pix_landscape.height())

        # 3. 切换回纵向（Portrait），验证预览纸张即时恢复纵向（高大于宽）
        dlg.combo_orientation.setCurrentIndex(1)
        pix_portrait = dlg.lbl_preview_image.pixmap()
        self.assertFalse(pix_portrait.isNull())
        self.assertGreater(pix_portrait.height(), pix_portrait.width())

        # 4. 切换为黑白/灰度模式
        dlg.combo_color.setCurrentIndex(1)
        pix_gray = dlg.lbl_preview_image.pixmap()
        self.assertFalse(pix_gray.isNull())

        # 5. 切换缩放模式
        dlg.combo_scale.setCurrentIndex(1)
        pix_actual = dlg.lbl_preview_image.pixmap()
        self.assertFalse(pix_actual.isNull())

        dlg.close()


if __name__ == "__main__":
    unittest.main()
