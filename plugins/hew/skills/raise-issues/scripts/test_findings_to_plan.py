"""Tests for findings_to_plan.

Run with `python3 -m unittest discover plugins/hew/skills/raise-issues/scripts`
— stdlib only; the CLI cases run the script as a subprocess.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from findings_to_plan import convert, derive_scope, derive_scope_legacy, review_key

SCRIPT = Path(__file__).with_name("findings_to_plan.py")


def finding(priority="P2", **kw):
    f = {"skill": "code", "priority": priority, "pattern": "god-function",
         "title": "Handler does everything", "files": ["internal/http/a.go"],
         "fix": "Split it.", "explanation": "Too much.", "done_when": "Split."}
    f.update(kw)
    return f


def key_of(line):
    for row in line["where"].splitlines():
        if row.startswith("review-key: "):
            return row[len("review-key: "):]
    raise AssertionError("no review-key line")


def cli(*args, findings=None, status="reviewed"):
    with tempfile.TemporaryDirectory() as d:
        path = Path(d, "findings.json")
        path.write_text(json.dumps(
            {"skill": "code", "status": status, "findings": findings or []}))
        return subprocess.run([sys.executable, str(SCRIPT), str(path), *args],
                              capture_output=True, text=True)


class Convert(unittest.TestCase):
    def test_legacy_portability_identity_emits_the_canonical_key(self):
        plans = [convert(finding(skill=skill, pattern="single-harness-tool"),
                         None, None, None, "bug")[0]
                 for skill in ("skills", "portability")]
        self.assertEqual(plans[0], plans[1])
        self.assertIn("review-key: portability/single-harness-tool/", plans[0]["where"])

    def test_pump_wiring(self):
        line, _ = convert(finding(), 12, 21, 34, "bug")
        self.assertEqual((line["parent"], line["blocked-by"], line["discovered-from"]),
                         (12, [21], 21))
        self.assertIn("review-key: code/god-function/internal/http/a.go", line["where"])
        self.assertIn("review-of: #21 (PR #34)", line["where"])

    def test_p0_files_as_p1(self):
        line, _ = convert(finding("P0"), None, None, None, "bug")
        self.assertEqual(line["priority"], "P1")

    def test_at_or_above_skips_less_severe(self):
        line, reason = convert(finding("P3"), None, None, None, "bug", at_or_above=2)
        self.assertIsNone(line)
        self.assertIn("below", reason)
        line, _ = convert(finding("P0"), None, None, None, "bug", at_or_above=2)
        self.assertEqual(line["priority"], "P1")

    def test_single_file_scope_is_unchanged(self):
        line, _ = convert(finding(), None, None, None, "bug")
        self.assertEqual(key_of(line),
                         "code/god-function/internal/http/a.go")

    def test_scope_is_the_finding_file_set(self):
        f = finding(files=["internal/store/store.go", "internal/store/index.go"])
        line, _ = convert(f, None, None, None, "bug")
        self.assertEqual(key_of(line),
                         "code/god-function/internal/store/{index.go,store.go}")

    def test_two_findings_in_one_package_get_different_keys(self):
        one, _ = convert(finding(files=["internal/store/store.go",
                                        "internal/store/index.go"]),
                         None, None, None, "bug")
        two, _ = convert(finding(files=["internal/store/store.go",
                                        "internal/store/verify.go"]),
                         None, None, None, "bug")
        self.assertNotEqual(key_of(one), key_of(two))

    def test_scope_crosses_directories_within_a_common_root(self):
        f = finding(files=["internal/store/store.go",
                           "internal/store/reconcile/apply.go"])
        self.assertEqual(derive_scope(f["files"]),
                         "internal/store/{reconcile/apply.go,store.go}")

    def test_repo_root_scope_names_every_file(self):
        f = finding(files=["cmd/api/main.go", "internal/worker/job.go"])
        self.assertEqual(derive_scope(f["files"]),
                         "./{cmd/api/main.go,internal/worker/job.go}")

    def test_legacy_scope_is_the_old_common_directory(self):
        files = ["internal/store/store.go", "internal/store/index.go"]
        self.assertEqual(derive_scope_legacy(files), "internal/store")
        self.assertEqual(derive_scope_legacy(["internal/http/a.go"]),
                         "internal/http/a.go")

    def test_family_names_the_reviewed_key(self):
        line, _ = convert(
            finding(), 12, 21, 34, "bug",
            reviewed_key="code/leaky-abstraction/internal/store/store.go",
        )
        self.assertTrue(key_of(line).endswith(
            "#family:code/leaky-abstraction/internal/store/store.go"))
        self.assertIn("review-of: #21 (PR #34)", line["where"])

    def test_family_is_not_added_for_a_product_issue(self):
        line, _ = convert(finding(), 12, 21, 34, "bug")
        self.assertNotIn("#family:", key_of(line))

    def test_review_key_helper(self):
        self.assertEqual(review_key("code", "p", "s"), "code/p/s")
        self.assertEqual(review_key("code", "p", "s", "code/q/t"),
                         "code/p/s#family:code/q/t")

    def test_missing_pattern_skipped(self):
        line, reason = convert(finding(pattern=None), None, None, None, "bug")
        self.assertIsNone(line)
        self.assertEqual(reason, "missing pattern")


class Cli(unittest.TestCase):
    def test_filters_by_severity(self):
        p = cli("--at-or-above", "P2", findings=[finding("P1"), finding("P3")])
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual([json.loads(l)["priority"] for l in p.stdout.splitlines()], ["P1"])

    def test_unreviewed_status_exits_3(self):
        self.assertEqual(cli(status="error").returncode, 3)

    def test_missing_flag_value_is_usage_error(self):
        p = cli("--parent")
        self.assertEqual(p.returncode, 2)
        self.assertNotIn("Traceback", p.stderr)

    def test_reviewed_key_reaches_the_plan(self):
        p = cli("--reviewed-issue", "21", "--reviewed-pr", "34",
                "--reviewed-key", "code/leaky-abstraction/internal/store/store.go",
                findings=[finding()])
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("code/god-function/internal/http/a.go"
                      "#family:code/leaky-abstraction/internal/store/store.go",
                      json.loads(p.stdout)["where"])

    def test_reviewed_key_rejects_whitespace(self):
        p = cli("--reviewed-key", "two words", findings=[finding()])
        self.assertEqual(p.returncode, 2)
        self.assertNotIn("Traceback", p.stderr)

    def test_non_numeric_flag_value_is_usage_error(self):
        self.assertEqual(cli("--reviewed-issue", "abc").returncode, 2)

    def test_unreadable_file_is_runtime_error(self):
        p = subprocess.run([sys.executable, str(SCRIPT), "/nonexistent.json"],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 1)
        self.assertNotIn("Traceback", p.stderr)


if __name__ == "__main__":
    unittest.main()
