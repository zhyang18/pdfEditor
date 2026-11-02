# PDF 编辑器 (PdfEditor) - 桌面专业版

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python Version](https://img.shields.io/badge/Python-3.10%20|%203.11%20|%203.12%20|%203.14-blue.svg)](https://www.python.org/)
[![GUI Framework](https://img.shields.io/badge/GUI-PySide6%20(Qt%206)-green.svg)](https://wiki.qt.io/Qt_for_Python)
[![PDF Engine](https://img.shields.io/badge/Engine-PyMuPDF%20(fitz)-orange.svg)](https://pymupdf.readthedocs.io/)
[![Tests](https://img.shields.io/badge/Tests-25%20Passed-brightgreen.svg)](tests/)

一款基于 **Python 3 + PySide6 (Qt 6) + PyMuPDF** 构建的现代化、高性能、轻量清爽的 Windows 桌面专业 PDF 编辑器。不仅具备强大的单页/多页排版、可视化图层盖章、多文档切片拼接合并、高精度无损拆分与 Word 双向互转能力，还针对 Windows 平台提供了原生高分屏适配、C 级毫秒启动画面以及标准化 Inno Setup 安装包与绿色便携版打包方案。

---

## 🌟 核心特色与功能全景

### 1. 文档浏览与高性能矢量渲染
- **超清毫秒级渲染引擎**：底层基于 MuPDF 工业级渲染库，毫秒级快速重绘，文本与矢量图形清晰锐利无边缘锯齿。
- **平滑自由缩放体系**：支持 25% ~ 500% 任意平滑缩放、鼠标 `Ctrl + 滚轮` 平滑缩放，并内置【适应窗口宽度】、【自适应整页】和【100% 原始尺寸】快速切换。
- **高分屏 HiDPI 完美自适应**：内嵌专属 Windows `app.manifest` 清单配置，支持 `PerMonitorV2` 级系统 DPI 动态缩放感知，在 2K/4K/高缩放比显示器下保持字体与图标极致细腻，杜绝模糊与拉伸变形。

### 2. 页面全生命周期编辑与组织
- **自由旋转**：支持顺时针 90°、180°、270° 旋转单页或针对全部页面批量旋转。
- **页面增删**：支持在文档任意指定位置插入标准 A4 空白页，或删除无用页面（内置安全边界保护机制，严防误删，自动保留至少 1 页）。
- **页面提取导出**：右键任意页面可一键将其单独提取导出为新的独立 PDF 文件。
- **拖拽与批量序列重排**：
  - **缩略图拖拽排版**：左侧面板直观呈现全部页面真实微缩图与当前页码，支持鼠标按住任意页面自由拖拽至目标位置瞬间重排；
  - **快捷步进微调**：支持选中页面后一键“向上移动”或“向下移动”；
  - **批量序列重排对话框**：提供专用重排向导，支持用户直接输入页码序列（例如：`3, 1, 2, 5, 4`）一键完成整篇文档的逻辑顺序重构。

### 3. 可视化交互图层与印章盖章
- **全格式图片插入**：支持导入 PNG、JPG、JPEG、BMP、WEBP 等常见图像格式（如合同印章、签名图片、标注插图等）。
- **八向锚点缩放与自由拖拽**：图片导入后作为动态交互图元浮动于 PDF 之上，支持按住中心任意位置平移，拖拽 8 个边角控制把手可等比例放缩，按键盘 `Delete` 键可快速撤销删除。
- **高精度物理点数固化（Burn-in）**：调整完毕后，点击工具栏【固化图片】，系统自动将其视口坐标精确换算为 PDF 物理点数坐标并永久写入底层 PDF 页面流。

### 4. PDF 可视化页面截断与拆分（Split）
- **交互式截断向导**：提供独立的 `SplitDialog` 拆分向导，集成交互式滑块与数字微调框，实时联动选择截断页码。
- **动态区间与页数统计卡片**：根据截断点实时计算并展示“前半部分（1 ~ N 页）”与“后半部分（N+1 ~ M 页）”的详细页码分布与页数统计。
- **安全路径校验**：支持自定义前后两份输出文件的保存路径，内置防止同名覆盖、文件占用与越界保护逻辑。

### 5. 多 PDF 文件批量切片拼接合并（Merge）
- **可视化多文件合并向导**：提供清晰的多文件列表视图，支持批量追加、移除待合并的 PDF 文件。
- **文件顺序灵活调整**：支持在列表中上下调整不同文件的拼接合并先后次序。
- **自定义切片页码提取**：不仅支持整篇合并，还支持为列表中的每个文件单独指定需要提取的页码区间（例如：文件 A 取 `1-3, 5` 页，文件 B 取 `全部`），实现多文档按需切片组装。

### 6. Word 与 PDF 高保真双向互转
- **PDF 导出为 Word (.docx)**：基于 `pdf2docx` 智能布局重构引擎，精准解析段落文字、字体样式、标题层级、内嵌图片与结构化数据表格，输出完全可二次编辑的高质量 `.docx` 文件。
- **Word 导入转换为 PDF**：
  - **原生 Office 优先方案**：优先探测并调用本地已安装的 Microsoft Office 或 WPS Office 官方 COM 自动化组件，100% 矢量无损导出 PDF；
  - **全环境通用兜底方案**：在未安装 Office 软件的机器上，自动无缝切换为纯 Python 格式解析渲染引擎，确保在任何极简环境下均能稳定完成转换。
- **多线程异步处理**：互转任务均在后台独立的 `QThread` 线程中执行，杜绝主界面假死卡顿，配有实时进度条与状态提示。

### 7. 批量自定义文本水印与体积优化
- **批量文本水印**：支持自定义水印文字、字体大小、不透明度（0%~100%）、旋转倾斜角（-180°~180°），并可指定应用于全部页面或特定页码范围。
- **体积无损压缩瘦身**：一键调用 `deflate=True` 数据流无损压缩，并深度清理未引用垃圾对象（`garbage=4`），大幅精简臃肿的 PDF 物理文件体积。

### 8. 现代化 Fluent 交互设计与撤销体系
- **深浅主题一键切换**：遵循现代 Fluent / Flat 扁平设计哲学，内置柔和清爽的浅色（Light）与沉浸式暗色（Dark）双套精美 QSS 样式表，支持一键热重载无缝切换。
- **纯矢量高清 SVG 图标库**：所有工具栏与菜单图标均采用纯代码动态生成的矢量 SVG（`assets/icons.py`），在任何高分辨率或缩放比例下无失真。
- **命令模式撤销/重做（Undo / Redo）**：完备的命令状态机（`HistoryManager`），对页面增删、旋转、重排等核心修改均提供 `Ctrl+Z` 撤销与 `Ctrl+Y` 重做支持。
- **拖拽即开与秒级启动**：支持从 Windows 资源管理器直接将 PDF/Word 文档拖入窗口秒级打开；集成 C 级原生 Bootloader Splash 屏，双击瞬间毫秒弹出启动封面，消除空白真空期。

---

## 🛠️ 项目目录结构

```
pdfEditor/
├── app.py                      # 应用程序主入口（包含环境初始化、HiDPI配置与单实例处理）
├── app.manifest                # Windows 原生程序清单（配置 PerMonitorV2 高分屏感知与长路径支持）
├── build_exe.py                # PyInstaller 自动化独立程序编译打包脚本
├── installer.iss               # Inno Setup 标准安装包构建向导脚本（生成 Setup.exe 安装包）
├── create_samples.py           # 附带的示例 PDF 合同与印章图片生成辅助脚本
├── requirements.txt            # 项目 Python 依赖库声明清单
├── LICENSE                     # MIT 开源授权协议文件
├── README.md                   # 项目全景说明文档与开发者指南
├── assets/                     # 静态资源与样式定义
│   ├── app.ico                 # 应用程序多分辨率高清图标
│   ├── splash.png              # 原生启动过渡画面背景图
│   ├── icons.py                # 纯矢量 SVG 图标库代码定义
│   ├── generate_icon.py        # 桌面图标自动绘制生成工具
│   ├── generate_splash.py      # 启动画面自动渲染工具
│   ├── style_light.qss         # 现代清爽浅色主题样式表
│   └── style_dark.qss          # 沉浸暗夜深色主题样式表
├── core/                       # 核心业务逻辑层（与 UI 解耦）
│   ├── __init__.py             # 核心模块导出声明
│   ├── pdf_document.py         # 基于 PyMuPDF 的底层文档操作封装（旋转、增删、拆分、水印、图层）
│   ├── pdf_merger.py           # 多文档切片抽取与拼接合并引擎
│   ├── word_converter.py       # Word 与 PDF 高保真双向互转核心调度器
│   ├── history_manager.py      # 基于命令模式的撤销/重做（Undo/Redo）历史状态管理器
│   ├── image_layer.py          # 浮动印章图层数据结构与物理坐标转换
│   └── utils.py                # 文件尺寸格式化、页码区间解析与路径解析通用工具集
├── ui/                         # 界面与人机交互展示层
│   ├── main_window.py          # 主窗口框架（菜单、动作绑定、拖放接收、状态提示）
│   ├── canvas_view.py          # 绘图主视口与支持八向交互拉伸缩放的 ImageOverlayItem
│   ├── thumbnail_panel.py      # 左侧缩略图交互面板（支持鼠标拖拽实时重排与右键菜单）
│   ├── toolbar.py              # 顶部现代 Fluent 胶囊样式功能工具栏
│   └── dialogs/                # 功能独立向导对话框组件
│       ├── split_dialog.py     # PDF 可视化页面截断与拆分向导
│       ├── merge_dialog.py     # 多文件切片拼接与合并向导
│       ├── word_dialog.py      # Word 与 PDF 互转异步进度条与状态提示框
│       ├── watermark_dialog.py # 文本水印配置向导
│       └── reorder_dialog.py   # 页面批量序列输入与重排向导
└── tests/                      # 自动化测试套件
    ├── test_core.py            # 核心文档操作单元测试
    ├── test_split.py           # PDF 拆分逻辑单元测试
    ├── test_ui.py              # 界面逻辑与信号插槽集成测试
    └── test_fixes.py           # 历史修复与边界情况覆盖测试
```

---

## 🚀 启动与构建指南

### 1. 环境准备与源码运行

建议使用 Python 3.10 及以上环境：

```bash
# 1. 克隆代码仓库
git clone https://github.com/zhyang18/pdfEditor.git
cd pdfEditor

# 2. 安装项目依赖
pip install -r requirements.txt

# 3. 运行应用程序
python app.py
```

### 2. 执行自动化测试套件

项目拥有完善的自动化测试覆盖，执行以下命令即可一键运行所有 25 项单元与集成测试：

```bash
python -m unittest discover -s tests -p "test_*.py"
```

### 3. 编译打包为 Windows 可执行程序

项目提供了 `build_exe.py` 自动化打包脚本，集成了依赖精简、排除冗余 Qt 模块、注入高清图标、配置 `app.manifest` 及注入原生 C 级启动过渡画面等优化：

#### 方案 A：便携绿色目录模式（推荐，秒级冷启动）
```bash
python build_exe.py
```
> **优势说明**：生成位于 `dist/PdfEditor/` 的便携免安装目录。程序启动时由操作系统直接进行内存映射加载，免除了单文件运行时往临时目录释放数百兆文件的额外耗时与杀毒软件扫描瓶颈，配合 C 级 Bootloader Splash 实现秒级瞬间启动。

#### 方案 B：单个独立 EXE 文件模式
```bash
python build_exe.py --onefile
```
> 生成位于 `dist/PdfEditor.exe` 的单一自包含文件，适合单文件快速分发场景。

#### 方案 C：使用 Inno Setup 制作标准 Windows 安装向导
若需要向最终用户交付标准的 Windows 安装向导（支持创建桌面图标、开始菜单组、控制面板一键卸载），在执行完成方案 A 打包后，直接使用 [Inno Setup 6](https://jrsoftware.org/isdl.php) 编译随附的 `installer.iss` 脚本：
```bash
iscc installer.iss
```
即可在 `dist/` 目录下生成 `PdfEditor_Setup_v1.0.0.exe` 安装包。

---

## 📄 开源协议与授权声明 (License & Attribution)

### 本项目开源授权
本项目代码采用 **[MIT License](LICENSE)** 开源授权许可。  
Copyright (c) 2026 **zhyang18**

您可以自由地使用、修改、合并、发布、分发本软件，但必须在所有副本中保留原始版权声明与许可声明。本软件按“原样”提供，不提供任何明示或暗示的担保。

---

### 第三方核心开源组件及合规说明

本项目基于一系列优秀的开源库与技术框架构建，在此向开源社区致以由衷的感谢。相关第三方组件各自遵循其独立的开源许可协议，开发者与使用者在分发或商业衍生时应遵循对应协议的规定：

| 依赖库 / 组件 | 官方主页 / 源码 | 开源协议 | 在本项目中的作用与合规说明 |
| :--- | :--- | :--- | :--- |
| **PySide6 (Qt 6)** | [Qt for Python](https://wiki.qt.io/Qt_for_Python) | **LGPLv3** / 商业许可 | 现代桌面 GUI 视口、主窗口及控件渲染。本项目作为动态链接库方式引入，符合 LGPLv3 规定。 |
| **PyMuPDF (fitz)** | [PyMuPDF GitHub](https://github.com/pymupdf/PyMuPDF) | **GNU AGPLv3** / 商业双许可 | 高性能 PDF 文档渲染、页面增删、切片拆分、水印与流压缩。使用者若在闭源商业网络产品中分发或托管，建议参考 Artifex 商业许可策略。 |
| **pdf2docx** | [pdf2docx GitHub](https://github.com/dothinking/pdf2docx) | **GNU GPLv3** | PDF 页面排版、文本段落、表格与内嵌图像反向重构为 Word (.docx)。 |
| **python-docx** | [python-docx GitHub](https://github.com/python-openxml/python-docx) | **MIT License** | Word 文档结构的读取与处理。 |
| **reportlab** | [ReportLab](https://www.reportlab.com/) | **BSD License** | 纯 Python 环境下兜底 Word 转 PDF 的排版生成引擎。 |
| **pywin32** | [pywin32 GitHub](https://github.com/mhammond/pywin32) | **PSF License** | 联动 Windows 原生 Office / WPS COM 自动化接口实现高保真转换。 |
| **comtypes** | [comtypes GitHub](https://github.com/enthought/comtypes) | **MIT License** | 轻量级纯 Python COM 客户端库支持。 |
| **PyInstaller** | [PyInstaller GitHub](https://github.com/pyinstaller/pyinstaller) | **GPLv2 with Bootloader Exception** | 仅作为构建打包工具使用，其内置的引导加载程序特别例外条款允许构建分发任意许可的应用程序。 |

---

## 🤝 贡献与反馈

欢迎提交 Issue 汇报使用中遇到的问题或提出新功能建议！如需贡献代码，请提交 Pull Request，共同完善更加极致易用的 PDF 桌面工具。
