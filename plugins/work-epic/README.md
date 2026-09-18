# work-epic

A Claude Code skill for working a [hew](https://github.com/lumberbarons/hew) epic by
orchestrating agents rather than by hand, using [herdr](https://github.com/lumberbarons/herdr)
to run them.

## Overview

- **work-epic** — resolves an epic's ready children with a deterministic script, spawns one
  worker agent per child (each running `work-issue`), spawns a reviewer agent over each
  delivered PR (running `review-code`), and stops at the human merge gate.

One epic, pumped: the orchestrator never implements, reviews by hand, merges, or closes. It
accelerates everything up to the human gates, not through them — the reviewer stage pre-digests
PRs so the human's queue says more than "draft".

## Prerequisites

- [`hew`](https://github.com/lumberbarons/hew) on PATH, authenticated via `gh auth login`
- [`herdr`](https://github.com/lumberbarons/herdr) CLI — the skill checks it is running inside
  herdr and stops if not
- The [`hew`](../hew) plugin — workers run `work-issue`
- The [`critique`](../critique) plugin — reviewers run `review-code`
- Run from a checkout of the target repository (`--repo owner/name` overrides detection)

## Usage

```
/work-epic:work-epic 12                     # pump epic 12
/work-epic:work-epic 12 --workers 3         # more live workers (cap ~4)
/work-epic:work-epic 12 --kind codex        # drive workers via skill files, not skills
/work-epic:work-epic 12 --dry-run           # resolver plan only, touch nothing
/work-epic:work-epic 12 --no-review         # workers only; PRs stay draft
```

## How it works

**The plan comes from a script.** `resolve_ready.py` reads the epic (two `hew` reads, one `gh`
read) and emits a JSON fan-out plan: eligible children in priority-sorted, oldest-tie-break
order; every open child left behind with its skip reason (`blocked`, `untriaged`, `claimed`).
A pump that picks differently on each run cannot be reasoned about from its logs, so the agent
never sorts hew output itself.

**Workers are fire-and-reap.** Each worker runs `work-issue --non-interactive --json`, spawned
without `--wait`; the pump reaps settled workers, reads each outcome file, and respawns into
freed capacity until the resolver's `eligible` is empty and no worker is in flight. Outcome
files live under `${TMPDIR:-/tmp}/opencode` so spawned agents never prompt for external access.

**Review is a gate, not a rubber stamp.** A reviewer agent runs `review-code` against each
delivered PR's head. Clean or P3-only flips the PR draft→ready; any P1/P2 is relayed verbatim as
a PR comment and the PR stays draft — findings are never fixed into a PR a human is about to
read.

**Multi-PR runs re-check coupling.** When one run delivered two or more PRs, they are merged
one at a time onto a throwaway integration branch and the quality gate runs over the union —
re-creating, across separate worker sessions, the check `work-issue --batch` gets within one
run. Never pushed, never a PR; a failure files the coupling as its own issue.

**The merge gate stays human.** No merges, no closes, no forced claims, no answering worker
dialogs. A finished epic is escalated for a human to close, never closed by the pump.
