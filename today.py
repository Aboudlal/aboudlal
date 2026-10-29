"""
Met à jour dark_mode.svg et light_mode.svg :
  - Uptime (âge calculé depuis la date de naissance)
  - Stats GitHub (repos, étoiles, commits, followers) via l'API GraphQL
  - Infos de contact
  - Portrait ASCII, si photo.jpg est présent dans le dépôt
Chaque valeur est retrouvée dans le SVG grâce à son attribut id.
"""
import datetime
import os
import xml.etree.ElementTree as ET

import requests
from dateutil import relativedelta

# ======================= À PERSONNALISER =======================
USER_NAME = "aboudlal"
BIRTHDAY = datetime.date(1990, 1, 1)   # <-- ta date de naissance (année, mois, jour)
EMAIL = "ton.email@exemple.com"       # <-- l'email que tu veux afficher publiquement
LINKEDIN = "aboudlal"
PHOTO = "photo.jpg"
ASCII_WIDTH = 40                       # largeur du portrait, en caractères
ASCII_MAX_ROWS = 25                    # nombre de lignes dispo dans le SVG
# ===============================================================

LINE_WIDTH = 58                        # largeur de la colonne de droite
HALF_WIDTH = 28                        # largeur des segments "Repos | Stars"
SVG_FILES = {"dark_mode.svg": "dark", "light_mode.svg": "light"}

NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)
HEADERS = {"authorization": "token " + os.environ["ACCESS_TOKEN"]}
API = "https://api.github.com/graphql"


# ---------------------------------------------------------------- Uptime
def uptime(birthday):
    d = relativedelta.relativedelta(datetime.date.today(), birthday)
    def plural(n, sing, plur):
        return f"{n} {sing if n <= 1 else plur}"
    return ", ".join([
        plural(d.years, "an", "ans"),
        f"{d.months} mois",
        plural(d.days, "jour", "jours"),
    ])


# ---------------------------------------------------------------- GitHub
def graphql(query, variables):
    r = requests.post(API, json={"query": query, "variables": variables},
                      headers=HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()
    if "errors" in data:
        raise RuntimeError(data["errors"])
    return data["data"]


def repos_and_stars(login):
    query = """
    query($login: String!, $cursor: String) {
      user(login: $login) {
        followers { totalCount }
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
            return repos["totalCount"], stars, user["followers"]["totalCount"]
        cursor = repos["pageInfo"]["endCursor"]


def total_commits(login):
    years = graphql("""
    query($login: String!) {
      user(login: $login) { contributionsCollection { contributionYears } }
    }""", {"login": login})["user"]["contributionsCollection"]["contributionYears"]

    query = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          totalCommitContributions
          restrictedContributionsCount
        }
      }
    }"""
    total = 0
    for y in years:
        c = graphql(query, {"login": login,
                            "from": f"{y}-01-01T00:00:00Z",
                            "to": f"{y}-12-31T23:59:59Z"})["user"]["contributionsCollection"]
        total += c["totalCommitContributions"] + c["restrictedContributionsCount"]
    return total


# ---------------------------------------------------------------- ASCII art
def ascii_portrait(path, invert):
    """Convertit la photo en lignes ASCII (caractères denses = zones claires en mode sombre)."""
    from PIL import Image, ImageOps
    ramp = " .'`^,:;Il!i><~+_-?][}{1)(|tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$"
    img = ImageOps.autocontrast(Image.open(path).convert("L"))
    w, h = img.size
    rows = min(ASCII_MAX_ROWS, max(1, int(h / w * ASCII_WIDTH * 0.5)))  # un caractère ≈ 2x plus haut que large
    img = img.resize((ASCII_WIDTH, rows))
    if invert:
        img = ImageOps.invert(img)
    lines = []
    for y in range(rows):
        lines.append("".join(ramp[img.getpixel((x, y)) * (len(ramp) - 1) // 255]
                             for x in range(ASCII_WIDTH)).rstrip())
    pad = (ASCII_MAX_ROWS - rows) // 2
    return [""] * pad + lines + [""] * (ASCII_MAX_ROWS - rows - pad)


# ---------------------------------------------------------------- SVG
def set_value(root, ident, value, width=LINE_WIDTH):
    """Remplace la valeur d'un id et recalcule les points de remplissage (id_dots)."""
    value = str(value)
    el = root.find(f".//*[@id='{ident}']")
    if el is None:
        print(f"id introuvable : {ident}")
        return
    el.text = value
    dots = root.find(f".//*[@id='{ident}_dots']")
    if dots is not None:
        # largeur = clé + ':' + ' ' + points + ' ' + valeur
        parent_key = _key_before(root, dots)
        n = width - len(parent_key) - 1 - len(value) - 2
        dots.text = " " + "." * max(n, 1) + " "


def _key_before(root, dots_el):
    """Retrouve le texte de la clé (tspan class=key) juste avant le tspan des points."""
    for parent in root.iter():
        children = list(parent)
        if dots_el in children:
            i = children.index(dots_el)
            if i > 0 and children[i - 1].get("class") == "key":
                return children[i - 1].text or ""
    return ""


def update_svg(filename, theme, values, ascii_lines):
    tree = ET.parse(filename)
    root = tree.getroot()
    for ident, (value, width) in values.items():
        set_value(root, ident, value, width)
    if ascii_lines:
        for i, line in enumerate(ascii_lines[theme]):
            el = root.find(f".//*[@id='ascii_{i}']")
            if el is not None:
                el.text = line
    tree.write(filename, encoding="utf-8", xml_declaration=True)


if __name__ == "__main__":
    repos, stars, followers = repos_and_stars(USER_NAME)
    commits = total_commits(USER_NAME)
    age = uptime(BIRTHDAY)
    print(f"Uptime: {age} | Repos: {repos} | Stars: {stars} | Commits: {commits} | Followers: {followers}")

    right_half = LINE_WIDTH - HALF_WIDTH - 3
    values = {
        "age_data": (age, LINE_WIDTH),
        "email": (EMAIL, LINE_WIDTH),
        "linkedin": (LINKEDIN, LINE_WIDTH),
        "repo_data": (f"{repos:,}", HALF_WIDTH),
        "star_data": (f"{stars:,}", right_half),
        "commit_data": (f"{commits:,}", HALF_WIDTH),
        "follower_data": (f"{followers:,}", right_half),
    }

    ascii_lines = None
    if os.path.exists(PHOTO):
        ascii_lines = {"dark": ascii_portrait(PHOTO, invert=False),
                       "light": ascii_portrait(PHOTO, invert=True)}

    for filename, theme in SVG_FILES.items():
        update_svg(filename, theme, values, ascii_lines)
    print("SVG mis à jour.")
