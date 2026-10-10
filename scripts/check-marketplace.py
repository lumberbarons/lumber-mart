#!/usr/bin/env python3
"""Check the marketplace listing and the plugin manifests stay in step.

Claude Code resolves a plugin through two files: its entry in
.claude-plugin/marketplace.json and its own .claude-plugin/plugin.json. The
entry name and the manifest name must agree, a plugin missing from the listing
is invisible, and a source path that does not exist is not caught by
`claude plugin validate` - only by install. Both files must also carry the same
version: Claude Code installs from plugin.json, while marketplace browsers such
as APM display the entry's version, so the pair drifting apart leaves consumers
unable to tell which revision they have.

Given --base <ref>, any plugin whose files changed relative to that ref must
have advanced its version past the one the ref carries. A change shipped under
an unchanged version is indistinguishable from no change at all. CI passes the
PR base commit, or the previous tip on a push to main, with full history
fetched.

Portable root manifests and the Codex catalog must agree with the Claude
metadata. The vendored Agent Plugins schema validates the portable format.

Run: uv run --no-project --with jsonschema python3 scripts/check-marketplace.py [--base <git-ref>]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
IDENTITY_FIELDS = ("name", "version", "description", "author", "homepage", "repository", "license", "keywords")

SEMVER = re.compile(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?\Z")
VERSION_PARTS = re.compile(r"(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?\Z")


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


def version_key(version: object) -> tuple[int, int, int, bool, str] | None:
    if not isinstance(version, str):
        return None
    match = VERSION_PARTS.match(version)
    if match is None:
        return None
    major, minor, patch = (int(match.group(index)) for index in (1, 2, 3))
    prerelease = match.group(4)
    # A release outranks any prerelease with the same numbers; prerelease
    # ordering is lexical, close enough for bump enforcement.
    return (major, minor, patch, prerelease is None, prerelease or "")


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip().splitlines()
        detail = stderr[0] if stderr else f"git {' '.join(args)} failed"
        raise RuntimeError(detail)
    return result.stdout


def check_bumps(root: Path, base: str, versions: dict[str, str], problems: list[str]) -> None:
    try:
        changed = git(root, "diff", "--name-only", f"{base}...HEAD").splitlines()
    except RuntimeError as error:
        problems.append(
            f"cannot diff against base {base!r}: {error}; "
            "fetch full history (fetch-depth: 0) before running with --base"
        )
        return
    for name, version in sorted(versions.items()):
        if not any(path.startswith(f"plugins/{name}/") for path in changed):
            continue
        relative = f"plugins/{name}/.claude-plugin/plugin.json"
        try:
            base_text = git(root, "show", f"{base}:{relative}")
        except RuntimeError:
            continue  # the plugin is new relative to the base
        try:
            base_data = json.loads(base_text)
        except json.JSONDecodeError:
            problems.append(f"{relative}: base copy on {base} is not valid JSON, cannot check its version")
            continue
        base_version = base_data.get("version") if isinstance(base_data, dict) else None
        current = version_key(version)
        previous = version_key(base_version)
        if current is None or previous is None:
            continue  # malformed versions are reported elsewhere
        if current <= previous:
            problems.append(
                f"{relative}: the plugin changed but version {version!r} has not advanced past "
                f"{base_version!r} on {base}; bump it in plugin.json and marketplace.json"
            )


def check_portable(root: Path, claude_marketplace: dict, problems: list[str]) -> None:
    schema = load(root / "scripts/schemas/plugin.schema.json", problems)
    validator = Draft202012Validator(schema) if schema is not None else None
    catalog_path = root / ".agents/plugins/marketplace.json"
    catalog = load(catalog_path, problems)
    if catalog is None:
        return
    if catalog.get("name") != claude_marketplace.get("name"):
        problems.append(f"{catalog_path}: name does not match the Claude marketplace")
    interface = catalog.get("interface")
    if not isinstance(interface, dict) or not interface.get("displayName"):
        problems.append(f"{catalog_path}: interface.displayName is missing")
    entries = catalog.get("plugins")
    if not isinstance(entries, list):
        problems.append(f"{catalog_path}: plugins is not an array")
        entries = []
    listed: dict[str, dict] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str) or not entry["name"]:
            problems.append(f"{catalog_path}: entry missing a name")
            continue
        name = entry["name"]
        if name in listed:
            problems.append(f"{catalog_path}: {name}: duplicate entry")
        listed[name] = entry
        source = entry.get("source")
        expected_path = f"./plugins/{name}"
        if source != {"source": "local", "path": expected_path}:
            problems.append(f"{catalog_path}: {name}: source must be local at {expected_path!r}")
        policy = entry.get("policy")
        if not isinstance(policy, dict) or policy.get("installation") not in (
            "AVAILABLE", "INSTALLED_BY_DEFAULT", "NOT_AVAILABLE"
        ) or policy.get("authentication") not in ("ON_INSTALL", "ON_USE"):
            problems.append(f"{catalog_path}: {name}: invalid installation/authentication policy")
        if not isinstance(entry.get("category"), str) or not entry["category"]:
            problems.append(f"{catalog_path}: {name}: category is missing")

    claude_entries = claude_marketplace.get("plugins", [])
    if not isinstance(claude_entries, list):
        claude_entries = []
    claude_listed = {entry["name"]: entry for entry in claude_entries
                     if isinstance(entry, dict) and isinstance(entry.get("name"), str)}
    if set(listed) != set(claude_listed):
        problems.append(f"{catalog_path}: plugin names do not match the Claude marketplace")
    for name, entry in listed.items():
        claude_entry = claude_listed.get(name)
        if claude_entry is not None:
            source = entry.get("source")
            if not isinstance(source, dict) or source.get("path") != claude_entry.get("source"):
                problems.append(f"{catalog_path}: {name}: source path differs from the Claude marketplace")

    for directory in sorted(path for path in (root / "plugins").iterdir() if path.is_dir()):
        manifest_path = directory / "plugin.json"
        manifest = load(manifest_path, problems)
        if manifest is None:
            continue
        if validator is not None:
            for error in validator.iter_errors(manifest):
                field = ".".join(str(part) for part in error.path) or "manifest"
                problems.append(f"{manifest_path}: {field}: {error.message}")
        if manifest.get("$schema") != PLUGIN_SCHEMA:
            problems.append(f"{manifest_path}: must declare the Agent Plugins 1.0.0 schema")
        claude = load(directory / ".claude-plugin/plugin.json", problems)
        if claude is not None:
            for field in IDENTITY_FIELDS:
                if manifest.get(field) != claude.get(field):
                    problems.append(f"{manifest_path}: {field} differs from the Claude manifest")
        if not list((directory / "skills").glob("*/SKILL.md")):
            problems.append(f"{directory}: no skills found at skills/<name>/SKILL.md")
        extensions = manifest.get("extensions")
        extension = extensions.get("com.openai", {}) if isinstance(extensions, dict) else {}
        interface = extension.get("interface") if isinstance(extension, dict) else None
        if not isinstance(interface, dict) or not interface.get("displayName") or not interface.get("shortDescription"):
            problems.append(f"{manifest_path}: OpenAI interface displayName/shortDescription is missing")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check marketplace and plugin manifests stay in step")
    parser.add_argument(
        "--base",
        metavar="REF",
        help="git ref to compare against; plugins changed relative to it must advance their version",
    )
    args = parser.parse_args()

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

    versions: dict[str, str] = {}
    for name, manifest_path in sorted(manifests.items()):
        manifest = load(manifest_path, problems)
        if manifest is None:
            continue
        if manifest.get("name") != name:
            problems.append(f"{manifest_path}: name {manifest.get('name')!r} does not match its directory {name!r}")
        version = manifest.get("version")
        if not isinstance(version, str) or not SEMVER.match(version):
            problems.append(f"{manifest_path}: version {version!r} is not a semantic version")
        else:
            versions[name] = version
        if not manifest.get("description"):
            problems.append(f"{manifest_path}: description is missing")
        entry = listed.get(name)
        if entry is not None:
            if entry.get("name") != manifest.get("name"):
                problems.append(f"{manifest_path}: name does not match its marketplace entry")
            if entry.get("description") != manifest.get("description"):
                problems.append(f"{marketplace_path}: {name}: description differs from the plugin manifest")
            entry_version = entry.get("version")
            if not isinstance(entry_version, str) or not entry_version:
                problems.append(
                    f"{marketplace_path}: {name}: entry has no version; set it to plugin.json's version {version!r}"
                )
            elif isinstance(version, str) and entry_version != version:
                problems.append(
                    f"{marketplace_path}: {name}: entry version {entry_version!r} does not match "
                    f"plugin.json version {version!r}"
                )

    check_portable(root, marketplace, problems)

    if args.base:
        check_bumps(root, args.base, versions, problems)

    return report(problems)


def report(problems: list[str]) -> int:
    for problem in problems:
        print(problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
