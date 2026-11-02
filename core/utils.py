"""
文件通用工具模块。
提供文件大小格式化、页码区间字符串解析与数值校验等通用辅助函数。
"""

import os
import sys
from typing import List


class ResourceUtils:
    """
    自包含静态资源寻址工具类。
    统一管理静态资源（样式表、图标等）的绝对路径定位，
    自动适配源码运行模式、便携绿色目录模式以及 PyInstaller 独立单文件运行模式 (sys._MEIPASS)。
    """

    @staticmethod
    def get_resource_path(relative_path: str) -> str:
        """
        获取指定相对路径资源的绝对系统物理路径。

        @param relative_path 资源的相对路径，如 'assets/style_light.qss'
        @return 资源的物理绝对路径；优先从 PyInstaller 内部临时工作区解析
        """
        # 1. 检查是否运行于 PyInstaller 临时打包工作区 (单文件模式)
        if hasattr(sys, "_MEIPASS"):
            meipass_path = os.path.join(sys._MEIPASS, relative_path)
            if os.path.exists(meipass_path):
                return meipass_path

        # 2. 源码模式或便携目录模式：基于项目根目录查找
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        normal_path = os.path.join(base_dir, relative_path)
        if os.path.exists(normal_path):
            return normal_path

        # 3. 兜底回退：当前工作目录
        return os.path.abspath(relative_path)


class FileUtils:
    """
    文件与格式化相关的工具类。
    提供文件大小计算与格式化等静态方法。
    """

    @staticmethod
    def format_file_size(size_bytes: int) -> str:
        """
        将字节大小转换为人类可读的文件大小字符串。

        @param size_bytes 文件的字节数整数值
        @return 格式化后的文件大小字符串，如 '1.25 MB' 或 '512 KB'
        """
        if size_bytes < 0:
            return "0 B"
        units = ["B", "KB", "MB", "GB", "TB"]
        size = float(size_bytes)
        unit_idx = 0
        while size >= 1024.0 and unit_idx < len(units) - 1:
            size /= 1024.0
            unit_idx += 1
        if unit_idx == 0:
            return f"{int(size)} {units[unit_idx]}"
        return f"{size:.2f} {units[unit_idx]}"

    @staticmethod
    def get_file_size_str(file_path: str) -> str:
        """
        获取指定路径文件的真实物理大小并返回格式化字符串。

        @param file_path 本地目标文件绝对路径
        @return 格式化后的大小描述；若文件不存在则返回 '0 B'
        """
        if not os.path.isfile(file_path):
            return "0 B"
        return FileUtils.format_file_size(os.path.getsize(file_path))


class PageRangeParser:
    """
    页码范围字符串解析工具类。
    支持将类似 '1-3, 5, 8-10' 的用户输入转换为具体的 0-based 页码索引列表。
    """

    @staticmethod
    def parse_page_ranges(range_str: str, max_pages: int) -> List[int]:
        """
        解析页码范围字符串为升序去重的 0-based 页面索引列表。

        @param range_str 用户输入的页码范围文本，例如 '1-3, 5, 8-10'；若为空或 'all' 则返回所有页
        @param max_pages 当前文档的最大总页数，必须大于 0
        @return 解析出的 0-based 页面索引整数列表
        """
        if max_pages <= 0:
            return []

        cleaned = range_str.strip()
        if not cleaned or cleaned.lower() == "all" or cleaned.lower() == "全部":
            return list(range(max_pages))

        result_indices = set()
        parts = cleaned.split(",")

        for part in parts:
            token = part.strip()
            if not token:
                continue
            if "-" in token:
                bounds = token.split("-")
                if len(bounds) == 2 and bounds[0].strip().isdigit() and bounds[1].strip().isdigit():
                    start = int(bounds[0].strip())
                    end = int(bounds[1].strip())
                    # 转换为 0-based 索引，处理用户可能倒序输入的范围
                    low = min(start, end)
                    high = max(start, end)
                    for p in range(low, high + 1):
                        if 1 <= p <= max_pages:
                            result_indices.add(p - 1)
            elif token.isdigit():
                p = int(token)
                if 1 <= p <= max_pages:
                    result_indices.add(p - 1)

        return sorted(list(result_indices))
