#!/usr/bin/env python3
"""Select and render up to three current GitHub projects for the profile README.

Requires GitHub CLI authentication (gh auth login) and Python 3.10+.
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "Readme.md"
START = "<!-- FEATURED-PROJECTS:START -->"
END = "<!-- FEATURED-PROJECTS:END -->"
EXCLUDED = {"aetherdz"}


def gh_json(*args: str):
    result = subprocess.run(
        ["gh", *args], check=True, capture_output=True, text=True, timeout=60
    )
    return json.loads(result.stdout)


def clean_markdown(value: str, limit: int = 220) -> str:
    """Keep repository metadata from injecting Markdown/HTML into README."""
    value = re.sub(r"[\r\n\t]+", " ", value)
    value = re.sub(r"[<>`*_\[\]()]", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:limit].rstrip()


TECH_ICONS = {
    "Python": "python",
    "Rust": "rust",
    "TypeScript": "typescript",
    "JavaScript": "javascript",
    "Node.js": "nodedotjs",
    "C++": "cplusplus",
    "C": "c",
    "Go": "go",
    "Dart": "dart",
    "Kotlin": "kotlin",
    "Swift": "swift",
    "Shell": "gnubash",
}


def language_icon(language: str | None) -> str:
    if not language or language not in TECH_ICONS:
        return ""
    return (
        f"<img alt=\"{language}\" src=\"https://cdn.simpleicons.org/"
        f"{TECH_ICONS[language]}\" width=\"24\" height=\"24\" />"
    )


def main() -> None:
    user = gh_json("api", "user")
    login = user["login"]
    repos = gh_json("api", "--paginate", f"users/{login}/repos?per_page=100&sort=updated")
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    eligible = [
        repo
        for repo in repos
        if not repo.get("fork")
        and not repo.get("archived")
        and repo.get("name", "").casefold() not in EXCLUDED
        and repo.get("description")
    ]

    recent = []
    for repo in eligible:
        try:
            commits = gh_json(
                "api",
                f"repos/{repo['full_name']}/commits?per_page=1",
            )
            if commits:
                commit_date = datetime.fromisoformat(
                    commits[0]["commit"]["committer"]["date"].replace("Z", "+00:00")
                )
                if commit_date >= cutoff:
                    repo["_commit_date"] = commit_date
                    recent.append(repo)
        except (subprocess.CalledProcessError, KeyError, ValueError):
            continue

    # Recent work is always included first; remaining positions are ranked by
    # stars, recent repository activity, and descriptive metadata.
    recent.sort(key=lambda repo: (repo["_commit_date"], repo["stargazers_count"]), reverse=True)
    selected = recent[:3]
    if len(selected) < 3:
        remaining = [repo for repo in eligible if repo not in selected]
        remaining.sort(
            key=lambda repo: (
                repo.get("stargazers_count", 0),
                repo.get("pushed_at", ""),
            ),
            reverse=True,
        )
        selected.extend(remaining[: 3 - len(selected)])

    cards = []
    if not selected:
        cards.append("<td align=\"center\">No public projects yet</td>")
    for repo in selected:
        description = clean_markdown(repo["description"])
        name = clean_markdown(repo["name"], limit=80)
        url = repo["html_url"]
        if not url.startswith("https://github.com/"):
            continue
        language = repo.get("language")
        icon = language_icon(language)
        cards.append(
            "<td align=\"center\" width=\"33%\">"
            f"<a href=\"{url}\"><strong>{name}</strong></a>"
            f"<br/><sub>{description}</sub>"
            f"<br/>{icon}"
            f"<br/><img alt=\"Repository stars\" src=\"https://img.shields.io/github/stars/{login}/{name}?style=flat-square&label=stars&color=64748b\" />"
            "</td>"
        )
    block = "\n".join([
        "<!-- Generated automatically by scripts/update-projects.py -->",
        "<div align=\"center\"><table><tr>" + "".join(cards) + "</tr></table></div>",
    ])
    readme = README.read_text(encoding="utf-8")
    if START not in readme or END not in readme:
        raise SystemExit("README is missing featured-project markers")
    before, rest = readme.split(START, 1)
    _, after = rest.split(END, 1)
    README.write_text(f"{before}{START}\n{block}\n{END}{after}", encoding="utf-8")
    print(f"Updated featured projects for @{login}: {len(selected)} repositories")


if __name__ == "__main__":
    main()
