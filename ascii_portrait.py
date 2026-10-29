"""
photo_cropped.png -> ASCII portrait, written into dark_mode.svg and light_mode.svg
(inside <g id="ascii-portrait">). Text only: one <tspan> per line, one colour.

Regenerate the portrait on its own:   python ascii_portrait.py
(photo_cropped.png comes from crop_photo.py)
"""
import re

import cv2
import numpy as np
from PIL import Image

SOURCE = "photo_cropped.png"
CHARSET = "@%#*+=-:. "      # densest -> lightest
COLS = 48                   # portrait width in characters
CHAR_ASPECT = 0.5           # character cell width / height
CLAHE_CLIP, CLAHE_GRID = 1.8, 4
X = 20                      # left margin (px)
FONT = "Consolas,'DejaVu Sans Mono','Courier New',monospace"
SVGS = {                    # file: (colour, invert)
    "dark_mode.svg": ("#c9d1d9", False),   # light areas = dense characters
    "light_mode.svg": ("#24292f", True),   # dark areas = dense characters
}


def load(path=SOURCE):
    gray, alpha = (np.array(c) for c in Image.open(path).convert("LA").split())
    return gray, alpha


def n_rows(gray):
    h, w = gray.shape
    return max(1, round(COLS * h / w * CHAR_ASPECT))


def ascii_rows(gray, alpha, invert=False):
    rows = n_rows(gray)
    # soften scan grain, then local contrast (CLAHE) on the subject only
    gray = cv2.bilateralFilter(gray, 7, 40, 7)
    fill = int(np.median(gray[alpha > 127])) if (alpha > 127).any() else 0
    work = np.where(alpha > 127, gray, fill).astype(np.uint8)
    eq = cv2.createCLAHE(clipLimit=CLAHE_CLIP, tileGridSize=(CLAHE_GRID, CLAHE_GRID)).apply(work)
    small = cv2.resize(eq, (COLS, rows), interpolation=cv2.INTER_AREA).astype(np.float64)
    fg = cv2.resize(alpha, (COLS, rows), interpolation=cv2.INTER_AREA) > 127

    lo, hi = np.percentile(small[fg], [1, 99]) if fg.any() else (0, 255)   # full grey range
    norm = np.clip((small - lo) / max(hi - lo, 1), 0, 1)
    if invert:
        norm = 1 - norm
    n = len(CHARSET) - 2                       # the space is kept for the background
    idx = np.rint((1 - norm) * n).astype(int)  # bright -> "@"
    idx[~fg] = len(CHARSET) - 1
    lines = ["".join(CHARSET[i] for i in row) for row in idx]
    while lines and not lines[0].strip():      # no empty line above or below
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def portrait_width(n_lines, top, bottom):
    """Width (px) of the portrait block when it spans exactly top..bottom."""
    return COLS * (bottom - top) / n_lines * CHAR_ASPECT


def block_svg(rows, top, bottom, colour):
    lh = (bottom - top) / len(rows)            # same height as the info column
    width = COLS * lh * CHAR_ASPECT
    size = lh * CHAR_ASPECT / 0.6              # monospace advance ~0.6em
    lines = "\n".join(
        f'<tspan x="{X}" y="{top + lh * (i + 0.8):.2f}" textLength="{width:.2f}" '
        f'lengthAdjust="spacingAndGlyphs">{r.ljust(COLS)}</tspan>'
        for i, r in enumerate(rows))
    return (f'<g id="ascii-portrait"><text x="{X}" y="{top:.2f}" fill="{colour}" '
            f'font-family="{FONT}" font-size="{size:.2f}px" xml:space="preserve">\n{lines}\n</text></g>')


def info_bounds(svg):
    """Top / bottom (px) of the info column, read from its data attributes."""
    m = re.search(r'data-top="([\d.]+)" data-bottom="([\d.]+)"', svg)
    return float(m.group(1)), float(m.group(2))


def main():
    gray, alpha = load()
    for filename, (colour, invert) in SVGS.items():
        with open(filename, encoding="utf-8") as f:
            svg = f.read()
        top, bottom = info_bounds(svg)
        block = block_svg(ascii_rows(gray, alpha, invert), top, bottom, colour)
        svg = re.sub(r'<g id="ascii-portrait">.*?</g>', lambda _: block, svg, count=1, flags=re.S)
        with open(filename, "w", encoding="utf-8") as f:
            f.write(svg)
    print("ASCII portrait written to", ", ".join(SVGS))


if __name__ == "__main__":
    main()
