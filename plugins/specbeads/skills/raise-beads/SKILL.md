---
name: raise-beads
description: File review findings as beads. Reads recent review output (from review-code, review-tests, review-docs, or any structured findings) from conversation context, deduplicates against existing open/closed beads, and creates bug/task beads with structured descriptions. Use after running a review skill to turn findings into trackable work.
---

# Raise Beads

Convert structured review findings into beads, with deduplication against existing work.

## User Input

You **MUST** consider the user input before proceeding (if any was given).

## Argument Parsing

Parse the input for:
- **`--dry-run`**: Show the bead list that would be created without running `bd create`
- **`<additional instructions>`**: Filtering or scope guidance (e.g., "only P1 and P2", "skip the naming findings")

## Prerequisites

- `bd` CLI available on PATH
- Recent review findings visible in conversation context (from critique's review-code, review-tests, review-docs, or equivalent)

If no review output is visible in the conversation, ask the user to paste the findings or run a review skill first.

## Workflow

### Step 1 — Locate findings

Scan the recent conversation for a review report. Look for:

- A header like `N files reviewed, M issues found (severity breakdown)`
- H3 findings with priority tags (`[P1]`, `[P2]`, `[P3]`, `[P4]`)
- Each finding should have a **Location** (file:line or file), an explanation, a fix, and ideally a done-when criterion

The findings may come from any of the critique review skills or a hand-written list. Be flexible: priorities, locations, and fixes are what matter. Minor formatting variation is fine.

If no findings are visible, stop and ask the user where to find them.

### Step 2 — Parse each finding

For each finding, extract:

- **Priority** (P1/P2/P3/P4) — the leading tag
- **Title** — the H3 heading text after the priority tag
- **Location** — file or file:line
- **Explanation** — what's wrong and why it matters
- **Fix** — the concrete prescription
- **Done when** — the verifiable criterion (if not explicit, derive one from the fix)
- **Finding source** — infer from surrounding context whether it came from a code review, tests review, or docs review. Used for title prefix and type routing.

If any required field is missing (priority, location, or fix), skip the finding and note it in the summary.

### Step 3 — Apply user filtering

If the input contains filtering guidance ("only P1 and P2", "skip the naming findings", "just the OrderService ones"), narrow the finding list accordingly before deduplication.

### Step 4 — Deduplicate against existing beads

Before creating any beads, check what already exists:

1. Run `bd list --status=open` to fetch open issues.
2. Run `bd list --status=closed` to fetch resolved issues.
3. For each finding, compare against open bead titles and descriptions. If an open bead already covers the same issue (same location, same category), skip creating a new one and note it in the summary.
4. **Check closed beads before suppressing.** For findings that match a closed bead title, run `bd show <id>` on the closed bead and verify the fix actually resolved the issue in the current code. Only suppress the finding if the fix is complete. If the problem still exists (in the same or different locations), create a new bead for the remaining instances. The goal is to prevent flip-flopping on intentional resolutions, not to give closed beads permanent immunity.

When in doubt, show the potential duplicate to the user rather than creating.

### Step 5 — Type and priority routing

For each remaining finding, determine the bead type:

| Source | Finding kind | Type |
|--------|-------------|------|
| review-code | Any | `bug` |
| review-tests | Quality bugs (shared state, tautological assertions, unclear names) | `bug` |
| review-tests | Missing coverage (edge cases, untested files, error paths) | `task` |
| review-docs | Errors (broken links, wrong commands, index drift, invalid globs) | `bug` |
| review-docs | Missing content (absent prereqs, missing sections, uncovered enumerations) | `task` |
| Unknown source | Infer from the finding's language — does it describe something broken, or something missing? | `bug` / `task` |

Priority maps directly: P1 → `--priority=1`, P2 → `--priority=2`, P3 → `--priority=3`, P4 → `--priority=4`.

Title prefix:
- Code findings: `Code: <specific issue>`
- Test findings: `Test: <specific issue>` (for bugs) or `Test: <what to add>` (for coverage)
- Docs findings: `Docs: <specific issue>` (for bugs) or `Docs: <what to add>` (for missing content)

### Step 6 — Confirm with user

Before running `bd create`, show the user a summary:

```
Would create N beads:
- [P1 bug] Code: <title> (src/foo.go:42)
- [P2 task] Test: <title> (tests/bar_test.go)
- ...

Would skip M findings (already covered by existing beads):
- Code: <title> → duplicate of sam-b3i (open)
- Docs: <title> → resolved by sam-b1c (closed, fix verified)
```

Ask the user to confirm before proceeding. Respect `--dry-run` — stop here without running `bd create`.

### Step 7 — Create beads

For each confirmed finding, run:

```bash
bd create --type=<bug|task> --priority=<1-4> --title="<prefix>: <title>" \
  --description="<file:line>

<explanation>

Fix: <concrete prescription>

Done when: <verifiable criterion>"
```

The description MUST use the three-part structure (location, explanation, Fix, Done when), with blank lines between parts for readability.

After creating, report the final result: how many beads were created, how many were deduped, any that were skipped due to missing fields.

## Description Format

Each bead description must follow this shape:

```
<file:line>

<Explanation of the problem: what is wrong or missing and why it matters.>

Fix: <Concrete prescription of exactly what to change or add. For API design
issues, specify the exact shape — parameter names, types, signatures — not just
the general approach. For missing content, specify exactly what section or
scenario to add.>

Done when: <A verifiable completion criterion that can be checked by reading
the diff or the file. Must reference specific functions, files, or observable
behaviours. Example: "Both parseSkillFrontmatter and parseAgentFrontmatter
delegate to a shared parseFrontmatterRaw; no duplicated delimiter-scanning
code remains in either function."
NOT: "The duplication is removed.">
```

## Notes

- The fix skill picks up beads created by raise-beads automatically — there is no coordination needed beyond running them in sequence.
- raise-beads does not re-run any review itself. If the findings are stale, re-run the review skill first.
- This skill is bead-specific. In environments without `bd`, read the review report directly or ask Claude to act on specific findings without going through beads.
