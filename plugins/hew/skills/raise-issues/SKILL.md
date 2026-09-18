---
name: raise-issues
description: File review findings as GitHub issues using the hew CLI, deduplicated by a stable review key so re-running a review does not re-file tracked work. Use after any critique review skill (review-code, review-tests, review-docs, review-o11y) or with a findings file, and whenever the user says "raise these", "file these findings", "turn this review into issues", "create issues for these", or runs a review inside an automated loop.
---

# Raise Issues

Turn structured review findings into hew issues, deduplicated by a stable key so the same
finding does not get filed twice when a review runs again.

> [!IMPORTANT]
> [REFERENCE.md](REFERENCE.md) carries slug handling, the findings and plan-file shapes, and a
> worked example. Read it before computing keys.

This skill does not run a review. If the findings are stale, re-run the review first.

## Input

Parse the input for:

- **`--findings <path>`** — a JSON findings file. Preferred, and the only form that behaves
  deterministically unattended.
- **`--dry-run`** — build the plan and run `hew apply --dry-run`, then stop.
- **`--non-interactive`** — never ask anything; skip the confirmation step and report the
  outcome instead.
- **anything else** — filtering guidance, e.g. "only P1 and P2", "skip the naming findings".

Findings come from `--findings` when given, otherwise from the review report in conversation
context (a `N files reviewed, M issues found` header followed by `[P1]`/`[P2]`/`[P3]` findings
with `**Location:**`, an explanation, a fix, and a done-when criterion). Formatting variation is
fine; priority, location and fix are what matter.

When neither is available: ask which findings to file if a human is present, and if
`--non-interactive` is set, report that no findings were supplied and exit without filing.

**Say which of the two nothing-happened cases you are in.** "Reviewed and found nothing" and
"never received findings" both file zero issues, and a loop that cannot tell them apart reports
a broken pipeline as a clean codebase.

## Prerequisites

`hew` on PATH and authenticated — exit code 4 from any `hew` command means run `gh auth login`.
Run from a checkout of the target repository; `--repo owner/name` overrides detection.

## Step 1 — Normalize each finding

Extract priority, title, location(s), explanation, fix, done-when criterion, and which review
skill produced it. Derive a done-when from the fix if it is missing. Skip any finding with no
priority, no location, or no fix, and count the skips in the final report rather than guessing.

## Step 2 — Compute the review key

The key is what makes a second run recognise its own earlier work:

```
review-key: <skill>/<pattern>/<scope>
```

- **`skill`** — `o11y`, `tests`, `docs`, or `code`.
- **`pattern`** — comes from the review itself when the findings file carries one, and must be
  passed through unchanged; re-spelling a slug here orphans every issue already filed under the
  original. Only when a finding arrives without one, pick from the vocabulary in the relevant
  critique skill's `REFERENCE.md`.
- **`scope`** — **derive this mechanically**: the deepest directory that contains every
  affected file, or the file path itself when there is exactly one. Do not choose it by
  judgement. Two runs that anchor the same finding at `internal/http` and
  `internal/http/handler` file it twice, and that single inconsistency is what turns a loop
  into a duplicate factory.

Severity is deliberately **not** part of the key. It legitimately moves between runs — after a
recalibration or a pattern collapse — and identity has to survive that.

## Step 3 — Deduplicate

Follow the read order the primer prescribes rather than inventing one — `hew search` first, then
`hew list --json --bodies --state all` when exhaustiveness matters, and `hew show <n>` only to
read a candidate those surfaced. Search on the key itself: `hew search "review-key: <key>"`.

The part to hold on to is `--state all`. Every step of that order spans closed issues as well as
open ones, and that is load-bearing rather than incidental: a dedup pass reading only open issues
re-files every finding the moment its fix merges, which is the failure this whole scheme exists
to prevent.

Then act on what came back:

| Match | Action |
|---|---|
| Open issue, same key | Already tracked — skip. If the scope widened (more files now affected), refresh the body with `hew set <n> --body-file <f>` rather than filing a second issue. |
| Closed as completed, same key | The pattern came back. File a new issue with `--discovered-from <n>` — this is a regression, and it is the most valuable thing the key buys you. |
| Closed as not-planned or duplicate | Suppress permanently. Re-filing something a human explicitly declined is the fastest way to get this pipeline muted. |
| No key match | Before filing, check the open review issues for the same problem under a different slug, and reuse the existing issue if you find one. This is the backstop for vocabulary drift. |

## Step 4 — Map onto hew fields

- **Priority maps straight across**: P1→`P1`, P2→`P2`, P3→`P3`, P4→`P4`. **Never assign P0.**
  It stays reserved for a human declaring an emergency, which is also what hew's own CI triage
  agent does.
- **Type**: `bug` for something broken or wrong; `task` for something missing — an absent test,
  an uncovered error path, a missing prerequisite section.
- **Body sections**: `where` ← the location list, then a blank line, then the `review-key:` line.
  `problem` ← the explanation. `fix` ← the prescription. `done-when` ← the criterion, as one or
  more checklist items.

The key lives in `where` because hew renders bodies as-is, which keeps it greppable by both
`hew search` and `hew list --bodies` without needing a field the tracker does not have.

**Write code-shaped text as code spans.** Paths, symbols, flags, commands, and error strings all
go in backticks — `` `internal/http/middleware/logging.go:13` ``, `` `r.Header` ``,
`` `fmt.Errorf("...: %w", err)` ``. Wrap the whole command rather than the flag inside it. hew
checks composed bodies and warns about unmarked code text, but the reason is not the warning:
review findings are made almost entirely of these strings, and an issue body is the one artifact
here written for a human in a browser rather than an agent in a terminal. Rendered as
proportional prose, the characters carrying the meaning — slashes, dots, double dashes — are
exactly the ones that dissolve into the sentence around them.

**The `review-key:` line is the exception — leave it bare.** It is an identity token that
`hew search` matches as a substring, not prose anyone reads, and its format is load-bearing:
re-rendering it orphans every issue already filed under the old spelling. Accept the warning on
that line.

## Step 5 — Write a plan, then apply it

Write every surviving finding to a JSONL plan (shape in REFERENCE.md) and apply it:

```bash
hew apply findings-plan.jsonl --dry-run    # always first
hew apply findings-plan.jsonl
```

Use a plan rather than a loop of `hew create` calls: creation is checkpointed to a state file as
it happens, so a run that dies halfway resumes without creating duplicates. That property is the
whole reason this is safe to run on a schedule.

Show the plan and confirm before applying, unless `--dry-run` or `--non-interactive` is set.

## Step 6 — Report

Close with counts that let the next run — or a human reading a job log — tell what happened:
issues filed, findings already tracked, findings suppressed against a declined issue,
regressions re-filed, and findings skipped as malformed.
