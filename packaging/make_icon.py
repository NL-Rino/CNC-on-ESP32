"""Vẽ biểu tượng pipecut.ico: đoạn ống trên nền xanh, vết cắt phát sáng.

Vẽ bằng mã (Pillow) thay vì lưu tệp ảnh nhị phân trong kho mã.
"""

import os
import sys

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))


def draw(size: int = 256) -> Image.Image:
    s = size / 256.0
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    bg = Image.new("RGBA", (size, size))
    top, bottom = (58, 118, 196), (22, 52, 104)          # xanh kiểu FreeCAD
    px = bg.load()
    for y in range(size):
        t = y / max(1, size - 1)
        c = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        for x in range(size):
            px[x, y] = c + (255,)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=int(48 * s), fill=255)
    img.paste(bg, (0, 0), mask)

    d = ImageDraw.Draw(img)
    # thân ống nằm chéo: hình bình hành + hai đầu elip
    x0, y0, x1, y1, r = 44 * s, 150 * s, 196 * s, 78 * s, 30 * s
    body = [(x0, y0 - r), (x1, y1 - r), (x1, y1 + r), (x0, y0 + r)]
    d.polygon(body, fill=(206, 214, 224, 255))
    d.line([(x0, y0 - r), (x1, y1 - r)], fill=(245, 248, 252, 255), width=max(1, int(4 * s)))
    d.line([(x0, y0 + r), (x1, y1 + r)], fill=(120, 132, 148, 255), width=max(1, int(4 * s)))
    d.ellipse([x1 - 14 * s, y1 - r, x1 + 14 * s, y1 + r], fill=(150, 162, 178, 255))
    d.ellipse([x1 - 7 * s, y1 - r * 0.62, x1 + 7 * s, y1 + r * 0.62], fill=(40, 60, 90, 255))
    d.ellipse([x0 - 14 * s, y0 - r, x0 + 14 * s, y0 + r], fill=(226, 232, 240, 255))

    # vết cắt vòng quanh ống, phát sáng cam
    cx, cy = (x0 + x1) / 2 + 8 * s, (y0 + y1) / 2 - 4 * s
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    g.ellipse([cx - 16 * s, cy - r - 6 * s, cx + 16 * s, cy + r + 6 * s],
              outline=(255, 140, 30, 220), width=max(2, int(12 * s)))
    glow = glow.filter(ImageFilter.GaussianBlur(max(1, 5 * s)))
    img = Image.alpha_composite(img, glow)
    d = ImageDraw.Draw(img)
    d.arc([cx - 13 * s, cy - r - 2 * s, cx + 13 * s, cy + r + 2 * s], 270, 90,
          fill=(255, 236, 170, 255), width=max(1, int(5 * s)))
    # mỏ cắt và tia
    tx = cx + 6 * s
    d.polygon([(tx - 12 * s, 14 * s), (tx + 12 * s, 14 * s), (tx + 6 * s, 52 * s), (tx - 6 * s, 52 * s)],
              fill=(236, 240, 245, 255))
    d.line([(tx, 54 * s), (tx, cy - r)], fill=(255, 210, 120, 255), width=max(1, int(5 * s)))
    return img


def main(out: str = os.path.join(HERE, "pipecut.ico")) -> None:
    big = draw(256)
    big.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    big.save(os.path.splitext(out)[0] + ".png")
    print(f"Đã vẽ {out}")


if __name__ == "__main__":
    main(*sys.argv[1:])
