"""Exercise the installed script against real, isolated Git repositories."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[3]
SCRIPTS = REPO / "plugins/critique/scripts"
SCRIPT = SCRIPTS / "review-mode.py"

class ReviewModeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        # Parent agent Git overrides must not redirect these scratch repos.
        for key in tuple(self.env):
            if key.startswith(("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")):
                del self.env[key]
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Review mode test")
        self.git("config", "user.email", "review@example.invalid")
        self.write("app.txt", "original\n")
        self.commit()

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, env=self.env,
                              text=True, capture_output=True, check=True).stdout.strip()

    def write(self, name, content):
        (self.root / name).write_text(content)

    def commit(self):
        self.git("add", ".")
        self.git("commit", "-m", "test change")

    def feature(self, name="feat/example"):
        self.git("switch", "-c", name)
        self.write("app.txt", "changed\n")
        self.commit()

    def run_mode(self, *args, cwd=None):
        return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd or self.root,
                              env=self.env, text=True, capture_output=True, check=False)

    def mode(self, *args, cwd=None):
        result = self.run_mode(*args, cwd=cwd)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_clean_feature_diff_fixes_and_identifies_snapshot(self):
        self.feature()
        before = self.git("status", "--porcelain")
        result = self.mode("--scope", "branch")
        self.assertEqual(result["mode"], "fix")
        self.assertTrue(result["automatic"])
        self.assertEqual(result["head"], self.git("rev-parse", "HEAD"))
        self.assertEqual(result["base_commit"], self.git("rev-parse", "main"))
        self.assertEqual(result["branch"], "feat/example")
        self.assertEqual(self.git("status", "--porcelain"), before)

    def test_fix_and_chore_prefixes_are_eligible(self):
        self.feature()
        for name in ("fix/example", "chore/example"):
            with self.subTest(name=name):
                self.git("branch", "-m", name)
                self.assertEqual(self.mode("--scope", "branch")["mode"], "fix")

    def test_pr_audit_unknown_and_omitted_scope_report_even_on_feature(self):
        self.feature()
        for args in ((), ("--scope", "pr"), ("--scope", "audit"), ("--scope", "unknown")):
            with self.subTest(args=args):
                self.assertEqual(self.mode(*args)["mode"], "report")

    def test_explicit_report_wins_over_automatic_eligibility(self):
        self.feature()
        self.assertEqual(self.mode("--scope", "branch", "--report-only")["mode"], "report")

    def test_explicit_fix_overrides_default_mode_without_claiming_auto_eligibility(self):
        self.write("untracked.txt", "existing user work")
        for scope in ("pr", "audit", "branch"):
            with self.subTest(scope=scope):
                result = self.mode("--scope", scope, "--fix")
                self.assertEqual(result["mode"], "fix")
                self.assertFalse(result["automatic"])

    def test_conflicting_or_invalid_arguments_never_emit_fix(self):
        self.feature()
        for args in (("--fix", "--report-only"), ("--scope", "feature"), ("--typo",)):
            with self.subTest(args=args):
                result = self.run_mode(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")

    def test_default_branch_reports(self):
        result = self.mode("--scope", "branch")
        self.assertEqual(result["mode"], "report")
        self.assertIn("default branch", result["reason"])

    def test_detached_head_reports(self):
        self.feature()
        self.git("switch", "--detach")
        self.assertEqual(self.mode("--scope", "branch")["mode"], "report")

    def test_release_and_unrecognized_branches_report(self):
        self.feature()
        for name in ("release/1.0", "develop", "feature/example"):
            with self.subTest(name=name):
                self.git("branch", "-m", name)
                self.assertEqual(self.mode("--scope", "branch")["mode"], "report")

    def test_staged_unstaged_and_untracked_changes_report(self):
        self.feature()
        self.write("app.txt", "user edits\n")
        self.assertEqual(self.mode("--scope", "branch")["mode"], "report")
        self.git("add", "app.txt")
        self.assertEqual(self.mode("--scope", "branch")["mode"], "report")
        self.commit()
        self.write("untracked.txt", "user work\n")
        self.assertEqual(self.mode("--scope", "branch")["mode"], "report")

    def test_empty_diff_reports(self):
        self.git("switch", "-c", "feat/empty")
        self.assertEqual(self.mode("--scope", "branch")["mode"], "report")

    def test_unknown_and_ambiguous_local_defaults_report(self):
        self.git("branch", "-m", "trunk")
        self.feature()
        self.assertEqual(self.mode("--scope", "branch")["mode"], "report")
        self.git("branch", "main", "trunk")
        self.git("branch", "master", "trunk")
        self.assertEqual(self.mode("--scope", "branch")["mode"], "report")

    def test_remote_without_recorded_default_does_not_guess_main(self):
        self.feature()
        self.git("remote", "add", "origin", str(self.root / "not-contacted"))
        self.assertEqual(self.mode("--scope", "branch")["mode"], "report")

    def test_recorded_remote_default_is_used_without_local_default_branch(self):
        self.git("branch", "-m", "trunk")
        self.git("remote", "add", "origin", str(self.root / "not-contacted"))
        self.git("update-ref", "refs/remotes/origin/trunk", "HEAD")
        self.git("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk")
        self.feature()
        result = self.mode("--scope", "branch")
        self.assertEqual(result["mode"], "fix")
        self.assertEqual(result["base"], "refs/remotes/origin/trunk")

    def test_dangling_remote_default_reports(self):
        self.feature()
        self.git("remote", "add", "origin", str(self.root / "not-contacted"))
        self.git("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/missing")
        self.assertEqual(self.mode("--scope", "branch")["mode"], "report")

    def test_unrelated_histories_report(self):
        self.git("switch", "--orphan", "feat/unrelated")
        self.write("new.txt", "new history\n")
        self.commit()
        self.assertEqual(self.mode("--scope", "branch")["mode"], "report")

    def test_not_a_repository_reports(self):
        with tempfile.TemporaryDirectory() as outside:
            self.assertEqual(self.mode("--scope", "branch", cwd=outside)["mode"], "report")

    def test_rechecking_detects_head_and_worktree_changes(self):
        self.feature()
        first = self.mode("--scope", "branch")
        self.write("app.txt", "later change\n")
        self.assertEqual(self.mode("--scope", "branch")["mode"], "report")
        self.commit()
        second = self.mode("--scope", "branch")
        self.assertEqual(second["mode"], "fix")
        self.assertNotEqual(first["head"], second["head"])


if __name__ == "__main__":
    unittest.main()
