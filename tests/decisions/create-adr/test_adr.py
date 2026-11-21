"""Tests for adr.py. Run: python3 -m unittest discover -s <this directory>.

The template and the checker define one format in two places. The first group pins
them together; the rest break one rule at a time, then drive `status` and
`backlinks` against a throwaway repository.
"""

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SKILL = REPO / "plugins/decisions/skills/create-adr"
sys.path.insert(0, str(SKILL / "scripts"))

import adr

TEMPLATE = SKILL / "assets" / "adr-template.md"

FILLED = """\
---
id: ADR-0004
title: Use Postgres for the event store
status: proposed
date: 2026-01-02
deciders: [alice]
supersedes: []
superseded-by: []
related: []
research: []
tags: [storage]
---

# ADR-0004: Use Postgres for the event store

## Context and Problem Statement

The ledger needs ordered, replayable events and the team already runs Postgres.

## Decision Drivers

- p99 read latency under 30 ms at 10k QPS on the checkout path
- no new datastore for the on-call rotation to learn

## Considered Options

1. **Postgres** — append-only table with a sequence column
2. **DynamoDB** — streams with TTL

## Decision Outcome

Chosen option: **Postgres**

The latency driver is met in the load test, and the operational driver rules out DynamoDB.

## Consequences

### Positive

- One datastore to operate

### Negative

- Write throughput is capped by a single primary

### Risks

- Replay of a year of events may need partitioning

## Pros and Cons of the Options

### Postgres

- Good: already operated

### DynamoDB

- Bad: new on-call burden

## Implementation Notes

All writes go through `ledger.Append`; nothing else may insert into `events`.

## References

- [Load test](https://example.com/load-test) — shows 22 ms p99
"""


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = adr.main(list(argv))
        except SystemExit as exit_:
            code = int(exit_.code or 0)
    return code, out.getvalue(), err.getvalue()


def problems(text: str, name: str = "0004-use-postgres.md") -> list[str]:
    return adr.check_text(text, Path(name), None)


def scaffold() -> str:
    """What init-adr.sh writes: the template with its three substitutions."""
    return (
        TEMPLATE.read_text(encoding="utf-8")
        .replace("ADR-NNNN", "ADR-0001")
        .replace("YYYY-MM-DD", "2026-01-02")
        .replace("TITLE_PLACEHOLDER", "Use X")
    )


class TemplateMatchesChecker(unittest.TestCase):
    def test_fresh_scaffold_fails_only_for_placeholders_and_deciders(self) -> None:
        found = problems(scaffold(), "0001-use-x.md")
        self.assertTrue(found)
        for line in found:
            self.assertTrue(
                "placeholder" in line or "`deciders` is empty" in line,
                f"unexpected complaint: {line}",
            )

    def test_every_template_blank_is_reported(self) -> None:
        lines = scaffold().splitlines()
        body = next(i for i, line in enumerate(lines) if line == "---" and i > 0) + 1
        # The template's body holds no link and no code span: every `[` in it is a blank.
        blanks = {n for n, line in enumerate(lines, 1) if n > body and "[" in line}
        self.assertGreater(len(blanks), 15)
        reported = {
            int(line.split(":")[1])
            for line in problems(scaffold(), "0001-use-x.md")
            if "placeholder" in line
        }
        self.assertEqual(sorted(blanks - reported), [])

    def test_filled_example_passes(self) -> None:
        self.assertEqual(problems(FILLED), [])


class FrontmatterRules(unittest.TestCase):
    def swap(self, old: str, new: str) -> list[str]:
        self.assertIn(old, FILLED)
        return problems(FILLED.replace(old, new, 1))

    def test_bad_status(self) -> None:
        self.assertTrue(any("status must be one of" in p for p in self.swap("status: proposed", "status: maybe")))

    def test_superseded_needs_superseded_by(self) -> None:
        self.assertTrue(any("must name what replaced it" in p for p in self.swap("status: proposed", "status: superseded")))

    def test_empty_deciders(self) -> None:
        self.assertTrue(any("deciders" in p for p in self.swap("deciders: [alice]", "deciders: []")))

    def test_id_must_match_file_name(self) -> None:
        self.assertTrue(any("does not match the file name" in p for p in self.swap("id: ADR-0004", "id: ADR-0009")))

    def test_bad_date(self) -> None:
        self.assertTrue(any("date must be" in p for p in self.swap("date: 2026-01-02", "date: 2026-13-45")))

    def test_unknown_key(self) -> None:
        self.assertTrue(any("unknown frontmatter key" in p for p in self.swap("tags: [storage]", "tags: [storage]\nowner: bob")))

    def test_missing_key(self) -> None:
        self.assertTrue(any("missing `research`" in p for p in self.swap("research: []\n", "")))

    def test_bad_research_id(self) -> None:
        self.assertTrue(any("RES-0001" in p for p in self.swap("research: []", "research: [rubbish]")))

    def test_link_to_missing_adr(self) -> None:
        self.assertTrue(any("which is not in" in p for p in self.swap("related: []", "related: [ADR-0099]")))

    def test_h1_must_match(self) -> None:
        self.assertTrue(any("H1 must be" in p for p in self.swap("# ADR-0004: Use Postgres for the event store", "# ADR-0004: Something else")))

    def test_superseded_by_on_live_adr(self) -> None:
        self.assertTrue(any("should be superseded" in p for p in self.swap("superseded-by: []", "superseded-by: [ADR-0003]")))


class BodyRules(unittest.TestCase):
    def test_missing_section(self) -> None:
        text = FILLED.replace("## Implementation Notes", "## Notes")
        found = problems(text)
        self.assertTrue(any("missing section `## Implementation Notes`" in p for p in found))

    def test_project_section_is_allowed(self) -> None:
        text = FILLED.replace("## References", "## Rollout\n\nBehind a flag.\n\n## References")
        self.assertEqual(problems(text), [])

    def test_out_of_order(self) -> None:
        text = FILLED.replace("## Consequences", "## Decision Drivers", 1).replace(
            "## Decision Drivers\n\n- p99", "## Consequences\n\n- p99", 1
        )
        self.assertTrue(any("out of order" in p for p in problems(text)))

    def test_empty_section(self) -> None:
        text = FILLED.replace("All writes go through `ledger.Append`; nothing else may insert into `events`.", "")
        self.assertTrue(any("`## Implementation Notes` is empty" in p for p in problems(text)))

    def test_placeholder_is_reported_with_its_line(self) -> None:
        text = FILLED.replace("- Good: already operated", "- Good: [what is good about it]")
        found = [p for p in problems(text) if "placeholder" in p]
        self.assertEqual(len(found), 1)
        self.assertIn("[what is good about it]", found[0])

    def test_links_code_and_fences_are_not_placeholders(self) -> None:
        text = FILLED.replace(
            "- Good: already operated",
            "- Good: see [the runbook](docs/runbook.md) and `events[some index]`\n\n"
            "```go\nx := []string{\"a b c\"} // [not a blank here]\n```",
        )
        self.assertEqual(problems(text), [])

    def test_headings_inside_a_fence_are_not_sections(self) -> None:
        text = FILLED.replace("- Good: already operated", "```\n## Not A Section\n```")
        self.assertEqual(problems(text), [])


def write(directory: Path, name: str, text: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(text, encoding="utf-8")
    return path


def research_doc(ident: str, status: str, related: str = "[]") -> str:
    return (
        f"---\nid: {ident}\ntitle: \"Q\"\nstatus: {status}\ndate: 2026-01-01\nauthors: []\n"
        f"supersedes: []\nsuperseded-by: []\nrelated: {related}\ntags: []\n---\n\n# {ident}: Q\n"
    )


class Lifecycle(unittest.TestCase):
    """status and backlinks, against a repository with a research directory."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (self.root / ".git").mkdir()
        self.adrs = self.root / "docs" / "adr"
        self.res = self.root / "docs" / "research"

    def new_adr(self, **fields: str) -> Path:
        text = FILLED
        for key, value in fields.items():
            old = next(line for line in FILLED.splitlines() if line.startswith(f"{key.replace('_', '-')}:"))
            text = text.replace(old, f"{key.replace('_', '-')}: {value}", 1)
        return write(self.adrs, "0004-use-postgres.md", text)

    def old_adr(self, status: str = "accepted") -> Path:
        text = FILLED.replace("ADR-0004", "ADR-0002").replace("status: proposed", f"status: {status}")
        if status == "superseded":
            text = text.replace("superseded-by: []", "superseded-by: [ADR-0004]")
        return write(self.adrs, "0002-use-dynamo.md", text)

    def test_duplicate_adr_number_is_reported(self) -> None:
        first = self.new_adr()
        twin = write(self.adrs, "0004-use-mysql.md", FILLED.replace("Use Postgres for the event store", "Use MySQL"))
        for path in (first, twin):
            code, out, _ = run("check", str(path))
            self.assertEqual(code, 1)
            self.assertIn("ADR number 0004 is also used by", out)

    def test_distinct_numbers_are_not_duplicates(self) -> None:
        self.old_adr()
        code, out, _ = run("check", str(self.new_adr()))
        self.assertEqual((code, out.strip()), (0, "ok"))

    def test_status_prints(self) -> None:
        path = self.new_adr()
        self.assertEqual(run("status", str(path)), (0, "proposed\n", ""))

    def test_accept_moves_status_and_date_and_nothing_else(self) -> None:
        path = self.new_adr()
        before = path.read_text(encoding="utf-8")
        code, out, _ = run("status", str(path), "accepted", "--date", "2026-02-03")
        self.assertEqual(code, 0, out)
        after = path.read_text(encoding="utf-8")
        self.assertEqual(
            after,
            before.replace("status: proposed", "status: accepted").replace("date: 2026-01-02", "date: 2026-02-03"),
        )
        self.assertEqual(run("check", str(path))[0], 0)

    def test_accept_refuses_a_document_that_fails_check(self) -> None:
        path = self.new_adr(deciders="[]")
        code, out, err = run("status", str(path), "accepted")
        self.assertEqual(code, 1)
        self.assertIn("deciders", out)
        self.assertIn("refusing", err)
        self.assertIn("status: proposed", path.read_text(encoding="utf-8"))

    def test_accept_refuses_an_already_accepted_adr(self) -> None:
        path = self.new_adr(status="accepted")
        code, out, _ = run("status", str(path), "accepted")
        self.assertEqual(code, 1)
        self.assertIn("only a `proposed` ADR can be accepted", out)

    def test_only_accepted_can_be_set(self) -> None:
        path = self.new_adr()
        code, _, err = run("status", str(path), "superseded")
        self.assertEqual(code, 2)
        self.assertIn("backlinks", err)

    def test_accept_refuses_draft_research(self) -> None:
        write(self.res, "0001-q.md", research_doc("RES-0001", "draft"))
        path = self.new_adr(research="[RES-0001]")
        code, out, _ = run("status", str(path), "accepted")
        self.assertEqual(code, 1)
        self.assertIn("RES-0001", out)
        self.assertIn("complete", out)

    def test_cited_research_must_exist_when_a_repository_is_known(self) -> None:
        path = self.new_adr(research="[RES-0007]")
        code, out, _ = run("check", str(path))
        self.assertEqual(code, 1)
        self.assertIn("RES-0007", out)

    def test_accept_refuses_to_supersede_a_proposed_adr(self) -> None:
        self.old_adr(status="proposed")
        path = self.new_adr(supersedes="[ADR-0002]")
        code, out, _ = run("status", str(path), "accepted")
        self.assertEqual(code, 1)
        self.assertIn("only an accepted ADR can be superseded", out)

    def test_backlinks_supersede_and_research(self) -> None:
        old = self.old_adr()
        res = write(self.res, "0001-q.md", research_doc("RES-0001", "complete", "[ADR-0001]"))
        path = self.new_adr(supersedes="[ADR-0002]", research="[RES-0001]")
        self.assertEqual(run("status", str(path), "accepted")[0], 0)

        code, out, _ = run("backlinks", str(path))
        self.assertEqual(code, 0, out)
        old_text = old.read_text(encoding="utf-8")
        self.assertIn("status: superseded", old_text)
        self.assertIn("superseded-by: [ADR-0004]", old_text)
        self.assertIn("related: [ADR-0001, ADR-0004]", res.read_text(encoding="utf-8"))
        self.assertEqual(run("check", str(old))[0], 0)

    def test_backlinks_touch_nothing_else(self) -> None:
        old = self.old_adr()
        before = old.read_text(encoding="utf-8")
        path = self.new_adr(supersedes="[ADR-0002]")
        run("status", str(path), "accepted")
        run("backlinks", str(path))
        self.assertEqual(
            old.read_text(encoding="utf-8"),
            before.replace("status: accepted", "status: superseded").replace(
                "superseded-by: []", "superseded-by: [ADR-0004]"
            ),
        )

    def test_backlinks_are_idempotent(self) -> None:
        self.old_adr()
        write(self.res, "0001-q.md", research_doc("RES-0001", "complete"))
        path = self.new_adr(supersedes="[ADR-0002]", research="[RES-0001]")
        run("status", str(path), "accepted")
        run("backlinks", str(path))
        snapshot = {p: p.read_text(encoding="utf-8") for p in self.root.rglob("*.md")}
        code, out, _ = run("backlinks", str(path))
        self.assertEqual((code, out.strip()), (0, "nothing to do"))
        self.assertEqual(snapshot, {p: p.read_text(encoding="utf-8") for p in self.root.rglob("*.md")})

    def test_backlinks_need_an_accepted_adr(self) -> None:
        path = self.new_adr()
        code, _, err = run("backlinks", str(path))
        self.assertEqual(code, 2)
        self.assertIn("accepted", err)


if __name__ == "__main__":
    unittest.main()
