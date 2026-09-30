#!/usr/bin/env python3
"""Check the marketplace listing and the plugin manifests stay in step.

Claude Code resolves a plugin through two files: its entry in
.claude-plugin/marketplace.json and its own .claude-plugin/plugin.json. The
entry name and the manifest name must agree, a plugin missing from the listing
is invisible, and a source path that does not exist is not caught by
`claude plugin validate` - only by install. This parses both files with the
standard library and exits 1 on any disagreement.

Run: python3 scripts/check-marketplace.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SEMVER = re.compile(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?\Z")


def load(path: Path, problems: list[str]) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        problems.append(f"{path}: invalid JSON: {error}")
        return None
    if not isinstance(data, dict):
        problems.append(f"{path}: not a JSON object")
        return None
    return data


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    problems: list[str] = []

    marketplace_path = root / ".claude-plugin" / "marketplace.json"
    marketplace = load(marketplace_path, problems)
    if marketplace is None:
        return report(problems)

    for field in ("name", "owner", "plugins"):
        if field not in marketplace:
            problems.append(f"{marketplace_path}: missing required field {field!r}")
    owner = marketplace.get("owner")
    if isinstance(owner, dict):
        if not owner.get("name"):
            problems.append(f"{marketplace_path}: owner.name is missing")
    elif owner is not None:
        problems.append(f"{marketplace_path}: owner is not an object")

    entries = marketplace.get("plugins")
    if not isinstance(entries, list):
        entries = []

    listed: dict[str, dict] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str) or not entry["name"]:
            problems.append(f"{marketplace_path}: entry missing a name")
            continue
        name = entry["name"]
        if name in listed:
            problems.append(f"{marketplace_path}: {name}: duplicate entry")
        listed[name] = entry
        source = entry.get("source")
        if isinstance(source, str):
            target = root / source
            if ".." in Path(source).parts or Path(source).is_absolute():
                problems.append(f"{marketplace_path}: {name}: source {source!r} escapes the marketplace root")
            elif not target.is_dir():
                problems.append(f"{marketplace_path}: {name}: source {source!r} does not exist")
            elif not (target / ".claude-plugin" / "plugin.json").is_file():
                problems.append(f"{marketplace_path}: {name}: source {source!r} has no .claude-plugin/plugin.json")
        elif not isinstance(source, dict):
            problems.append(f"{marketplace_path}: {name}: source is missing")

    manifests: dict[str, Path] = {}
    for manifest_path in sorted((root / "plugins").glob("*/.claude-plugin/plugin.json")):
        manifests[manifest_path.parts[-3]] = manifest_path

    for plugin_dir in sorted(path for path in (root / "plugins").iterdir() if path.is_dir()):
        if plugin_dir.name not in manifests:
            problems.append(f"{plugin_dir}: no .claude-plugin/plugin.json")
        if plugin_dir.name not in listed:
            problems.append(f"{plugin_dir}: not listed in {marketplace_path.name}")
    for name in sorted(listed):
        if name not in manifests:
            problems.append(f"{marketplace_path}: {name}: listed but there is no plugins/{name}/.claude-plugin/plugin.json")

    for name, manifest_path in sorted(manifests.items()):
        manifest = load(manifest_path, problems)
        if manifest is None:
            continue
        if manifest.get("name") != name:
            problems.append(f"{manifest_path}: name {manifest.get('name')!r} does not match its directory {name!r}")
        version = manifest.get("version")
        if not isinstance(version, str) or not SEMVER.match(version):
            problems.append(f"{manifest_path}: version {version!r} is not a semantic version")
        if not manifest.get("description"):
            problems.append(f"{manifest_path}: description is missing")
        entry = listed.get(name)
        if entry is not None and entry.get("name") != manifest.get("name"):
            problems.append(f"{manifest_path}: name does not match its marketplace entry")
        if entry is not None and "version" in entry and "version" in manifest:
            problems.append(f"{marketplace_path}: {name}: entry version is ignored because plugin.json sets one")

    return report(problems)


def report(problems: list[str]) -> int:
    for problem in problems:
        print(problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
