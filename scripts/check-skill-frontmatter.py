#!/usr/bin/env python3
"""Validate every skill's frontmatter against the Agent Skills spec.

Installers and harnesses each parse SKILL.md with their own YAML parser, and a
description that only parses under a lenient one installs for some agents and
fails for others - `claude plugin validate` does not read frontmatter at all,
so this is the only check that catches that class of breakage.

Run: uv run --no-project --with pyyaml python3 scripts/check-skill-frontmatter.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

MAX_NAME = 64
MAX_DESCRIPTION = 1024
MAX_COMPATIBILITY = 500
NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


def frontmatter(text: str) -> str | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    return None if end == -1 else text[4:end]


def problems(path: Path) -> list[str]:
    raw = frontmatter(path.read_text(encoding="utf-8"))
    if raw is None:
        return ["missing or unterminated frontmatter"]
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as error:
        return [f"invalid YAML: {str(error).strip().splitlines()[0]}"]
    if not isinstance(data, dict):
        return ["frontmatter is not a YAML mapping"]

    found: list[str] = []
    name = data.get("name")
    if not isinstance(name, str) or not name:
        found.append("name: missing or not a non-empty string")
    else:
        if len(name) > MAX_NAME:
            found.append(f"name: {len(name)} characters, over the {MAX_NAME} limit")
        if not NAME.match(name):
            found.append("name: may only contain lowercase letters, numbers and single hyphens")
        if name != path.parent.name:
            found.append(f"name: {name!r} does not match its directory {path.parent.name!r}")
    description = data.get("description")
    if not isinstance(description, str) or not description.strip():
        found.append("description: missing or empty")
    elif len(description) > MAX_DESCRIPTION:
        found.append(f"description: {len(description)} characters, over the {MAX_DESCRIPTION} limit")
    compatibility = data.get("compatibility")
    if compatibility is not None and (
        not isinstance(compatibility, str) or len(compatibility) > MAX_COMPATIBILITY
    ):
        found.append(f"compatibility: must be a string of at most {MAX_COMPATIBILITY} characters")
    if data.get("license") is not None and not isinstance(data["license"], str):
        found.append("license: must be a string")
    if data.get("metadata") is not None and not isinstance(data["metadata"], dict):
        found.append("metadata: must be a mapping")
    allowed_tools = data.get("allowed-tools")
    if allowed_tools is not None and not isinstance(allowed_tools, str):
        found.append("allowed-tools: must be a space-separated string")
    return found


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    skills = sorted((root / "plugins").glob("*/skills/*/SKILL.md"))
    if not skills:
        print("no SKILL.md files found under plugins/", file=sys.stderr)
        return 1
    failed = False
    for path in skills:
        for problem in problems(path):
            print(f"{path.relative_to(root)}: {problem}")
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
