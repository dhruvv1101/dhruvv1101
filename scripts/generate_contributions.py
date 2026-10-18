#!/usr/bin/env python3
"""Render a small, factual profile graphic from GitHub's contribution calendar."""

import argparse
import calendar
from collections import defaultdict
from datetime import date
import json
import math
import os
from pathlib import Path
import urllib.error
import urllib.request
from xml.sax.saxutils import escape


QUERY = """query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}"""


def monthly_contributions(login: str, token: str):
    payload = json.dumps({"query": QUERY, "variables": {"login": login}}).encode()
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "profile-contribution-artwork",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"GitHub API returned HTTP {error.code}") from error

    if data.get("errors"):
        raise RuntimeError(f"GitHub GraphQL error: {data['errors'][0]['message']}")
    user = data.get("data", {}).get("user")
    if not user:
        raise RuntimeError(f"GitHub user {login!r} was not found")

    days = [
        day
        for week in user["contributionsCollection"]["contributionCalendar"]["weeks"]
        for day in week["contributionDays"]
    ]
    latest = max(date.fromisoformat(day["date"]) for day in days)
    months = []
    year, month = latest.year, latest.month
    for _ in range(12):
        months.append((year, month))
        month -= 1
        if month == 0:
            year -= 1
            month = 12
    months.reverse()
    counts = defaultdict(int)
    for day in days:
        when = date.fromisoformat(day["date"])
        counts[(when.year, when.month)] += day["contributionCount"]
    return [(year, month, counts[(year, month)]) for year, month in months]


def svg_open(title):
    return [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 190" '
        'width="900" height="190" role="img">',
        f"<title>{escape(title)}</title>",
        '<style>text{font-family:Georgia,serif;fill:#2f3437}'
        '.meta{font:12px Arial,sans-serif;fill:#787774}'
        '@media(prefers-reduced-motion:reduce){.runner{display:none}}</style>',
        '<rect x="1" y="1" width="898" height="188" rx="8" '
        'fill="#fbfbfa" stroke="#eaeaea"/>',
    ]


def render_constellation(months):
    total = sum(count for _, _, count in months)
    peak = max((count for _, _, count in months), default=1) or 1
    first_year, first_month, _ = months[0]
    last_year, last_month, _ = months[-1]
    period = (
        f"{calendar.month_abbr[first_month]} {first_year}–"
        f"{calendar.month_abbr[last_month]} {last_year}"
    )
    points = []
    for index, (_, _, count) in enumerate(months):
        x = 55 + index * 71.8
        y = 126 - 64 * math.sqrt(count / peak)
        points.append((x, y, count))

    output = svg_open("Contribution constellation for the past twelve calendar months")
    output += [
        '<text x="30" y="34" font-size="18">Contribution constellation</text>',
        f'<text class="meta" x="870" y="34" text-anchor="end">'
        f'{total} contributions / {period}</text>',
        '<polyline fill="none" stroke="#b4c8c0" stroke-width="1.5" '
        + 'points="'
        + " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in points)
        + '"/>',
    ]
    for (year, month, _), (x, y, count) in zip(months, points):
        radius = 3.5 + 5.5 * math.sqrt(count / peak)
        output.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" '
            'fill="#346538" stroke="#fbfbfa" stroke-width="2"/>'
        )
        output.append(
            f'<text class="meta" x="{x:.1f}" y="158" text-anchor="middle">'
            f'{calendar.month_abbr[month]}</text>'
        )
    output.append("</svg>")
    return "\n".join(output) + "\n"


def render_pacman(months):
    peak = max((count for _, _, count in months), default=1) or 1
    output = svg_open("Pac-Man eating a year of monthly contribution dots")
    output += [
        '<text x="30" y="34" font-size="18">Pac-Man / contributions</text>',
        '<text class="meta" x="870" y="34" text-anchor="end">Dots scale with monthly activity</text>',
        '<line x1="48" y1="104" x2="852" y2="104" stroke="#d7d4cd" stroke-width="1"/>',
    ]
    for index, (_, month, count) in enumerate(months):
        x = 55 + index * 71.8
        radius = 3 + 4 * math.sqrt(count / peak)
        output.append(
            f'<circle cx="{x:.1f}" cy="104" r="{radius:.1f}" fill="#8cae91">'
            '<animate attributeName="opacity" values="1;1;0;0;1" '
            f'keyTimes="0;{max(0, (x-40)/820-0.015):.4f};{(x-40)/820:.4f};0.99;1" '
            'dur="12s" repeatCount="indefinite"/></circle>'
        )
        output.append(
            f'<text class="meta" x="{x:.1f}" y="157" text-anchor="middle">'
            f'{calendar.month_abbr[month]}</text>'
        )
    output += [
        '<g class="runner" transform="translate(40 104)">',
        '<animateTransform attributeName="transform" type="translate" '
        'from="40 104" to="860 104" dur="12s" repeatCount="indefinite"/>',
        '<path d="M0 0 L12 -9 A15 15 0 0 0 -15 0 Z" fill="#956400">'
        '<animateTransform attributeName="transform" type="rotate" '
        'values="0;18;0" dur="0.35s" repeatCount="indefinite"/></path>',
        '<path d="M0 0 L12 9 A15 15 0 0 1 -15 0 Z" fill="#956400">'
        '<animateTransform attributeName="transform" type="rotate" '
        'values="0;-18;0" dur="0.35s" repeatCount="indefinite"/></path>',
        '<circle cx="-2" cy="-7" r="1.5" fill="#2f3437"/>',
        '</g>',
        '</svg>',
    ]
    return "\n".join(output) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", required=True)
    parser.add_argument("--out-dir", type=Path, default=Path("profile"))
    args = parser.parse_args()
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        parser.error("GITHUB_TOKEN is required")
    months = monthly_contributions(args.user, token)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "contribution-constellation.svg").write_text(
        render_constellation(months), encoding="utf-8"
    )
    (args.out_dir / "pacman-contribution-graph.svg").write_text(
        render_pacman(months), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
