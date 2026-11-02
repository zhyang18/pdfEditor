"""
文本水印添加配置对话框模块。
支持设置水印文本内容、旋转角度、字号大小、透明度以及作用的目标页面范围。
自适应高分屏 DPI 与窗口弹性布局，彻底杜绝界面遮挡与按钮裁切。
"""

import os
from typing import Optional, List
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QSpinBox, QSlider, QRadioButton,
    QButtonGroup, QWidget
)
from PySide6.QtCore import Qt
from core.utils import PageRangeParser, ResourceUtils
from assets.icons import IconLibrary


class WatermarkDialog(QDialog):
    """
    水印配置参数输入对话框。
    获取用户设置的水印内容与样式，并生成参数供文档引擎调用。
    采用弹性尺寸与自适应布局，确保任何屏幕缩放下完整显示。
    """

    def __init__(self, max_pages: int, parent: Optional[QWidget] = None) -> None:
        """
        初始化水印配置对话框。

        @param max_pages 当前文档的总页数
        @param parent 父窗口组件
        """
        super().__init__(parent)
        self._max_pages = max_pages
        self.setWindowTitle("添加文本水印 - PDF Editor")
        self.resize(440, 500)
        self.setMinimumSize(400, 460)

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

    def _init_ui(self) -> None:
        """
        初始化控件布局。
        采用自适应垂直间距与充裕的边距，确保控件与底部按钮呼吸感充沛。
        """
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # 1. 水印文字输入
        layout.addWidget(QLabel("水印文字内容："))
        self.text_input = QLineEdit("机密文件 请勿外传")
        self.text_input.setMinimumHeight(32)
        layout.addWidget(self.text_input)

        # 2. 字号与倾角
        param_layout = QHBoxLayout()
        param_layout.addWidget(QLabel("字号："))
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(12, 120)
        self.font_size_spin.setValue(40)
        self.font_size_spin.setMinimumHeight(30)
        param_layout.addWidget(self.font_size_spin)

        param_layout.addSpacing(20)
        param_layout.addWidget(QLabel("倾斜角度："))
        self.angle_spin = QSpinBox()
        self.angle_spin.setRange(-90, 90)
        self.angle_spin.setValue(45)
        self.angle_spin.setMinimumHeight(30)
        param_layout.addWidget(self.angle_spin)
        layout.addLayout(param_layout)

        # 3. 不透明度滑块
        layout.addWidget(QLabel("不透明度 (透明度级别)："))
        opacity_layout = QHBoxLayout()
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(5, 100)
        self.opacity_slider.setValue(25)

        self.opacity_label = QLabel("25%")
        self.opacity_label.setFixedWidth(40)
        self.opacity_slider.valueChanged.connect(
            lambda v: self.opacity_label.setText(f"{v}%")
        )

        opacity_layout.addWidget(self.opacity_slider)
        opacity_layout.addWidget(self.opacity_label)
        layout.addLayout(opacity_layout)

        # 4. 应用页码范围
        layout.addWidget(QLabel("应用页面范围："))
        self.btn_group = QButtonGroup(self)
        self.all_pages_radio = QRadioButton("所有页面")
        self.all_pages_radio.setChecked(True)
        self.custom_pages_radio = QRadioButton("自定义页码 (如 1-3, 5)：")

        self.btn_group.addButton(self.all_pages_radio)
        self.btn_group.addButton(self.custom_pages_radio)

        layout.addWidget(self.all_pages_radio)
        layout.addWidget(self.custom_pages_radio)

        self.range_input = QLineEdit()
        self.range_input.setPlaceholderText("请输入页码范围，例如：1-3, 5")
        self.range_input.setEnabled(False)
        self.range_input.setMinimumHeight(30)
        self.custom_pages_radio.toggled.connect(self.range_input.setEnabled)
        layout.addWidget(self.range_input)

        layout.addStretch()

        # 5. 底部按钮操作栏（拥有充裕的上下内边距，杜绝边缘遮挡）
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 8, 0, 0)
        btn_layout.addStretch()

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setMinimumHeight(34)
        self.cancel_btn.setMinimumWidth(80)
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        self.ok_btn = QPushButton("确定添加")
        self.ok_btn.setIcon(IconLibrary.get_icon("watermark", 16))
        self.ok_btn.setProperty("primary", "true")
        self.ok_btn.setMinimumHeight(34)
        self.ok_btn.setMinimumWidth(100)
        self.ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.ok_btn)

        layout.addLayout(btn_layout)

    def get_watermark_params(self) -> tuple[str, float, float, float, Optional[List[int]]]:
        """
        获取用户配置的水印参数元组。

        @return 包含 (text, font_size, opacity, angle, page_indices) 的元组
        """
        text = self.text_input.text().strip()
        font_size = float(self.font_size_spin.value())
        opacity = float(self.opacity_slider.value()) / 100.0
        angle = float(self.angle_spin.value())

        if self.all_pages_radio.isChecked():
            pages = None
        else:
            pages = PageRangeParser.parse_page_ranges(self.range_input.text(), self._max_pages)

        return (text, font_size, opacity, angle, pages)
