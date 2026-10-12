#!/usr/bin/env python3
"""Render a test MML symbol palette for the Brain sub-LCD (240x120, XRGB8888).

Usage: mkpalette.py out.raw [out.png]
Writes raw XRGB8888 (240*120*4 bytes) for /dev/fb1, and optionally a PNG preview.
The grid layout is printed so touch coordinates can be matched to cells.
"""
import sys
from PIL import Image, ImageDraw, ImageFont

W, H = 240, 120
COLS, ROWS = 8, 3
ROWS_SYM = [
    ["@", "<", ">", "&", "^", "[", "]", "/"],
    ["{", "}", "#", "+", "-", ".", ",", "%"],
    ["(", ")", "=", ":", "'", '"', "_", "|"],
]
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"

img = Image.new("L", (W, H), 255)
d = ImageDraw.Draw(img)
font = ImageFont.truetype(FONT, 26)
cw, ch = W / COLS, H / ROWS
for r in range(ROWS):
    for c in range(COLS):
        x0, y0 = round(c * cw), round(r * ch)
        x1, y1 = round((c + 1) * cw) - 1, round((r + 1) * ch) - 1
        d.rectangle([x0, y0, x1, y1], outline=0)
        s = ROWS_SYM[r][c]
        d.text(((x0 + x1) / 2, (y0 + y1) / 2), s, font=font, fill=0, anchor="mm")
# corner marker (top-left) to check orientation
d.rectangle([1, 1, 5, 5], fill=0)

raw = bytearray()
for v in img.tobytes():
    raw += bytes((v, v, v, 0))  # B, G, R, X
open(sys.argv[1], "wb").write(raw)
if len(sys.argv) > 2:
    img.resize((W * 3, H * 3), Image.NEAREST).save(sys.argv[2])
print(f"cell {cw:.0f}x{ch:.0f}px; rows: " + " / ".join("".join(r) for r in ROWS_SYM))
