"""
文件通用工具模块。
提供文件大小格式化、页码区间字符串解析与数值校验等通用辅助函数。
"""

import os
import sys
import re
from typing import List, Optional, Dict, Any, Tuple


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
        # 1. 检查是否运行于 PyInstaller 临时打包工作区 (单文件模式或设置了 _MEIPASS 的便携模式)
        if hasattr(sys, "_MEIPASS"):
            meipass_path = os.path.join(sys._MEIPASS, relative_path)
            if os.path.exists(meipass_path):
                return meipass_path

        # 2. 检查是否运行于 PyInstaller 冻结可执行文件模式 (便携绿色目录模式)
        if getattr(sys, "frozen", False):
            exe_dir = os.path.dirname(sys.executable)
            for sub in ("", "_internal"):
                cand_path = os.path.join(exe_dir, sub, relative_path) if sub else os.path.join(exe_dir, relative_path)
                if os.path.exists(cand_path):
                    return cand_path

        # 3. 源码模式：基于项目根目录查找
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        normal_path = os.path.join(base_dir, relative_path)
        if os.path.exists(normal_path):
            return normal_path

        # 4. 兜底回退：当前工作目录
        return os.path.abspath(relative_path)

    @staticmethod
    def get_asset_path(asset_name: str) -> str:
        """
        获取 assets 目录下的静态资源绝对物理路径。

        @param asset_name 资产文件名或 assets 子路径，如 'qtbase_zh_CN.qm' 或 'assets/style_light.qss'
        @return 资产文件的物理绝对路径
        """
        normalized_name = asset_name.replace("\\", "/")
        if normalized_name.startswith("assets/"):
            return ResourceUtils.get_resource_path(asset_name)
        return ResourceUtils.get_resource_path(os.path.join("assets", asset_name))

    @staticmethod
    def load_stylesheet(style_name: str) -> str:
        """
        加载指定名称的 QSS 样式表文件，并将其中引用的 assets 静态资源相对路径自动解析为跨平台绝对物理路径。

        @param style_name 样式表文件名或相对路径，如 'style_light.qss' 或 'style_dark.qss'
        @return 解析并完成路径重写后的完整 QSS 样式表文本；若文件不存在则返回空字符串
        """
        style_path = ResourceUtils.get_asset_path(style_name)
        if not os.path.isfile(style_path):
            return ""

        try:
            with open(style_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            return ""

        def _replace_asset_url(match: re.Match) -> str:
            rel_asset = match.group(1).strip("'\"")
            abs_asset = ResourceUtils.get_resource_path(rel_asset).replace("\\", "/")
            return f'url("{abs_asset}")'

        rewritten_content = re.sub(
            r'url\s*\(\s*["\']?(assets/[^"\'\)]+)["\']?\s*\)',
            _replace_asset_url,
            content
        )
        return rewritten_content


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


class PageReorderHelper:
    """
    页面重排与定向移动计算辅助类。
    提供自然语言口令解析、范围移动顺序计算、全排列范围展开及撤销逆置换计算。
    """

    @staticmethod
    def indices_to_range_str(indices: List[int]) -> str:
        """
        将 0-based 页面索引列表转换为人类易读的 1-based 连续范围字符串（例如 '1-5, 8'）。

        @param indices 0-based 页面索引列表
        @return 格式化后的 1-based 页码范围文本
        """
        if not indices:
            return ""

        sorted_pages = sorted(list(set(p + 1 for p in indices if p >= 0)))
        if not sorted_pages:
            return ""

        ranges = []
        start = sorted_pages[0]
        prev = sorted_pages[0]

        for p in sorted_pages[1:]:
            if p == prev + 1:
                prev = p
            else:
                if start == prev:
                    ranges.append(str(start))
                else:
                    ranges.append(f"{start}-{prev}")
                start = p
                prev = p

        if start == prev:
            ranges.append(str(start))
        else:
            ranges.append(f"{start}-{prev}")

        return ", ".join(ranges)

    @staticmethod
    def parse_smart_command(command: str, total_pages: int) -> Optional[Dict[str, Any]]:
        """
        解析自然语言或快捷口令字符串为结构化调序参数。
        支持如：
        - '将1-5页插入20页后面' / '把1-5页移到20页后'
        - '1-5页插入20页前面' / '1-5移到20页前'
        - '将1-5页移到最前面' / '1-5移到开头'
        - '将1-5页移到最后面' / '1-5移到末尾'
        - '1-5 -> 20' / '1-5 after 20' / '1-5 before 20'
        - '1-5 插入 20' (默认插在 20 页后)

        @param command 用户输入的文本口令
        @param total_pages 当前文档总页数
        @return 结构化字典，包含 'source_pages' (List[int]), 'action' (str), 'target_page' (Optional[int])；解析失败时返回 None
        """
        if total_pages <= 0:
            return None

        cmd = command.strip()
        if not cmd:
            return None

        # 统一标准化中文字符、全角标点与连字符
        cmd_std = cmd.replace("，", ",").replace("－", "-").replace("—", "-").replace("～", "-").replace("~", "-")

        # 1. 匹配移至最前面 / 首页
        m_start = re.match(
            r"^(?:将|把)?\s*([0-9,\-\s]+?)\s*(?:页)?\s*(?:移动?|插入|移到|放到|置于)?\s*(?:到|至)?\s*(?:最前|最前面|开头|首页|第一页|start)$",
            cmd_std,
            re.IGNORECASE
        )
        if m_start:
            src_str = m_start.group(1).strip()
            src_pages = PageRangeParser.parse_page_ranges(src_str, total_pages)
            if src_pages:
                return {"source_pages": src_pages, "action": "start", "target_page": None}

        # 2. 匹配移至最后面 / 末尾
        m_end = re.match(
            r"^(?:将|把)?\s*([0-9,\-\s]+?)\s*(?:页)?\s*(?:移动?|插入|移到|放到|置于)?\s*(?:到|至)?\s*(?:最后|最后面|末尾|末页|最后一页|end)$",
            cmd_std,
            re.IGNORECASE
        )
        if m_end:
            src_str = m_end.group(1).strip()
            src_pages = PageRangeParser.parse_page_ranges(src_str, total_pages)
            if src_pages:
                return {"source_pages": src_pages, "action": "end", "target_page": None}

        # 3. 匹配在某页之后 / 后面（中文句式）
        m_after = re.match(
            r"^(?:将|把)?\s*([0-9,\-\s]+?)\s*(?:页)?\s*(?:移动?|插入|移到|放到|置于)?\s*(?:到|至|在)?\s*([0-9]+)\s*(?:页)?\s*(?:之?后|后面|后头|之后)$",
            cmd_std
        )
        if m_after:
            src_str = m_after.group(1).strip()
            target_p = int(m_after.group(2).strip())
            src_pages = PageRangeParser.parse_page_ranges(src_str, total_pages)
            if src_pages and 1 <= target_p <= total_pages:
                return {"source_pages": src_pages, "action": "after", "target_page": target_p - 1}

        # 4. 匹配在某页之前 / 前面（中文句式）
        m_before = re.match(
            r"^(?:将|把)?\s*([0-9,\-\s]+?)\s*(?:页)?\s*(?:移动?|插入|移到|放到|置于)?\s*(?:到|至|在)?\s*([0-9]+)\s*(?:页)?\s*(?:之?前|前面|前头|之前)$",
            cmd_std
        )
        if m_before:
            src_str = m_before.group(1).strip()
            target_p = int(m_before.group(2).strip())
            src_pages = PageRangeParser.parse_page_ranges(src_str, total_pages)
            if src_pages and 1 <= target_p <= total_pages:
                return {"source_pages": src_pages, "action": "before", "target_page": target_p - 1}

        # 5. 匹配箭头快捷语法 '1-5 -> 20' 或 '1-5 => 20'（默认放置在目标页后）
        m_arrow = re.match(r"^([0-9,\-\s]+?)\s*(?:->|=>|一>)\s*([0-9]+)$", cmd_std)
        if m_arrow:
            src_str = m_arrow.group(1).strip()
            target_p = int(m_arrow.group(2).strip())
            src_pages = PageRangeParser.parse_page_ranges(src_str, total_pages)
            if src_pages and 1 <= target_p <= total_pages:
                return {"source_pages": src_pages, "action": "after", "target_page": target_p - 1}

        # 6. 匹配英文语法 '1-5 after 20' 与 '1-5 before 20'
        m_en_after = re.match(r"^([0-9,\-\s]+?)\s+after\s+([0-9]+)$", cmd_std, re.IGNORECASE)
        if m_en_after:
            src_str = m_en_after.group(1).strip()
            target_p = int(m_en_after.group(2).strip())
            src_pages = PageRangeParser.parse_page_ranges(src_str, total_pages)
            if src_pages and 1 <= target_p <= total_pages:
                return {"source_pages": src_pages, "action": "after", "target_page": target_p - 1}

        m_en_before = re.match(r"^([0-9,\-\s]+?)\s+before\s+([0-9]+)$", cmd_std, re.IGNORECASE)
        if m_en_before:
            src_str = m_en_before.group(1).strip()
            target_p = int(m_en_before.group(2).strip())
            src_pages = PageRangeParser.parse_page_ranges(src_str, total_pages)
            if src_pages and 1 <= target_p <= total_pages:
                return {"source_pages": src_pages, "action": "before", "target_page": target_p - 1}

        # 7. 匹配省略后缀的短指令，如 '1-5 插入 20' 或 '1-5 移到 20'（默认放置在目标页后）
        m_default = re.match(
            r"^(?:将|把)?\s*([0-9,\-\s]+?)\s*(?:页)?\s*(?:插入|移到|放到|移动到)\s*(?:到|至|在)?\s*([0-9]+)\s*(?:页)?$",
            cmd_std
        )
        if m_default:
            src_str = m_default.group(1).strip()
            target_p = int(m_default.group(2).strip())
            src_pages = PageRangeParser.parse_page_ranges(src_str, total_pages)
            if src_pages and 1 <= target_p <= total_pages:
                return {"source_pages": src_pages, "action": "after", "target_page": target_p - 1}

        return None

    @staticmethod
    def calculate_move_order(
        total_pages: int,
        source_indices: List[int],
        action: str,
        target_index: Optional[int] = None
    ) -> List[int]:
        """
        根据指定的待移动源页面索引集合与插入动作，计算重排后的 0-based 完整页面全排列索引列表。

        @param total_pages 文档总页数
        @param source_indices 待移动源页面 0-based 索引列表
        @param action 移动目标动作类型：'after'、'before'、'start'、'end'
        @param target_index 目标页面 0-based 索引（当 action 为 'start' 或 'end' 时可为 None）
        @return 重新编排后的 0-based 页面索引全排列列表
        """
        if total_pages <= 0:
            raise ValueError(f"文档总页数无效: {total_pages}")

        if not source_indices:
            raise ValueError("待移动页面列表不能为空")

        for idx in source_indices:
            if not (0 <= idx < total_pages):
                raise ValueError(f"待移动页码索引越界: {idx}")

        source_set = set(source_indices)
        if len(source_set) == total_pages:
            # 全部页面同时移动，无需改变顺序
            return list(source_indices)

        # 提取除去待移动页面后的剩余页面序列（保持原有先后顺序）
        remaining = [i for i in range(total_pages) if i not in source_set]

        if action == "start":
            new_order = list(source_indices) + remaining
        elif action == "end":
            new_order = remaining + list(source_indices)
        elif action == "after":
            if target_index is None or not (0 <= target_index < total_pages):
                raise ValueError(f"目标页码索引无效: {target_index}")
            if target_index in source_set:
                raise ValueError(f"目标页码 (第 {target_index + 1} 页) 不能包含在待移动页面范围内")
            target_pos = remaining.index(target_index)
            new_order = remaining[:target_pos + 1] + list(source_indices) + remaining[target_pos + 1:]
        elif action == "before":
            if target_index is None or not (0 <= target_index < total_pages):
                raise ValueError(f"目标页码索引无效: {target_index}")
            if target_index in source_set:
                raise ValueError(f"目标页码 (第 {target_index + 1} 页) 不能包含在待移动页面范围内")
            target_pos = remaining.index(target_index)
            new_order = remaining[:target_pos] + list(source_indices) + remaining[target_pos:]
        else:
            raise ValueError(f"未知的移动动作: {action}")

        if sorted(new_order) != list(range(total_pages)):
            raise ValueError("重排计算生成的页面索引未能构成有效全排列")

        return new_order

    @staticmethod
    def calculate_inverse_permutation(new_order: List[int]) -> List[int]:
        """
        计算指定全排列置换的数学逆置换列表，供撤销 (Undo) 操作完美恢复原页面排列。

        @param new_order 重排后的 0-based 页面索引全排列
        @return 逆置换 0-based 页面索引列表
        """
        total = len(new_order)
        inverse = [0] * total
        for new_pos, orig_page in enumerate(new_order):
            if not (0 <= orig_page < total):
                raise ValueError(f"置换中存在无效页面索引: {orig_page}")
            inverse[orig_page] = new_pos
        return inverse

    @staticmethod
    def expand_ranges_to_permutation(seq_str: str, total_pages: int) -> Optional[List[int]]:
        """
        将包含范围简写的序列字符串（如 '6-20, 1-5, 21-30'）展开并严格校验为合法的 0-based 全排列。

        @param seq_str 包含连续范围或逗号分隔的序列文本
        @param total_pages 文档总页数
        @return 合法的 0-based 全排列列表；若有重复、遗漏、非数字或越界则返回 None
        """
        if total_pages <= 0:
            return None

        cleaned = seq_str.strip().replace("，", ",")
        if not cleaned:
            return None

        parts = cleaned.split(",")
        expanded_pages: List[int] = []

        for part in parts:
            token = part.strip()
            if not token:
                continue
            if "-" in token:
                bounds = token.split("-")
                if len(bounds) != 2:
                    return None
                b0 = bounds[0].strip()
                b1 = bounds[1].strip()
                if not (b0.isdigit() and b1.isdigit()):
                    return None
                start = int(b0)
                end = int(b1)
                step = 1 if start <= end else -1
                for p in range(start, end + step, step):
                    expanded_pages.append(p)
            elif token.isdigit():
                expanded_pages.append(int(token))
            else:
                return None

        # 校验全排列属性：数量严格一致且集合严格等于 1 到 total_pages
        if len(expanded_pages) != total_pages:
            return None

        indices = [p - 1 for p in expanded_pages]
        if sorted(indices) != list(range(total_pages)):
            return None

        return indices

    @staticmethod
    def validate_custom_sequence(
        seq_str: str,
        total_pages: int
    ) -> Tuple[bool, Optional[List[int]], str]:
        """
        详细校验用户输入的自定义重排序列文本，并返回诊断结果信息。

        @param seq_str 包含连续范围或逗号/空格分隔的自定义序列文本
        @param total_pages 当前文档的总页数
        @return 元组 (是否完全合法, 0-based 页面索引全排列列表（不合法时为 None）, 诊断说明信息)
        """
        if total_pages <= 0:
            return False, None, "文档总页数无效"

        cleaned = seq_str.strip().replace("，", ",")
        if not cleaned:
            return False, None, "请输入有效的页码序列"

        raw_tokens = [t.strip() for t in cleaned.replace(" ", ",").split(",") if t.strip()]
        if not raw_tokens:
            return False, None, "请输入有效的页码序列"

        expanded_pages: List[int] = []
        for token in raw_tokens:
            if "-" in token:
                bounds = token.split("-")
                if len(bounds) != 2:
                    return False, None, f"'{token}' 不是合法的页码范围格式 (例如: 1-5)"
                b0 = bounds[0].strip()
                b1 = bounds[1].strip()
                if not (b0.isdigit() and b1.isdigit()):
                    return False, None, f"范围 '{token}' 包含非数字字符"
                start = int(b0)
                end = int(b1)
                if not (1 <= start <= total_pages):
                    return False, None, f"范围起始页码 {start} 超出当前有效范围 (1 ~ {total_pages})"
                if not (1 <= end <= total_pages):
                    return False, None, f"范围结束页码 {end} 超出当前有效范围 (1 ~ {total_pages})"
                step = 1 if start <= end else -1
                for p in range(start, end + step, step):
                    expanded_pages.append(p)
            else:
                if not token.isdigit():
                    return False, None, f"'{token}' 不是合法的页码数字"
                p = int(token)
                if not (1 <= p <= total_pages):
                    return False, None, f"页码 {p} 超出当前有效范围 (1 ~ {total_pages})"
                expanded_pages.append(p)

        # 检查重复页码
        seen = set()
        duplicates: List[int] = []
        for p in expanded_pages:
            if p in seen:
                if p not in duplicates:
                    duplicates.append(p)
            else:
                seen.add(p)

        all_expected = set(range(1, total_pages + 1))
        missing = sorted(list(all_expected - seen))

        if duplicates:
            dup_str = ", ".join(str(p) for p in sorted(duplicates))
            return False, None, f"以下页码重复输入：第 {dup_str} 页"

        if missing:
            miss_str = ", ".join(str(p) for p in missing[:8])
            if len(missing) > 8:
                miss_str += f" 等共 {len(missing)} 页"
            return False, None, f"已输入 {len(expanded_pages)}/{total_pages} 页，缺少：第 {miss_str} 页"

        if len(expanded_pages) != total_pages:
            return False, None, f"页码总数不符（当前 {len(expanded_pages)} 页，应为 {total_pages} 页）"

        indices = [p - 1 for p in expanded_pages]
        return True, indices, f"序列完整合法（共 {total_pages} 页全排列）"

    @staticmethod
    def generate_default_sequence(total_pages: int) -> List[int]:
        """
        生成从 0 到 total_pages - 1 的默认原始自然升序 0-based 页面索引列表。

        @param total_pages 当前文档总页数
        @return 默认原始顺序的 0-based 页面索引列表
        """
        return list(range(total_pages))

    @staticmethod
    def generate_reversed_sequence(total_pages: int) -> List[int]:
        """
        生成倒序排列（从 total_pages - 1 到 0）的 0-based 页面索引列表。

        @param total_pages 当前文档总页数
        @return 倒序排列的 0-based 页面索引列表
        """
        return list(range(total_pages - 1, -1, -1))

    @staticmethod
    def generate_odd_even_sequence(total_pages: int, odd_first: bool = True) -> List[int]:
        """
        生成奇数页与偶数页分流编排的 0-based 页面索引列表。

        @param total_pages 当前文档总页数
        @param odd_first 为 True 时奇数页（1-based 1, 3, 5... 即 0-based 0, 2, 4...）在前；为 False 时偶数页在前
        @return 奇偶分组后的 0-based 页面索引列表
        """
        odds = [i for i in range(total_pages) if i % 2 == 0]
        evens = [i for i in range(total_pages) if i % 2 == 1]
        return odds + evens if odd_first else evens + odds

    @staticmethod
    def format_action_description(
        source_indices: List[int],
        action: str,
        target_index: Optional[int],
        total_pages: int
    ) -> str:
        """
        生成当前调序操作的易读文本描述。

        @param source_indices 待移动页面 0-based 索引列表
        @param action 移动动作类型 ('after', 'before', 'start', 'end')
        @param target_index 目标页面 0-based 索引
        @param total_pages 文档总页数
        @return 格式化后的动作描述字符串
        """
        src_str = PageReorderHelper.indices_to_range_str(source_indices)
        if not src_str:
            return "未选择待移动页面"

        if action == "start":
            return f"将第 {src_str} 页移至文档最前面 (作为第 1 页)"
        elif action == "end":
            return f"将第 {src_str} 页移至文档最后面 (作为第 {total_pages} 页)"
        elif action == "after" and target_index is not None:
            return f"将第 {src_str} 页插入到第 {target_index + 1} 页之后"
        elif action == "before" and target_index is not None:
            return f"将第 {src_str} 页插入到第 {target_index + 1} 页之前"
        return "未知操作类型"

    @staticmethod
    def format_change_summary(new_order: List[int], source_indices: List[int]) -> str:
        """
        比对原始顺序与重排后顺序，生成源页面移动前后的具体新位置说明。

        @param new_order 重排后的 0-based 页面索引列表
        @param source_indices 移动源页面 0-based 索引列表
        @return 变动说明文字，包含源页面移动前后的具体新位置
        """
        if not source_indices or not new_order:
            return ""

        src_str = PageReorderHelper.indices_to_range_str(source_indices)
        new_positions = [new_order.index(s) for s in source_indices if s in new_order]
        new_pos_str = PageReorderHelper.indices_to_range_str(new_positions)

        return f"原第 {src_str} 页 移动后将位于 第 {new_pos_str} 页"

