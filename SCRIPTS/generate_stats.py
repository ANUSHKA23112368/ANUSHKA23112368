#!/usr/bin/env python3
"""Generate self-hosted GitHub profile cards (SVG) using only the GitHub API.

No third-party card servers are involved, so the images cannot be rate limited
or go offline. Run by .github/workflows/profile-stats.yml, which commits the
SVG files in ./assets back to the repository.

Environment variables:
  GH_TOKEN      token with read access (GITHUB_TOKEN works for public data;
                a classic PAT with read:user + repo adds private contributions)
  PROFILE_USER  GitHub username (default: ANUSHKA23112368)
  OUT_DIR       output folder (default: assets)

Run with --demo to render sample cards without calling the API.
"""
import datetime
import json
import os
import sys
import urllib.request
from html import escape

LOGIN = os.environ.get("PROFILE_USER", "ANUSHKA23112368")
TOKEN = os.environ.get("GH_TOKEN", "")
OUT = os.environ.get("OUT_DIR", "assets")

BG, ACCENT, TEXT, MUTED = "#0d1117", "#00ff66", "#c9d1d9", "#8b949e"
FONT = "'Segoe UI', Ubuntu, 'Helvetica Neue', Arial, sans-serif"
W, H = 495, 195

USER_Q = """
query($login:String!){
  user(login:$login){
    name
    login
    followers{ totalCount }
    repositories(ownerAffiliations:OWNER, privacy:PUBLIC){ totalCount }
    pullRequests{ totalCount }
    issues{ totalCount }
    contributionsCollection{
      totalCommitContributions
      restrictedContributionsCount
      contributionCalendar{
        totalContributions
        weeks{ contributionDays{ date contributionCount } }
      }
    }
  }
}
"""

REPOS_Q = """
query($login:String!, $cursor:String){
  user(login:$login){
    repositories(first:100, after:$cursor, ownerAffiliations:OWNER, isFork:false, privacy:PUBLIC){
      pageInfo{ hasNextPage endCursor }
      nodes{
        stargazerCount
        languages(first:10, orderBy:{field:SIZE, direction:DESC}){
          edges{ size node{ name color } }
        }
      }
    }
  }
}
"""


def gql(query, variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={
            "Authorization": f"bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "profile-stats-generator",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.load(resp)
    if data.get("errors"):
        raise RuntimeError(f"GitHub API error: {data['errors']}")
    return data["data"]


def fetch():
    if not TOKEN:
        raise SystemExit("GH_TOKEN is not set")
    user = gql(USER_Q, {"login": LOGIN})["user"]
    stars, langs = 0, {}
    cursor = None
    while True:
        block = gql(REPOS_Q, {"login": LOGIN, "cursor": cursor})["user"]["repositories"]
        for repo in block["nodes"]:
            stars += repo["stargazerCount"]
            for edge in repo["languages"]["edges"]:
                name = edge["node"]["name"]
                color = edge["node"]["color"] or "#8b949e"
                size, _ = langs.get(name, (0, color))
                langs[name] = (size + edge["size"], color)
        if not block["pageInfo"]["hasNextPage"]:
            break
        cursor = block["pageInfo"]["endCursor"]

    cc = user["contributionsCollection"]
    days = [
        (d["date"], d["contributionCount"])
        for week in cc["contributionCalendar"]["weeks"]
        for d in week["contributionDays"]
    ]
    return {
        "name": user["name"] or user["login"],
        "followers": user["followers"]["totalCount"],
        "repos": user["repositories"]["totalCount"],
        "prs": user["pullRequests"]["totalCount"],
        "issues": user["issues"]["totalCount"],
        "commits": cc["totalCommitContributions"] + cc["restrictedContributionsCount"],
        "stars": stars,
        "total_contrib": cc["contributionCalendar"]["totalContributions"],
        "days": days,
        "langs": sorted(((n, s, c) for n, (s, c) in langs.items()), key=lambda x: -x[1]),
    }


def demo():
    import math
    today = datetime.date.today()
    days = [
        ((today - datetime.timedelta(days=89 - i)).isoformat(),
         max(0, int(3 + 3 * math.sin(i / 4) + (i % 7 == 0) * 4)))
        for i in range(90)
    ]
    return {
        "name": "Anushka Gaur", "followers": 12, "repos": 24, "prs": 8, "issues": 3,
        "commits": 312, "stars": 17, "total_contrib": 84, "days": days,
        "langs": [("Jupyter Notebook", 3589, "#DA5B0B"), ("Python", 3096, "#3572A5"),
                  ("JavaScript", 1556, "#f1e05a"), ("TypeScript", 1086, "#3178c6"),
                  ("CSS", 372, "#563d7c"), ("HTML", 300, "#e34c26")],
    }


def card(title, body, subtitle=""):
    sub = (f'<text x="25" y="52" fill="{MUTED}" font-size="12">{escape(subtitle)}</text>'
           if subtitle else "")
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{escape(title)}">
  <style>text{{font-family:{FONT}}}</style>
  <rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="4.5" fill="{BG}" stroke="{ACCENT}"/>
  <text x="25" y="35" fill="{ACCENT}" font-size="18" font-weight="600">{escape(title)}</text>
  {sub}
  {body}
</svg>
"""


def stats_svg(d):
    items = [("Total Stars", d["stars"]), ("Commits (last year)", d["commits"]),
             ("Pull Requests", d["prs"]), ("Issues", d["issues"]),
             ("Public Repos", d["repos"]), ("Followers", d["followers"])]
    body = []
    for i, (label, value) in enumerate(items):
        x = 25 + (i % 2) * 225
        y = 72 + (i // 2) * 43
        body.append(f'<text x="{x}" y="{y}" fill="{TEXT}" font-size="22" font-weight="700">{value:,}</text>')
        body.append(f'<text x="{x}" y="{y + 17}" fill="{MUTED}" font-size="12">{escape(label)}</text>')
    return card(f"{d['name']}'s GitHub Stats", "\n  ".join(body))


def langs_svg(d):
    langs = d["langs"][:6]
    total = sum(s for _, s, _ in d["langs"]) or 1
    bar_x, bar_w, bar_y, bar_h = 25, 445, 62, 10
    parts, x = [], bar_x
    for name, size, color in langs:
        w = bar_w * size / total
        parts.append(f'<rect x="{x:.2f}" y="{bar_y}" width="{w:.2f}" height="{bar_h}" fill="{escape(color)}"/>')
        x += w
    body = [
        f'<clipPath id="bar"><rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="{bar_h}" rx="5"/></clipPath>',
        f'<g clip-path="url(#bar)">{"".join(parts)}</g>',
    ]
    for i, (name, size, color) in enumerate(langs):
        cx = 25 + (i % 2) * 225
        cy = 100 + (i // 2) * 28
        pct = 100 * size / total
        body.append(f'<circle cx="{cx + 5}" cy="{cy - 4}" r="5" fill="{escape(color)}"/>')
        body.append(f'<text x="{cx + 17}" y="{cy}" fill="{TEXT}" font-size="13">{escape(name)} {pct:.1f}%</text>')
    return card("Most Used Languages", "\n  ".join(body))


def activity_svg(d):
    days = d["days"][-60:]
    counts = [c for _, c in days]
    top = max(counts + [1])
    x0, x1, y0, y1 = 30, 470, 70, 160
    step = (x1 - x0) / max(len(days) - 1, 1)
    pts = [(x0 + i * step, y1 - (c / top) * (y1 - y0)) for i, c in enumerate(counts)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"{x0},{y1} {line} {x1},{y1}"
    total = sum(counts)
    body = [
        '<defs><linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{ACCENT}" stop-opacity="0.35"/>'
        f'<stop offset="1" stop-color="{ACCENT}" stop-opacity="0"/></linearGradient></defs>',
        f'<line x1="{x0}" y1="{y1}" x2="{x1}" y2="{y1}" stroke="{MUTED}" stroke-opacity="0.4"/>',
        f'<polygon points="{area}" fill="url(#fill)"/>',
        f'<polyline points="{line}" fill="none" stroke="{ACCENT}" stroke-width="2" stroke-linejoin="round"/>',
        f'<text x="{x0}" y="{y1 + 18}" fill="{MUTED}" font-size="11">{escape(days[0][0])}</text>',
        f'<text x="{x1}" y="{y1 + 18}" fill="{MUTED}" font-size="11" text-anchor="end">{escape(days[-1][0])}</text>',
        f'<text x="{x1}" y="{y0 - 6}" fill="{MUTED}" font-size="11" text-anchor="end">peak {top}/day</text>',
    ]
    return card("Contribution Activity", "\n  ".join(body), f"{total} contributions in the last {len(days)} days")


def main():
    data = demo() if "--demo" in sys.argv else fetch()
    os.makedirs(OUT, exist_ok=True)
    for name, svg in (("stats.svg", stats_svg(data)),
                      ("top-langs.svg", langs_svg(data)),
                      ("activity.svg", activity_svg(data))):
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as fh:
            fh.write(svg)
        print("wrote", os.path.join(OUT, name))


if __name__ == "__main__":
    main()
