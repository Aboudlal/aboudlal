"""
Builds the neofetch-style profile card:
  - dark_mode.svg / light_mode.svg: coloured card shown in README.md
  - README.md: selectable text version (```text block between
    <!-- PROFILE:START --> and <!-- PROFILE:END -->), rebuilt on every run so
    values stay aligned on the right edge
ASCII portrait from photo_cropped.png (see ascii_portrait.py), live GitHub stats.

Stats come from the GitHub GraphQL API (ACCESS_TOKEN secret, or the workflow's
built-in token). Every dynamic value has an id in the SVG (age_data, repo_data,
contrib_data, star_data, commit_data, follower_data, loc_data, loc_add, loc_del).
"""
import datetime
import os
from xml.sax.saxutils import escape

import requests
from dateutil import relativedelta

import ascii_portrait

# =========================== SETTINGS ===========================
USER_NAME = "aboudlal"
BIRTHDAY = None                 # e.g. datetime.date(1990, 1, 31); None hides the Uptime line
EMAIL_PERSONAL = None           # e.g. "name@example.com"; None hides the line
EMAIL_WORK = None               # e.g. "contact@elitevisa.com"; None hides the line

INFO = [  # (key, id, value) | "title" | None (blank line) | special rows
    "abdellah@boudlal",
    ("OS", "os", "Windows 11, iOS, Linux"),
    ("Uptime", "age_data", "UPTIME"),
    ("Host", "host", "Elite Visa (Founder, since 2018)"),
    ("Kernel", "kernel", "Data Analyst"),
    ("IDE", "ide", "VSCode, Jupyter, Power BI Desktop"),
    None,
    ("Languages.Programming", "lang_prog", "SQL, Python, DAX"),
    ("Languages.Computer", "lang_comp", "HTML, CSS, JSON, Markdown"),
    ("Languages.Real", "lang_real", "French, Arabic, English"),
    None,
    ("Tools.Data", "tools_data", "Power BI, Excel, Tableau"),
    ("Tools.Libraries", "tools_libs", "Pandas, NumPy, Matplotlib"),
    None,
    "Contact",
    ("Website", "website", "abdellahboudlal.com"),
    ("Email.Personal", "email_personal", EMAIL_PERSONAL),
    ("Email.Work", "email_work", EMAIL_WORK),
    ("LinkedIn", "linkedin", "aboudlal"),
    None,
    "GitHub Stats",
    "STATS",
]

WIDTH, HALF = 60, 30            # info column width / left half of the stats rows (characters)
FONT_SIZE, LINE_H = 16, 24
CHAR_W = 0.602 * FONT_SIZE      # monospace advance used to size the card
PAD, GAP = 20, 25
FONT = "Consolas,'DejaVu Sans Mono','Courier New',monospace"

THEMES = {
    "dark_mode.svg": dict(bg="#161b22", border="#30363d", text="#c9d1d9", key="#ffa657",
                          value="#a5d6ff", cc="#616e7f", add="#3fb950", rem="#f85149"),
    "light_mode.svg": dict(bg="#f6f8fa", border="#d0d7de", text="#24292f", key="#953800",
                           value="#0a3069", cc="#8c959f", add="#1a7f37", rem="#cf222e"),
}
# ================================================================

TOKEN = os.environ.get("ACCESS_TOKEN") or os.environ.get("GITHUB_TOKEN")
HEADERS = {"authorization": f"bearer {TOKEN}"}


# ------------------------------------------------------------- GitHub
def graphql(query, **variables):
    r = requests.post("https://api.github.com/graphql", json={"query": query, "variables": variables},
                      headers=HEADERS, timeout=60)
    r.raise_for_status()
    data = r.json()
    if "errors" in data:
        raise RuntimeError(data["errors"])
    return data["data"]


def github_stats(login):
    user = graphql("""query($login: String!) { user(login: $login) {
        id
        followers { totalCount }
        contributionsCollection { contributionYears }
        repositoriesContributedTo(includeUserRepositories: true,
          contributionTypes: [COMMIT, PULL_REQUEST, REPOSITORY]) { totalCount }
    } }""", login=login)["user"]

    repos, cursor = [], None
    while True:
        page = graphql("""query($login: String!, $cursor: String) { user(login: $login) {
            repositories(first: 100, after: $cursor, ownerAffiliations: OWNER) {
              totalCount
              pageInfo { hasNextPage endCursor }
              nodes { name stargazerCount isFork }
            } } }""", login=login, cursor=cursor)["user"]["repositories"]
        repos += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]

    commits = 0
    for y in user["contributionsCollection"]["contributionYears"]:
        c = graphql("""query($login: String!, $from: DateTime!, $to: DateTime!) { user(login: $login) {
            contributionsCollection(from: $from, to: $to) {
              totalCommitContributions restrictedContributionsCount } } }""",
                    login=login, **{"from": f"{y}-01-01T00:00:00Z", "to": f"{y}-12-31T23:59:59Z"}
                    )["user"]["contributionsCollection"]
        commits += c["totalCommitContributions"] + c["restrictedContributionsCount"]

    added = deleted = 0
    for repo in repos:
        if repo["isFork"]:
            continue
        cursor = None
        while True:
            ref = graphql("""query($owner: String!, $name: String!, $id: ID!, $cursor: String) {
                repository(owner: $owner, name: $name) { defaultBranchRef { target { ... on Commit {
                  history(first: 100, after: $cursor, author: {id: $id}) {
                    pageInfo { hasNextPage endCursor }
                    nodes { additions deletions } } } } } } }""",
                          owner=login, name=repo["name"], id=user["id"], cursor=cursor
                          )["repository"]["defaultBranchRef"]
            if not ref:
                break
            hist = ref["target"]["history"]
            added += sum(n["additions"] for n in hist["nodes"])
            deleted += sum(n["deletions"] for n in hist["nodes"])
            if not hist["pageInfo"]["hasNextPage"]:
                break
            cursor = hist["pageInfo"]["endCursor"]

    return dict(repos=len(repos), contrib=user["repositoriesContributedTo"]["totalCount"],
                stars=sum(r["stargazerCount"] for r in repos), commits=commits,
                followers=user["followers"]["totalCount"],
                added=added, deleted=deleted, loc=added - deleted)


def uptime(birthday):
    d = relativedelta.relativedelta(datetime.date.today(), birthday)
    unit = lambda n, w: f"{n} {w}{'' if n == 1 else 's'}"
    return ", ".join([unit(d.years, "year"), unit(d.months, "month"), unit(d.days, "day")])


# ------------------------------------------------------------- Info column
def span(text, cls=None, ident=None):
    attrs = (f' class="{cls}"' if cls else "") + (f' id="{ident}"' if ident else "")
    return f"<tspan{attrs}>{escape(text)}</tspan>" if attrs else escape(text)


def row(key, parts, width):
    """'Key:' on the left, value parts right-aligned, spaces in between."""
    value_len = sum(len(t) for t, *_ in parts)
    spaces = " " * max(width - len(key) - 1 - value_len, 1)
    return span(f"{key}:", "key") + spaces + "".join(span(*p) for p in parts)


def title(text):
    return escape(text) + " " + span("-" * (WIDTH - len(text) - 1), "cc")


def info_lines(s, age):
    f = lambda n: f"{n:,}"
    lines = []
    for item in INFO:
        if item is None:
            lines.append("")
        elif item == "STATS":
            lines.append(row("Repos", [(f(s["repos"]), "value", "repo_data"), (" {Contributed: ",),
                                       (f(s["contrib"]), "value", "contrib_data"), ("}",)], HALF)
                         + span(" | ", "cc") +
                         row("Stars", [(f(s["stars"]), "value", "star_data")], WIDTH - HALF - 3))
            lines.append(row("Commits", [(f(s["commits"]), "value", "commit_data")], HALF)
                         + span(" | ", "cc") +
                         row("Followers", [(f(s["followers"]), "value", "follower_data")], WIDTH - HALF - 3))
            lines.append(row("Lines of Code on GitHub", [
                (f(s["loc"]), "value", "loc_data"), (" ( ",),
                (f(s["added"]) + "++", "add", "loc_add"), (", ",),
                (f(s["deleted"]) + "--", "rem", "loc_del"), (" )",)], WIDTH))
        elif isinstance(item, str):
            lines.append(title(item))
        else:
            key, ident, value = item
            if value == "UPTIME":
                value = age
            if value is None:
                continue
            lines.append(row(key, [(value, "value", ident)], WIDTH))
    return lines


def render(t, lines, n_portrait_rows):
    first = PAD + 0.75 * FONT_SIZE                     # first baseline
    top, bottom = PAD, first + (len(lines) - 1) * LINE_H + 0.25 * FONT_SIZE
    info_x = round(ascii_portrait.X + ascii_portrait.portrait_width(n_portrait_rows, top, bottom) + GAP)
    width = round(info_x + WIDTH * CHAR_W + PAD)
    height = round(bottom + PAD)
    info = "\n".join(f'<tspan x="{info_x}" y="{first + i * LINE_H:.0f}">{l}</tspan>'
                     for i, l in enumerate(lines))
    return f"""<?xml version='1.0' encoding='UTF-8'?>
<svg xmlns="http://www.w3.org/2000/svg" width="{width}px" height="{height}px" font-family="{FONT}" font-size="{FONT_SIZE}px">
<style>
.key {{fill: {t['key']};}}
.value {{fill: {t['value']};}}
.cc {{fill: {t['cc']};}}
.add {{fill: {t['add']};}}
.rem {{fill: {t['rem']};}}
text, tspan {{white-space: pre;}}
</style>
<rect width="{width}px" height="{height}px" fill="{t['bg']}" stroke="{t['border']}" rx="15"/>
<g id="ascii-portrait"></g>
<text id="info" x="{info_x}" y="{first:.0f}" fill="{t['text']}" xml:space="preserve" data-top="{top:.2f}" data-bottom="{bottom:.2f}">
{info}
</text>
</svg>
"""


# ------------------------------------------------------------- README text version
def text_row(key, value, width):
    return f"{key}:" + " " * max(width - len(key) - 1 - len(value), 1) + value


def text_lines(s, age):
    f = lambda n: f"{n:,}"
    lines = []
    for item in INFO:
        if item is None:
            lines.append("")
        elif item == "STATS":
            right = WIDTH - HALF - 3
            lines.append(text_row("Repos", f"{f(s['repos'])} {{Contributed: {f(s['contrib'])}}}", HALF)
                         + " | " + text_row("Stars", f(s["stars"]), right))
            lines.append(text_row("Commits", f(s["commits"]), HALF) + " | "
                         + text_row("Followers", f(s["followers"]), right))
            lines.append(text_row("Lines of Code on GitHub",
                                  f"{f(s['loc'])} ( {f(s['added'])}++, {f(s['deleted'])}-- )", WIDTH))
        elif isinstance(item, str):
            lines.append(f"{item} " + "-" * (WIDTH - len(item) - 1))
        else:
            key, _, value = item
            if value == "UPTIME":
                value = age
            if value is not None:
                lines.append(text_row(key, value, WIDTH))
    return lines


def build(stats):
    age = uptime(BIRTHDAY) if BIRTHDAY else None
    gray, alpha = ascii_portrait.load()
    # coloured SVG cards
    lines = info_lines(stats, age)
    n_rows = len(ascii_portrait.ascii_rows(gray, alpha))
    for filename, theme in THEMES.items():
        with open(filename, "w", encoding="utf-8") as fh:
            fh.write(render(theme, lines, n_rows))
    ascii_portrait.write_svgs(gray, alpha)
    # selectable text version in README.md
    ascii_portrait.write_readme(ascii_portrait.compose(ascii_portrait.text_rows(gray, alpha),
                                                       text_lines(stats, age)))


if __name__ == "__main__":
    stats = github_stats(USER_NAME)
    print(stats)
    build(stats)
    print("SVG files and README.md updated.")
