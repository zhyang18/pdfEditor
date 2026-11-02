"""
生成随附的示例文档与图片。
供用户首次启动体验编辑、插入图片、重排页面时直接取用。
"""

import os
import pymupdf
from PIL import Image, ImageDraw


def create_demo_assets(target_dir: str) -> None:
    """
    在指定目录下生成样例 PDF 与样例配图。

    @param target_dir 生成目标目录
    """
    pdf_path = os.path.join(target_dir, "示例合同文档.pdf")
    img_path = os.path.join(target_dir, "示例印章图.png")

    # 1. 生成 4 页具有不同背景与排版样式的示例 PDF
    doc = pymupdf.open()
    pages_data = [
        ("合同首页 - 合作框架协议", "甲方：科技创新有限责任公司\n乙方：数字化运营服务集团\n\n日期：2026年11月\n版本：V2.0 终稿"),
        ("第二页 - 双方权利与义务", "1. 甲方负责提供基础数据与需求说明；\n2. 乙方负责系统的全流程设计、实施与测试交付；\n3. 双方应对商业机密保持严格保密义务。"),
        ("第三页 - 验收标准与付款节点", "阶段一：系统架构设计评审通过（付款 30%）；\n阶段二：核心功能全部验证通过（付款 50%）；\n阶段三：系统正式部署上线并验收（付款 20%）。"),
        ("第四页 - 签字盖章页", "甲方代表签字：__________________    日期：____年__月__日\n\n乙方代表签字：__________________    日期：____年__月__日\n\n（请在下方空白处插入公章图片）"),
    ]

    for title, content in pages_data:
        page = doc.new_page(width=595.0, height=842.0)
        # 页面标题
        page.insert_text(pymupdf.Point(60, 100), title, fontsize=20, fontname="china-s", color=(0.15, 0.25, 0.55))
        # 水平分割线
        page.draw_line(pymupdf.Point(60, 120), pymupdf.Point(535, 120), color=(0.8, 0.85, 0.9), width=1.5)
        # 正文内容
        page.insert_textbox(pymupdf.Rect(60, 150, 535, 750), content, fontsize=13, fontname="china-s", color=(0.2, 0.2, 0.2))
        # 页脚
        page.insert_text(pymupdf.Point(260, 800), "PDF Editor 示例文档", fontsize=10, fontname="china-s", color=(0.6, 0.6, 0.6))

    doc.save(pdf_path, garbage=4, deflate=True)
    doc.close()

    # 2. 生成一个透明背景的红色印章样例图片
    img = Image.new("RGBA", (240, 240), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # 红色双圆环
    draw.ellipse([10, 10, 230, 230], outline=(220, 38, 38, 240), width=6)
    draw.ellipse([18, 18, 222, 222], outline=(220, 38, 38, 180), width=2)
    # 中央五角星
    center = (120, 120)
    draw.regular_polygon((center, 30), n_sides=5, fill=(220, 38, 38, 230))
    img.save(img_path, "PNG")

    print(f"Demo PDF created: {pdf_path}")
    print(f"Demo Stamp created: {img_path}")


if __name__ == "__main__":
    create_demo_assets(os.path.dirname(os.path.abspath(__file__)))
