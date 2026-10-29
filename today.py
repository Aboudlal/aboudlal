"""
Updates the neofetch-style card in README.md (selectable text, ```text block
between <!-- STATS:START --> and <!-- STATS:END -->):
  - photo_cropped.png: tight head + shoulders crop of photo.jpg (or the GitHub
    avatar) with the background removed; ascii_portrait.py turns it into text
  - Uptime computed from the birth date
  - GitHub stats (repos, stars, commits, followers) from the GraphQL API
"""
import datetime
import io
import os

import cv2
import numpy as np
import requests
from dateutil import relativedelta
from PIL import Image

import ascii_portrait

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

# --- Portrait crop ---
CROPPED = "photo_cropped.png"
FACE_RATIO = 0.70             # head height / image height
CROP_ASPECT = 0.694           # crop width / height
TOP_MARGIN = 0.02             # space kept above the hair (fraction of crop height)
FACE_BOX = (205, 72, 110, 115)  # manual fallback (x, y, w, h) if no face is detected

WIDTH = 58                    # info column width (characters)

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
    """Crop head + shoulders and remove the background. Returns a grayscale+alpha (LA) PIL image."""
    rgb = np.array(img.convert("RGB"))
    H, W = rgb.shape[:2]
    face = detect_face(rgb)
    if face is None:  # no face: centred square from the top
        face = (int(W * 0.35), int(H * 0.15), int(W * 0.3), int(H * 0.3))
    fx, fy, fw, fh = face

    # Whole head ~ face box + hair above + chin below
    head_top, head_h = fy - 0.55 * fh, 1.75 * fh
    crop_h = head_h / FACE_RATIO
    crop_w = crop_h * CROP_ASPECT
    cx = fx + fw / 2
    x0, y0 = int(cx - crop_w / 2), int(head_top - 0.06 * crop_h)
    final_h = int(crop_h)
    x1, y1 = int(x0 + crop_w), int(y0 + crop_h * 1.4)   # extra room below, trimmed after

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
    alpha = (fg > 0.5).astype(np.uint8) * 255

    # Tighten the top: start just above the first row of hair, keep the same aspect ratio
    rows_fg = np.where((alpha > 0).sum(axis=1) > cw * 0.02)[0]
    top = max(0, int(rows_fg[0] - TOP_MARGIN * final_h)) if len(rows_fg) else 0
    gray, alpha = gray[top:top + final_h], alpha[top:top + final_h]
    if gray.shape[0] < final_h:  # not enough photo below: pad with transparent rows
        missing = final_h - gray.shape[0]
        gray = np.vstack([gray, np.zeros((missing, cw))])
        alpha = np.vstack([alpha, np.zeros((missing, cw), np.uint8)])
    return Image.merge("LA", (Image.fromarray(gray.clip(0, 255).astype(np.uint8)),
                              Image.fromarray(alpha)))


# ------------------------------------------------------------- Info column
def kv(label, value, width):
    dots = "." * max(width - len(label) - len(value) - 3, 1)
    return f"{label}: {dots} {value}"


def info_lines(stats, age):
    lines = []
    for item in INFO:
        if item is None:
            lines.append("")
        elif item == "STATS":
            half = 28
            lines.append(kv("Repos", f"{stats['repos']:,}", half) + " | " +
                         kv("Stars", f"{stats['stars']:,}", WIDTH - half - 3))
            lines.append(kv("Commits", f"{stats['commits']:,}", half) + " | " +
                         kv("Followers", f"{stats['followers']:,}", WIDTH - half - 3))
        elif isinstance(item, str):
            lines.append(f"{item} {'-' * (WIDTH - len(item) - 1)}")
        else:
            label, _, value = item
            if label == "Uptime":
                if age is None:
                    continue
                value = age
            lines.append(kv(label, value, WIDTH))
    return lines


def load_photo(stats):
    if os.path.exists(PHOTO):
        return Image.open(PHOTO)
    return Image.open(io.BytesIO(requests.get(stats["avatar"], timeout=30).content))


if __name__ == "__main__":
    stats = github_stats(USER_NAME)
    age = uptime(BIRTHDAY) if BIRTHDAY else None
    print(f"Uptime: {age} | Repos: {stats['repos']} | Stars: {stats['stars']} | "
          f"Commits: {stats['commits']} | Followers: {stats['followers']}")

    portrait(load_photo(stats)).save(CROPPED)
    rows = ascii_portrait.ascii_rows(*ascii_portrait.load(CROPPED))
    ascii_portrait.write_readme(ascii_portrait.compose(rows, info_lines(stats, age)))
    print("README.md updated.")
