"""
应用程序图标生成器模块。
使用 PIL 在本地生成包含多分辨率 (16~256px) 的现代扁平风格 Windows ICO 图标文件。
"""

import os
from PIL import Image, ImageDraw


def generate_app_icon(output_path: str) -> bool:
    """
    生成高分辨率的多尺寸 Windows .ico 应用程序图标文件。

    @param output_path 目标 .ico 文件的输出路径
    @return 生成是否成功
    """
    try:
        # 创建 256x256 高清母图
        size = 256
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        # 绘制圆角矩形背景（科技蓝渐变色底）
        margin = 12
        radius = 48
        draw.rounded_rectangle(
            [margin, margin, size - margin, size - margin],
            radius=radius,
            fill=(37, 99, 235, 255)
        )

        # 绘制中央白色 PDF 标识图形与页面折角
        page_left = 64
        page_top = 48
        page_right = 192
        page_bottom = 208
        corner_cut = 36

        # 页面主轮廓
        polygon = [
            (page_left, page_top),
            (page_right - corner_cut, page_top),
            (page_right, page_top + corner_cut),
            (page_right, page_bottom),
            (page_left, page_bottom)
        ]
        draw.polygon(polygon, fill=(255, 255, 255, 255))

        # 折角阴影三角形
        corner_poly = [
            (page_right - corner_cut, page_top),
            (page_right - corner_cut, page_top + corner_cut),
            (page_right, page_top + corner_cut)
        ]
        draw.polygon(corner_poly, fill=(203, 213, 225, 255))

        # 绘制页面文字横线示意装饰
        line_color = (148, 163, 184, 255)
        for y in [104, 128, 152, 176]:
            draw.line([(80, y), (176, y)], fill=line_color, width=8)

        # 保存为包含多重分辨率的 .ico 文件
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        image.save(
            output_path,
            format="ICO",
            sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
        )
        return os.path.isfile(output_path)
    except Exception:
        return False


if __name__ == "__main__":
    icon_target = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.ico")
    generate_app_icon(icon_target)
    print(f"Icon generated at: {icon_target}")
