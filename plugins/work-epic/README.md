# work-epic

A skill for working a [hew](https://github.com/lumberbarons/hew) epic by orchestrating
[Orca](https://github.com/stablyai/orca)-managed worktrees and supervised agents rather than
working by hand. The coordinator can be any agent; the implementer, reviewer, and reconciler
are chosen from the pool independently.

## Overview

- **work-epic** — resolves an epic's ready children with a deterministic script, creates one
  Orca worktree per child, starts a supervised implementer in it (running `work-issue`), runs a
  reviewer over each delivered PR in a transient review worktree (running `review-code`), files
  the findings as epic children, reconciles conflicts in the child's own worktree, merges PRs
  once CI is green, and re-pumps until the epic is drained.
- **Multi-agent by design** — implementers and reviewers are chosen independently from a pool.
  The default reviewer is a different agent from the implementer whenever the implementer pool
  has another agent, and a re-review rotates again. A Claude implementation can get a Codex review; an
  opencode implementation can get a Claude review.

One epic, pumped: the orchestrator never implements, reviews by hand, closes, or reconciles a
conflict itself. It accelerates everything up to the gates, not through them — and which gate
is which depends on the mode you pick.

## Modes

**Autonomous (default).** The reviewer is a findings generator: P1/P2 findings become epic
children (filed `blocked-by` the reviewed issue, so their fixes unblock exactly when the PR
merges), and a PR merges once its checks are green, its review is current, and nothing at or
above `--block-on` (default P1) is open. After each merge the pump fast-forwards main, so every
new child branches off what actually shipped. A P1 finding holds its PR — the human resolves it
by closing the finding child or fixing the branch — and a merge conflict is filed and escalated;
under `--resolve-conflicts` a reconciler worker instead merges the default branch in, in the
child's own worktree, and reconciles both sides' intent. Its new head is re-reviewed before any
merge.

**`--human-review`.** The older contract, unchanged: every PR stays a draft, P1/P2 findings are
relayed as comments, multi-PR runs get the throwaway integration branch, and every merge is a
human's click.

## Multi-agent roles

The pump separates four roles, and they can be four different agents:

| Role | Runs | Default |
|---|---|---|
| Implementer | `work-issue` in the child worktree | `opencode` |
| Reviewer | `review-code` in a transient review worktree | `auto`: the implementer pool minus the implementer (same-agent if the pool has one) |
| Reconciler | the conflict contract in the child worktree | the child's implementer |
| Coordinator | this skill: plans, spawns, reaps, merges | whichever agent you started |

The flags are explicit:

```
--implementers opencode,claude,codex   # implementation pool; all = the supported set
--reviewers auto                       # the implementer pool minus the implementer
--reviewers claude,codex               # explicit reviewer pool
--reconciler codex                     # conflict resolution agent; auto = implementer
```

Assignment is deterministic by issue/PR number, not by spawn order:
`implementer(n) = implementers[n % len]`, and the reviewer is
`candidates[(pr + round - 1) % len]` from the pool minus the implementer. That means the same
issue gets the same implementer on every run, and round 2 of a review can be a third point of
view. The chosen agents are recorded on the Task, the worktree comment, and the report.

**Orca does not expose an installed-agent list through its CLI.** `worker-start --help` names
known ids, and `orca account list --json` shows managed accounts/rate limits, but neither proves
an agent is installed or enabled on the host. The runtime's `agentSession.agents` and
`agentSession.subscribeAvailability` RPCs power the Orca app's picker; they are not CLI
commands. The pool is your declaration of what is installed. A failed `worker-start` names the
agent that could not launch and costs only that child; the pump reports it and never silently
swaps in another agent.

Supported ids are `opencode`, `codex`, and `claude`. Install `work-issue` in an agent before
naming it as an implementer, and `review-code` before naming it as a reviewer. Adding a fourth
agent means adding its prompt adapter in `skills/work-epic/REFERENCE.md`, not changing the
orchestration.

## Prerequisites

- [Orca](https://github.com/stablyai/orca) 1.4+ running, with the session inside an
  Orca-managed terminal/worktree. The `orca-cli` and `orchestration` skills should be in
  context; the skill stops if it cannot see the coordinator worktree.
- The target repository registered in Orca (`orca repo list --json`).
- [`hew`](https://github.com/lumberbarons/hew) on PATH, authenticated via `gh auth login`.
- The [`hew`](../hew) plugin — implementers run `work-issue`; findings are filed through
  raise-issues' converter script.
- The [`critique`](../critique) plugin — reviewers run `review-code`.
- `work-issue` installed for every implementer and `review-code` installed for every reviewer
  (opencode/claude load them by name; codex is pointed at the files). Reconcilers read the
  quality-gate table from the work-issue skill directory, so it must be readable on the host.
  The coordinator only needs raise-issues' converter.
- Run from an Orca-managed worktree of the target repository (`--repo owner/name` overrides
  detection). Prefer a dedicated worktree for the coordinator: the pump writes a `.work-epic/`
  scratch directory and a status comment there.

Orca has no push-notification command. Escalations land as the affected worktree's unread dot
plus its comment and workspace status, and as the pump's final report; the pump still stops at
every gate rather than routing around it.

## Usage

```
/work-epic:work-epic 12                            # pump epic 12; merge on CI green
/work-epic:work-epic 12 --human-review             # stop at drafts; every merge is human
/work-epic:work-epic 12 --block-on P2              # P1 and P2 findings hold PRs
/work-epic:work-epic 12 --workers 3                # more live workers (cap ~4)
/work-epic:work-epic 12 --max-open-prs 3           # smaller PR backlog (default 2 × workers)
/work-epic:work-epic 12 --implementers all         # rotate opencode/claude/codex implementers
/work-epic:work-epic 12 --implementers claude --reviewers codex   # fixed cross-agent pairing
/work-epic:work-epic 12 --implementers opencode,claude --reviewers codex --reconciler claude
/work-epic:work-epic 12 --dry-run                  # resolver + Orca + merge plans only
/work-epic:work-epic 12 --no-review                # autonomous: merge on CI green alone
/work-epic:work-epic 12 --allow-no-checks          # repo has no CI: no checks counts as green
/work-epic:work-epic 12 --resolve-conflicts        # delegate PR conflicts to a reconciler
/work-epic:work-epic 12 --resume                   # pick up your own claims a crashed run left
```

The pump fast-forwards the main checkout after each merge, so it must be on the default branch
for that step; if the human has another branch checked out, the pump leaves it alone, skips the
fast-forward, and says so. Child worktrees are always based on `origin/<default>` explicitly, so
the human's checkout never determines what a worker branches from.

## How it works

**The plans come from scripts.** `resolve_ready.py` reads the epic and emits a JSON fan-out
plan — eligible children in priority-sorted, oldest-tie-break order, every open child left
behind with its skip reason (including children already in review or whose worker failed, so
the pump never respawns its own work), plus the main checkout and default branch. `pr_state.py`
reads the epic's open PRs (CI rollups, merge states, review rounds, finding holds) and emits one
deterministic action per PR. A pump that picks differently on each run cannot be reasoned about
from its logs, so the agent never sorts hew or gh output itself.

**The worktree is the unit.** Every child gets its own Orca worktree, created with
`worker-start --worktree new-child` and nested under the coordinator in the sidebar. The
worktree carries the child's issue link, PR link, workspace status, comment, and checkout. It
stays alive through review and reconciliation — the reconciler reuses it, so it does not pay for
a second checkout or a second setup — and is removed when the PR merges, when it did no work, or
when a stalled checkout is clean. A held, conflicted, failed, or blocked child keeps its
worktree, marked unread, so the human has a live card to open. Reviewers get their own transient worktree with a
named `review/<pr>-r<round>` branch, so they never fight the child over its branch.

**Implementers are supervised, fire-and-reap; the reviewer is chosen independently and is a
different agent whenever the pool allows.** `worker-start` creates a Task and an authoritative
Dispatch, then launches the chosen agent. The
pump waits on the Run mailbox with `orchestration check --wait --types
worker_done,escalation,question`, processes the whole FIFO batch, acknowledges it, and only then
spawns into the freed capacity. Outcome files are written inside the worker's own worktree, so no
agent prompts for an external directory, and `worker-release` archives the terminal output
before closing it. A worker parked on a permission prompt shows up in `worker-show` as
`observation.agentWait`; the pump marks the worktree unread and never answers it.

The implementer for child `n` is `implementers[n % len]`. The reviewer for PR `p`, round `r` is
`candidates[(p + r - 1) % len]`, where `candidates` is the reviewer pool minus that PR's
implementer (or the whole pool when it would otherwise be empty). So the first review has a
different point of view whenever the implementer pool has another agent or the reviewer list
names one, and a re-review rotates again.

**Review is a findings generator (and a gate).** A reviewer runs `review-code` against each
delivered PR's head on a named review branch. In autonomous mode its findings are converted
into `hew apply` plan lines and filed as epic children — deduplicated by review key,
`blocked-by` the reviewed issue — so the pump itself picks the fixes up once the blocker clears.
Every review leaves one round comment on the PR recording the head it reviewed; a finding at or
above `--block-on` holds the PR as a draft, and a review that could not run is escalated, never
read as clean.

**The merge pass is classified, not judged.** `pr_state.py` decides per PR: merge (green,
current review, no holds, up to date with default), mark a draft ready, update the branch when
it falls behind default (server-side, via `gh pr update-branch`), re-review a moved head,
file-and-escalate a conflict — or, under `--resolve-conflicts`, hand it to a reconciler and
re-review the new head — hold on a blocking finding, flag branch protection it cannot satisfy,
or wait for CI — where "no checks yet" is waiting, not green. The pump executes the
classification, updates the child worktree's card, and re-runs the planner after every write.

**PRs don't pile up behind main.** Two bounds keep the backlog short and fresh. The resolver's
spawn budget (`--max-open-prs`) stops new work once open PRs plus workers in flight reach the
cap, so the pump drains before it grows. The merge pass is a queue: one PR at a time is brought
up to date and merged, so every merge ran CI on current main, and no CI is spent updating PRs
that the next merge would put behind again. "Behind" is measured with the compare API, so this
holds whether or not branch protection requires up-to-date branches. It never merges outside the
epic, never `--admin`, never force-pushes, and never reconciles a conflict itself.

**The merge gate is CI + severity; the judgement gates stay human.** Closing issues and the
epic, clearing a hold, resolving a conflict (unless `--resolve-conflicts` delegates it), and
anything past a blocked worker's dialog are decisions the pump escalates, never makes.

**Multi-PR runs still re-check coupling in human-review mode.** Delivered PRs are merged one at
a time onto a throwaway integration branch and gated over the union. Autonomous mode dropped the
replica: main is the integration surface, every PR is brought up to date with the default branch
just before it merges, and CI is the gate that runs where it ships.
