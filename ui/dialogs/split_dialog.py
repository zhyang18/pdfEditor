"""
PDF 文件拆分向导对话框组件。
支持用户在任意指定页面之后将当前 PDF 拆分成两个独立的 PDF 文件。
提供交互式滑块/微调框选择拆分点、动态区间与页数统计卡片、自定义输出路径及安全保存校验。
"""

import os
from typing import Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QSpinBox, QSlider, QFileDialog,
    QMessageBox, QWidget, QFrame
)
from PySide6.QtCore import Qt
from core.pdf_document import PdfDocument
from core.utils import ResourceUtils
from assets.icons import IconLibrary


class SplitDialog(QDialog):
    """
    PDF 文档拆分向导对话框。
    引导用户可视化选择截断页码，并在指定位置将文档无损拆分为前后两份独立的 PDF 文件。
    """

    def __init__(
        self,
        doc: PdfDocument,
        initial_split_page: int = 1,
        parent: Optional[QWidget] = None
    ) -> None:
        """
        初始化 PDF 拆分向导对话框。

        @param doc 目标待拆分的 PDF 核心文档对象
        @param initial_split_page 初始默认截断页码（1-based，即在该页之后截断）
        @param parent 包含该对话框的父窗口组件
        """
        super().__init__(parent)
        self._doc = doc
        self._total_pages = doc.page_count
        self._source_path = doc.file_path or ""
        self._custom_path_1 = False
        self._custom_path_2 = False

        self.setWindowTitle("拆分 PDF - PDF Editor")
        self.resize(620, 560)
        self.setMinimumSize(560, 500)

        self._init_ui(initial_split_page)
        self._apply_theme(parent)

    def _apply_theme(self, parent: Optional[QWidget]) -> None:
        """
        应用父窗口主题样式表或加载默认浅色样式，确保对话框风格一致。

        @param parent 父窗口组件
        """
        if parent is not None and hasattr(parent, "styleSheet") and parent.styleSheet():
            self.setStyleSheet(parent.styleSheet())
        else:
            style_path = ResourceUtils.get_resource_path(os.path.join("assets", "style_light.qss"))
            if os.path.isfile(style_path):
                with open(style_path, "r", encoding="utf-8") as f:
                    self.setStyleSheet(f.read())

    def _init_ui(self, initial_split_page: int) -> None:
        """
        初始化对话框界面布局与各交互控件。

        @param initial_split_page 初始截断页码
        """
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # 1. 顶部向导标题
        lbl_title = QLabel("PDF 页面拆分向导")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #1E293B;")
        layout.addWidget(lbl_title)

        lbl_desc = QLabel("在指定页码之后将当前 PDF 截断并拆分为前后两份独立的 PDF 文件。")
        lbl_desc.setStyleSheet("color: #64748B; font-size: 12px;")
        layout.addWidget(lbl_desc)

        # 2. 原文档基本信息
        file_name = os.path.basename(self._source_path) if self._source_path else "未命名文档"
        lbl_info = QLabel(f"当前源文件：{file_name}（共 {self._total_pages} 页）")
        lbl_info.setStyleSheet("background: #F1F5F9; border: 1px solid #E2E8F0; border-radius: 6px; padding: 8px 12px; font-size: 12px; color: #334155;")
        layout.addWidget(lbl_info)

        # 判断是否可拆分
        if self._total_pages < 2:
            lbl_warning = QLabel("当前文档总页数少于 2 页，无法拆分为两个独立的 PDF 文件。")
            lbl_warning.setStyleSheet("color: #DC2626; font-size: 13px; font-weight: bold; margin: 20px 0;")
            layout.addWidget(lbl_warning)
            btn_close = QPushButton("关闭")
            btn_close.clicked.connect(self.reject)
            layout.addWidget(btn_close, alignment=Qt.AlignRight)
            return

        # 3. 拆分控制区（滑块 + 微调框）
        split_box = QFrame()
        split_box.setStyleSheet("background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; padding: 12px;")
        split_layout = QVBoxLayout(split_box)
        split_layout.setContentsMargins(12, 12, 12, 12)
        split_layout.setSpacing(8)

        lbl_split_prompt = QLabel("拆分位置选择（在选定页面之后切开）：")
        lbl_split_prompt.setStyleSheet("font-weight: 600; color: #1E293B;")
        split_layout.addWidget(lbl_split_prompt)

        ctrl_layout = QHBoxLayout()
        ctrl_layout.setSpacing(12)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(1, self._total_pages - 1)
        self.slider.setTickPosition(QSlider.TicksBelow)
        self.slider.setTickInterval(max(1, (self._total_pages - 1) // 10))

        self.spin_box = QSpinBox()
        self.spin_box.setRange(1, self._total_pages - 1)
        self.spin_box.setSuffix(" 页后")
        self.spin_box.setMinimumWidth(90)
        self.spin_box.setMinimumHeight(30)

        # 设定初值
        init_val = max(1, min(initial_split_page, self._total_pages - 1))
        self.slider.setValue(init_val)
        self.spin_box.setValue(init_val)

        # 双向信号绑定
        self.slider.valueChanged.connect(self.spin_box.setValue)
        self.spin_box.valueChanged.connect(self.slider.setValue)
        self.slider.valueChanged.connect(self._on_split_point_changed)

        ctrl_layout.addWidget(QLabel("第 1 页"))
        ctrl_layout.addWidget(self.slider, 1)
        ctrl_layout.addWidget(QLabel(f"第 {self._total_pages - 1} 页"))
        ctrl_layout.addWidget(self.spin_box)

        split_layout.addLayout(ctrl_layout)
        layout.addWidget(split_box)

        # 4. 拆分结果两卡片预览与输出路径配置
        # 卡片 1：前半部分
        card1 = QFrame()
        card1.setStyleSheet("background: #F8FAFC; border: 1px solid #CBD5E1; border-radius: 8px;")
        card1_layout = QVBoxLayout(card1)
        card1_layout.setContentsMargins(12, 10, 12, 10)
        card1_layout.setSpacing(6)

        self.lbl_part1_summary = QLabel()
        self.lbl_part1_summary.setStyleSheet("font-weight: bold; color: #2563EB;")
        card1_layout.addWidget(self.lbl_part1_summary)

        path1_layout = QHBoxLayout()
        path1_layout.setSpacing(8)
        self.edit_path1 = QLineEdit()
        self.edit_path1.setMinimumHeight(28)
        self.edit_path1.textEdited.connect(self._on_path1_edited)
        btn_browse1 = QPushButton("浏览...")
        btn_browse1.setMinimumHeight(28)
        btn_browse1.clicked.connect(self._on_browse_path1)
        path1_layout.addWidget(self.edit_path1, 1)
        path1_layout.addWidget(btn_browse1)
        card1_layout.addLayout(path1_layout)
        layout.addWidget(card1)

        # 卡片 2：后半部分
        card2 = QFrame()
        card2.setStyleSheet("background: #F8FAFC; border: 1px solid #CBD5E1; border-radius: 8px;")
        card2_layout = QVBoxLayout(card2)
        card2_layout.setContentsMargins(12, 10, 12, 10)
        card2_layout.setSpacing(6)

        self.lbl_part2_summary = QLabel()
        self.lbl_part2_summary.setStyleSheet("font-weight: bold; color: #7C3AED;")
        card2_layout.addWidget(self.lbl_part2_summary)

        path2_layout = QHBoxLayout()
        path2_layout.setSpacing(8)
        self.edit_path2 = QLineEdit()
        self.edit_path2.setMinimumHeight(28)
        self.edit_path2.textEdited.connect(self._on_path2_edited)
        btn_browse2 = QPushButton("浏览...")
        btn_browse2.setMinimumHeight(28)
        btn_browse2.clicked.connect(self._on_browse_path2)
        path2_layout.addWidget(self.edit_path2, 1)
        path2_layout.addWidget(btn_browse2)
        card2_layout.addLayout(path2_layout)
        layout.addWidget(card2)

        # 5. 底部操作栏
        layout.addStretch(1)
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("color: #64748B; font-size: 12px;")
        btn_layout.addWidget(self.lbl_status, 1)

        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setMinimumWidth(80)
        self.btn_cancel.setMinimumHeight(32)
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_start = QPushButton("开始拆分")
        self.btn_start.setIcon(IconLibrary.get_icon("split", 16))
        self.btn_start.setStyleSheet("background-color: #7C3AED; color: white; font-weight: bold;")
        self.btn_start.setMinimumWidth(110)
        self.btn_start.setMinimumHeight(32)
        self.btn_start.clicked.connect(self._on_start_split)
        btn_layout.addWidget(self.btn_start)

        layout.addLayout(btn_layout)

        # 初始刷新卡片展示与默认文件名
        self._update_cards(init_val)

    def _on_split_point_changed(self, split_val: int) -> None:
        """
        截断页码变更回调函数，同步刷新卡片信息与默认生成文件路径。

        @param split_val 当前选中的分界页码
        """
        self._update_cards(split_val)

    def _update_cards(self, split_val: int) -> None:
        """
        更新前后两部分的概要信息与目标路径。

        @param split_val 截断页码（1-based）
        """
        part1_pages = split_val
        part2_pages = self._total_pages - split_val

        self.lbl_part1_summary.setText(
            f"第一部分：第 1 ~ {split_val} 页（共 {part1_pages} 页）"
        )
        self.lbl_part2_summary.setText(
            f"第二部分：第 {split_val + 1} ~ {self._total_pages} 页（共 {part2_pages} 页）"
        )

        base_dir = os.path.dirname(self._source_path) if self._source_path else os.getcwd()
        stem = os.path.splitext(os.path.basename(self._source_path))[0] if self._source_path else "文档"

        # 若用户未手动输入自定义路径，则自动根据页码区间动态推荐文件名
        if not self._custom_path_1:
            name1 = f"{stem}_第1部分(1-{split_val}页).pdf"
            self.edit_path1.setText(os.path.join(base_dir, name1))

        if not self._custom_path_2:
            name2 = f"{stem}_第2部分({split_val + 1}-{self._total_pages}页).pdf"
            self.edit_path2.setText(os.path.join(base_dir, name2))

    def _on_path1_edited(self, text: str) -> None:
        """
        第一部分路径输入框手动修改事件。

        @param text 用户输入的路径文本
        """
        self._custom_path_1 = True

    def _on_path2_edited(self, text: str) -> None:
        """
        第二部分路径输入框手动修改事件。

        @param text 用户输入的路径文本
        """
        self._custom_path_2 = True

    def _on_browse_path1(self) -> None:
        """
        弹出文件保存选择对话框，为第一部分选择导出路径。
        """
        current_path = self.edit_path1.text().strip()
        path, _ = QFileDialog.getSaveFileName(
            self,
            "选择第一部分保存路径",
            current_path,
            "PDF 文件 (*.pdf)"
        )
        if path:
            self.edit_path1.setText(path)
            self._custom_path_1 = True

    def _on_browse_path2(self) -> None:
        """
        弹出文件保存选择对话框，为第二部分选择导出路径。
        """
        current_path = self.edit_path2.text().strip()
        path, _ = QFileDialog.getSaveFileName(
            self,
            "选择第二部分保存路径",
            current_path,
            "PDF 文件 (*.pdf)"
        )
        if path:
            self.edit_path2.setText(path)
            self._custom_path_2 = True

    def _validate_paths(self, path1: str, path2: str) -> bool:
        """
        校验输出路径的合法性、互斥性与源文件安全性。

        @param path1 第一部分目标路径
        @param path2 第二部分目标路径
        @return 路径校验通过返回 True，否则返回 False
        """
        is_offscreen = os.environ.get("QT_QPA_PLATFORM") == "offscreen"

        if not path1 or not path2:
            if not is_offscreen:
                QMessageBox.warning(self, "提示", "请完整填写两个拆分文件的保存路径。")
            return False

        abs1 = os.path.abspath(path1)
        abs2 = os.path.abspath(path2)

        if abs1.lower() == abs2.lower():
            if not is_offscreen:
                QMessageBox.warning(self, "提示", "两个拆分文件的输出路径不能相同，请分别指定不同文件名。")
            return False

        if self._source_path:
            abs_src = os.path.abspath(self._source_path)
            if abs1.lower() == abs_src.lower() or abs2.lower() == abs_src.lower():
                if not is_offscreen:
                    QMessageBox.warning(self, "提示", "输出文件不能覆盖当前正在编辑的源文件，请指定新的文件名。")
                return False

        dir1 = os.path.dirname(abs1)
        dir2 = os.path.dirname(abs2)
        if not os.path.isdir(dir1) or not os.path.isdir(dir2):
            if not is_offscreen:
                QMessageBox.warning(self, "提示", "指定的保存目录不存在，请选择有效的保存路径。")
            return False

        return True

    def _on_start_split(self) -> None:
        """
        执行拆分逻辑并将当前文档保存为两份独立 PDF 文件。
        """
        split_point = self.slider.value()
        path1 = self.edit_path1.text().strip()
        path2 = self.edit_path2.text().strip()

        if not self._validate_paths(path1, path2):
            return

        self.btn_start.setEnabled(False)
        self.btn_cancel.setEnabled(False)
        self.lbl_status.setText("正在执行拆分并保存文档...")

        success = self._doc.split_document(split_point, path1, path2)

        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(True)

        is_offscreen = os.environ.get("QT_QPA_PLATFORM") == "offscreen"

        if success:
            self.lbl_status.setText("拆分已成功完成！")
            if not is_offscreen:
                reply = QMessageBox.information(
                    self,
                    "拆分成功",
                    f"PDF 已成功拆分为两部分：\n\n"
                    f"1. {os.path.basename(path1)} (第 1 ~ {split_point} 页)\n"
                    f"2. {os.path.basename(path2)} (第 {split_point + 1} ~ {self._total_pages} 页)\n\n"
                    f"输出目录：\n{os.path.dirname(os.path.abspath(path1))}\n\n"
                    f"是否立即在文件管理器中打开所在文件夹？",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )
                if reply == QMessageBox.Yes:
                    try:
                        os.startfile(os.path.dirname(os.path.abspath(path1)))
                    except Exception:
                        pass
            self.accept()
        else:
            self.lbl_status.setText("拆分失败。")
            if not is_offscreen:
                QMessageBox.critical(self, "错误", "拆分 PDF 时发生错误，请检查磁盘空间或写入权限。")
