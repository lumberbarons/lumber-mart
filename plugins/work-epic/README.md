# work-epic

A skill for burning down a [hew](https://github.com/lumberbarons/hew) epic, or any set of issues,
by orchestrating [Orca](https://github.com/stablyai/orca)-managed worktrees and supervised agents
rather than working by hand. Give it issue numbers, an epic, or a description of the work; it
implements, reviews, fixes, repairs, and merges until everything is done — or until a decision
only a human can make.

## Overview

- **One golden path.** It resolves the ready issues with a deterministic script, creates one Orca
  worktree per issue, starts a supervised implementer in it (`work-issue`), has a *different* agent
  review the delivered PR (`review-code`) and fix what it finds in that same session, repairs
  conflicts and red CI, and merges on CI green. Then it re-pumps until nothing else can move.
- **Review once, fix in the session that found it.** A PR is reviewed a single time. The reviewer
  fixes every P1 and P2 it can, safely and inside the PR's own files, runs the quality gate, and
  pushes. A finding is never handed to a later session, so nothing is re-reviewed and no finding
  spawns a finding.
- **The paper trail is kept.** Every finding at P2 or above is filed as an issue, deduplicated by
  review key. The ones the reviewer fixed are closed with the fixing commit; the ones it could not
  fix stay open as backlog.
- **Few reasons to stop.** An unfixed P1, a repair that failed twice, an outage, a review that did
  not run, or branch protection it cannot satisfy. Each parks the item and the rest keeps draining;
  the final report lists every decision needed.

The orchestrator never implements, reviews, fixes, or closes the epic itself.

## Agents

| Role | Runs | Agent |
|---|---|---|
| Implementer | `work-issue` in the issue's worktree | `opencode` |
| Reviewer | `review-code`, then fixes what it found, in the same worktree | `claude` |
| Repairer | the repair contract (conflict or red CI), in the same worktree | `opencode` |
| Coordinator | this skill: plans, spawns, reaps, merges | whichever agent you started |

The agents are a single block in `skills/work-epic/SKILL.md`; change them there. The reviewer is
deliberately not the implementer — a second point of view is the point. Install `work-issue` for
the implementer and `review-code` for the reviewer, and make the work-issue skill directory
readable on the host: the reviewer's fixes and the repairer read its quality-gate table.

**Orca does not expose an installed-agent list through its CLI**, so the agents are your
declaration of what is installed. A failed `worker-start` names the agent that could not launch and
costs only that issue; the pump reports it and never silently swaps in another agent.

## Prerequisites

- [Orca](https://github.com/stablyai/orca) 1.4+ running, with the session inside an Orca-managed
  terminal/worktree. The `orca-cli` and `orchestration` skills should be in context; the skill
  stops if it cannot see the coordinator worktree.
- The target repository registered in Orca (`orca repo list --json`), with CI. A PR with no checks
  reads as "CI has not reported yet" and is never merged.
- [`hew`](https://github.com/lumberbarons/hew) on PATH, authenticated via `gh auth login`.
- The [`hew`](../hew) plugin — implementers run `work-issue`; findings are filed through
  raise-issues' converter script.
- The [`critique`](../critique) plugin — reviewers run `review-code`.
- Run from an Orca-managed worktree of the target repository (`--repo owner/name` overrides
  detection). Prefer a dedicated worktree for the coordinator: the pump writes a `.work-epic/`
  scratch directory and a status comment there.

Orca has no push-notification command. Escalations land as the affected worktree's unread dot plus
its comment and workspace status, and as the pump's final report.

## Usage

```
/work-epic:work-epic 12                         # an epic: its children
/work-epic:work-epic 21 22 25                   # a set of issues
/work-epic:work-epic fix all the bugs in the importer
                                                # a description: the pump lists the issues it
                                                # found and waits for your go-ahead
/work-epic:work-epic 12 --workers 3             # more live workers (cap ~4)
/work-epic:work-epic 12 --dry-run               # resolver + merge plans only
/work-epic:work-epic 12 --resume                # pick up your own claims a crashed run left
```

There are no other flags. Merges are squash, conflicts and red CI are repaired, and a P1 the
reviewer could not fix holds its PR; these are the policy.

The pump fast-forwards the main checkout after each merge, so it must be on the default branch for
that step; if the human has another branch checked out, the pump leaves it alone, skips the
fast-forward, and says so. Worktrees are always based on `origin/<default>` explicitly, so the
human's checkout never determines what a worker branches from.

## How it works

**The plans come from scripts.** `resolve_ready.py` reads the scope and emits a JSON fan-out plan —
eligible issues in priority-sorted, oldest-tie-break order, every open issue left behind with its
skip reason (including issues already in review and issues whose worker failed, so the pump never
respawns its own work), plus the main checkout and default branch. `pr_state.py` reads the scope's
open PRs (CI rollups, merge states, review comment, open findings) and emits one deterministic
action per PR. A pump that picks differently on each run cannot be reasoned about from its logs, so
the agent never sorts hew or gh output itself. Both take the same scope; an epic number stands for
its children.

**The worktree is the unit.** Every issue gets its own Orca worktree, created with
`worker-start --worktree new-child` and nested under the coordinator in the sidebar. The worktree
carries the issue link, PR link, workspace status, comment, and checkout, and it stays alive through
review and repair — the reviewer and the repairer work in the implementer's own checkout, so there
is no second checkout, no second setup, and no branch to collide with. It is removed when the PR
merges or when it did no work. A held, conflicted, failed, or blocked issue keeps its worktree,
marked unread, so the human has a live card to open.

**Agents are supervised, fire-and-reap.** `worker-start` creates a Task and an authoritative
Dispatch, then launches the agent. The pump waits on the Run mailbox with
`orchestration check --wait --types worker_done,escalation,question`, processes the whole FIFO
batch, acknowledges it, and only then spawns into the freed capacity. Outcome files are written
inside the worker's own worktree, and `worker-release` archives the terminal output before closing
it. A worker parked on a permission prompt shows up in `worker-show` as `observation.agentWait`; the
pump marks the worktree unread and never answers it.

**Review is a fix, not a report.** The reviewer runs `review-code` over the PR's diff, then — in the
same session — makes the smallest fix for each P1 and P2 inside the PR's own files, gates it, and
pushes. The coordinator files every finding as an issue, closes the fixed ones, and posts one round
comment. A finding that needs a design decision, reaches outside the PR, or fails its gate stays
open; at P1 it holds the PR until the human closes it.

**The merge pass is classified, not judged.** `pr_state.py` decides per PR: merge (green, reviewed,
no holds, up to date with default), mark a draft ready, update the branch when it falls behind
default (server-side, via `gh pr update-branch`), repair a conflict or a red CI run, hold on an
unfixed P1, flag branch protection it cannot satisfy, or wait for CI — where "no checks yet" is
waiting, not green. A repair that fails twice parks the PR. The pump executes the classification,
updates the worktree's card, and re-runs the planner after every write.

**PRs don't pile up behind main.** Two bounds keep the backlog short and fresh. The resolver's spawn
budget (twice `--workers`) stops new work once open PRs plus workers in flight reach the cap, so the
pump drains before it grows. The merge pass is a queue: one PR at a time is brought up to date and
merged, so every merge ran CI on current main, and no CI is spent updating PRs that the next merge
would put behind again. "Behind" is measured with the compare API, so this holds whether or not
branch protection requires up-to-date branches. It never merges outside the scope, never `--admin`,
and never force-pushes.

**What the pump never does.** It never closes an issue or the epic (it closes only the review
findings it filed and the reviewer fixed), never force-claims, never answers a worker's dialog, and
never edits code itself. Nothing the reviewer or repairer pushes is reviewed again: the quality gate
and CI are the check.
