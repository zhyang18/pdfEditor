"""
PDF 文档专业打印配置与实时预览对话框模块。
支持真实物理与虚拟打印机枚举、全量/当前页/自定义页码范围（如 6-8）精准选取、
即时输入语法与越界校验、双栏高保真纸张翻页预览以及向核心调度器输出规范打印参数。
"""

import os
from typing import Optional, List, Tuple
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QSpinBox, QComboBox, QRadioButton,
    QButtonGroup, QWidget, QFrame, QGroupBox, QCheckBox,
    QMessageBox, QScrollArea
)
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPixmap, QImage, QPainter, QColor, QPen
from PySide6.QtPrintSupport import QPrintDialog, QPrinter, QPrinterInfo
from core.pdf_document import PdfDocument
from core.pdf_printer import PdfPrinter, PrintConfiguration
from core.utils import ResourceUtils, PageRangeParser
from assets.icons import IconLibrary


class PrintDialog(QDialog):
    """
    PDF 现代化双栏专业打印对话框。
    左侧承载打印机选择、自定义页码范围输入与打印参数配置；右侧提供所见即所得的真实纸张渲染高保真翻页预览。
    """

    def __init__(
        self,
        doc: PdfDocument,
        current_page_index: int = 0,
        parent: Optional[QWidget] = None
    ) -> None:
        """
        初始化打印对话框实例并装配各功能部件与自适应样式。

        @param doc 目标待打印的核心 PDF 文档对象
        @param current_page_index 当前正在主视口中浏览的页面索引（从 0 开始）
        @param parent 包含该对话框的父窗口组件
        """
        super().__init__(parent)
        self._doc = doc
        self._total_pages = doc.page_count
        self._current_page_index = max(0, min(current_page_index, max(0, self._total_pages - 1)))
        self._selected_page_indices: List[int] = []
        self._preview_list_index: int = 0
        self._print_config: Optional[PrintConfiguration] = None

        self.setWindowTitle("打印 - PDF Editor")
        self.resize(820, 620)
        self.setMinimumSize(780, 580)

        self._init_ui()
        self._apply_theme(parent)
        self._load_printers()
        self._update_page_selection()

    def _apply_theme(self, parent: Optional[QWidget]) -> None:
        """
        应用父窗口主题样式表或加载默认浅色样式，确保对话框风格一致。

        @param parent 父窗口组件
        """
        if parent is not None and hasattr(parent, "styleSheet") and parent.styleSheet():
            self.setStyleSheet(parent.styleSheet())
        else:
            content = ResourceUtils.load_stylesheet("style_light.qss")
            if content:
                self.setStyleSheet(content)

    def _init_ui(self) -> None:
        """
        初始化对话框整体双栏网格布局与各控制面板。
        """
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(20, 18, 20, 18)
        main_layout.setSpacing(20)

        # 左栏：配置控制面板
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)
        left_panel.setFixedWidth(380)

        # 1. 顶部文档基本信息
        file_name = os.path.basename(self._doc.file_path) if self._doc.file_path else "未命名文档"
        lbl_info = QLabel(f"📄 当前文档：{file_name}（共 {self._total_pages} 页）")
        lbl_info.setProperty("info_banner", "true")
        left_layout.addWidget(lbl_info)

        # 2. 目标打印机配置组
        group_printer = QGroupBox("目标打印机")
        layout_printer = QVBoxLayout(group_printer)
        layout_printer.setSpacing(8)

        printer_row = QHBoxLayout()
        self.combo_printers = QComboBox()
        self.combo_printers.setMinimumHeight(32)
        printer_row.addWidget(self.combo_printers, 1)

        btn_system_dialog = QPushButton("系统首选项...")
        btn_system_dialog.setToolTip("打开 Windows 打印机驱动高级属性")
        btn_system_dialog.clicked.connect(self._on_open_system_printer_properties)
        printer_row.addWidget(btn_system_dialog)
        layout_printer.addLayout(printer_row)

        self.lbl_printer_status = QLabel("")
        self.lbl_printer_status.setStyleSheet("color: #64748B; font-size: 11px;")
        layout_printer.addWidget(self.lbl_printer_status)
        left_layout.addWidget(group_printer)

        # 3. 页面范围配置组（核心重点功能）
        group_range = QGroupBox("页面范围")
        layout_range = QVBoxLayout(group_range)
        layout_range.setSpacing(8)

        self.btn_group_range = QButtonGroup(self)
        self.radio_all = QRadioButton(f"全部页面 (第 1 - {self._total_pages} 页)")
        self.radio_all.setChecked(True)
        self.radio_current = QRadioButton(f"当前页面 (第 {self._current_page_index + 1} 页)")
        self.radio_custom = QRadioButton("自定义页码范围 (如: 6-8)")

        self.btn_group_range.addButton(self.radio_all)
        self.btn_group_range.addButton(self.radio_current)
        self.btn_group_range.addButton(self.radio_custom)

        layout_range.addWidget(self.radio_all)
        layout_range.addWidget(self.radio_current)
        layout_range.addWidget(self.radio_custom)

        self.txt_custom_range = QLineEdit()
        self.txt_custom_range.setPlaceholderText("请输入页码范围，例如: 6-8 或 1-3, 5")
        self.txt_custom_range.setMinimumHeight(30)
        self.txt_custom_range.setEnabled(False)
        self.txt_custom_range.textChanged.connect(self._on_range_text_changed)
        layout_range.addWidget(self.txt_custom_range)

        self.radio_all.toggled.connect(self._on_range_radio_toggled)
        self.radio_current.toggled.connect(self._on_range_radio_toggled)
        self.radio_custom.toggled.connect(self._on_range_radio_toggled)

        # 即时解析与状态校验提示区域（支持动态换行自适应与滚动视图显示）
        self.scroll_range_hint = QScrollArea()
        self.scroll_range_hint.setWidgetResizable(True)
        self.scroll_range_hint.setFrameShape(QFrame.NoFrame)
        self.scroll_range_hint.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_range_hint.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_range_hint.setMaximumHeight(80)
        self.scroll_range_hint.setMinimumHeight(28)
        self.scroll_range_hint.setStyleSheet("QScrollArea { background: transparent; border: none; margin-top: 4px; }")
        self.scroll_range_hint.viewport().setStyleSheet("background: transparent;")

        self.lbl_range_hint = QLabel("")
        self.lbl_range_hint.setWordWrap(True)
        self.lbl_range_hint.setStyleSheet("font-size: 11px; padding: 2px 0;")
        self.lbl_range_hint.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.scroll_range_hint.setWidget(self.lbl_range_hint)

        layout_range.addWidget(self.scroll_range_hint)
        left_layout.addWidget(group_range)

        # 4. 打印参数配置组
        group_options = QGroupBox("打印设置")
        layout_options = QVBoxLayout(group_options)
        layout_options.setSpacing(8)

        # 份数与逐份
        row_copies = QHBoxLayout()
        row_copies.addWidget(QLabel("打印份数："))
        self.spin_copies = QSpinBox()
        self.spin_copies.setRange(1, 999)
        self.spin_copies.setValue(1)
        self.spin_copies.setMinimumHeight(28)
        row_copies.addWidget(self.spin_copies)

        self.chk_collate = QCheckBox("逐份打印")
        self.chk_collate.setChecked(True)
        row_copies.addWidget(self.chk_collate)
        layout_options.addLayout(row_copies)

        # 方向与缩放
        row_orient_scale = QHBoxLayout()
        row_orient_scale.addWidget(QLabel("方向："))
        self.combo_orientation = QComboBox()
        self.combo_orientation.addItems(["自动匹配页面", "纵向 (Portrait)", "横向 (Landscape)"])
        row_orient_scale.addWidget(self.combo_orientation)

        row_orient_scale.addWidget(QLabel("缩放："))
        self.combo_scale = QComboBox()
        self.combo_scale.addItems(["适应可打印区域", "实际大小 (100%)"])
        row_orient_scale.addWidget(self.combo_scale)
        layout_options.addLayout(row_orient_scale)

        # 色彩模式
        row_color = QHBoxLayout()
        row_color.addWidget(QLabel("色彩："))
        self.combo_color = QComboBox()
        self.combo_color.addItems(["彩色 (Color)", "黑白/灰度 (Grayscale)"])
        row_color.addWidget(self.combo_color)
        layout_options.addLayout(row_color)

        # 关联打印参数变更即时联动刷新预览
        self.combo_orientation.currentIndexChanged.connect(self._on_print_settings_changed)
        self.combo_scale.currentIndexChanged.connect(self._on_print_settings_changed)
        self.combo_color.currentIndexChanged.connect(self._on_print_settings_changed)

        left_layout.addWidget(group_options)
        left_layout.addStretch()

        # 5. 底部动作按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setMinimumHeight(34)
        self.btn_cancel.setMinimumWidth(80)
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_print = QPushButton("开始打印")
        self.btn_print.setIcon(IconLibrary.get_icon("print", 18))
        self.btn_print.setProperty("primary", "true")
        self.btn_print.setMinimumHeight(34)
        self.btn_print.setMinimumWidth(110)
        self.btn_print.clicked.connect(self._on_start_print_clicked)
        btn_layout.addWidget(self.btn_print)

        left_layout.addLayout(btn_layout)
        main_layout.addWidget(left_panel)

        # 右栏：高保真所见即所得打印预览视口
        right_panel = QFrame()
        right_panel.setFrameShape(QFrame.StyledPanel)
        right_panel.setProperty("card_accent", "true")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(14, 14, 14, 14)
        right_layout.setSpacing(10)

        lbl_preview_title = QLabel("打印效果实时预览")
        lbl_preview_title.setProperty("card_title", "true")
        lbl_preview_title.setStyleSheet("font-size: 13px;")
        right_layout.addWidget(lbl_preview_title)

        # 预览位图展示区域
        self.lbl_preview_image = QLabel("正在加载预览...")
        self.lbl_preview_image.setAlignment(Qt.AlignCenter)
        self.lbl_preview_image.setProperty("card", "true")
        self.lbl_preview_image.setStyleSheet("padding: 4px;")
        right_layout.addWidget(self.lbl_preview_image, 1)

        # 底部翻页控制器
        preview_ctrl = QHBoxLayout()
        self.btn_prev_preview = QPushButton("< 上一页")
        self.btn_prev_preview.setMinimumHeight(28)
        self.btn_prev_preview.clicked.connect(self._on_prev_preview_clicked)
        preview_ctrl.addWidget(self.btn_prev_preview)

        self.lbl_preview_index = QLabel("第 0 / 0 页")
        self.lbl_preview_index.setAlignment(Qt.AlignCenter)
        self.lbl_preview_index.setStyleSheet("font-weight: 500; color: #475569; min-width: 130px;")
        preview_ctrl.addWidget(self.lbl_preview_index)

        self.btn_next_preview = QPushButton("下一页 >")
        self.btn_next_preview.setMinimumHeight(28)
        self.btn_next_preview.clicked.connect(self._on_next_preview_clicked)
        preview_ctrl.addWidget(self.btn_next_preview)

        right_layout.addLayout(preview_ctrl)
        main_layout.addWidget(right_panel, 1)

    def _load_printers(self) -> None:
        """
        加载当前操作系统安装的所有真实打印机，并自动选中默认打印机。
        """
        self.combo_printers.clear()
        printers = PdfPrinter.get_available_printers()
        default_printer = PdfPrinter.get_default_printer()

        if not printers:
            self.combo_printers.addItem("（未检测到可用打印机）")
            self.combo_printers.setEnabled(False)
            self.lbl_printer_status.setText("系统未安装任何物理或虚拟打印机，请先在 Windows 中添加打印机。")
            self.lbl_printer_status.setStyleSheet("color: #DC2626; font-size: 11px;")
            self.btn_print.setEnabled(False)
            return

        for p_name in printers:
            self.combo_printers.addItem(p_name)

        if default_printer and default_printer in printers:
            idx = printers.index(default_printer)
            self.combo_printers.setCurrentIndex(idx)
            self.lbl_printer_status.setText(f"默认打印机：{default_printer}")
        else:
            self.lbl_printer_status.setText(f"已选择打印机：{self.combo_printers.currentText()}")

        self.combo_printers.currentIndexChanged.connect(self._on_printer_changed)

    def _on_printer_changed(self) -> None:
        """
        响应打印机选择切换，更新状态提示。
        """
        printer_name = self.combo_printers.currentText()
        if printer_name and printer_name != "（未检测到可用打印机）":
            self.lbl_printer_status.setText(f"当前打印机：{printer_name}")

    def _on_open_system_printer_properties(self) -> None:
        """
        唤起 Windows 系统的原生 QPrintDialog 打印驱动属性配置界面。
        """
        printer_name = self.combo_printers.currentText()
        if not printer_name or printer_name == "（未检测到可用打印机）":
            QMessageBox.warning(self, "提示", "请先选择一个有效的打印机。")
            return

        printer_info = QPrinterInfo.printerInfo(printer_name)
        if printer_info.isNull():
            QMessageBox.warning(self, "提示", f"无法获取打印机 '{printer_name}' 的系统配置。")
            return

        printer = QPrinter(printer_info)
        sys_dialog = QPrintDialog(printer, self)
        sys_dialog.setWindowTitle(f"打印机属性 - {printer_name}")
        sys_dialog.exec()

    def _on_range_radio_toggled(self) -> None:
        """
        响应页面范围单选框切换，联动输入框的使能状态并更新页码解析。
        """
        is_custom = self.radio_custom.isChecked()
        self.txt_custom_range.setEnabled(is_custom)
        if is_custom:
            self.txt_custom_range.setFocus()
        self._update_page_selection()

    def _on_range_text_changed(self) -> None:
        """
        响应自定义页码文本输入变化，触发即时语法校验与视图刷新。
        """
        if self.radio_custom.isChecked():
            self._update_page_selection()

    def _validate_custom_range(self, text: str) -> Tuple[bool, List[int], str]:
        """
        对用户输入的自定义页码范围文本进行严谨的词法解析与边界校验。

        @param text 用户输入的页码范围字符串（例如 '6-8' 或 '1-3, 5'）
        @return 包含 (是否完全合法, 解析后的 0-based 页面索引列表, 状态提示文本) 的元组
        """
        cleaned = text.strip()
        if not cleaned:
            return False, [], "请输入待打印的页码范围，例如：6-8"

        # 检查是否包含非法字符
        allowed_chars = set("0123456789,- ")
        if any(c not in allowed_chars for c in cleaned):
            return False, [], "输入包含非法字符，仅支持数字、减号 '-' 与逗号 ','"

        tokens = [t.strip() for t in cleaned.split(",") if t.strip()]
        if not tokens:
            return False, [], "请输入有效的页码范围"

        indices_set = set()
        for tok in tokens:
            if "-" in tok:
                parts = tok.split("-")
                if len(parts) != 2 or not parts[0].strip().isdigit() or not parts[1].strip().isdigit():
                    return False, [], f"范围表达式 '{tok}' 语法格式无效，正确格式如：6-8"
                start = int(parts[0].strip())
                end = int(parts[1].strip())
                if start < 1 or end < 1:
                    return False, [], "页码必须从 1 开始"
                if start > self._total_pages or end > self._total_pages:
                    return False, [], f"页码范围 '{tok}' 超出文档最大总页数 ({self._total_pages} 页)"
                low = min(start, end)
                high = max(start, end)
                for p in range(low, high + 1):
                    indices_set.add(p - 1)
            elif tok.isdigit():
                p = int(tok)
                if p < 1:
                    return False, [], "页码必须从 1 开始"
                if p > self._total_pages:
                    return False, [], f"页码 {p} 超出文档最大总页数 ({self._total_pages} 页)"
                indices_set.add(p - 1)
            else:
                return False, [], f"无效的页码元素：'{tok}'"

        indices = sorted(list(indices_set))
        if not indices:
            return False, [], "未能解析到任何有效页面"

        # 构造完整、易读的页码清单（完整展示，不作人为截断）
        display_pages = [str(i + 1) for i in indices]
        pages_str = ", ".join(display_pages)

        return True, indices, f"✓ 将打印第 {pages_str} 页（共 {len(indices)} 页）"

    def _set_range_hint(self, text: str, style_sheet: str) -> None:
        """
        设置页面范围提示文本与样式，并根据换行行数动态自适应调整滚动视口高度。

        @param text 待显示的提示信息文本
        @param style_sheet 提示标签的样式表字符串
        """
        self.lbl_range_hint.setText(text)
        self.lbl_range_hint.setStyleSheet(f"{style_sheet} line-height: 1.4; padding: 2px 0;")
        self.lbl_range_hint.adjustSize()
        # 页面范围卡片有效宽度约为 340 像素
        hint_height = self.lbl_range_hint.heightForWidth(340)
        # 单行给予 28px 充裕高度，多行可扩展至 80px 并支持垂直滚动，彻底避免文字裁切或被上方输入框遮挡
        actual_height = max(28, min(80, hint_height + 8))
        self.scroll_range_hint.setFixedHeight(actual_height)

    def _update_page_selection(self) -> None:
        """
        根据当前选中的单选状态解析待打印的页码序列，并动态刷新提示与预览。
        """
        if self._total_pages <= 0:
            self._selected_page_indices = []
            self._set_range_hint("当前文档没有任何页面可打印。", "color: #DC2626; font-size: 11px;")
            self.btn_print.setEnabled(False)
            self._update_preview()
            return

        if self.radio_all.isChecked():
            self._selected_page_indices = list(range(self._total_pages))
            self._set_range_hint(f"✓ 将打印全部页面（共 {self._total_pages} 页）", "color: #16A34A; font-size: 11px; font-weight: 500;")
            self.btn_print.setEnabled(self.combo_printers.isEnabled())
        elif self.radio_current.isChecked():
            self._selected_page_indices = [self._current_page_index]
            self._set_range_hint(f"✓ 将打印当前第 {self._current_page_index + 1} 页（共 1 页）", "color: #16A34A; font-size: 11px; font-weight: 500;")
            self.btn_print.setEnabled(self.combo_printers.isEnabled())
        else:
            # 自定义范围（核心重点）
            is_valid, indices, msg = self._validate_custom_range(self.txt_custom_range.text())
            if is_valid:
                self._selected_page_indices = indices
                self._set_range_hint(msg, "color: #16A34A; font-size: 11px; font-weight: 500;")
                self.btn_print.setEnabled(self.combo_printers.isEnabled())
            else:
                self._selected_page_indices = []
                self._set_range_hint(f"⚠ {msg}", "color: #DC2626; font-size: 11px;")
                self.btn_print.setEnabled(False)

        self._preview_list_index = 0
        self._update_preview()

    def _on_print_settings_changed(self) -> None:
        """
        响应打印设置（方向、缩放、色彩模式等）变更，实时重新渲染右侧纸张高保真预览。
        """
        self._update_preview()

    def _render_virtual_paper_preview(
        self,
        page_image: QImage,
        orientation: str,
        scale_mode: str,
        color_mode: str,
        target_w: int,
        target_h: int
    ) -> QPixmap:
        """
        根据方向、缩放模式与色彩配置，将页面渲染至虚拟打印纸张上，生成所见即所得的预览位图。

        @param page_image 原始页面渲染位图
        @param orientation 页面方向 ("auto", "portrait", "landscape")
        @param scale_mode 缩放模式 ("fit", "actual")
        @param color_mode 色彩模式 ("color", "grayscale")
        @param target_w 目标可用视口宽度（像素）
        @param target_h 目标可用视口高度（像素）
        @return 包含虚拟纸张边框与排版的 QPixmap 预览图像
        """
        orig_w = page_image.width()
        orig_h = page_image.height()
        is_landscape_content = orig_w > orig_h

        # 1. 确定纸张物理方向
        if orientation == "landscape":
            paper_landscape = True
        elif orientation == "portrait":
            paper_landscape = False
        else:  # auto 自动匹配页面
            paper_landscape = is_landscape_content

        # 2. 计算纸张宽高比（保持标准页面长宽比）
        ratio = max(orig_w, orig_h) / float(max(1, min(orig_w, orig_h)))
        paper_ratio = ratio if paper_landscape else (1.0 / ratio)

        # 3. 在视口范围内拟合最大可用纸张大小
        if target_w / float(target_h) > paper_ratio:
            paper_h = target_h
            paper_w = int(paper_h * paper_ratio)
        else:
            paper_w = target_w
            paper_h = int(paper_w / paper_ratio)

        paper_w = max(40, paper_w)
        paper_h = max(40, paper_h)

        # 4. 创建白色背景的高保真虚拟打印纸
        paper = QImage(paper_w, paper_h, QImage.Format_ARGB32_Premultiplied)
        paper.fill(QColor(255, 255, 255))

        painter = QPainter(paper)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        # 5. 处理色彩模式（黑白/灰度 vs 彩色）
        draw_img = page_image
        if color_mode == "grayscale":
            draw_img = draw_img.convertToFormat(QImage.Format_Grayscale8)

        # 6. 计算缩放比例与居中绘制区域
        if scale_mode == "actual":
            # 实际大小模式：100% 原始比例居中呈现
            scale = min(1.0, min(paper_w / float(orig_w), paper_h / float(orig_h)))
        else:
            # 适应模式：等比例贴合纸张最大可用范围并居中
            scale = min(paper_w / float(orig_w), paper_h / float(orig_h))

        dest_w = orig_w * scale
        dest_h = orig_h * scale
        dest_x = (paper_w - dest_w) / 2.0
        dest_y = (paper_h - dest_h) / 2.0

        painter.drawImage(QRectF(dest_x, dest_y, dest_w, dest_h), draw_img)

        # 7. 绘制真实纸张的边缘描边线条
        painter.setPen(QPen(QColor(203, 213, 225), 1.5))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(QRectF(0.5, 0.5, paper_w - 1, paper_h - 1))
        painter.end()

        return QPixmap.fromImage(paper)

    def _update_preview(self) -> None:
        """
        高保真渲染并呈现右侧当前正在预览的页面纸张图像。
        根据用户选择的横向/纵向方向、黑白/彩色色彩与缩放模式实时更新所见即所得打印效果。
        """
        if not self._selected_page_indices:
            self.lbl_preview_image.setPixmap(QPixmap())
            self.lbl_preview_image.setText("暂无有效页面可供预览")
            self.lbl_preview_index.setText("第 0 / 0 页")
            self.btn_prev_preview.setEnabled(False)
            self.btn_next_preview.setEnabled(False)
            return

        total_selected = len(self._selected_page_indices)
        self._preview_list_index = max(0, min(self._preview_list_index, total_selected - 1))
        actual_page_idx = self._selected_page_indices[self._preview_list_index]

        self.btn_prev_preview.setEnabled(self._preview_list_index > 0)
        self.btn_next_preview.setEnabled(self._preview_list_index < total_selected - 1)
        self.lbl_preview_index.setText(f"第 {self._preview_list_index + 1} / {total_selected} 页 (原第 {actual_page_idx + 1} 页)")

        # 获取当前的打印参数配置用于实时预览模拟
        orient_idx = self.combo_orientation.currentIndex()
        orient_map = {0: "auto", 1: "portrait", 2: "landscape"}
        orientation = orient_map.get(orient_idx, "auto")

        scale_idx = self.combo_scale.currentIndex()
        scale_map = {0: "fit", 1: "actual"}
        scale_mode = scale_map.get(scale_idx, "fit")

        color_idx = self.combo_color.currentIndex()
        color_mode = "grayscale" if color_idx == 1 else "color"

        # 使用 120 DPI 渲染适于对话框视口快速展示的高保真图像
        img = PdfPrinter.render_printable_page(self._doc, actual_page_idx, dpi=120)
        if img is not None and not img.isNull():
            target_size = self.lbl_preview_image.size()
            max_w = max(180, target_size.width() - 20)
            max_h = max(240, target_size.height() - 20)
            pix = self._render_virtual_paper_preview(
                page_image=img,
                orientation=orientation,
                scale_mode=scale_mode,
                color_mode=color_mode,
                target_w=max_w,
                target_h=max_h
            )
            self.lbl_preview_image.setText("")
            self.lbl_preview_image.setPixmap(pix)
        else:
            self.lbl_preview_image.setPixmap(QPixmap())
            self.lbl_preview_image.setText(f"第 {actual_page_idx + 1} 页预览加载失败")

    def resizeEvent(self, event) -> None:
        """
        响应对话框窗口尺寸变化，自适应重绘右侧页面预览位图。

        @param event 窗口尺寸调整事件对象
        """
        super().resizeEvent(event)
        self._update_preview()

    def _on_prev_preview_clicked(self) -> None:
        """
        向前切换预览上一页。
        """
        if self._preview_list_index > 0:
            self._preview_list_index -= 1
            self._update_preview()

    def _on_next_preview_clicked(self) -> None:
        """
        向后切换预览下一页。
        """
        if self._preview_list_index < len(self._selected_page_indices) - 1:
            self._preview_list_index += 1
            self._update_preview()

    def _on_start_print_clicked(self) -> None:
        """
        响应【开始打印】按钮点击，组装打印配置数据并关闭对话框进入执行调度。
        """
        printer_name = self.combo_printers.currentText()
        if not printer_name or printer_name == "（未检测到可用打印机）":
            QMessageBox.critical(self, "错误", "未检测到可用的系统打印机，无法开始打印。")
            return

        if not self._selected_page_indices:
            QMessageBox.warning(self, "提示", "请指定至少一页有效的待打印页码。")
            return

        # 映射方向与缩放模式
        orient_idx = self.combo_orientation.currentIndex()
        orient_map = {0: "auto", 1: "portrait", 2: "landscape"}
        orientation = orient_map.get(orient_idx, "auto")

        scale_idx = self.combo_scale.currentIndex()
        scale_map = {0: "fit", 1: "actual"}
        scale_mode = scale_map.get(scale_idx, "fit")

        color_idx = self.combo_color.currentIndex()
        color_mode = "grayscale" if color_idx == 1 else "color"

        self._print_config = PrintConfiguration(
            printer_name=printer_name,
            page_indices=list(self._selected_page_indices),
            copies=self.spin_copies.value(),
            collate=self.chk_collate.isChecked(),
            color_mode=color_mode,
            orientation=orientation,
            scale_mode=scale_mode
        )
        self.accept()

    def get_print_configuration(self) -> Optional[PrintConfiguration]:
        """
        获取用户完成配置并确认提交的打印配置实体对象。

        @return 若用户点击打印返回 PrintConfiguration 实例，若取消则返回 None
        """
        return self._print_config
