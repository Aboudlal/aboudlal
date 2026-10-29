"""
Turns photo_cropped.png into an ASCII portrait and writes it into README.md,
on the left of the info column, inside a ```text code block placed between
<!-- STATS:START --> and <!-- STATS:END -->.

Run it on its own to regenerate only the portrait:   python ascii_portrait.py
(the info column already in README.md is kept as is)

photo_cropped.png is a grayscale image with an alpha channel:
transparent pixels = background (rendered as spaces).
"""
import re

import cv2
import numpy as np
from PIL import Image

SOURCE = "photo_cropped.png"
README = "README.md"
START, END = "<!-- STATS:START -->", "<!-- STATS:END -->"

CHARSET = "@%#*+=-:. "      # densest -> lightest
COLS = 50                   # portrait width in characters
CHAR_ASPECT = 0.38          # width / height of a character in GitHub code blocks (6.5px x 17.3px)
GAP = 3                     # spaces between the portrait and the info column
INVERT = False              # False: light areas = dense characters (made for GitHub dark mode)
CLAHE_CLIP, CLAHE_GRID = 3.0, 6


def load(path=SOURCE):
    img = Image.open(path).convert("LA")
    gray, alpha = (np.array(c) for c in img.split())
    return gray, alpha


def ascii_rows(gray, alpha, invert=INVERT):
    h, w = gray.shape
    rows = max(1, round(COLS * h / w * CHAR_ASPECT))

    # Local contrast (CLAHE) on the subject only, so eyes, nose and beard stand out
    fill = int(np.median(gray[alpha > 127])) if (alpha > 127).any() else 0
    work = np.where(alpha > 127, gray, fill).astype(np.uint8)   # neutral background: no halo
    eq = cv2.createCLAHE(clipLimit=CLAHE_CLIP, tileGridSize=(CLAHE_GRID, CLAHE_GRID)).apply(work)
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


def compose(portrait, info):
    """Portrait on the left, info column vertically centred on the right, as a ```text block."""
    top = max(0, (len(portrait) - len(info)) // 2)
    height = max(len(portrait), top + len(info))
    portrait = portrait + [""] * (height - len(portrait))
    info = [""] * top + info + [""] * (height - top - len(info))
    lines = [(p.ljust(COLS) + " " * GAP + i).rstrip() for p, i in zip(portrait, info)]
    return "```text\n" + "\n".join(lines) + "\n```"


def read_info(path=README):
    """Info column currently in README.md (everything right of the portrait)."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    block = re.search(re.escape(START) + r"\s*```text\n(.*?)\n```", text, re.S)
    if not block:
        return []
    info = [line[COLS + GAP:] for line in block.group(1).split("\n")]
    while info and not info[0].strip():
        info.pop(0)
    while info and not info[-1].strip():
        info.pop()
    return info


def write_readme(block, path=README):
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        text = ""
    new = f"{START}\n{block}\n{END}"
    if START in text and END in text:
        text = re.sub(re.escape(START) + r".*?" + re.escape(END), lambda _: new, text, count=1, flags=re.S)
    else:
        text = new + "\n" + text
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def main():
    gray, alpha = load()
    write_readme(compose(ascii_rows(gray, alpha), read_info()))
    print("ASCII portrait written to", README)


if __name__ == "__main__":
    main()
