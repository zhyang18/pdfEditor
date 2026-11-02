"""
Word 与 PDF 双向格式互转对话框及后台异步线程模块。
支持 PDF 高保真导出为 Word (.docx) 以及本地 Word 文件转换并导入到当前编辑器。
自适应高分屏布局，确保弹窗信息与控制按钮舒展完整显示。
"""

import os
from typing import Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QProgressBar, QMessageBox, QWidget
)
from PySide6.QtCore import QThread, Signal, Qt
from core.word_converter import WordConverter
from core.utils import ResourceUtils
from assets.icons import IconLibrary


class ConvertWorkerThread(QThread):
    """
    文档格式转换后台工作线程。
    在后台异步执行 pdf2docx 或 COM 转换，避免长时间转换阻塞 GUI 主事件循环。
    """

    progress_updated = Signal(int, str)
    conversion_finished = Signal(bool, str)

    def __init__(self, mode: str, src_path: str, dst_path: str, parent: Optional[QWidget] = None) -> None:
        """
        初始化转换工作线程。

        @param mode 转换模式，'pdf_to_word' 或 'word_to_pdf'
        @param src_path 源输入文件绝对路径
        @param dst_path 目标输出文件绝对路径
        @param parent 父对象
        """
        super().__init__(parent)
        self._mode = mode
        self._src_path = src_path
        self._dst_path = dst_path

    def run(self) -> None:
        """
        线程执行主体逻辑。
        """
        def on_progress(percent: int, msg: str) -> None:
            self.progress_updated.emit(percent, msg)

        try:
            if self._mode == "pdf_to_word":
                success = WordConverter.pdf_to_word(
                    self._src_path,
                    self._dst_path,
                    progress_callback=on_progress
                )
            else:
                success = WordConverter.word_to_pdf(
                    self._src_path,
                    self._dst_path,
                    progress_callback=on_progress
                )
            self.conversion_finished.emit(success, self._dst_path)
        except Exception as e:
            self.conversion_finished.emit(False, str(e))


class WordConvertDialog(QDialog):
    """
    Word 格式转换进度展示与交互对话框。
    展示动态百分比进度条与当前详细步骤描述。
    """

    def __init__(
        self,
        mode: str,
        src_path: str,
        dst_path: str,
        parent: Optional[QWidget] = None
    ) -> None:
        """
        初始化转换对话框并启动后台转换线程。

        @param mode 转换模式，'pdf_to_word'（导出为 Word）或 'word_to_pdf'（导入 Word）
        @param src_path 源文件路径
        @param dst_path 目标输出文件路径
        @param parent 父组件
        """
        super().__init__(parent)
        self._mode = mode
        self._src_path = src_path
        self._dst_path = dst_path
        self._is_success = False

        title = "正在导出为 Word 文档..." if mode == "pdf_to_word" else "正在将 Word 文档转换为 PDF..."
        self.setWindowTitle(title)
        self.resize(480, 240)
        self.setMinimumSize(440, 210)

        self._init_ui()
        self._apply_theme(parent)
        self._start_thread()

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
    def is_success(self) -> bool:
        """
        获取转换是否成功完成。

        @return 若成功完成转换返回 True，否则返回 False
        """
        return self._is_success

    @property
    def output_path(self) -> str:
        """
        获取生成的目标文件路径。

        @return 输出文件绝对路径
        """
        return self._dst_path

    def _init_ui(self) -> None:
        """
        初始化对话框布局与控件。
        """
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        icon_name = "to_word" if self._mode == "pdf_to_word" else "from_word"
        self.icon_label = QLabel()
        self.icon_label.setPixmap(IconLibrary.get_icon(icon_name, 36).pixmap(36, 36))
        self.icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.icon_label)

        self.status_label = QLabel("正在准备转换...")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #334155; font-weight: 500; font-size: 13px;")
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(16)
        layout.addWidget(self.progress_bar)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 6, 0, 0)
        btn_layout.addStretch()

        self.close_btn = QPushButton("请稍候...")
        self.close_btn.setMinimumHeight(34)
        self.close_btn.setMinimumWidth(90)
        self.close_btn.setEnabled(False)
        self.close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.close_btn)

        layout.addLayout(btn_layout)

    def _start_thread(self) -> None:
        """
        启动后台异步工作线程。
        """
        self.worker = ConvertWorkerThread(self._mode, self._src_path, self._dst_path, self)
        self.worker.progress_updated.connect(self._on_progress_update)
        self.worker.conversion_finished.connect(self._on_finished)
        self.worker.start()

    def _on_progress_update(self, percent: int, msg: str) -> None:
        """
        处理进度与描述更新事件。

        @param percent 进度百分比整数 (0~100)
        @param msg 当前进度描述文本
        """
        self.progress_bar.setValue(percent)
        self.status_label.setText(msg)

    def _on_finished(self, success: bool, output_or_err: str) -> None:
        """
        处理转换完成事件。

        @param success 是否成功
        @param output_or_err 输出文件路径或异常错误文本
        """
        self._is_success = success
        if success:
            self.progress_bar.setValue(100)
            self.status_label.setText("转换已成功完成！")
            self.close_btn.setText("完成")
            self.close_btn.setEnabled(True)
            self.close_btn.setProperty("primary", "true")
        else:
            self.status_label.setText(f"转换失败：{output_or_err}")
            self.close_btn.setText("关闭")
            self.close_btn.setEnabled(True)
            QMessageBox.critical(self, "转换失败", f"处理过程中发生错误：\n{output_or_err}")
