"""
批量页码重新编排与定向移动对话框模块。
支持自然语言与快捷口令解析（如“将1-5页插入20页后面”）、可视化表单定向移动与经典全序列自定义排序。
采用自适应弹性尺寸，彻底避免高分屏下的窗口裁切与控件遮挡。
"""

import os
from typing import Optional, List
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QMessageBox, QWidget, QTabWidget,
    QComboBox, QSpinBox, QGroupBox, QFrame
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from core.utils import ResourceUtils, PageRangeParser, PageReorderHelper
from assets.icons import IconLibrary


class ReorderDialog(QDialog):
    """
    页面重排与定向移动对话框。
    提供自然语言口令、表单定向插入以及经典自定义排序（支持逗号全排列与范围简写）多种调序模式。
    """

    def __init__(
        self,
        page_count: int,
        initial_source_page: Optional[int] = None,
        parent: Optional[QWidget] = None
    ) -> None:
        """
        初始化页面重排与移动对话框。

        @param page_count 当前文档的总页数
        @param initial_source_page 初始选中的源页面 0-based 索引（可选）
        @param parent 包含该对话框的父组件
        """
        super().__init__(parent)
        self._page_count = page_count
        self._initial_source_page = initial_source_page
        self._new_order: List[int] = []
        self._direct_computed_order: Optional[List[int]] = None
        self._operation_description: str = ""
        self._is_syncing: bool = False

        self.setWindowTitle("页面排序与定向移动 - PDF Editor")
        self.resize(580, 540)
        self.setMinimumSize(520, 480)

        self._init_ui()
        self._apply_theme(parent)
        self._setup_initial_values()

    def _apply_theme(self, parent: Optional[QWidget]) -> None:
        """
        应用父窗口或本地主题样式表，确保控件适配当前亮色/暗色风格。

        @param parent 父窗口组件
        """
        if parent is not None and hasattr(parent, "styleSheet") and parent.styleSheet():
            self.setStyleSheet(parent.styleSheet())
        else:
            content = ResourceUtils.load_stylesheet("style_light.qss")
            if content:
                self.setStyleSheet(content)

    @property
    def new_order(self) -> List[int]:
        """
        获取重新编排后的 0-based 页面索引列表。

        @return 重新编排的页面索引列表
        """
        return self._new_order

    @property
    def operation_description(self) -> str:
        """
        获取当前调序操作的人类可读描述，用于撤销栈提示。

        @return 调序操作说明文本
        """
        return self._operation_description

    def _init_ui(self) -> None:
        """
        初始化界面控件与多标签页布局。
        """
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        # 1. 顶部智能口令快速输入卡片
        cmd_group = QGroupBox("快捷口令输入 (支持自然语言)")
        cmd_layout = QVBoxLayout(cmd_group)
        cmd_layout.setContentsMargins(12, 10, 12, 12)
        cmd_layout.setSpacing(6)

        self.cmd_input = QLineEdit()
        self.cmd_input.setPlaceholderText("直接输入口令，例如：将1-5页插入20页后面、把3页移到最前、3, 1, 2, 4")
        self.cmd_input.setMinimumHeight(34)
        self.cmd_input.textChanged.connect(self._on_smart_command_text_changed)
        self.cmd_input.returnPressed.connect(self._on_cmd_input_return_pressed)
        cmd_layout.addWidget(self.cmd_input)

        self.cmd_tip_label = QLabel("💡 提示：输入口令后下方表单与预览将自动实时联动解析；亦可在此直接输入自定义序列。")
        self.cmd_tip_label.setProperty("secondary", "true")
        self.cmd_tip_label.setStyleSheet("font-size: 11px;")
        cmd_layout.addWidget(self.cmd_tip_label)

        layout.addWidget(cmd_group)

        # 2. 模式切换标签页
        self.tab_widget = QTabWidget()

        # 选项卡一：定向移动与插入模式
        self.tab_direct = QWidget()
        self._init_tab_direct()
        self.tab_widget.addTab(self.tab_direct, "页面定向移动/插入 (推荐)")

        # 选项卡二：经典自定义排序模式
        self.tab_custom = QWidget()
        self._init_tab_custom()
        self.tab_widget.addTab(self.tab_custom, "自定义排序 (全页码顺序编排)")

        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tab_widget)

        # 3. 实时变动与预览卡片
        preview_group = QGroupBox("实时变动与新顺序预览")
        preview_layout = QVBoxLayout(preview_group)
        preview_layout.setContentsMargins(12, 8, 12, 10)
        preview_layout.setSpacing(6)

        self.lbl_action_desc = QLabel("动作说明：就绪")
        self.lbl_action_desc.setStyleSheet("font-weight: 600; font-size: 12px;")
        preview_layout.addWidget(self.lbl_action_desc)

        self.lbl_change_summary = QLabel("")
        self.lbl_change_summary.setProperty("accent", "true")
        self.lbl_change_summary.setStyleSheet("font-size: 12px; font-weight: 500;")
        preview_layout.addWidget(self.lbl_change_summary)

        self.lbl_seq_preview = QLabel("新顺序：")
        self.lbl_seq_preview.setWordWrap(True)
        self.lbl_seq_preview.setProperty("secondary", "true")
        self.lbl_seq_preview.setStyleSheet("font-size: 11px;")
        preview_layout.addWidget(self.lbl_seq_preview)

        self.lbl_error = QLabel("")
        self.lbl_error.setProperty("danger", "true")
        self.lbl_error.setStyleSheet("font-weight: bold; font-size: 12px;")
        self.lbl_error.setVisible(False)
        preview_layout.addWidget(self.lbl_error)

        layout.addWidget(preview_group)

        # 4. 底部操作按钮
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 4, 0, 0)
        btn_layout.addStretch()

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setAutoDefault(False)
        self.cancel_btn.setDefault(False)
        self.cancel_btn.setMinimumHeight(34)
        self.cancel_btn.setMinimumWidth(80)
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        self.ok_btn = QPushButton("应用新顺序")
        self.ok_btn.setAutoDefault(False)
        self.ok_btn.setDefault(False)
        self.ok_btn.setProperty("primary", "true")
        self.ok_btn.setIcon(IconLibrary.get_icon("reorder", 16))
        self.ok_btn.setMinimumHeight(34)
        self.ok_btn.setMinimumWidth(110)
        self.ok_btn.clicked.connect(self._on_apply_clicked)
        btn_layout.addWidget(self.ok_btn)

        layout.addLayout(btn_layout)

        # 确保所有按钮均不自动响应回车触发，防止按回车时误触按钮导致输入内容被重置
        for btn in self.findChildren(QPushButton):
            btn.setAutoDefault(False)
            btn.setDefault(False)

    def _init_tab_direct(self) -> None:
        """
        初始化定向移动与插入模式的表单界面。
        """
        layout = QVBoxLayout(self.tab_direct)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # 第一行：待移动页面范围
        row1 = QHBoxLayout()
        lbl_source = QLabel("待移动页面：")
        lbl_source.setMinimumWidth(80)
        row1.addWidget(lbl_source)

        self.source_edit = QLineEdit()
        self.source_edit.setPlaceholderText("例如: 1-5 或 1, 3, 5")
        self.source_edit.setMinimumHeight(32)
        self.source_edit.textChanged.connect(self._on_form_changed)
        self.source_edit.returnPressed.connect(self._on_source_edit_return_pressed)
        row1.addWidget(self.source_edit, 1)

        self.btn_current_page = QPushButton("选中当前页")
        self.btn_current_page.setAutoDefault(False)
        self.btn_current_page.setDefault(False)
        self.btn_current_page.setToolTip("将源页面快速设为缩略图正在选中的页面")
        self.btn_current_page.clicked.connect(self._on_current_page_clicked)
        row1.addWidget(self.btn_current_page)

        layout.addLayout(row1)

        # 第二行：插入位置关系与目标页码
        row2 = QHBoxLayout()
        lbl_target = QLabel("目标位置：")
        lbl_target.setMinimumWidth(80)
        row2.addWidget(lbl_target)

        self.action_combo = QComboBox()
        self.action_combo.addItem("插入到目标页之后 (推荐)", "after")
        self.action_combo.addItem("插入到目标页之前", "before")
        self.action_combo.addItem("移至文档最前面 (第 1 页)", "start")
        self.action_combo.addItem("移至文档最后面 (末尾页)", "end")
        self.action_combo.setMinimumHeight(32)
        self.action_combo.currentIndexChanged.connect(self._on_action_combo_changed)
        row2.addWidget(self.action_combo, 1)

        self.lbl_target_num = QLabel("目标页码：第")
        row2.addWidget(self.lbl_target_num)

        self.target_spin = QSpinBox()
        self.target_spin.setRange(1, self._page_count)
        self.target_spin.setValue(1)
        self.target_spin.setMinimumHeight(32)
        self.target_spin.setMinimumWidth(65)
        self.target_spin.valueChanged.connect(self._on_form_changed)
        row2.addWidget(self.target_spin)

        self.lbl_target_suffix = QLabel("页")
        row2.addWidget(self.lbl_target_suffix)

        layout.addLayout(row2)

        info_label = QLabel(f"当前文档总页数：{self._page_count} 页。支持跨页大范围精准移动。")
        info_label.setProperty("secondary", "true")
        info_label.setStyleSheet("font-size: 11px;")
        layout.addWidget(info_label)
        layout.addStretch()

    def _init_tab_custom(self) -> None:
        """
        初始化经典自定义排序模式界面。
        支持逗号序列、空格序列及范围语法缩写，并提供恢复初始、整篇倒排、同步定向移动结果及清空等快捷排序操作。
        """
        layout = QVBoxLayout(self.tab_custom)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        desc = QLabel(
            f"当前文档共有 {self._page_count} 页。\n"
            "请输入新的页码顺序，用逗号或空格分隔（例如：3, 1, 2, 4），支持范围简写（例如：6-20, 1-5）："
        )
        desc.setStyleSheet("font-size: 12px; line-height: 1.4;")
        layout.addWidget(desc)

        # 快捷排序辅助按钮栏
        tools_layout = QHBoxLayout()
        tools_layout.setSpacing(6)

        self.btn_reset_seq = QPushButton("恢复初始顺序")
        self.btn_reset_seq.setAutoDefault(False)
        self.btn_reset_seq.setDefault(False)
        self.btn_reset_seq.setToolTip(f"恢复为自然升序 1, 2, 3... {self._page_count}")
        self.btn_reset_seq.clicked.connect(self._on_reset_sequence_clicked)
        tools_layout.addWidget(self.btn_reset_seq)

        self.btn_reverse_seq = QPushButton("整篇逆序倒排")
        self.btn_reverse_seq.setAutoDefault(False)
        self.btn_reverse_seq.setDefault(False)
        self.btn_reverse_seq.setToolTip(f"整篇页面倒序排列 {self._page_count}... 1")
        self.btn_reverse_seq.clicked.connect(self._on_reverse_sequence_clicked)
        tools_layout.addWidget(self.btn_reverse_seq)

        self.btn_sync_from_direct = QPushButton("同步定向移动结果")
        self.btn_sync_from_direct.setAutoDefault(False)
        self.btn_sync_from_direct.setDefault(False)
        self.btn_sync_from_direct.setToolTip("将定向移动选项卡计算的当前新顺序快速填入此处进行二次自定义编辑")
        self.btn_sync_from_direct.clicked.connect(self._on_sync_from_direct_clicked)
        tools_layout.addWidget(self.btn_sync_from_direct)

        self.btn_clear_seq = QPushButton("清空")
        self.btn_clear_seq.setAutoDefault(False)
        self.btn_clear_seq.setDefault(False)
        self.btn_clear_seq.setToolTip("清空输入框内容")
        self.btn_clear_seq.clicked.connect(self._on_clear_sequence_clicked)
        tools_layout.addWidget(self.btn_clear_seq)

        tools_layout.addStretch()
        layout.addLayout(tools_layout)

        # 核心自定义序列文本框
        self.seq_input = QLineEdit()
        self.seq_input.setPlaceholderText(f"例如：3, 1, 2, 4 或 6-20, 1-5")
        self.seq_input.setMinimumHeight(34)
        self.seq_input.textChanged.connect(self._on_seq_input_changed)
        self.seq_input.returnPressed.connect(self._on_seq_input_return_pressed)
        layout.addWidget(self.seq_input)

        # 自定义排序诊断信息标签
        self.lbl_seq_diag = QLabel("")
        self.lbl_seq_diag.setStyleSheet("font-size: 11px;")
        layout.addWidget(self.lbl_seq_diag)

        layout.addStretch()

    def _setup_initial_values(self) -> None:
        """
        根据传入的当前页数与选中页设置界面初始状态。
        """
        self._is_syncing = True

        # 设置源页面默认值
        if self._initial_source_page is not None and 0 <= self._initial_source_page < self._page_count:
            default_src = str(self._initial_source_page + 1)
        else:
            default_src = "1-5" if self._page_count >= 5 else "1"
        self.source_edit.setText(default_src)

        # 设置目标页码默认值
        if self._page_count >= 20:
            self.target_spin.setValue(20)
        else:
            self.target_spin.setValue(self._page_count)

        # 自定义全排列输入框默认填入完整的当前原始页码序列 "1, 2, 3..."
        default_seq = ", ".join(str(i + 1) for i in range(self._page_count))
        self.seq_input.setText(default_seq)

        # 智能口令初始默认
        self.cmd_input.setText(f"将{default_src}页插入{self.target_spin.value()}页后面")

        self._is_syncing = False
        self._recompute_from_form()

    def _on_action_combo_changed(self) -> None:
        """
        响应插入位置关系下拉框改变，动态启用或禁用目标页码输入框。
        """
        action = self.action_combo.currentData()
        need_target = action in ("after", "before")
        self.target_spin.setEnabled(need_target)
        self.lbl_target_num.setEnabled(need_target)
        self.lbl_target_suffix.setEnabled(need_target)
        self._on_form_changed()

    def _on_current_page_clicked(self) -> None:
        """
        点击“选中当前页”按钮，将源页面输入框快速设置为当前浏览的页面。
        """
        if self._initial_source_page is not None and 0 <= self._initial_source_page < self._page_count:
            self.source_edit.setText(str(self._initial_source_page + 1))
        else:
            self.source_edit.setText("1")

    def _on_smart_command_text_changed(self, text: str) -> None:
        """
        实时监听顶部智能口令文本输入，自动解析并同步回填至表单或自定义排序。

        @param text 用户输入的口令字符串
        """
        if self._is_syncing:
            return

        cmd = text.strip()
        if not cmd:
            return

        # 1. 尝试检测是否直接输入了自定义排序全排列/范围简写序列（如 "3, 1, 2, 4"）
        if any(c in cmd for c in [",", "，"]) or (" " in cmd and not any(k in cmd for k in ["将", "把", "移", "插", "前", "后"])):
            is_valid, indices, diag = PageReorderHelper.validate_custom_sequence(cmd, self._page_count)
            if is_valid and indices is not None:
                self._is_syncing = True
                try:
                    self.tab_widget.setCurrentIndex(1)
                    self.seq_input.setText(cmd)
                finally:
                    self._is_syncing = False
                self._on_seq_input_changed(cmd)
                return

        # 2. 尝试解析自然语言口令（定向移动/插入）
        parsed = PageReorderHelper.parse_smart_command(cmd, self._page_count)
        if parsed is None:
            return

        self._is_syncing = True
        try:
            # 自动切换到定向移动选项卡
            self.tab_widget.setCurrentIndex(0)

            # 同步源页面
            src_str = PageReorderHelper.indices_to_range_str(parsed["source_pages"])
            self.source_edit.setText(src_str)

            # 同步动作
            action = parsed["action"]
            idx = self.action_combo.findData(action)
            if idx >= 0:
                self.action_combo.setCurrentIndex(idx)

            # 同步目标页
            target_p = parsed["target_page"]
            if target_p is not None:
                self.target_spin.setValue(target_p + 1)
        finally:
            self._is_syncing = False

        self._recompute_from_form(sync_cmd=False)

    def _on_form_changed(self) -> None:
        """
        响应定向移动表单控件的值改变。
        """
        if self._is_syncing:
            return
        self._recompute_from_form(sync_cmd=True)

    def _recompute_from_form(self, sync_cmd: bool = False) -> None:
        """
        根据当前定向移动表单控件计算新页面全排列索引，并更新预览与错误状态。

        @param sync_cmd 是否同步更新智能口令文本框
        """
        src_text = self.source_edit.text().strip()
        source_indices = PageRangeParser.parse_page_ranges(src_text, self._page_count)
        action = self.action_combo.currentData()
        target_page_1based = self.target_spin.value()
        target_idx = target_page_1based - 1 if action in ("after", "before") else None

        if sync_cmd and not self._is_syncing and source_indices:
            self._is_syncing = True
            try:
                src_str = PageReorderHelper.indices_to_range_str(source_indices)
                if action == "after":
                    self.cmd_input.setText(f"将{src_str}页插入{target_page_1based}页后面")
                elif action == "before":
                    self.cmd_input.setText(f"将{src_str}页插入{target_page_1based}页前面")
                elif action == "start":
                    self.cmd_input.setText(f"将{src_str}页移到最前面")
                elif action == "end":
                    self.cmd_input.setText(f"将{src_str}页移到最后面")
            finally:
                self._is_syncing = False

        # 校验与计算
        if not source_indices:
            self._show_error("请输入有效的待移动页面范围（例如：1-5）！")
            return

        if action in ("after", "before") and target_idx in source_indices:
            self._show_error(f"目标页码 (第 {target_page_1based} 页) 不能包含在待移动页面范围内！")
            return

        try:
            computed_order = PageReorderHelper.calculate_move_order(
                self._page_count,
                source_indices,
                action,
                target_idx
            )
            self._direct_computed_order = computed_order
            self._new_order = computed_order
            self._operation_description = PageReorderHelper.format_action_description(
                source_indices,
                action,
                target_idx,
                self._page_count
            )

            # 更新预览
            self._clear_error()
            self.lbl_action_desc.setText(f"✔ 动作：{self._operation_description}")
            self.lbl_change_summary.setText(
                PageReorderHelper.format_change_summary(computed_order, source_indices)
            )
            self._update_preview_label(computed_order)

        except Exception as e:
            self._show_error(str(e))

    def _on_seq_input_changed(self, text: str) -> None:
        """
        响应自定义排序全排列序列输入框文本改变。

        @param text 输入的自定义序列字符串
        """
        if self._is_syncing:
            return

        is_valid, indices, diag_msg = PageReorderHelper.validate_custom_sequence(text, self._page_count)
        if is_valid and indices is not None:
            self._new_order = indices
            self._operation_description = "批量自定义重排页面顺序"
            self._clear_error()
            self.lbl_action_desc.setText("✔ 动作：应用自定义全局序列重排")
            self.lbl_change_summary.setText("自定义顺序编排已生效")
            self.lbl_seq_diag.setText(f"✔ {diag_msg}")
            self.lbl_seq_diag.setStyleSheet("color: #16A34A; font-size: 11px; font-weight: bold;")
            self._update_preview_label(indices)
        else:
            # 正在编辑或输入不完整状态
            self.lbl_seq_diag.setText(f"ℹ {diag_msg}")
            self.lbl_seq_diag.setStyleSheet("color: #D97706; font-size: 11px;")
            self.lbl_action_desc.setText("动作说明：正在编辑自定义序列...")
            self.lbl_change_summary.setText("")
            self.lbl_seq_preview.setText(f"状态提示：{diag_msg}")
            # 不在编辑中途将按钮锁死，用户可在点击应用时查看明确校验弹窗
            self.lbl_error.setVisible(False)
            self.ok_btn.setEnabled(True)

    def _on_reset_sequence_clicked(self) -> None:
        """
        点击“恢复初始顺序”按钮，重置为 1 到 N 自然升序序列。
        """
        seq = PageReorderHelper.generate_default_sequence(self._page_count)
        self.seq_input.setText(", ".join(str(p + 1) for p in seq))

    def _on_reverse_sequence_clicked(self) -> None:
        """
        点击“整篇逆序倒排”按钮，快速倒转页面全序列。
        """
        seq = PageReorderHelper.generate_reversed_sequence(self._page_count)
        self.seq_input.setText(", ".join(str(p + 1) for p in seq))

    def _on_sync_from_direct_clicked(self) -> None:
        """
        点击“同步定向移动结果”按钮，将定向移动计算出的最新排列载入自定义输入框中。
        """
        if self._direct_computed_order:
            self.seq_input.setText(", ".join(str(p + 1) for p in self._direct_computed_order))
        else:
            self._on_reset_sequence_clicked()

    def _on_clear_sequence_clicked(self) -> None:
        """
        点击“清空”按钮，清空自定义排序输入框。
        """
        self.seq_input.clear()
        self.seq_input.setFocus()

    def _on_tab_changed(self, index: int) -> None:
        """
        响应标签页切换，动态激活对应的重排模式并同步刷新预览。

        @param index 切换到的标签索引
        """
        if index == 0:
            self._recompute_from_form(sync_cmd=False)
        else:
            self._on_seq_input_changed(self.seq_input.text())

    def _update_preview_label(self, order: List[int]) -> None:
        """
        更新底部新顺序序列预览文本展示。

        @param order 0-based 页面索引列表
        """
        pages_1based = [str(p + 1) for p in order]
        if len(pages_1based) <= 30:
            preview_str = ", ".join(pages_1based)
        else:
            preview_str = ", ".join(pages_1based[:20]) + f" ... (共 {len(pages_1based)} 页) ... " + ", ".join(pages_1based[-5:])
        self.lbl_seq_preview.setText(f"预计新顺序：{preview_str}")

    def _show_error(self, err_msg: str) -> None:
        """
        显示校验错误信息并禁用确定按钮。

        @param err_msg 错误提示文本
        """
        self.lbl_error.setText(f"❌ {err_msg}")
        self.lbl_error.setVisible(True)
        self.lbl_action_desc.setText("动作说明：参数存在冲突")
        self.lbl_change_summary.setText("")
        self.ok_btn.setEnabled(False)

    def _clear_error(self) -> None:
        """
        清除错误信息并启用确定按钮。
        """
        self.lbl_error.setVisible(False)
        self.lbl_error.setText("")
        self.ok_btn.setEnabled(True)

    def _on_apply_clicked(self) -> None:
        """
        校验最终生成的新排列并接受对话框。
        针对不同选项卡执行针对性的严格校验与友好的错误弹窗提示。
        """
        current_tab = self.tab_widget.currentIndex()

        # 1. 若当前在自定义排序选项卡
        if current_tab == 1:
            seq_text = self.seq_input.text().strip()
            is_valid, indices, diag_msg = PageReorderHelper.validate_custom_sequence(seq_text, self._page_count)
            if not is_valid or indices is None:
                QMessageBox.warning(
                    self,
                    "校验未通过",
                    f"{diag_msg}！\n\n输入的页码序列必须完整包含从 1 到 {self._page_count} 的所有页码，且不能有重复或遗漏。"
                )
                self.seq_input.setFocus()
                return

            self._new_order = indices
            self._operation_description = "批量自定义重排页面顺序"
            self.accept()
            return

        # 2. 若当前在定向移动选项卡
        if not self._new_order or len(self._new_order) != self._page_count:
            QMessageBox.warning(self, "提示", "尚未生成有效的页面重排序列，请检查待移动页面与目标位置！")
            return

        if sorted(self._new_order) != list(range(self._page_count)):
            QMessageBox.warning(self, "校验未通过", "生成的页面序列未能构成完整全排列，无法应用！")
            return

        self.accept()

    def _on_cmd_input_return_pressed(self) -> None:
        """
        响应快捷口令输入框的回车键（Enter/Return）按下事件。
        保留当前输入文本，重新解析并同步界面状态，避免内容丢失或回到初始状态。
        """
        text = self.cmd_input.text()
        self._on_smart_command_text_changed(text)

    def _on_source_edit_return_pressed(self) -> None:
        """
        响应待移动页面输入框的回车键（Enter/Return）按下事件。
        保留当前输入文本，重新计算新顺序与预览，避免内容丢失或回到初始状态。
        """
        self._on_form_changed()

    def _on_seq_input_return_pressed(self) -> None:
        """
        响应自定义序列输入框的回车键（Enter/Return）按下事件。
        保留当前输入文本，刷新诊断与预览信息，避免内容丢失或回到初始状态。
        """
        self._on_seq_input_changed(self.seq_input.text())

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """
        处理对话框按键事件。
        当焦点位于文本输入框中时，按回车键仅触发输入确认与解析，保留输入内容，防止误触发按钮导致状态重置。

        @param event 键盘按键事件对象
        """
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            focused = self.focusWidget()
            if isinstance(focused, QLineEdit):
                # 处于输入框中时，正常派发 returnPressed 并保留用户输入，拦截对话框级默认按钮触发
                event.accept()
                return
        super().keyPressEvent(event)
