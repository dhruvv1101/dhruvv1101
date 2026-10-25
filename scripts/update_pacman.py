#!/usr/bin/env python3
"""Refresh contribution cells in the supplied Pacman SVGs without changing their art."""

import argparse
import json
import os
from pathlib import Path
import re
import urllib.request


QUERY = """query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        weeks { contributionDays { date contributionCount color } }
      }
    }
  }
}"""

LIGHT = ("#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39")
DARK = ("#161b22", "#0e4429", "#006d32", "#26a641", "#39d353")
CELL = re.compile(r'<rect class="c(?: k[0-9a-z]+)?" x="(?P<x>\d+)" y="(?P<y>\d+)"')
MOVE_POINT = re.compile(
    r'([0-9.]+)%\{transform:translate\((-?\d+)px,(-?\d+)px\)\}'
)


def fetch_days(login: str, token: str) -> list[dict]:
    payload = json.dumps({"query": QUERY, "variables": {"login": login}}).encode()
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "dhruvv1101-pacman-profile",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)
    if result.get("errors"):
        raise RuntimeError(result["errors"][0]["message"])
    user = result.get("data", {}).get("user")
    if not user:
        raise RuntimeError(f"GitHub user {login!r} was not found")
    days = [
        day
        for week in user["contributionsCollection"]["contributionCalendar"]["weeks"]
        for day in week["contributionDays"]
    ]
    if len(days) < 365:
        raise RuntimeError(f"Expected at least 365 contribution days, got {len(days)}")
    return days[-365:]


def base36(number: int) -> str:
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    if number == 0:
        return "0"
    result = ""
    while number:
        number, remainder = divmod(number, 36)
        result = digits[remainder] + result
    return result


def eat_time(x: int, y: int, points: list[tuple[float, int, int]]) -> float:
    center_x = x + 6
    vertical = [(time, py) for time, px, py in points if px == center_x]
    if len(vertical) == 2:
        (start, start_y), (end, end_y) = vertical
        if start_y == 8 and end_y == 104:
            fraction = (y - 1 - 8) / 96
        elif start_y == 104 and end_y == 8:
            fraction = (104 - (y + 13)) / 96
        else:
            raise ValueError(f"Unexpected route at x={center_x}")
        return max(0.0, start + (end - start) * fraction)

    # The final column has only Sunday's cell; Pacman reaches it on the exit row.
    for (start, sx, sy), (end, ex, ey) in zip(points, points[1:]):
        if sy == ey == 8 and sx <= x - 1 <= ex:
            return start + (end - start) * (x - 1 - sx) / (ex - sx)
    raise ValueError(f"No Pacman route for cell ({x}, {y})")


def render(svg: str, days: list[dict], dark: bool) -> str:
    style_match = re.search(r"<style>(.*?)</style>", svg, re.DOTALL)
    if not style_match:
        raise ValueError("SVG has no inline style")
    style = style_match.group(1)
    base_style = re.match(r"\.c\{[^}]+\}", style)
    if not base_style or "@keyframes mv{" not in style or "@keyframes dr{" not in style:
        raise ValueError("SVG does not match the supplied Pacman artwork")
    empty_color = DARK[0] if dark else LIGHT[0]
    if f"fill:{empty_color}" not in base_style.group():
        raise ValueError("SVG theme does not match its filename")
    motion = style[style.index("@keyframes mv{") :]
    move_only = motion[: motion.index("@keyframes dr{")]
    points = [
        (float(time), int(x), int(y))
        for time, x, y in MOVE_POINT.findall(move_only)
    ]
    if len(points) < 100:
        raise ValueError("Pacman motion path is incomplete")

    frames = []
    index = 0

    def update_cell(match: re.Match) -> str:
        nonlocal index
        if index >= 365:
            raise ValueError("SVG contains more than 365 contribution cells")
        x, y = int(match["x"]), int(match["y"])
        if (x, y) != (2 + (index // 7) * 16, 2 + (index % 7) * 16):
            raise ValueError(f"Unexpected cell position at index {index}: ({x}, {y})")
        day = days[index]
        index += 1
        count = day["contributionCount"]
        if not count:
            return f'<rect class="c" x="{x}" y="{y}"'
        color = day["color"].lower()
        if color not in LIGHT[1:]:
            raise ValueError(f"Unknown GitHub contribution color {color!r}")
        fill = DARK[LIGHT.index(color)] if dark else color
        name = "k" + base36(len(frames))
        time = eat_time(x, y, points)
        frames.append(
            f"@keyframes {name}{{{time:.3f}%{{fill:{fill}}}"
            f"{time + 0.010:.3f}%,100%{{fill:{empty_color}}}}}"
            f".c.{name}{{fill:{fill};animation-name:{name}}}"
        )
        return f'<rect class="c {name}" x="{x}" y="{y}"'

    updated = CELL.sub(update_cell, svg)
    if index != 365:
        raise ValueError(f"Expected 365 contribution cells, got {index}")
    new_style = base_style.group() + "".join(frames) + motion
    return updated.replace(style_match.group(0), f"<style>{new_style}</style>", 1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", default="dhruvv1101")
    parser.add_argument(
        "--assets", type=Path, default=Path(__file__).resolve().parents[1] / "assets"
    )
    args = parser.parse_args()
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        parser.error("GITHUB_TOKEN is required to read the contribution calendar")
    days = fetch_days(args.user, token)
    for filename, dark in (
        ("pacman-contribution-graph-dark.svg", True),
        ("pacman-contribution-graph.svg", False),
    ):
        path = args.assets / filename
        before = path.read_text(encoding="utf-8")
        after = render(before, days, dark)
        if after != before:
            path.write_text(after, encoding="utf-8", newline="\n")
            print(f"Updated {path}")
        else:
            print(f"Already current: {path}")


if __name__ == "__main__":
    main()
