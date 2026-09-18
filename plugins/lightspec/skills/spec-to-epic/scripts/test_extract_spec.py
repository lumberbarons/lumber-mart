from __future__ import annotations

import unittest
from pathlib import Path

from extract_spec import SpecFormatError, parse

MINIMAL = """\
# Widget Export

**Slug**: `009-widget-export`
**Created**: 2026-01-01
**Status**: Accepted

## Description

Export widgets as CSV.

## Prior Decisions

- None

## Out of Scope

- Import

## Assumptions

- CSV only for now

## User Stories

### US1 — Export widgets (P1)

As a user, I want to export widgets so that I can share them

Exports the current filtered view.

## Tasks

### US1

- [ ] T001 Add the export button — `internal/ui/export.go`
- [ ] T002 Stream rows as CSV — `internal/csv/writer.go`, `internal/csv/rows.go`

### Cross-cutting

- [ ] T003 Wire the CLI flag — `cmd/widget/main.go`

## Done When

- [ ] Exporting 0 rows writes a header-only file
- [ ] Exporting 10,000 rows completes in under a second
"""


class ParseTests(unittest.TestCase):
    def test_minimal_spec_round_trips(self) -> None:
        data = parse(MINIMAL, Path("specs/009-widget-export/spec.md"))
        self.assertEqual(data["title"], "Widget Export")
        self.assertEqual(data["slug"], "009-widget-export")
        self.assertEqual(data["status"], "Accepted")
        self.assertEqual(data["description"], "Export widgets as CSV.")
        self.assertEqual(data["prior_decisions"], ["None"])
        self.assertEqual(data["out_of_scope"], ["Import"])
        self.assertEqual(data["done_when"], [
            "Exporting 0 rows writes a header-only file",
            "Exporting 10,000 rows completes in under a second",
        ])

    def test_story_carries_its_own_tasks_and_paths(self) -> None:
        data = parse(MINIMAL, Path("spec.md"))
        self.assertEqual(len(data["stories"]), 1)
        story = data["stories"][0]
        self.assertEqual(story["id"], 1)
        self.assertEqual(story["priority"], "P1")
        self.assertEqual(story["story"], "As a user, I want to export widgets so that I can share them")
        self.assertEqual(story["narrative"], "Exports the current filtered view.")
        self.assertEqual([task["id"] for task in story["tasks"]], ["T001", "T002"])
        # A task can name more than one path — both must survive, not just the first.
        self.assertEqual(story["tasks"][1]["paths"], ["internal/csv/writer.go", "internal/csv/rows.go"])

    def test_cross_cutting_tasks_are_kept_out_of_every_story(self) -> None:
        data = parse(MINIMAL, Path("spec.md"))
        self.assertEqual([task["id"] for task in data["cross_cutting_tasks"]], ["T003"])
        for story in data["stories"]:
            self.assertNotIn("T003", [task["id"] for task in story["tasks"]])

    def test_story_with_no_tasks_is_rejected(self) -> None:
        broken = MINIMAL.replace(
            "### US1\n\n- [ ] T001 Add the export button — `internal/ui/export.go`\n"
            "- [ ] T002 Stream rows as CSV — `internal/csv/writer.go`, `internal/csv/rows.go`\n",
            "### US1\n\n",
        )
        with self.assertRaises(SpecFormatError):
            parse(broken, Path("spec.md"))

    def test_task_group_without_matching_story_is_rejected(self) -> None:
        broken = MINIMAL.replace("### US1\n\n- [ ] T001", "### US2\n\n- [ ] T001")
        with self.assertRaises(SpecFormatError):
            parse(broken, Path("spec.md"))

    def test_missing_status_line_is_rejected(self) -> None:
        broken = MINIMAL.replace("**Status**: Accepted\n", "")
        with self.assertRaises(SpecFormatError):
            parse(broken, Path("spec.md"))

    def test_real_spec_parses(self) -> None:
        # The fixture above is deliberately tiny; this is the load-bearing case.
        repo_spec = (
            Path(__file__).resolve().parents[4]
            / "specs" / "001-deterministic-retirement-engine" / "spec.md"
        )
        if not repo_spec.is_file():
            self.skipTest("repo spec not present in this checkout")
        data = parse(repo_spec.read_text(encoding="utf-8"), repo_spec)
        self.assertEqual(len(data["stories"]), 8)
        self.assertEqual(sum(len(s["tasks"]) for s in data["stories"]), 25)
        self.assertEqual(len(data["done_when"]), 8)


if __name__ == "__main__":
    unittest.main()
