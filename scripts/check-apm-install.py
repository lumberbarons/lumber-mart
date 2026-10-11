#!/usr/bin/env python3
"""Install every plugin through APM's CLI and verify complete deployed skills.

Run: uv run --no-project --with apm-cli==0.33.0 python3 scripts/check-apm-install.py
Exercises marketplace selectors and the plugin subpaths existing users pin.
All package, project, and APM configuration writes stay in a temporary tree.
"""

import contextlib
import difflib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner
from apm_cli.cli import cli
import apm_cli.config as config


def inventory(directory: Path, package: Path) -> dict[str, bytes]:
    files = {}
    for path in directory.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts or path.name == ".apm-pin":
            continue
        content = path.read_bytes()
        if path.suffix == ".md":
            # APM rebases Markdown links to files outside a deployed skill.
            # Compare their package-relative destinations, not install paths.
            def normalize_link(match):
                target, separator, fragment = match[1].partition("#")
                if not target or ":" in target:
                    return match[0]
                resolved = (path.parent / target).resolve()
                if not resolved.is_file():
                    return match[0]
                for base, prefix in ((directory, "@skill"), (package, "@package")):
                    if resolved.is_relative_to(base.resolve()):
                        relative = resolved.relative_to(base.resolve()).as_posix()
                        return f"]({prefix}/{relative}{separator}{fragment})"
                return match[0]
            content = re.sub(r"\]\(([^)]+)\)", normalize_link,
                             content.decode()).encode()
        files[str(path.relative_to(directory))] = content
    return files


def invoke(runner: CliRunner, arguments: list[str]) -> None:
    result = runner.invoke(cli, arguments, obj={})
    if result.exit_code:
        raise RuntimeError(f"apm {' '.join(arguments)} failed:\n{result.output}\n{result.exception}")


def main() -> int:
    source = Path(__file__).resolve().parent.parent
    catalog = json.loads((source / ".claude-plugin/marketplace.json").read_text())
    with tempfile.TemporaryDirectory(prefix="lumber-apm-check-") as temporary:
        root = Path(temporary).resolve()
        market = root / "market"
        shutil.copytree(source / ".claude-plugin", market / ".claude-plugin")
        shutil.copytree(source / "plugins", market / "plugins",
                        ignore=shutil.ignore_patterns("__pycache__"))
        # APM has no public configuration-root override. Click's CLI test runner
        # invokes the actual commands; patch only their user configuration paths.
        with patch.object(config, "CONFIG_DIR", str(root / "apm-config")), \
                patch.object(config, "CONFIG_FILE", str(root / "apm-config/config.json")):
            runner = CliRunner()
            invoke(runner, ["marketplace", "add", str(market), "--name", catalog["name"]])
            for route, scope in (("marketplace", "project"), ("subpath", "project"),
                                 ("marketplace", "global"), ("subpath", "global")):
                project = root / f"{scope}-{route}"
                project.mkdir()
                home = project / "user"
                home.mkdir()
                selectors = [f"{entry['name']}@{catalog['name']}" if route == "marketplace"
                             else str(market / entry["source"]) for entry in catalog["plugins"]]
                expanduser = os.path.expanduser
                def isolated_expanduser(path):
                    if path == "~" or path.startswith("~/"):
                        return str(home) + path[1:]
                    return expanduser(path)
                with contextlib.chdir(project), patch.object(Path, "home", return_value=home), \
                        patch("os.path.expanduser", side_effect=isolated_expanduser), \
                        patch.dict(os.environ, {"XDG_CONFIG_HOME": str(home / ".config")}):
                    arguments = ["install", *selectors, "--target", "opencode"]
                    if scope == "global":
                        arguments.append("--global")
                    invoke(runner, arguments)
                expected = {}
                for entry in catalog["plugins"]:
                    for skill in sorted((market / entry["source"] / "skills").iterdir()):
                        if not (skill / "SKILL.md").is_file():
                            continue
                        if skill.name in expected:
                            raise RuntimeError(f"duplicate deployed skill ID: {skill.name}")
                        expected[skill.name] = (entry["name"], inventory(skill, market / entry["source"]))
                deployed = home / ".config/opencode/skills" if scope == "global" else project / ".agents/skills"
                package_root = home / ".apm" if scope == "global" else project
                actual_names = {path.name for path in deployed.iterdir() if path.is_dir()}
                if actual_names != set(expected):
                    raise RuntimeError(f"{route}: expected {sorted(expected)}, got {sorted(actual_names)}")
                for name, (plugin, files) in expected.items():
                    actual = inventory(deployed / name, package_root / "apm_modules/_local" / plugin)
                    if actual != files:
                        changed = sorted(key for key in set(files) | set(actual)
                                         if files.get(key) != actual.get(key))
                        detail = "\n".join("".join(difflib.unified_diff(
                            files[key].decode(errors="replace").splitlines(keepends=True),
                            actual[key].decode(errors="replace").splitlines(keepends=True),
                            fromfile=f"source/{key}", tofile=f"deployed/{key}"))
                            for key in changed if key in files and key in actual)
                        raise RuntimeError(f"{route}: incomplete/changed skill {name}: {changed}\n{detail}")
                print(f"APM OpenCode {scope} {route}: {len(catalog['plugins'])} plugins, "
                      f"{len(expected)} skills, all bundled files match (Markdown links rebased)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
