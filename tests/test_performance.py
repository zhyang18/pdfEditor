"""
长 PDF 与低配置环境性能专项自动化测试模块。
针对几百页大文件场景下的秒级打开、视口优先异步懒加载、LRU 显存淘汰上限以及单页增量式快速操作进行全方位量化验证。
"""

import os
import time
import tempfile
import unittest
import pymupdf
import psutil

from PySide6.QtWidgets import QApplication, QStyleOptionViewItem
from PySide6.QtCore import Qt, QPoint, QRect
from PySide6.QtGui import QImage, QPainter

os.environ["QT_QPA_PLATFORM"] = "offscreen"

app = QApplication.instance()
if app is None:
    app = QApplication([])

from ui.main_window import MainWindow
from ui.thumbnail_panel import ThumbnailListWidget


class TestPerformanceAndLazyLoading(unittest.TestCase):
    """
    大文档性能与异步懒加载自动化测试类。
    """

    def setUp(self) -> None:
        """
        初始化大文档测试文件与测试环境。
        """
        self.test_dir = tempfile.mkdtemp()
        self.large_pdf = os.path.join(self.test_dir, "large_300_pages.pdf")

        # 生成一个包含 300 页真实内容的长 PDF
        doc = pymupdf.open()
        for i in range(300):
            p = doc.new_page(width=595.0, height=842.0)
            p.insert_text(pymupdf.Point(50, 100), f"Performance Test Document - Page {i + 1}", fontsize=14)
            p.draw_line(pymupdf.Point(50, 120), pymupdf.Point(545, 120), color=(0.2, 0.4, 0.8), width=1.0)
        doc.save(self.large_pdf)
        doc.close()

    def tearDown(self) -> None:
        """
        清理临时测试资源。
        """
        try:
            if os.path.exists(self.large_pdf):
                os.remove(self.large_pdf)
            if os.path.exists(self.test_dir):
                os.rmdir(self.test_dir)
        except Exception:
            pass

    def test_300_pages_instant_load_performance(self) -> None:
        """
        验证 300 页长 PDF 的缩略图生成与首屏呈现耗时严格小于 150 毫秒，
        且全量骨架即时填充，绝不阻塞 UI 主线程。
        """
        window = MainWindow()
        window.show()

        start_time = time.perf_counter()
        window.load_pdf(self.large_pdf)
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        list_widget = window.thumbnail_panel.list_widget
        self.assertEqual(list_widget.count(), 300, "300 页文档必须即时创建 300 个骨架 Item")

        # 验证打开与布局耗时小于 150ms（优化前需要 20000ms+）
        self.assertLess(elapsed_ms, 150.0, f"打开 300 页 PDF 耗时过长: {elapsed_ms:.1f}ms")

        # 验证初始状态下非首屏页未阻塞式光栅化，保持占位状态
        item_299 = list_widget.item(299)
        self.assertIsNotNone(item_299)
        self.assertIsNone(item_299.data(Qt.UserRole + 1), "远端页面初始应为占位骨架状态，不应同步分配大图内存")

        window.close()

    def test_thumbnail_skeleton_paint_robustness(self) -> None:
        """
        验证当缩略图处于未加载骨架状态时，委托 paint 能够正常绘制优雅纸张骨架且不抛出任何异常。
        """
        window = MainWindow()
        window.show()
        window.load_pdf(self.large_pdf)

        list_widget = window.thumbnail_panel.list_widget
        delegate = list_widget.thumbnail_delegate

        # 取末尾尚未加载位图的骨架项
        idx_299 = list_widget.model().index(299, 0)
        card_size = list_widget.card_size
        img = QImage(card_size.width(), card_size.height(), QImage.Format_ARGB32)
        painter = QPainter(img)
        opt = QStyleOptionViewItem()
        opt.rect = QRect(0, 0, card_size.width(), card_size.height())

        try:
            delegate.paint(painter, opt, idx_299)
        except Exception as e:
            self.fail(f"骨架屏绘制抛出异常: {e}")
        finally:
            painter.end()

        window.close()

    def test_lru_cache_and_eviction_bounded_memory(self) -> None:
        """
        验证缩略图 LRU 淘汰机制正常工作：
        当加载的缩略图超出容量阈值时，自动回收远端页面的显存，确保总缓存数量被严格限制在有界安全范围内。
        """
        window = MainWindow()
        window.show()
        window.load_pdf(self.large_pdf)

        panel = window.thumbnail_panel
        list_widget = panel.list_widget

        # 模拟工作线程连续返回 100 张缩略图
        test_qimage = QImage(150, 212, QImage.Format_RGB888)
        test_qimage.fill(Qt.white)

        for i in range(100):
            panel._on_thumbnail_ready(i, test_qimage)

        # 验证受控的缓存数量严格不超过 MAX_CACHED_THUMBNAILS (80 张)
        self.assertLessEqual(len(panel._cached_pages), panel.MAX_CACHED_THUMBNAILS)

        # 视口当前位于顶部首屏，验证在达到容量阈值后最远端的页面（如第 70 页）已被淘汰回收
        item_70 = list_widget.item(70)
        self.assertIsNone(item_70.data(Qt.UserRole + 1), "超出容量阈值且距当前视口较远的页面应被 LRU 淘汰回收")

        # 模拟视口滚动至第 200 页并继续加载，验证远离视口的原首屏页（第 0 页）被自动淘汰
        list_widget.get_visible_range = lambda: (195, 205)
        for i in range(150, 220):
            panel._on_thumbnail_ready(i, test_qimage)

        first_item = list_widget.item(0)
        self.assertIsNone(first_item.data(Qt.UserRole + 1), "当视口滚动至远端后，旧首屏页面应被自动淘汰回收")

        window.close()

    def test_incremental_page_rotate_speed(self) -> None:
        """
        验证单页旋转操作采用增量式就地更新，耗时严格小于 20 毫秒，且无需全量重载 300 页。
        """
        window = MainWindow()
        window.show()
        window.load_pdf(self.large_pdf)

        start_time = time.perf_counter()
        window._on_thumbnail_rotate(5, 90)
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        self.assertLess(elapsed_ms, 20.0, f"单页旋转操作过慢: {elapsed_ms:.1f}ms")
        self.assertEqual(window.thumbnail_panel.list_widget.count(), 300)

        window.close()

    def test_incremental_page_move_speed(self) -> None:
        """
        验证页面拖拽移动命令（PageMoveCommand）采用增量式局部刷新，耗时严格小于 20 毫秒。
        """
        window = MainWindow()
        window.show()
        window.load_pdf(self.large_pdf)

        start_time = time.perf_counter()
        window._on_page_order_changed(2, 10)
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        self.assertLess(elapsed_ms, 20.0, f"页面拖拽排序过慢: {elapsed_ms:.1f}ms")
        self.assertEqual(window.thumbnail_panel.list_widget.count(), 300)

        window.close()

    def test_incremental_page_delete_speed(self) -> None:
        """
        验证页面删除操作采用增量式局部移除，总页数即时变为 299，耗时严格小于 20 毫秒。
        """
        window = MainWindow()
        window.show()
        window.load_pdf(self.large_pdf)

        start_time = time.perf_counter()
        window._on_thumbnail_delete(10)
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        self.assertLess(elapsed_ms, 20.0, f"单页删除操作过慢: {elapsed_ms:.1f}ms")
        self.assertEqual(window.thumbnail_panel.list_widget.count(), 299)
        self.assertEqual(window._doc.page_count, 299)

        window.close()


if __name__ == "__main__":
    unittest.main()
