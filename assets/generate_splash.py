"""
启动画面图像生成脚本。
使用 PIL 生成现代 Fluent 风格的高分辨率启动封面图 (assets/splash.png)，
用于 PyInstaller C 级 Bootloader 在双击可执行文件瞬间提供原生毫秒级视觉响应。
"""

import os
from PIL import Image, ImageDraw, ImageFont


def generate_splash_image(output_path: str) -> bool:
    """
    生成现代 Fluent 极简风格的高清应用程序启动过渡图。

    @param output_path 目标 PNG 图像文件的绝对输出路径
    @return 生成是否成功，成功返回 True，失败返回 False
    """
    try:
        width, height = 480, 260
        image = Image.new("RGBA", (width, height), (248, 250, 252, 255))
        draw = ImageDraw.Draw(image)

        # 绘制背景卡片（圆角矩形，白底带柔和描边）
        margin = 6
        radius = 16
        draw.rounded_rectangle(
            [margin, margin, width - margin, height - margin],
            radius=radius,
            fill=(255, 255, 255, 255),
            outline=(226, 232, 240, 255),
            width=2
        )

        # 绘制应用主图标（科技蓝圆角矩形底 + 白色文档标记）
        icon_cx = width // 2
        icon_cy = 60
        icon_size = 56
        icon_x0 = icon_cx - icon_size // 2
        icon_y0 = icon_cy - icon_size // 2
        icon_x1 = icon_x0 + icon_size
        icon_y1 = icon_y0 + icon_size

        draw.rounded_rectangle(
            [icon_x0, icon_y0, icon_x1, icon_y1],
            radius=12,
            fill=(37, 99, 235, 255)
        )

        # 绘制中央白色折角文档图标
        doc_x0 = icon_x0 + 14
        doc_y0 = icon_y0 + 10
        doc_x1 = icon_x1 - 14
        doc_y1 = icon_y1 - 10
        cut = 10
        doc_poly = [
            (doc_x0, doc_y0),
            (doc_x1 - cut, doc_y0),
            (doc_x1, doc_y0 + cut),
            (doc_x1, doc_y1),
            (doc_x0, doc_y1)
        ]
        draw.polygon(doc_poly, fill=(255, 255, 255, 255))

        # 尝试加载微软雅黑字体，若无则使用默认字体
        font_title = None
        font_sub = None
        font_status = None
        for font_path in [
            "C:/Windows/Fonts/msyhbd.ttc",
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/simhei.ttf"
        ]:
            if os.path.isfile(font_path):
                try:
                    font_title = ImageFont.truetype(font_path, 22)
                    font_sub = ImageFont.truetype(font_path, 12)
                    font_status = ImageFont.truetype(font_path, 11)
                    break
                except Exception:
                    continue

        if font_title is None:
            font_title = ImageFont.load_default()
            font_sub = ImageFont.load_default()
            font_status = ImageFont.load_default()

        # 绘制应用主标题
        title_text = "PDF 编辑器"
        draw.text((width // 2, 122), title_text, fill=(15, 23, 42, 255), font=font_title, anchor="mm")

        # 绘制应用副标题
        sub_text = "现代轻量 · 高性能矢量渲染"
        draw.text((width // 2, 154), sub_text, fill=(100, 116, 139, 255), font=font_sub, anchor="mm")

        # 绘制装饰进度槽与提示文字
        bar_w = 260
        bar_h = 4
        bar_x0 = (width - bar_w) // 2
        bar_y0 = 190
        draw.rounded_rectangle(
            [bar_x0, bar_y0, bar_x0 + bar_w, bar_y0 + bar_h],
            radius=2,
            fill=(241, 245, 249, 255)
        )
        # 激活态高亮进度指示
        draw.rounded_rectangle(
            [bar_x0, bar_y0, bar_x0 + 120, bar_y0 + bar_h],
            radius=2,
            fill=(37, 99, 235, 255)
        )

        status_text = "正在就绪应用程序..."
        draw.text((width // 2, 216), status_text, fill=(148, 163, 184, 255), font=font_status, anchor="mm")

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        image.save(output_path, "PNG")
        print(f"[√] 启动过渡图生成完成: {output_path}")
        return True
    except Exception as e:
        print(f"[×] 生成启动过渡图失败: {e}")
        return False


if __name__ == "__main__":
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target = os.path.join(base, "assets", "splash.png")
    generate_splash_image(target)
