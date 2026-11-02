"""
核心业务模块包初始化文件。
配置系统环境，跳过未使用的 AI 布局模型探测以确保打包后无缺失模型文件异常。
"""

import sys

# 禁用未使用的 pymupdf AI 布局分析模型检测，避免缺少 onnx/yaml 资源时的报错
if "pymupdf.layout" not in sys.modules:
    sys.modules["pymupdf.layout"] = None
