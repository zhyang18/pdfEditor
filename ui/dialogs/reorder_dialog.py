"""
批量页码重新编排输入对话框模块。
支持用户一次性输入完整的页码重排序列文本，并执行语法校验与顺序映射。
采用自适应弹性尺寸，彻底避免高分屏下的窗口裁切与控件遮挡。
"""

import os
from typing import Optional, List
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QMessageBox, QWidget
)
from core.utils import ResourceUtils
from assets.icons import IconLibrary


class ReorderDialog(QDialog):
    """
    批量页码重排输入对话框。
    接收形如 '3, 1, 2, 4, 5' 的页码序列，校验是否构成有效全排列。
    """

    def __init__(self, page_count: int, parent: Optional[QWidget] = None) -> None:
        """
        初始化批量重排对话框。

        @param page_count 当前文档的总页数
        @param parent 父组件
        """
        super().__init__(parent)
        self._page_count = page_count
        self._new_order: List[int] = []

        self.setWindowTitle("批量调整页码顺序 - PDF Editor")
        self.resize(480, 250)
        self.setMinimumSize(420, 220)

        self._init_ui()
        self._apply_theme(parent)

    def _apply_theme(self, parent: Optional[QWidget]) -> None:
        """
        应用父窗口或本地主题样式表，确保控件适配当前亮色/暗色风格。

        @param parent 父窗口组件
        """
        if parent is not None and hasattr(parent, "styleSheet") and parent.styleSheet():
            self.setStyleSheet(parent.styleSheet())
        else:
            style_path = ResourceUtils.get_resource_path(os.path.join("assets", "style_light.qss"))
            if os.path.isfile(style_path):
                with open(style_path, "r", encoding="utf-8") as f:
                    self.setStyleSheet(f.read())

    @property
    def new_order(self) -> List[int]:
        """
        获取解析后的 0-based 页面新顺序索引列表。

        @return 重新编排的页面索引列表
        """
        return self._new_order

    def _init_ui(self) -> None:
        """
        初始化界面控件与布局。
        """
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        desc_label = QLabel(f"当前文档共有 {self._page_count} 页。\n请输入新的页码顺序，用逗号分隔（例如：3, 1, 2, 4）：")
        desc_label.setStyleSheet("color: #334155; font-size: 13px; line-height: 1.4;")
        layout.addWidget(desc_label)

        # 默认填入当前页码序列 "1, 2, 3..."
        default_seq = ", ".join(str(i + 1) for i in range(self._page_count))
        self.input_edit = QLineEdit(default_seq)
        self.input_edit.setMinimumHeight(34)
        layout.addWidget(self.input_edit)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 8, 0, 0)
        btn_layout.addStretch()

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setMinimumHeight(34)
        self.cancel_btn.setMinimumWidth(80)
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        self.ok_btn = QPushButton("应用新顺序")
        self.ok_btn.setProperty("primary", "true")
        self.ok_btn.setIcon(IconLibrary.get_icon("move_up", 16))
        self.ok_btn.setMinimumHeight(34)
        self.ok_btn.setMinimumWidth(110)
        self.ok_btn.clicked.connect(self._validate_and_accept)
        btn_layout.addWidget(self.ok_btn)

        layout.addLayout(btn_layout)

    def _validate_and_accept(self) -> None:
        """
        校验用户输入的序列是否包含 1 到 page_count 的每个整数且无重复遗漏。
        """
        text = self.input_edit.text().strip()
        if not text:
            QMessageBox.warning(self, "提示", "请输入有效的页码序列！")
            return

        tokens = text.replace("，", ",").split(",")
        parsed_pages: List[int] = []

        for token in tokens:
            t = token.strip()
            if not t:
                continue
            if not t.isdigit():
                QMessageBox.warning(self, "格式错误", f"'{t}' 不是有效的页码数字！")
                return
            p = int(t)
            if not (1 <= p <= self._page_count):
                QMessageBox.warning(self, "页码越界", f"页码 {p} 超出当前有效范围 (1 ~ {self._page_count})！")
                return
            parsed_pages.append(p)

        if len(parsed_pages) != self._page_count or set(parsed_pages) != set(range(1, self._page_count + 1)):
            QMessageBox.warning(self, "校验未通过", f"输入的页码序列必须完整包含从 1 到 {self._page_count} 的所有页码，且不能有重复或遗漏！")
            return

        # 转换为 0-based 索引列表
        self._new_order = [p - 1 for p in parsed_pages]
        self.accept()
