"""
Turns photo_cropped.png into an ASCII portrait and writes it into
dark_mode.svg and light_mode.svg (inside <g id="ascii-portrait">).

Run it on its own to regenerate the portrait:   python ascii_portrait.py

photo_cropped.png is a grayscale image with an alpha channel:
transparent pixels = background (rendered as spaces).
"""
import re

import cv2
import numpy as np
from PIL import Image

SOURCE = "photo_cropped.png"
CHARSET = "@%#*+=-:. "      # densest -> lightest
COLS = 60                   # portrait width in characters
CHAR_ASPECT = 0.5           # a character cell is ~2x taller than wide
CLAHE_CLIP, CLAHE_GRID = 3.0, 8
SVGS = {                    # file: (text colour, invert)
    "dark_mode.svg": ("#c9d1d9", False),   # light areas = dense characters
    "light_mode.svg": ("#24292f", True),   # dark areas = dense characters
}
X = 15                      # left margin (px)


def load(path=SOURCE):
    img = Image.open(path).convert("LA")
    gray, alpha = (np.array(c) for c in img.split())
    return gray, alpha


def ascii_rows(gray, alpha, invert):
    h, w = gray.shape
    rows = max(1, round(COLS * h / w * CHAR_ASPECT))

    # Local contrast on the face (CLAHE), then shrink to one pixel per character
    eq = cv2.createCLAHE(clipLimit=CLAHE_CLIP, tileGridSize=(CLAHE_GRID, CLAHE_GRID)).apply(gray)
    small = cv2.resize(eq, (COLS, rows), interpolation=cv2.INTER_AREA).astype(np.float64)
    fg = cv2.resize(alpha, (COLS, rows), interpolation=cv2.INTER_AREA) > 127

    # Stretch the full grey range of the subject (1st-99th percentile)
    lo, hi = np.percentile(small[fg], [1, 99]) if fg.any() else (0, 255)
    norm = np.clip((small - lo) / max(hi - lo, 1), 0, 1)
    if invert:
        norm = 1 - norm

    n = len(CHARSET) - 2                          # last char (space) is reserved for the background
    idx = np.rint((1 - norm) * n).astype(int)     # bright -> 0 (densest)
    idx[~fg] = len(CHARSET) - 1
    return ["".join(CHARSET[i] for i in row) for row in idx]


def info_bounds(svg):
    """Top and bottom (px) of the right column, from its tspans' y values."""
    block = re.search(r'<text id="info".*?</text>', svg, re.S).group(0)
    ys = [float(y) for y in re.findall(r'<tspan x="[\d.]+" y="([\d.]+)"', block)]
    size = float(re.search(r'font-size="([\d.]+)px"', svg).group(1))
    return min(ys) - 0.75 * size, max(ys) + 0.25 * size


def block_svg(rows, top, bottom, colour):
    lh = (bottom - top) / len(rows)            # line height: same total height as the right column
    char_w = lh * CHAR_ASPECT                  # cell width
    font = char_w / 0.6                        # monospace advance ~0.6em
    width = char_w * len(rows[0])
    lines = "\n".join(
        f'<tspan x="{X}" y="{top + lh * (i + 0.8):.2f}" textLength="{width:.2f}" '
        f'lengthAdjust="spacingAndGlyphs">{r}</tspan>'
        for i, r in enumerate(rows))
    return (f'<g id="ascii-portrait">\n'
            f'<text x="{X}" y="{top:.2f}" fill="{colour}" font-size="{font:.2f}px" '
            f'font-family="ConsolasFallback,Consolas,\'DejaVu Sans Mono\',\'Courier New\',monospace" '
            f'xml:space="preserve">\n{lines}\n</text>\n</g>')


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
