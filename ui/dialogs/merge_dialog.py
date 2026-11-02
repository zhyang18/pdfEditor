"""
多 PDF 文件合并对话框组件。
支持批量添加 PDF 文件、外部拖拽文件导入、列表内上下调整合并顺序、
设置每个文件的页码切片范围，并一键合并导出。全面适配 Fluent 浅色与暗色主题。
"""

import os
from typing import Optional, List
import pymupdf
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog,
    QMessageBox, QProgressBar, QLabel, QWidget
)
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
from core.pdf_merger import PdfMerger, MergeItem
from core.utils import ResourceUtils
from assets.icons import IconLibrary


class MergeDialog(QDialog):
    """
    多 PDF 文件合并管理向导对话框。
    提供可视化的文件队列管理、外部拖拽文件导入与页码范围切片配置。
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        初始化多文件合并对话框，配置拖拽接收并应用当前主题样式。

        @param parent 包含该对话框的父组件
        """
        super().__init__(parent)
        self.setWindowTitle("多文件合并向导 - PDF Editor")
        self.resize(780, 500)
        self.setMinimumSize(640, 380)
        self.setAcceptDrops(True)

        self._init_ui()
        self._apply_theme(parent)

    def _apply_theme(self, parent: Optional[QWidget]) -> None:
        """
        应用父窗口或本地主题样式表，确保表格与控件适配当前亮色/暗色风格。

        @param parent 父窗口组件
        """
        if parent is not None and hasattr(parent, "styleSheet") and parent.styleSheet():
            self.setStyleSheet(parent.styleSheet())
        else:
            style_path = ResourceUtils.get_resource_path(os.path.join("assets", "style_light.qss"))
            if os.path.isfile(style_path):
                with open(style_path, "r", encoding="utf-8") as f:
                    self.setStyleSheet(f.read())

    def _init_ui(self) -> None:
        """
        初始化对话框界面布局与表格控件，并挂载拖拽事件监听。
        """
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 提示说明文本
        hint_label = QLabel(
            "可添加多个 PDF 文件并按列表从上到下的顺序合并。支持直接从外部拖拽 PDF 文件至此处导入；"
            "双击“合并页码范围”列可自定义提取页（如 1-3, 5）。"
        )
        hint_label.setWordWrap(True)
        hint_label.setStyleSheet("color: #64748B; font-size: 12px; line-height: 1.4;")
        layout.addWidget(hint_label)

        # 文件列表表格
        self.table = QTableWidget(0, 4, self)
        self.table.setHorizontalHeaderLabels(["序号", "文件名称", "总页数", "合并页码范围 (双击可修改)"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setAlternatingRowColors(True)

        # 开启表格接收拖拽并安装事件过滤器，确保无论拖到表格任何区域均可触发导入
        self.table.setAcceptDrops(True)
        self.table.installEventFilter(self)
        self.table.viewport().installEventFilter(self)

        layout.addWidget(self.table)

        # 按钮操作栏
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.add_btn = QPushButton("添加 PDF 文件...")
        self.add_btn.setIcon(IconLibrary.get_icon("open", 16))
        self.add_btn.clicked.connect(self._on_add_files)
        btn_layout.addWidget(self.add_btn)

        self.up_btn = QPushButton("向上移动")
        self.up_btn.setIcon(IconLibrary.get_icon("move_up", 16))
        self.up_btn.clicked.connect(self._on_move_up)
        btn_layout.addWidget(self.up_btn)

        self.down_btn = QPushButton("向下移动")
        self.down_btn.setIcon(IconLibrary.get_icon("move_down", 16))
        self.down_btn.clicked.connect(self._on_move_down)
        btn_layout.addWidget(self.down_btn)

        self.remove_btn = QPushButton("移除")
        self.remove_btn.setIcon(IconLibrary.get_icon("delete_page", 16))
        self.remove_btn.clicked.connect(self._on_remove_item)
        btn_layout.addWidget(self.remove_btn)

        self.clear_btn = QPushButton("清空全部")
        self.clear_btn.clicked.connect(self._on_clear_all)
        btn_layout.addWidget(self.clear_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # 底部确定与取消按钮
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        bottom_layout.addWidget(self.cancel_btn)

        self.start_btn = QPushButton("开始合并并保存...")
        self.start_btn.setIcon(IconLibrary.get_icon("merge", 16))
        self.start_btn.setProperty("primary", "true")
        self.start_btn.clicked.connect(self._on_start_merge)
        bottom_layout.addWidget(self.start_btn)

        layout.addLayout(bottom_layout)

    def add_pdf_files(self, file_paths: List[str]) -> int:
        """
        向待合并表格中批量追加有效的 PDF 文件，并读取其真实总页数。

        @param file_paths 待添加的本地文件路径列表
        @return 成功添加的文件总数
        """
        added_count = 0
        for raw_path in file_paths:
            file_path = os.path.normpath(raw_path)
            if not os.path.isfile(file_path):
                continue
            if not file_path.lower().endswith(".pdf"):
                continue

            try:
                doc = pymupdf.open(file_path)
                page_count = len(doc)
                doc.close()
            except Exception:
                continue

            row = self.table.rowCount()
            self.table.insertRow(row)

            item_idx = QTableWidgetItem(str(row + 1))
            item_idx.setTextAlignment(Qt.AlignCenter)
            item_idx.setFlags(item_idx.flags() & ~Qt.ItemIsEditable)

            item_name = QTableWidgetItem(os.path.basename(file_path))
            item_name.setToolTip(file_path)
            item_name.setData(Qt.UserRole, file_path)
            item_name.setFlags(item_name.flags() & ~Qt.ItemIsEditable)

            item_pages = QTableWidgetItem(f"{page_count} 页")
            item_pages.setTextAlignment(Qt.AlignCenter)
            item_pages.setFlags(item_pages.flags() & ~Qt.ItemIsEditable)

            item_range = QTableWidgetItem("全部")
            item_range.setTextAlignment(Qt.AlignCenter)

            self.table.setItem(row, 0, item_idx)
            self.table.setItem(row, 1, item_name)
            self.table.setItem(row, 2, item_pages)
            self.table.setItem(row, 3, item_range)
            added_count += 1

        if added_count > 0:
            self._refresh_index_numbers()
        return added_count

    def _extract_pdf_urls(self, event) -> List[str]:
        """
        从拖拽事件中提取以 .pdf 结尾的有效本地文件路径列表。

        @param event 拖拽事件对象
        @return 包含的有效 PDF 本地文件路径列表
        """
        pdf_paths: List[str] = []
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                local_path = os.path.normpath(url.toLocalFile())
                if os.path.isfile(local_path) and local_path.lower().endswith(".pdf"):
                    pdf_paths.append(local_path)
        return pdf_paths

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """
        响应拖拽进入对话框事件，若包含 PDF 文件则允许放置。

        @param event 拖拽进入事件
        """
        if self._extract_pdf_urls(event):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        """
        响应拖拽在对话框内移动事件。

        @param event 拖拽移动事件
        """
        if self._extract_pdf_urls(event):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        """
        响应拖拽在对话框内释放事件，将拖入的 PDF 文件自动追加到表格列表中。

        @param event 拖拽释放事件
        """
        pdf_paths = self._extract_pdf_urls(event)
        if pdf_paths:
            self.add_pdf_files(pdf_paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def eventFilter(self, watched, event) -> bool:
        """
        事件过滤器：拦截表格及其视口组件上的拖拽事件并转发处理，确保拖到表格也能无缝导入。

        @param watched 被监听的目标组件对象
        @param event 发生的 Qt 事件
        @return 若事件已被处理返回 True，否则返回父类处理结果
        """
        if watched in (self.table, self.table.viewport()):
            if event.type() in (QEvent.DragEnter, QEvent.DragMove):
                if self._extract_pdf_urls(event):
                    event.acceptProposedAction()
                    return True
            elif event.type() == QEvent.Drop:
                pdf_paths = self._extract_pdf_urls(event)
                if pdf_paths:
                    self.add_pdf_files(pdf_paths)
                    event.acceptProposedAction()
                    return True
        return super().eventFilter(watched, event)

    def _on_add_files(self) -> None:
        """
        弹出文件选择器，批量添加 PDF 文件并读取真实总页数。
        """
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择待合并的 PDF 文件",
            "",
            "PDF 文件 (*.pdf)"
        )
        if files:
            self.add_pdf_files(files)

    def _refresh_index_numbers(self) -> None:
        """
        重新编排刷新表格序号列。
        """
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if item is not None:
                item.setText(str(r + 1))

    def _on_move_up(self) -> None:
        """
        将选中的行在列表中向上移动一位。
        """
        curr = self.table.currentRow()
        if curr <= 0:
            return

        # 交换两行数据
        self._swap_rows(curr, curr - 1)
        self.table.selectRow(curr - 1)
        self._refresh_index_numbers()

    def _on_move_down(self) -> None:
        """
        将选中的行在列表中向下移动一位。
        """
        curr = self.table.currentRow()
        if curr < 0 or curr >= self.table.rowCount() - 1:
            return

        self._swap_rows(curr, curr + 1)
        self.table.selectRow(curr + 1)
        self._refresh_index_numbers()

    def _swap_rows(self, row1: int, row2: int) -> None:
        """
        交换表格中两行项的数据。

        @param row1 第一个行索引
        @param row2 第二个行索引
        """
        for c in range(1, 4):
            item1 = self.table.takeItem(row1, c)
            item2 = self.table.takeItem(row2, c)
            self.table.setItem(row1, c, item2)
            self.table.setItem(row2, c, item1)

    def _on_remove_item(self) -> None:
        """
        从列表中移除当前选中的行。
        """
        curr = self.table.currentRow()
        if curr >= 0:
            self.table.removeRow(curr)
            self._refresh_index_numbers()

    def _on_clear_all(self) -> None:
        """
        清空全部待合并文件列表。
        """
        self.table.setRowCount(0)

    def _on_start_merge(self) -> None:
        """
        收集配置项，弹出保存路径对话框，并调用底层合并引擎执行合并。
        """
        count = self.table.rowCount()
        if count < 2:
            QMessageBox.warning(self, "提示", "请至少添加 2 个 PDF 文件进行合并！")
            return

        out_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存合并后的 PDF 文件",
            "合并文档.pdf",
            "PDF 文件 (*.pdf)"
        )
        if not out_path:
            return

        items: List[MergeItem] = []
        for r in range(count):
            path = self.table.item(r, 1).data(Qt.UserRole)
            rng = self.table.item(r, 3).text().strip()
            items.append(MergeItem(file_path=path, page_range=rng))

        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, count)
        self.start_btn.setEnabled(False)

        def on_progress(curr, total, name):
            self.progress_bar.setValue(curr)

        merger = PdfMerger()
        success = merger.merge_files(items, out_path, on_progress)

        self.progress_bar.setVisible(False)
        self.start_btn.setEnabled(True)

        if success:
            QMessageBox.information(self, "成功", f"文件合并成功！\n保存路径：{out_path}")
            self.accept()
        else:
            QMessageBox.critical(self, "错误", "合并过程中发生错误，请检查文件是否损坏或受保护。")
