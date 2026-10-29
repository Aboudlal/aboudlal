"""
Builds dark_mode.svg and light_mode.svg (neofetch-style profile card).
  - ASCII portrait from photo.jpg (or the GitHub profile picture):
    tight head + shoulders crop, background removed, contrast/brightness boost
  - Uptime computed from the birth date
  - GitHub stats (repos, stars, commits, followers) from the GraphQL API
Every dynamic value has an id in the SVG (age_data, repo_data, ascii_0, ...).
"""
import datetime
import io
import os
from xml.sax.saxutils import escape

import cv2
import numpy as np
import requests
from dateutil import relativedelta
from PIL import Image, ImageEnhance

# =========================== SETTINGS ===========================
USER_NAME = "aboudlal"
BIRTHDAY = None  # e.g. datetime.date(1990, 1, 31) -> shows the Uptime line
PHOTO = "photo.jpg"  # used if present, otherwise the GitHub avatar

INFO = [  # (label, id, value)  -- None = blank line, str = section header
    "abdellah@boudlal",
    ("Role", "role", "Data Analyst"),
    ("Host", "host", "Elite Visa (Founder, since 2018)"),
    ("Uptime", "age_data", None),
    None,
    ("Languages", "languages", "SQL, Python, DAX"),
    ("Tools", "tools", "Power BI, Excel, Tableau"),
    ("Libraries", "libraries", "Pandas, NumPy, Matplotlib"),
    ("Real", "real", "French, Arabic, English"),
    ("Focus", "focus", "Dashboards, KPIs, data cleaning, reporting"),
    None,
    "- Contact",
    ("Website", "website", "abdellahboudlal.com"),
    ("LinkedIn", "linkedin", "aboudlal"),
    ("GitHub", "github", "aboudlal"),
    None,
    "- GitHub Stats",
    "STATS",
]

# --- Portrait ---
ASCII_STYLE = "braille"       # "classic" or "braille"
ASCII_COLS, ASCII_ROWS = 60, 40
CHARSET = "@%#*+=-:. "        # densest -> lightest (bright pixels = dense chars)
FACE_RATIO = 0.70             # head height / image height
CONTRAST, BRIGHTNESS = 1.40, 1.15
FACE_BOX = (205, 72, 110, 115)            # manual fallback (x, y, w, h) if no face is detected

# --- Layout (px) ---
ASCII_FONT, ASCII_LH = 10.5, 12.5   # small font for the portrait block
ASCII_X, ASCII_Y0 = 15, 25
ASCII_WIDTH_PX = 378                # every portrait line is stretched to this width
INFO_X, INFO_Y0, INFO_LH, INFO_FONT = 420, 30, 20, 16
CARD_W, CARD_H = 1000, 530
WIDTH = 58                          # right column width (characters)

THEMES = {
    "dark_mode.svg":  dict(bg="#161b22", text="#c9d1d9", key="#ffa657", value="#a5d6ff", cc="#616e7f", border="#30363d"),
    "light_mode.svg": dict(bg="#f6f8fa", text="#24292f", key="#953800", value="#0a3069", cc="#c2cfde", border="#d0d7de"),
}
# ================================================================

TOKEN = os.environ.get("ACCESS_TOKEN") or os.environ.get("GITHUB_TOKEN")
HEADERS = {"authorization": f"bearer {TOKEN}"}


# ------------------------------------------------------------- GitHub
def graphql(query, variables):
    r = requests.post("https://api.github.com/graphql",
                      json={"query": query, "variables": variables},
                      headers=HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()
    if "errors" in data:
        raise RuntimeError(data["errors"])
    return data["data"]


def github_stats(login):
    query = """
    query($login: String!, $cursor: String) {
      user(login: $login) {
        avatarUrl(size: 460)
        followers { totalCount }
        contributionsCollection { contributionYears }
        repositories(first: 100, after: $cursor, ownerAffiliations: OWNER) {
          totalCount
          pageInfo { hasNextPage endCursor }
          nodes { stargazerCount }
        }
      }
    }"""
    cursor, stars = None, 0
    while True:
        user = graphql(query, {"login": login, "cursor": cursor})["user"]
        repos = user["repositories"]
        stars += sum(n["stargazerCount"] for n in repos["nodes"])
        if not repos["pageInfo"]["hasNextPage"]:
            break
        cursor = repos["pageInfo"]["endCursor"]

    commits_query = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          totalCommitContributions
          restrictedContributionsCount
        }
      }
    }"""
    commits = 0
    for y in user["contributionsCollection"]["contributionYears"]:
        c = graphql(commits_query, {"login": login,
                                    "from": f"{y}-01-01T00:00:00Z",
                                    "to": f"{y}-12-31T23:59:59Z"})["user"]["contributionsCollection"]
        commits += c["totalCommitContributions"] + c["restrictedContributionsCount"]

    return dict(repos=repos["totalCount"], stars=stars, commits=commits,
                followers=user["followers"]["totalCount"], avatar=user["avatarUrl"])


def uptime(birthday):
    d = relativedelta.relativedelta(datetime.date.today(), birthday)
    unit = lambda n, w: f"{n} {w}{'' if n == 1 else 's'}"
    return ", ".join([unit(d.years, "year"), unit(d.months, "month"), unit(d.days, "day")])


# ------------------------------------------------------------- Portrait
def detect_face(rgb):
    """Largest frontal face (x, y, w, h), or FACE_BOX, or None."""
    try:
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40))
        if len(faces):
            return tuple(int(v) for v in max(faces, key=lambda f: f[2] * f[3]))
    except Exception as e:  # cascade missing, etc.
        print("Face detection unavailable:", e)
    return FACE_BOX


def portrait(img):
    """Crop head + shoulders, remove background (black), boost contrast/brightness. Returns grayscale PIL image."""
    rgb = np.array(img.convert("RGB"))
    H, W = rgb.shape[:2]
    face = detect_face(rgb)
    if face is None:  # no face: centred square from the top
        face = (int(W * 0.35), int(H * 0.15), int(W * 0.3), int(H * 0.3))
    fx, fy, fw, fh = face

    # Whole head ~ face box + hair above + chin below
    head_top, head_h = fy - 0.55 * fh, 1.75 * fh
    crop_h = head_h / FACE_RATIO
    aspect = ASCII_WIDTH_PX / (ASCII_ROWS * ASCII_LH)       # portrait block width / height
    crop_w = crop_h * aspect
    cx = fx + fw / 2
    x0, y0 = int(cx - crop_w / 2), int(head_top - 0.06 * crop_h)
    x1, y1 = int(x0 + crop_w), int(y0 + crop_h)

    # Pad with edge pixels if the crop goes outside the photo
    pad = max(0, -x0, -y0, x1 - W, y1 - H)
    if pad:
        rgb = cv2.copyMakeBorder(rgb, pad, pad, pad, pad, cv2.BORDER_REPLICATE)
        x0, y0, x1, y1 = x0 + pad, y0 + pad, x1 + pad, y1 + pad
        fx, fy = fx + pad, fy + pad
    crop = np.ascontiguousarray(rgb[y0:y1, x0:x1])
    ch, cw = crop.shape[:2]

    # Background removal with GrabCut, seeded by the face position
    mask = np.full((ch, cw), cv2.GC_PR_BGD, np.uint8)
    hx0, hx1 = int(fx - x0 - 0.15 * fw), int(fx - x0 + 1.15 * fw)
    hy0 = int(fy - y0 - 0.55 * fh)
    mask[max(hy0, 0):, max(hx0, 0):min(hx1, cw)] = cv2.GC_PR_FGD           # head + neck column
    mask[int(fy - y0 + 1.5 * fh):, int(cw * 0.08):int(cw * 0.92)] = cv2.GC_PR_FGD  # shoulders
    mask[int(fy - y0 + 0.15 * fh):int(fy - y0 + 0.9 * fh),
         int(fx - x0 + 0.2 * fw):int(fx - x0 + 0.8 * fw)] = cv2.GC_FGD      # sure: centre of face
    mask[:, :2] = mask[:, -2:] = cv2.GC_BGD                                  # sure: side borders
    mask[:2, :] = cv2.GC_BGD
    try:
        bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
        cv2.grabCut(cv2.cvtColor(crop, cv2.COLOR_RGB2BGR), mask, None, bgd, fgd, 5, cv2.GC_INIT_WITH_MASK)
        fg = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 1.0, 0.0)
        fg = cv2.GaussianBlur(fg, (5, 5), 0)
    except cv2.error as e:
        print("Background removal failed:", e)
        fg = np.ones((ch, cw))

    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY).astype(np.float64) * fg  # background -> black
    out = Image.fromarray(gray.clip(0, 255).astype(np.uint8))
    out = ImageEnhance.Contrast(out).enhance(CONTRAST)
    out = ImageEnhance.Brightness(out).enhance(BRIGHTNESS)
    # keep the background pure black after the enhancements
    out = Image.fromarray((np.array(out) * (fg > 0.5)).astype(np.uint8))
    return out


def ascii_classic(gray):
    small = np.array(gray.resize((ASCII_COLS, ASCII_ROWS), Image.LANCZOS), dtype=np.float64)
    n = len(CHARSET) - 1
    idx = np.rint((1 - small / 255) * n).astype(int)          # bright -> index 0 (densest)
    return ["".join(CHARSET[i] for i in row) for row in idx]


def ascii_braille(gray):
    w, h = ASCII_COLS * 2, ASCII_ROWS * 4
    dots = np.array(gray.resize((w, h), Image.LANCZOS).convert("1"))  # Floyd-Steinberg dithering
    bits = [(0, 0, 0x01), (0, 1, 0x02), (0, 2, 0x04), (1, 0, 0x08),
            (1, 1, 0x10), (1, 2, 0x20), (0, 3, 0x40), (1, 3, 0x80)]
    rows = []
    for r in range(ASCII_ROWS):
        line = ""
        for c in range(ASCII_COLS):
            code = sum(b for dx, dy, b in bits if dots[r * 4 + dy, c * 2 + dx])
            line += chr(0x2800 + code)
        rows.append(line)
    return rows


# ------------------------------------------------------------- SVG
def kv(label, ident, value, width):
    dots = " " + "." * max(width - len(label) - len(value) - 3, 1) + " "
    return (f'<tspan class="key">{escape(label)}</tspan>:'
            f'<tspan class="cc" id="{ident}_dots">{dots}</tspan>'
            f'<tspan class="value" id="{ident}">{escape(value)}</tspan>')


def info_lines(stats, age):
    lines = []
    for item in INFO:
        if item is None:
            lines.append("")
        elif item == "STATS":
            half = 28
            lines.append(kv("Repos", "repo_data", f"{stats['repos']:,}", half) + " | " +
                         kv("Stars", "star_data", f"{stats['stars']:,}", WIDTH - half - 3))
            lines.append(kv("Commits", "commit_data", f"{stats['commits']:,}", half) + " | " +
                         kv("Followers", "follower_data", f"{stats['followers']:,}", WIDTH - half - 3))
        elif isinstance(item, str):
            lines.append(f'{escape(item)} <tspan class="cc">{"-" * (WIDTH - len(item) - 1)}</tspan>')
        else:
            label, ident, value = item
            if ident == "age_data":
                if age is None:
                    continue
                value = age
            lines.append(kv(label, ident, value, WIDTH))
    return lines


def render(t, ascii_rows, lines):
    rows_per_card = (CARD_H - INFO_Y0) // INFO_LH
    top = INFO_Y0 + (rows_per_card - len(lines)) // 2 * INFO_LH
    art = "\n".join(
        f'<tspan x="{ASCII_X}" y="{ASCII_Y0 + i * ASCII_LH}" id="ascii_{i}" '
        f'textLength="{ASCII_WIDTH_PX}" lengthAdjust="spacingAndGlyphs">{escape(r)}</tspan>'
        for i, r in enumerate(ascii_rows))
    info = "\n".join(f'<tspan x="{INFO_X}" y="{top + i * INFO_LH}">{l}</tspan>' for i, l in enumerate(lines))
    return f"""<?xml version='1.0' encoding='UTF-8'?>
<svg xmlns="http://www.w3.org/2000/svg" font-family="ConsolasFallback,Consolas,'DejaVu Sans Mono','Courier New',monospace" width="{CARD_W}px" height="{CARD_H}px" font-size="{INFO_FONT}px">
<style>
@font-face {{ src: local('Consolas'), local('Consolas Bold'); font-family: 'ConsolasFallback'; font-display: swap; -webkit-size-adjust: 109%; size-adjust: 109%; }}
.key {{fill: {t['key']};}}
.value {{fill: {t['value']};}}
.cc {{fill: {t['cc']};}}
.ascii {{font-size: {ASCII_FONT}px; font-family: 'DejaVu Sans Mono',Consolas,'Courier New',monospace;}}
text, tspan {{white-space: pre;}}
</style>
<rect width="{CARD_W}px" height="{CARD_H}px" fill="{t['bg']}" stroke="{t['border']}" rx="15"/>
<text class="ascii" x="{ASCII_X}" y="{ASCII_Y0}" fill="{t['text']}" xml:space="preserve">
{art}
</text>
<text x="{INFO_X}" y="{INFO_Y0}" fill="{t['text']}" xml:space="preserve">
{info}
</text>
</svg>
"""


def load_photo(stats):
    if os.path.exists(PHOTO):
        return Image.open(PHOTO)
    return Image.open(io.BytesIO(requests.get(stats["avatar"], timeout=30).content))


if __name__ == "__main__":
    stats = github_stats(USER_NAME)
    age = uptime(BIRTHDAY) if BIRTHDAY else None
    print(f"Uptime: {age} | Repos: {stats['repos']} | Stars: {stats['stars']} | "
          f"Commits: {stats['commits']} | Followers: {stats['followers']}")

    gray = portrait(load_photo(stats))
    rows = ascii_braille(gray) if ASCII_STYLE == "braille" else ascii_classic(gray)
    lines = info_lines(stats, age)
    for filename, theme in THEMES.items():
        with open(filename, "w", encoding="utf-8") as f:
            f.write(render(theme, rows, lines))
    print("SVG files updated.")
