"""Exercise both host catalogs, portable schemas, and release enforcement."""

import contextlib
import importlib.util
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("check_marketplace", SCRIPTS / "check-marketplace.py")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class MarketplaceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.portable = "plugins/example/plugin.json"
        self.claude = "plugins/example/.claude-plugin/plugin.json"
        self.catalog = ".agents/plugins/marketplace.json"
        self.legacy_catalog = ".claude-plugin/marketplace.json"
        identity = {"name": "example", "version": "1.0.0", "description": "Example skills"}
        self.write(self.claude, identity)
        self.write(self.portable, {
            "$schema": checker.PLUGIN_SCHEMA, **identity,
            "extensions": {"com.openai": {"interface": {
                "displayName": "Example", "shortDescription": "Example skills"
            }}},
        })
        self.write(self.legacy_catalog, {
            "name": "example-market", "owner": {"name": "Example"},
            "plugins": [{**identity, "source": "./plugins/example"}],
        })
        self.write(self.catalog, {
            "name": "example-market", "interface": {"displayName": "Example Market"},
            "plugins": [{"name": "example", "source": {
                "source": "local", "path": "./plugins/example"
            }, "policy": {"installation": "AVAILABLE", "authentication": "ON_USE"},
                "category": "Developer Tools"}],
        })
        skill = self.root / "plugins/example/skills/hello/SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("---\nname: hello\ndescription: Say hello.\n---\nSay hello.\n")
        schema = self.root / "scripts/schemas/plugin.schema.json"
        schema.parent.mkdir(parents=True)
        shutil.copyfile(SCRIPTS / "schemas/plugin.schema.json", schema)

    def write(self, relative, data):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))

    def edit(self, relative, mutate):
        data = json.loads((self.root / relative).read_text())
        mutate(data)
        self.write(relative, data)

    def run_check(self, *arguments):
        output = io.StringIO()
        with patch.object(checker, "__file__", str(self.root / "scripts/check-marketplace.py")), \
                patch("sys.argv", ["check-marketplace.py", *arguments]), contextlib.redirect_stdout(output):
            code = checker.main()
        return code, output.getvalue()

    def assert_rejected(self, expected):
        code, output = self.run_check()
        self.assertEqual(code, 1, output)
        self.assertIn(expected, output)

    def test_valid_dual_host_marketplace(self):
        self.assertEqual(self.run_check(), (0, ""))

    def test_missing_portable_manifest(self):
        (self.root / self.portable).unlink()
        self.assert_rejected("plugin.json: invalid JSON")

    def test_wrong_schema(self):
        self.edit(self.portable, lambda data: data.update({"$schema": "legacy"}))
        self.assert_rejected("must declare the Agent Plugins")

    def test_nonportable_top_level_field(self):
        self.edit(self.portable, lambda data: data.update(skills="./skills/"))
        self.assert_rejected("Additional properties are not allowed")

    def test_bad_extensions_reports_instead_of_crashing(self):
        self.edit(self.portable, lambda data: data.update(extensions=[]))
        self.assert_rejected("OpenAI interface")

    def test_root_identity_must_match_claude(self):
        for field, value in (("name", "renamed"), ("version", "1.1.0"),
                             ("description", "Different"), ("license", "MIT")):
            with self.subTest(field=field):
                original = (self.root / self.portable).read_text()
                self.edit(self.portable, lambda data: data.update({field: value}))
                self.assert_rejected(f"{field} differs from the Claude manifest")
                (self.root / self.portable).write_text(original)

    def test_catalog_identity_must_match(self):
        self.edit(self.catalog, lambda data: data.update(name="other"))
        self.assert_rejected("name does not match the Claude marketplace")

    def test_missing_codex_entry(self):
        self.edit(self.catalog, lambda data: data.update(plugins=[]))
        self.assert_rejected("plugin names do not match")

    def test_duplicate_codex_entry(self):
        self.edit(self.catalog, lambda data: data["plugins"].append(data["plugins"][0].copy()))
        self.assert_rejected("duplicate entry")

    def test_unsafe_and_wrong_source_paths(self):
        for source in ("../outside", "/tmp/example", "./plugins/wrong", "plugins/example"):
            with self.subTest(source=source):
                self.edit(self.catalog, lambda data: data["plugins"][0]["source"].update(path=source))
                self.assert_rejected("source must be local")

    def test_missing_policy(self):
        self.edit(self.catalog, lambda data: data["plugins"][0].pop("policy"))
        self.assert_rejected("invalid installation/authentication policy")

    def test_bad_policy(self):
        self.edit(self.catalog, lambda data: data["plugins"][0]["policy"].update(authentication="NEVER"))
        self.assert_rejected("invalid installation/authentication policy")

    def test_missing_category(self):
        self.edit(self.catalog, lambda data: data["plugins"][0].pop("category"))
        self.assert_rejected("category is missing")

    def test_missing_skills(self):
        shutil.rmtree(self.root / "plugins/example/skills")
        self.assert_rejected("no skills found")

    def test_claude_entry_version_drift(self):
        self.edit(self.legacy_catalog, lambda data: data["plugins"][0].update(version="1.1.0"))
        self.assert_rejected("does not match plugin.json version")

    def test_claude_entry_description_drift(self):
        self.edit(self.legacy_catalog, lambda data: data["plugins"][0].update(description="Outdated"))
        self.assert_rejected("description differs from the plugin manifest")

    def git(self, *arguments):
        return subprocess.run(["git", "-C", str(self.root), *arguments], check=True,
                              capture_output=True, text=True).stdout.strip()

    def test_changed_plugin_requires_version_bump(self):
        self.git("init", "-q")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.com")
        self.git("add", ".")
        self.git("commit", "-qm", "Baseline")
        base = self.git("rev-parse", "HEAD")
        (self.root / "plugins/example/README.md").write_text("New behavior")
        self.git("add", ".")
        self.git("commit", "-qm", "Change without bump")
        code, output = self.run_check("--base", base)
        self.assertEqual(code, 1)
        self.assertIn("has not advanced past", output)
        for relative in (self.portable, self.claude):
            self.edit(relative, lambda data: data.update(version="1.1.0"))
        self.edit(self.legacy_catalog, lambda data: data["plugins"][0].update(version="1.1.0"))
        self.git("add", ".")
        self.git("commit", "-qm", "Bump both manifests and catalog")
        self.assertEqual(self.run_check("--base", base), (0, ""))


if __name__ == "__main__":
    unittest.main()
