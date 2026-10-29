"""
photo_cropped.png -> ASCII portrait, written in two places:
  1. dark_mode.svg / light_mode.svg  (coloured card, inside <g id="ascii-portrait">)
  2. README.md, text version          (```text block between <!-- PROFILE:START --> and <!-- PROFILE:END -->)

Regenerate the portrait on its own:   python ascii_portrait.py
(the info columns already in the SVGs / README are kept; photo_cropped.png comes from crop_photo.py)
"""
import os
import re

import cv2
import numpy as np
from PIL import Image

SOURCE, README = "photo_cropped.png", "README.md"
START, END = "<!-- PROFILE:START -->", "<!-- PROFILE:END -->"
CHARSET = "@%#*+=-:. "      # densest -> lightest
CLAHE_CLIP, CLAHE_GRID = 1.8, 4

# SVG card
SVG_COLS, SVG_ASPECT = 48, 0.5      # width in characters, character width / line height
X = 20                              # left margin (px)
FONT = "Consolas,'DejaVu Sans Mono','Courier New',monospace"
SVGS = {                            # file: (colour, invert)
    "dark_mode.svg": ("#c9d1d9", False),   # light areas = dense characters
    "light_mode.svg": ("#24292f", True),   # dark areas = dense characters
}

# README text version (max 100 characters wide: 37 + 3 + 60)
TXT_COLS, TXT_ASPECT, GAP = 37, 0.38, 3   # GitHub code blocks: ~6.5 x 17.3 px per character


def load(path=SOURCE):
    gray, alpha = (np.array(c) for c in Image.open(path).convert("LA").split())
    return gray, alpha


def ascii_rows(gray, alpha, cols=SVG_COLS, aspect=SVG_ASPECT, invert=False):
    h, w = gray.shape
    rows = max(1, round(cols * h / w * aspect))
    # soften scan grain, then local contrast (CLAHE) on the subject only
    gray = cv2.bilateralFilter(gray, 7, 40, 7)
    fill = int(np.median(gray[alpha > 127])) if (alpha > 127).any() else 0
    work = np.where(alpha > 127, gray, fill).astype(np.uint8)
    eq = cv2.createCLAHE(clipLimit=CLAHE_CLIP, tileGridSize=(CLAHE_GRID, CLAHE_GRID)).apply(work)
    small = cv2.resize(eq, (cols, rows), interpolation=cv2.INTER_AREA).astype(np.float64)
    fg = cv2.resize(alpha, (cols, rows), interpolation=cv2.INTER_AREA) > 127

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


# ------------------------------------------------------------- SVG
def portrait_width(n_lines, top, bottom):
    """Width (px) of the SVG portrait block when it spans exactly top..bottom."""
    return SVG_COLS * (bottom - top) / n_lines * SVG_ASPECT


def block_svg(rows, top, bottom, colour):
    lh = (bottom - top) / len(rows)            # same height as the info column
    width = SVG_COLS * lh * SVG_ASPECT
    size = lh * SVG_ASPECT / 0.6               # monospace advance ~0.6em
    lines = "\n".join(
        f'<tspan x="{X}" y="{top + lh * (i + 0.8):.2f}" textLength="{width:.2f}" '
        f'lengthAdjust="spacingAndGlyphs">{r.ljust(SVG_COLS)}</tspan>'
        for i, r in enumerate(rows))
    return (f'<g id="ascii-portrait"><text x="{X}" y="{top:.2f}" fill="{colour}" '
            f'font-family="{FONT}" font-size="{size:.2f}px" xml:space="preserve">\n{lines}\n</text></g>')


def write_svgs(gray, alpha):
    for filename, (colour, invert) in SVGS.items():
        if not os.path.exists(filename):   # SVG cards are optional
            continue
        with open(filename, encoding="utf-8") as f:
            svg = f.read()
        m = re.search(r'data-top="([\d.]+)" data-bottom="([\d.]+)"', svg)
        top, bottom = float(m.group(1)), float(m.group(2))
        block = block_svg(ascii_rows(gray, alpha, invert=invert), top, bottom, colour)
        svg = re.sub(r'<g id="ascii-portrait">.*?</g>', lambda _: block, svg, count=1, flags=re.S)
        with open(filename, "w", encoding="utf-8") as f:
            f.write(svg)


# ------------------------------------------------------------- README text version
def text_rows(gray, alpha):
    return ascii_rows(gray, alpha, cols=TXT_COLS, aspect=TXT_ASPECT)


def compose(portrait, info):
    """Portrait and info side by side, both starting on the first line."""
    height = max(len(portrait), len(info))
    portrait = portrait + [""] * (height - len(portrait))
    info = info + [""] * (height - len(info))
    lines = [(p.ljust(TXT_COLS) + " " * GAP + i).rstrip() for p, i in zip(portrait, info)]
    return "```text\n" + "\n".join(lines) + "\n```"


def read_info(path=README):
    """Info column currently in the README text block."""
    with open(path, encoding="utf-8") as f:
        m = re.search(re.escape(START) + r"\s*```text\n(.*?)\n```", f.read(), re.S)
    if not m:
        return []
    info = [line[TXT_COLS + GAP:] for line in m.group(1).split("\n")]
    while info and not info[-1].strip():
        info.pop()
    return info


def write_readme(block, path=README):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    new = f"{START}\n{block}\n{END}"
    text = re.sub(re.escape(START) + r".*?" + re.escape(END), lambda _: new, text, count=1, flags=re.S)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def main():
    gray, alpha = load()
    write_svgs(gray, alpha)
    write_readme(compose(text_rows(gray, alpha), read_info()))
    print("ASCII portrait written to", ", ".join(SVGS), "and", README)


if __name__ == "__main__":
    main()
