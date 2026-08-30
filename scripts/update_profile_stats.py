#!/usr/bin/env python3
"""Generate an ASCII-style SVG from public GitHub profile data."""

from __future__ import annotations

import html
import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen


API_ROOT = "https://api.github.com"
OUTPUT_PATH = Path("assets/github-profile-stats.svg")
LANGUAGE_COLORS = {
    "C": "#555555",
    "C++": "#f34b7d",
    "CSS": "#563d7c",
    "HTML": "#e34c26",
    "JavaScript": "#f1e05a",
    "Python": "#3572A5",
    "Shell": "#89e051",
}


def request_json(path: str) -> tuple[object, object]:
    token = os.environ.get("GITHUB_TOKEN", "")
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "chaturbhuj-profile-stats",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = Request(f"{API_ROOT}{path}", headers=headers)
    with urlopen(request, timeout=30) as response:
        return json.load(response), response.headers


def paginated(path: str) -> list[dict]:
    items: list[dict] = []
    page = 1
    separator = "&" if "?" in path else "?"
    while True:
        data, _ = request_json(f"{path}{separator}per_page=100&page={page}")
        if not isinstance(data, list):
            raise RuntimeError(f"Expected a list from GitHub API path: {path}")
        items.extend(data)
        if len(data) < 100:
            return items
        page += 1


def count_items(path: str) -> int:
    separator = "&" if "?" in path else "?"
    data, headers = request_json(f"{path}{separator}per_page=1")
    if not isinstance(data, list) or not data:
        return 0

    link_header = headers.get("Link", "")
    last_page = re.search(r"[?&]page=(\d+)>; rel=\"last\"", link_header)
    return int(last_page.group(1)) if last_page else len(data)


def collect_stats(username: str) -> dict:
    fixture = os.environ.get("PROFILE_STATS_FIXTURE")
    if fixture:
        return json.loads(Path(fixture).read_text(encoding="utf-8"))

    escaped_username = quote(username, safe="")
    user, _ = request_json(f"/users/{escaped_username}")
    repositories = paginated(
        f"/users/{escaped_username}/repos?type=owner&sort=full_name"
    )
    repositories = [
        repository
        for repository in repositories
        if not repository.get("fork") and not repository.get("archived")
    ]

    stars = sum(int(repository.get("stargazers_count", 0)) for repository in repositories)
    repository_commits = 0
    language_bytes: Counter[str] = Counter()

    for repository in repositories:
        repository_name = quote(repository["name"], safe="")
        base_path = f"/repos/{escaped_username}/{repository_name}"
        repository_commits += count_items(f"{base_path}/commits")
        languages, _ = request_json(f"{base_path}/languages")
        if isinstance(languages, dict):
            language_bytes.update(
                {language: int(byte_count) for language, byte_count in languages.items()}
            )

    return {
        "display_name": user.get("name") or username,
        "followers": int(user.get("followers", 0)),
        "languages": dict(language_bytes),
        "location": user.get("location") or "Not set",
        "public_repos": len(repositories),
        "repository_commits": repository_commits,
        "stars": stars,
        "username": username,
    }


def language_summary(languages: dict[str, int]) -> list[tuple[str, float]]:
    total = sum(languages.values())
    if total <= 0:
        return []

    ranked = sorted(languages.items(), key=lambda item: item[1], reverse=True)
    visible = ranked[:4]
    hidden_total = sum(byte_count for _, byte_count in ranked[4:])
    if hidden_total:
        visible.append(("Other", hidden_total))
    return [(name, byte_count * 100 / total) for name, byte_count in visible]


def render_svg(stats: dict) -> str:
    username = html.escape(str(stats["username"]))
    display_name = html.escape(str(stats["display_name"]))
    location = html.escape(str(stats["location"]))
    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    languages = language_summary(stats.get("languages", {}))

    bar_x = 52.0
    bar_y = 349.0
    bar_width = 896.0
    current_x = bar_x
    bar_parts: list[str] = []
    legend_parts: list[str] = []

    if languages:
        for index, (name, percentage) in enumerate(languages):
            width = bar_width * percentage / 100
            color = LANGUAGE_COLORS.get(name, "#8b949e")
            bar_parts.append(
                f'<rect x="{current_x:.2f}" y="{bar_y}" width="{width:.2f}" '
                f'height="12" fill="{color}" rx="2" />'
            )
            legend_x = 52 + index * 178
            legend_parts.append(
                f'<circle cx="{legend_x + 5}" cy="386" r="5" fill="{color}" />'
                f'<text x="{legend_x + 17}" y="391" class="small">'
                f'{html.escape(name)} {percentage:.1f}%</text>'
            )
            current_x += width
    else:
        bar_parts.append(
            '<rect x="52" y="349" width="896" height="12" fill="#30363d" rx="2" />'
        )
        legend_parts.append(
            '<text x="52" y="391" class="small">No public language data yet</text>'
        )

    ascii_lines = [
        " ██████╗██████╗ ",
        "██╔════╝██╔══██╗",
        "██║     ██████╔╝",
        "██║     ██╔═══╝ ",
        "╚██████╗██║     ",
        " ╚═════╝╚═╝     ",
    ]
    ascii_svg = "".join(
        f'<text x="52" y="{165 + index * 25}" class="ascii">{line}</text>'
        for index, line in enumerate(ascii_lines)
    )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="430" viewBox="0 0 1000 430" role="img" aria-labelledby="title description">
  <title id="title">{display_name}'s live GitHub statistics</title>
  <desc id="description">Automatically updated public GitHub repository activity for {username}.</desc>
  <style>
    .title {{ fill: #f0f6fc; font: 700 30px ui-monospace, SFMono-Regular, Consolas, monospace; }}
    .handle {{ fill: #7ee787; font: 600 16px ui-monospace, SFMono-Regular, Consolas, monospace; }}
    .heading {{ fill: #58a6ff; font: 600 15px ui-monospace, SFMono-Regular, Consolas, monospace; letter-spacing: 1px; }}
    .label {{ fill: #d29922; font: 600 16px ui-monospace, SFMono-Regular, Consolas, monospace; }}
    .value {{ fill: #f0f6fc; font: 600 19px ui-monospace, SFMono-Regular, Consolas, monospace; }}
    .small {{ fill: #c9d1d9; font: 14px ui-monospace, SFMono-Regular, Consolas, monospace; }}
    .muted {{ fill: #8b949e; font: 12px ui-monospace, SFMono-Regular, Consolas, monospace; }}
    .ascii {{ fill: #39d353; font: 700 23px ui-monospace, SFMono-Regular, Consolas, monospace; white-space: pre; }}
  </style>
  <rect width="1000" height="430" rx="12" fill="#0d1117" />
  <rect x="1" y="1" width="998" height="428" rx="11" fill="none" stroke="#30363d" stroke-width="2" />
  <text x="52" y="55" class="title">{display_name}</text>
  <text x="52" y="86" class="handle">@{username}</text>
  <line x1="52" y1="112" x2="948" y2="112" stroke="#30363d" />
  {ascii_svg}
  <rect x="400" y="138" width="548" height="170" rx="8" fill="#161b22" stroke="#30363d" />
  <text x="430" y="169" class="heading">PUBLIC GITHUB ACTIVITY</text>
  <text x="430" y="203" class="label">Repositories</text>
  <text x="600" y="203" class="value">{int(stats['public_repos'])}</text>
  <text x="708" y="203" class="label">Stars</text>
  <text x="900" y="203" class="value">{int(stats['stars'])}</text>
  <text x="430" y="240" class="label">Repo commits</text>
  <text x="600" y="240" class="value">{int(stats['repository_commits'])}</text>
  <text x="708" y="240" class="label">Followers</text>
  <text x="900" y="240" class="value">{int(stats['followers'])}</text>
  <text x="430" y="276" class="small">Location: {location}</text>
  <text x="430" y="296" class="muted">Updated hourly · {updated_at}</text>
  <text x="52" y="333" class="heading">LANGUAGES IN PUBLIC REPOSITORIES</text>
  {''.join(bar_parts)}
  {''.join(legend_parts)}
</svg>
'''


def main() -> None:
    username = os.environ.get("PROFILE_USERNAME", "Chaturbhuj075")
    stats = collect_stats(username)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(render_svg(stats), encoding="utf-8")
    print(
        "Generated",
        OUTPUT_PATH,
        f"({stats['public_repos']} repos, {stats['repository_commits']} commits)",
    )


if __name__ == "__main__":
    main()
