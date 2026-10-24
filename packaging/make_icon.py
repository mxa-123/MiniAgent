# -*- coding: utf-8 -*-
"""用纯标准库生成一个 32x32 的 MiniAgent.ico（无第三方依赖）。

图标含义：青色圆角方块 + 白色「智能体脸」+ 两只眼睛。
输出：assets/miniagent.ico
"""
import os
import struct

W = H = 32
R = 8  # 圆角半径


def in_rounded(x, y, w, h, r):
    if x < r and y < r:
        return (r - x) ** 2 + (r - y) ** 2 <= r * r
    if x >= w - r and y < r:
        return (x - (w - r)) ** 2 + (r - y) ** 2 <= r * r
    if x < r and y >= h - r:
        return (r - x) ** 2 + (y - (h - r)) ** 2 <= r * r
    if x >= w - r and y >= h - r:
        return (x - (w - r)) ** 2 + (y - (h - r)) ** 2 <= r * r
    return True


def build_pixels():
    """返回 BGRA 像素行（自底向上），每个像素 (b,g,r,a)。"""
    # 青色背景
    bg = (0x2B, 0xB6, 0xA8)  # (r,g,b)
    bg_dark = (0x1F, 0x8F, 0x84)
    face = (0xFF, 0xFF, 0xFF)
    eye = (0x22, 0x33, 0x33)
    rows = []
    for y in range(H):
        row = []
        for x in range(W):
            if not in_rounded(x, y, W, H, R):
                row.append((0, 0, 0, 0))
                continue
            # 背景：底部略深，做一点竖向渐变
            t = y / float(H)
            r = int(bg[0] + (bg_dark[0] - bg[0]) * t)
            g = int(bg[1] + (bg_dark[1] - bg[1]) * t)
            b = int(bg[2] + (bg_dark[2] - bg[2]) * t)
            # 白色脸：中心圆
            cx, cy, fr = 16, 15, 9
            if (x - cx) ** 2 + (y - cy) ** 2 <= fr * fr:
                r, g, b = face
                # 眼睛：左右两点
                for ex in (cx - 4, cx + 4):
                    if (x - ex) ** 2 + (y - (cy - 1)) ** 2 <= 2 * 2:
                        r, g, b = eye
            row.append((b, g, r, 255))
        rows.append(row)
    # ICO 像素是自底向上存储
    rows.reverse()
    return rows


def write_ico(path):
    rows = build_pixels()
    # 构造 BITMAPINFOHEADER + 像素数据
    pixel_bytes = bytearray()
    for row in rows:
        for (b, g, r, a) in row:
            pixel_bytes += bytes((b, g, r, a))
    info_header = struct.pack(
        "<IiiHHIIiiII", 40, W, H * 2, 1, 32, 0, len(pixel_bytes), 0, 0, 0, 0
    )
    image = info_header + bytes(pixel_bytes)
    # ICONDIR
    icondir = struct.pack("<HHH", 0, 1, 1)
    # ICONDIRENTRY
    entry = struct.pack(
        "<BBBBHHII", W, H, 0, 0, 1, 32, len(image), 6 + 16
    )
    with open(path, "wb") as f:
        f.write(icondir)
        f.write(entry)
        f.write(image)
    print("已生成图标: %s (%d bytes)" % (path, os.path.getsize(path)))


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "assets", "miniagent.ico")
    write_ico(os.path.abspath(out))
