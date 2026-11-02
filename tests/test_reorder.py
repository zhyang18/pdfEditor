"""
页面重排与定向移动功能自动化单元测试套件。
针对自然语言口令解析、范围移动顺序计算、逆置换数学还原、全排列范围展开、对话框交互及命令撤销重做进行全方位验证。
"""

import os
import unittest
import tempfile
import pymupdf
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QKeyEvent

os.environ["QT_QPA_PLATFORM"] = "offscreen"
app = QApplication.instance()
if app is None:
    app = QApplication([])

from core.utils import PageReorderHelper, PageRangeParser
from core.pdf_document import PdfDocument
from ui.dialogs.reorder_dialog import ReorderDialog
from ui.main_window import MainWindow, PageReorderCommand


class TestPageReorder(unittest.TestCase):
    """
    页面重排与定向移动业务逻辑测试类。
    """

    def setUp(self) -> None:
        """
        初始化每个测试用例的前置环境，生成临时测试 PDF 文件。
        """
        self.test_dir = tempfile.mkdtemp()
        self.sample_pdf = os.path.join(self.test_dir, "reorder_sample.pdf")

        # 创建一个具有 25 页的真实 PDF 文件
        doc = pymupdf.open()
        for i in range(25):
            page = doc.new_page(width=595.0, height=842.0)
            page.insert_text(pymupdf.Point(50, 100), f"Page {i + 1}", fontsize=20)
        doc.save(self.sample_pdf)
        doc.close()

    def tearDown(self) -> None:
        """
        清理临时测试文件与工作区。
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

    def test_smart_command_parsing(self) -> None:
        """
        测试智能自然语言与快捷口令的语法解析准确性。
        """
        total = 25

        # 1. 核心需求句式："将1-5页插入20页后面"
        res1 = PageReorderHelper.parse_smart_command("将1-5页插入20页后面", total)
        self.assertIsNotNone(res1)
        self.assertEqual(res1["source_pages"], [0, 1, 2, 3, 4])
        self.assertEqual(res1["action"], "after")
        self.assertEqual(res1["target_page"], 19)

        # 2. 各种同义句式
        res2 = PageReorderHelper.parse_smart_command("把1-5页移到20页后", total)
        self.assertIsNotNone(res2)
        self.assertEqual(res2["action"], "after")
        self.assertEqual(res2["target_page"], 19)

        res3 = PageReorderHelper.parse_smart_command("1-5页插入20页前面", total)
        self.assertIsNotNone(res3)
        self.assertEqual(res3["action"], "before")
        self.assertEqual(res3["target_page"], 19)

        # 3. 移至最前与最后
        res4 = PageReorderHelper.parse_smart_command("将1-5页移到最前面", total)
        self.assertIsNotNone(res4)
        self.assertEqual(res4["action"], "start")
        self.assertIsNone(res4["target_page"])

        res5 = PageReorderHelper.parse_smart_command("1-5放到最后面", total)
        self.assertIsNotNone(res5)
        self.assertEqual(res5["action"], "end")
        self.assertIsNone(res5["target_page"])

        # 4. 快捷符号与英文简写
        res6 = PageReorderHelper.parse_smart_command("1-5 -> 20", total)
        self.assertIsNotNone(res6)
        self.assertEqual(res6["action"], "after")
        self.assertEqual(res6["target_page"], 19)

        res7 = PageReorderHelper.parse_smart_command("1-5 after 20", total)
        self.assertIsNotNone(res7)
        self.assertEqual(res7["action"], "after")
        self.assertEqual(res7["target_page"], 19)

        res8 = PageReorderHelper.parse_smart_command("1-5 before 10", total)
        self.assertIsNotNone(res8)
        self.assertEqual(res8["action"], "before")
        self.assertEqual(res8["target_page"], 9)

        # 5. 离散页码输入："1, 3, 5 插入 20 后面"
        res9 = PageReorderHelper.parse_smart_command("1, 3, 5 插入 20 后面", total)
        self.assertIsNotNone(res9)
        self.assertEqual(res9["source_pages"], [0, 2, 4])
        self.assertEqual(res9["action"], "after")
        self.assertEqual(res9["target_page"], 19)

        # 6. 非法输入返回 None
        self.assertIsNone(PageReorderHelper.parse_smart_command("随意文字内容", total))
        self.assertIsNone(PageReorderHelper.parse_smart_command("", total))

    def test_calculate_move_order_after(self) -> None:
        """
        测试“将1-5页插入20页后面”算法计算出的全排列顺序。
        """
        total = 25
        source = [0, 1, 2, 3, 4]  # 第 1-5 页
        target = 19               # 第 20 页

        new_order = PageReorderHelper.calculate_move_order(total, source, "after", target)
        self.assertEqual(len(new_order), 25)
        self.assertEqual(sorted(new_order), list(range(25)))

        # 验证位置关系：
        # 原第 6-20 页（索引 5..19）排在最前（前 15 个位置）
        self.assertEqual(new_order[:15], list(range(5, 20)))
        # 紧随第 20 页之后的 5 个位置是原第 1-5 页（索引 0..4）
        self.assertEqual(new_order[15:20], [0, 1, 2, 3, 4])
        # 最后 5 个位置是原第 21-25 页（索引 20..24）
        self.assertEqual(new_order[20:], list(range(20, 25)))

        # 验证新位置索引
        pos_20 = new_order.index(19)
        self.assertEqual(pos_20, 14)
        self.assertEqual(new_order[pos_20 + 1: pos_20 + 6], [0, 1, 2, 3, 4])

    def test_calculate_move_order_before(self) -> None:
        """
        测试“将1-5页插入20页前面”算法计算出的全排列顺序。
        """
        total = 25
        source = [0, 1, 2, 3, 4]  # 第 1-5 页
        target = 19               # 第 20 页

        new_order = PageReorderHelper.calculate_move_order(total, source, "before", target)
        self.assertEqual(len(new_order), 25)
        self.assertEqual(sorted(new_order), list(range(25)))

        # 原第 6-19 页（索引 5..18，共 14 页）在最前
        self.assertEqual(new_order[:14], list(range(5, 19)))
        # 原第 1-5 页（索引 0..4）紧接着插入在第 20 页之前
        self.assertEqual(new_order[14:19], [0, 1, 2, 3, 4])
        # 随后是原第 20 页（索引 19）
        self.assertEqual(new_order[19], 19)
        # 最后是原第 21-25 页（索引 20..24）
        self.assertEqual(new_order[20:], list(range(20, 25)))

    def test_calculate_move_order_start_and_end(self) -> None:
        """
        测试将指定页面移至最前或最后的顺序算法。
        """
        total = 10
        source = [7, 8, 9]  # 第 8-10 页

        # 移至最前
        order_start = PageReorderHelper.calculate_move_order(total, source, "start")
        self.assertEqual(order_start, [7, 8, 9, 0, 1, 2, 3, 4, 5, 6])

        # 移至最后
        source_head = [0, 1]  # 第 1-2 页
        order_end = PageReorderHelper.calculate_move_order(total, source_head, "end")
        self.assertEqual(order_end, [2, 3, 4, 5, 6, 7, 8, 9, 0, 1])

    def test_move_order_conflict_validation(self) -> None:
        """
        测试目标页码位于待移动范围内部时的安全拦截机制。
        """
        total = 10
        source = [0, 1, 2, 3, 4]  # 第 1-5 页

        # 尝试插入第 3 页（索引 2）后面，应抛出异常
        with self.assertRaises(ValueError):
            PageReorderHelper.calculate_move_order(total, source, "after", 2)

        # 尝试插入第 1 页（索引 0）前面，应抛出异常
        with self.assertRaises(ValueError):
            PageReorderHelper.calculate_move_order(total, source, "before", 0)

    def test_inverse_permutation_restoration(self) -> None:
        """
        测试逆置换的数学准确性，确保置换与逆置换复合后严格等价于恒等置换。
        """
        total = 25
        source = [0, 1, 2, 3, 4]
        target = 19
        new_order = PageReorderHelper.calculate_move_order(total, source, "after", target)
        inverse = PageReorderHelper.calculate_inverse_permutation(new_order)

        # 模拟连续两次 select
        # 第 1 次将原始数组映射为 new_order
        original = list(range(total))
        permuted = [original[i] for i in new_order]
        # 第 2 次按 inverse 还原
        restored = [permuted[i] for i in inverse]
        self.assertEqual(restored, original)

    def test_expand_ranges_to_permutation(self) -> None:
        """
        测试全排列范围简写语法展开（如 '6-20, 1-5, 21-25'）。
        """
        total = 25
        seq_text = "6-20, 1-5, 21-25"
        indices = PageReorderHelper.expand_ranges_to_permutation(seq_text, total)
        self.assertIsNotNone(indices)
        self.assertEqual(len(indices), 25)
        self.assertEqual(sorted(indices), list(range(25)))

        # 遗漏页码返回 None
        self.assertIsNone(PageReorderHelper.expand_ranges_to_permutation("1-20", total))
        # 重复页码返回 None
        self.assertIsNone(PageReorderHelper.expand_ranges_to_permutation("1-20, 20-25", total))

    def test_reorder_dialog_integration(self) -> None:
        """
        测试 ReorderDialog 图形界面各组件联动。
        """
        dlg = ReorderDialog(page_count=25, initial_source_page=0)
        self.assertEqual(dlg._page_count, 25)

        # 模拟在口令框中输入“将1-5页插入20页后面”
        dlg.cmd_input.setText("将1-5页插入20页后面")
        self.assertEqual(dlg.source_edit.text(), "1-5")
        self.assertEqual(dlg.action_combo.currentData(), "after")
        self.assertEqual(dlg.target_spin.value(), 20)
        self.assertTrue(dlg.ok_btn.isEnabled())

        # 验证生成的新顺序
        order = dlg.new_order
        self.assertEqual(len(order), 25)
        self.assertEqual(order[15:20], [0, 1, 2, 3, 4])

        # 模拟产生冲突：把目标页设在待移动范围内（例如第 3 页）
        dlg.target_spin.setValue(3)
        self.assertFalse(dlg.ok_btn.isEnabled())
        self.assertIn("不能包含在待移动页面范围内", dlg.lbl_error.text())

        dlg.close()

    def test_reorder_command_undo_redo(self) -> None:
        """
        测试 PageReorderCommand 在真实主窗口与真实 PDF 上的撤销与重做。
        """
        window = MainWindow()
        window.load_pdf(self.sample_pdf)
        self.assertEqual(window._doc.page_count, 25)

        # 构造将 1-5 页插入 20 页后面的新顺序
        new_order = PageReorderHelper.calculate_move_order(25, [0, 1, 2, 3, 4], "after", 19)

        # 执行重排命令
        cmd = PageReorderCommand(window._doc, new_order, "将第 1-5 页插入到第 20 页之后", window)
        success = window._history.push(cmd)
        self.assertTrue(success)

        # 验证文档第 16 页（0-based 15）内容确实是原第 1 页
        page_16_text = window._doc._doc[15].get_text()
        self.assertIn("Page 1", page_16_text)

        # 测试撤销 (Ctrl+Z)
        self.assertTrue(window._history.can_undo())
        window._on_undo()

        # 撤销后，第 1 页（0-based 0）应当恢复为原第 1 页
        page_1_text = window._doc._doc[0].get_text()
        self.assertIn("Page 1", page_1_text)

        # 测试重做 (Ctrl+Y)
        self.assertTrue(window._history.can_redo())
        window._on_redo()
        page_16_text_after_redo = window._doc._doc[15].get_text()
        self.assertIn("Page 1", page_16_text_after_redo)

        window.close()

    def test_custom_sequence_validation(self) -> None:
        """
        测试自定义全序列重排文本的语法解析、容错与诊断提示。
        """
        total = 5

        # 1. 经典逗号全排列
        ok, res, msg = PageReorderHelper.validate_custom_sequence("3, 1, 2, 5, 4", total)
        self.assertTrue(ok)
        self.assertEqual(res, [2, 0, 1, 4, 3])

        # 2. 空格与混合分隔符全排列
        ok2, res2, msg2 = PageReorderHelper.validate_custom_sequence("5 4 3 2 1", total)
        self.assertTrue(ok2)
        self.assertEqual(res2, [4, 3, 2, 1, 0])

        # 3. 范围简写语法全排列
        ok3, res3, msg3 = PageReorderHelper.validate_custom_sequence("3-5, 1-2", total)
        self.assertTrue(ok3)
        self.assertEqual(res3, [2, 3, 4, 0, 1])

        # 4. 越界异常
        ok4, res4, msg4 = PageReorderHelper.validate_custom_sequence("1, 2, 3, 4, 6", total)
        self.assertFalse(ok4)
        self.assertIn("超出当前有效范围", msg4)

        # 5. 重复页码异常
        ok5, res5, msg5 = PageReorderHelper.validate_custom_sequence("1, 2, 2, 3, 4", total)
        self.assertFalse(ok5)
        self.assertIn("重复输入", msg5)

        # 6. 缺少页码异常
        ok6, res6, msg6 = PageReorderHelper.validate_custom_sequence("1, 2, 3", total)
        self.assertFalse(ok6)
        self.assertIn("缺少", msg6)

    def test_custom_sequence_generators(self) -> None:
        """
        测试常用自定义排序序列生成辅助算法。
        """
        total = 6
        # 默认顺序
        self.assertEqual(PageReorderHelper.generate_default_sequence(total), [0, 1, 2, 3, 4, 5])
        # 倒序
        self.assertEqual(PageReorderHelper.generate_reversed_sequence(total), [5, 4, 3, 2, 1, 0])
        # 奇数页在前 (1-based 1, 3, 5, 2, 4, 6 对应 0-based 0, 2, 4, 1, 3, 5)
        self.assertEqual(PageReorderHelper.generate_odd_even_sequence(total, odd_first=True), [0, 2, 4, 1, 3, 5])
        # 偶数页在前
        self.assertEqual(PageReorderHelper.generate_odd_even_sequence(total, odd_first=False), [1, 3, 5, 0, 2, 4])

    def test_custom_tab_ui_interaction(self) -> None:
        """
        测试 ReorderDialog 中自定义排序选项卡的交互、快捷按钮及口令联动。
        """
        dlg = ReorderDialog(page_count=5)

        # 切换到自定义排序 Tab
        dlg.tab_widget.setCurrentIndex(1)
        self.assertEqual(dlg.tab_widget.currentIndex(), 1)
        self.assertEqual(dlg.seq_input.text(), "1, 2, 3, 4, 5")

        # 测试点击“整篇逆序倒排”按钮
        dlg.btn_reverse_seq.click()
        self.assertEqual(dlg.seq_input.text(), "5, 4, 3, 2, 1")
        self.assertEqual(dlg.new_order, [4, 3, 2, 1, 0])

        # 测试手动输入自定义顺序 "3, 1, 2, 5, 4"
        dlg.seq_input.setText("3, 1, 2, 5, 4")
        self.assertEqual(dlg.new_order, [2, 0, 1, 4, 3])

        # 测试在口令框中直接输入自定义序列 "5, 4, 3, 2, 1"，验证自动切到自定义 Tab 并生效
        dlg.cmd_input.setText("5, 4, 3, 2, 1")
        self.assertEqual(dlg.tab_widget.currentIndex(), 1)
        self.assertEqual(dlg.new_order, [4, 3, 2, 1, 0])

        dlg.close()

    def test_return_key_preserves_input(self) -> None:
        """
        测试输入完成后按回车键保留当前输入内容，不误触发重置按钮回到初始状态。
        """
        dlg = ReorderDialog(page_count=18, initial_source_page=0)
        dlg.show()

        # 1. 在快捷口令输入框输入自然语言口令并按下回车键
        input_text = "把1，5，12到18后"
        dlg.cmd_input.setText(input_text)
        return_event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
        app.sendEvent(dlg.cmd_input, return_event)

        # 验证回车后内容完整保留，未被冲掉或回到初始状态
        self.assertEqual(dlg.cmd_input.text(), input_text)
        self.assertEqual(dlg.source_edit.text(), "1, 5, 12")
        self.assertEqual(dlg.target_spin.value(), 18)

        # 2. 在定向移动源页面输入框输入内容并按下回车键
        dlg.source_edit.setText("2-4, 8")
        app.sendEvent(dlg.source_edit, return_event)
        self.assertEqual(dlg.source_edit.text(), "2-4, 8")

        # 3. 在自定义排序输入框输入内容并按下回车键
        dlg.tab_widget.setCurrentIndex(1)
        dlg.seq_input.setText("18, 17, 1-16")
        app.sendEvent(dlg.seq_input, return_event)
        self.assertEqual(dlg.seq_input.text(), "18, 17, 1-16")

        dlg.close()


if __name__ == "__main__":
    unittest.main()
