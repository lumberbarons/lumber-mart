# work-epic

A Claude Code skill for working a [hew](https://github.com/lumberbarons/hew) epic by
orchestrating agents rather than by hand, using [herdr](https://github.com/lumberbarons/herdr)
to run them.

## Overview

- **work-epic** — resolves an epic's ready children with a deterministic script, spawns one
  worker agent per child (each running `work-issue`), spawns a reviewer agent over each
  delivered PR (running `review-code`), files the findings as epic children, merges PRs once
  CI is green, and re-pumps until the epic is drained.

One epic, pumped: the orchestrator never implements, reviews by hand, closes, or resolves
conflicts. It accelerates everything up to the gates, not through them — and which gate is
which depends on the mode you pick.

## Modes

**Autonomous (default).** The reviewer is a findings generator: P1/P2 findings become epic
children (filed `blocked-by` the reviewed issue, so their fixes unblock exactly when the PR
merges), and a PR merges once its checks are green, its review is current, and nothing at or
above `--block-on` (default P1) is open. After each merge the pump fast-forwards main, so
every new worktree branches off what actually shipped. A P1 finding holds its PR — the human
resolves it by closing the finding child or fixing the branch — and a merge conflict is filed,
never auto-resolved.

**`--human-review`.** The older contract, unchanged: every PR stays a draft, P1/P2 findings
are relayed as comments, multi-PR runs get the throwaway integration branch, and every merge
is a human's click.

## Prerequisites

- [`hew`](https://github.com/lumberbarons/hew) on PATH, authenticated via `gh auth login`
- [`herdr`](https://github.com/lumberbarons/herdr) CLI — the skill checks it is running inside
  herdr and stops if not
- The [`hew`](../hew) plugin — workers run `work-issue`; findings are filed through
  raise-issues' converter script
- The [`critique`](../critique) plugin — reviewers run `review-code`
- Run from a checkout of the target repository (`--repo owner/name` overrides detection)

## Usage

```
/work-epic:work-epic 12                            # pump epic 12; merge on CI green
/work-epic:work-epic 12 --human-review             # stop at drafts; every merge is human
/work-epic:work-epic 12 --block-on P2              # P1 and P2 findings hold PRs
/work-epic:work-epic 12 --workers 3                # more live workers (cap ~4)
/work-epic:work-epic 12 --max-open-prs 3           # smaller PR backlog (default 2 × workers)
/work-epic:work-epic 12 --kind codex               # drive workers via skill files, not skills
/work-epic:work-epic 12 --dry-run                  # resolver + merge-pass plans only
/work-epic:work-epic 12 --no-review                # autonomous: merge on CI green alone
/work-epic:work-epic 12 --allow-no-checks          # repo has no CI: no checks counts as green
/work-epic:work-epic 12 --resume                   # pick up your own claims a crashed run left
```

The pump spawns from, and fast-forwards, the main checkout, so that checkout must be on the
default branch; it stops and says so otherwise rather than touch a branch you are working on.

## How it works

**The plans come from scripts.** `resolve_ready.py` reads the epic and emits a JSON fan-out
plan — eligible children in priority-sorted, oldest-tie-break order, every open child left
behind with its skip reason (including children already in review or whose worker
failed, so the pump never respawns its own work), plus the main checkout and default branch. `pr_state.py` reads
the epic's open PRs (CI rollups, merge states, review rounds, finding holds) and emits one
deterministic action per PR. A pump that picks differently on each run cannot be reasoned
about from its logs, so the agent never sorts hew or gh output itself.

**Workers are fire-and-reap.** Each worker runs `work-issue --non-interactive --json`, spawned
without `--wait`; the pump reaps settled workers, reads each outcome file, and respawns into
freed capacity. Outcome files live under `${TMPDIR:-/tmp}/opencode` so spawned agents never
prompt for external access.

**Review is a findings generator (and a gate).** A reviewer agent runs `review-code` against
each delivered PR's head. In autonomous mode its findings are converted into `hew apply` plan
lines and filed as epic children — deduplicated by review key, `blocked-by` the reviewed
issue — so the pump itself picks the fixes up once the blocker clears. Every review leaves one
round comment on the PR recording the head it reviewed; a finding at or above `--block-on`
holds the PR as a draft, and a review that could not run is escalated, never read as clean.

**The merge pass is classified, not judged.** `pr_state.py` decides per PR: merge (green,
current review, no holds, up to date with default), mark a draft ready, update the branch when
it falls behind default (server-side, via `gh pr update-branch`), re-review a moved head,
file-and-escalate a conflict, hold on a blocking finding, flag branch protection it cannot
satisfy, or wait for CI — where "no checks yet" is waiting, not green. The pump executes the
classification and re-runs the planner after every write.

**PRs don't pile up behind main.** Two bounds keep the backlog short and fresh. The resolver's
spawn budget (`--max-open-prs`) stops new work once open PRs plus workers in flight reach the
cap, so the pump drains before it grows. The merge pass is a queue: one PR at a time is
brought up to date and merged, so every merge ran CI on current main, and no CI is spent
updating PRs that the next merge would put behind again. "Behind" is measured with the
compare API, so this holds whether or not branch protection requires up-to-date branches. It never merges outside the epic,
never `--admin`, never force-pushes, and never resolves a conflict.

**The merge gate is CI + severity; the judgement gates stay human.** Closing issues and the
epic, clearing a hold, resolving a conflict, and anything past a blocked worker's dialog
are decisions the pump escalates, never makes.

**Multi-PR runs still re-check coupling in human-review mode.** Delivered PRs are merged one
at a time onto a throwaway integration branch and gated over the union. Autonomous mode
dropped the replica: main is the integration surface, every PR is brought up to date with
the default branch just before it merges, and CI is the gate that runs where it ships.
