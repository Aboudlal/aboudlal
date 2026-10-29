"""
Builds dark_mode.svg and light_mode.svg (neofetch-style profile card).
  - ASCII portrait generated from the GitHub profile picture
  - Uptime computed from the birth date
  - GitHub stats (repos, stars, commits, followers) from the GraphQL API
Every dynamic value has an id in the SVG (age_data, repo_data, ...).
"""
import datetime
import io
import os
from xml.sax.saxutils import escape

import requests
from dateutil import relativedelta
from PIL import Image, ImageOps

# =========================== SETTINGS ===========================
USER_NAME = "aboudlal"
BIRTHDAY = None  # e.g. datetime.date(1990, 1, 31) -> shows the Uptime line

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

ASCII_COLS, ROWS = 40, 25          # portrait size (characters x lines)
CROP = (0.12, 0.0, 0.88, 1.0)      # part of the avatar to keep (left, top, right, bottom)
RAMP = " .:-=+*#%@"                # light -> dense characters
WIDTH = 58                         # right column width (characters)

THEMES = {
    "dark_mode.svg":  dict(bg="#161b22", text="#c9d1d9", key="#ffa657", value="#a5d6ff", cc="#616e7f", border="#30363d", invert=False),
    "light_mode.svg": dict(bg="#f6f8fa", text="#24292f", key="#953800", value="#0a3069", cc="#c2cfde", border="#d0d7de", invert=True),
}
# ================================================================

TOKEN = os.environ.get("ACCESS_TOKEN") or os.environ.get("GITHUB_TOKEN")
HEADERS = {"authorization": f"bearer {TOKEN}"}


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
        avatarUrl(size: 400)
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


def ascii_portrait(img, invert):
    img = ImageOps.grayscale(img)
    w, h = img.size
    img = img.crop((int(CROP[0] * w), int(CROP[1] * h), int(CROP[2] * w), int(CROP[3] * h)))
    img = ImageOps.autocontrast(img.resize((ASCII_COLS, ROWS), Image.LANCZOS), cutoff=2)
    if invert:
        img = ImageOps.invert(img)
    n = len(RAMP) - 1
    return ["".join(RAMP[round(img.getpixel((x, y)) / 255 * n)] for x in range(ASCII_COLS))
            for y in range(ROWS)]


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


def render(theme, ascii_rows, lines):
    x_ascii, x_info, y0, lh = 15, 420, 30, 20
    height = y0 + ROWS * lh
    top = y0 + (ROWS - len(lines)) // 2 * lh
    art = "\n".join(f'<tspan x="{x_ascii}" y="{y0 + i * lh}" id="ascii_{i}">{escape(r)}</tspan>'
                    for i, r in enumerate(ascii_rows))
    info = "\n".join(f'<tspan x="{x_info}" y="{top + i * lh}">{l}</tspan>' for i, l in enumerate(lines))
    t = theme
    return f"""<?xml version='1.0' encoding='UTF-8'?>
<svg xmlns="http://www.w3.org/2000/svg" font-family="ConsolasFallback,Consolas,'DejaVu Sans Mono','Courier New',monospace" width="1000px" height="{height}px" font-size="16px">
<style>
@font-face {{ src: local('Consolas'), local('Consolas Bold'); font-family: 'ConsolasFallback'; font-display: swap; -webkit-size-adjust: 109%; size-adjust: 109%; }}
.key {{fill: {t['key']};}}
.value {{fill: {t['value']};}}
.cc {{fill: {t['cc']};}}
text, tspan {{white-space: pre;}}
</style>
<rect width="1000px" height="{height}px" fill="{t['bg']}" stroke="{t['border']}" rx="15"/>
<text x="{x_ascii}" y="{y0}" fill="{t['text']}" xml:space="preserve">
{art}
</text>
<text x="{x_info}" y="{y0}" fill="{t['text']}" xml:space="preserve">
{info}
</text>
</svg>
"""


if __name__ == "__main__":
    stats = github_stats(USER_NAME)
    age = uptime(BIRTHDAY) if BIRTHDAY else None
    print(f"Uptime: {age} | Repos: {stats['repos']} | Stars: {stats['stars']} | "
          f"Commits: {stats['commits']} | Followers: {stats['followers']}")

    avatar = Image.open(io.BytesIO(requests.get(stats["avatar"], timeout=30).content))
    lines = info_lines(stats, age)
    for filename, theme in THEMES.items():
        svg = render(theme, ascii_portrait(avatar, theme["invert"]), lines)
        with open(filename, "w", encoding="utf-8") as f:
            f.write(svg)
    print("SVG files updated.")
