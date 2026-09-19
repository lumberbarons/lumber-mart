---
name: work-epic
description: Pump a hew epic end to end with herdr-managed agents — resolve the epic's ready children, spawn one worker agent per child running work-issue, review each delivered PR with a reviewer agent running review-code, file the findings as epic children, and merge PRs once CI is green. Autonomous mode (the default) merges on green; `--human-review` stops at drafts and leaves every merge to a human. Use whenever the user wants an epic worked by orchestrating agents — "work on this epic", "drain epic 12", "orchestrate #42", "fan out this epic to workers", "pump the epic and merge it". Not for a single issue (that goes to work-issue) and never for closing issues or the epic itself.
argument-hint: "Epic number. Flags: --human-review, --block-on P1|P2|none (default P1), --merge-method squash|merge|rebase (default squash), --workers N (default 2), --kind opencode|codex, --dry-run, --no-review"
---

# Work Epic

One epic, pumped: resolve its ready children, spawn a herdr agent per child, review each
delivered PR with a second agent, file the findings, merge on green, and re-pump. This skill
orchestrates; it never implements or reviews by hand.

**Two modes.** In autonomous mode (the default) the merge gate is CI green plus reviewer
severity: PRs whose checks pass and whose review surfaced nothing at or above `--block-on`
are marked ready and merged, main is fast-forwarded, and the pump continues into the freed
work. `--human-review` restores the older contract: every PR stays a draft and every merge
is a human's click. Both modes keep the same hard gates — the pump never closes an issue or
an epic, never force-claims, never answers a worker's dialog, never resolves a merge
conflict, and never merges a PR outside the epic it was given. Escalations reach the human
through `herdr notification show`; the pump stops and reports rather than route around a
gate.

> [!IMPORTANT]
> [REFERENCE.md](REFERENCE.md) carries both scripts' output schemas, the worker and reviewer
> prompt templates, the findings-filing flow, naming rules, timeout budgets, the merge-pass
> command list, and the report format. Read it before the reaping step.

## The scripts

Spawn and merge decisions come from scripts, not from hew or gh JSON sorted in your head —
a pump that picks differently on each run cannot be reasoned about from its logs. Resolve
both once against this skill's own directory:

```bash
RESOLVE="<this skill's directory>/scripts/resolve_ready.py"
PRSTATE="<this skill's directory>/scripts/pr_state.py"
```

Both are read-only (hew and git/gh reads, never writes) and neither decides anything a human
owns — they filter, sort, size, and classify; the skill acts. Anything that sorts, filters,
or sizes hew output in your head instead of running them is an anti-pattern.

## Prerequisites

This skill controls herdr, so first check it is running inside herdr at all:

```bash
test "${HERDR_ENV:-}" = 1
```

If the check fails, say so and stop — do not spawn agents into a session you cannot observe. The
herdr skill should be in context; if not, run `herdr --skill` first and follow its CLI-discovery
rule (`--help` over probing).

`hew` on PATH and authenticated — exit code 4 from any `hew` command means run `gh auth login`,
and here that halts the whole pump as an `error`, not as an empty queue.

## Arguments

Strip flags; what remains is the epic number.

- **`<epic-n>`** — the epic to pump. A non-epic number is redirected to `work-issue`.
- **`--human-review`** — no merges, no findings filing: PRs stay draft with findings relayed
  as comments, the integration pass runs, and the human merge gate is absolute.
- **`--block-on P1|P2|none`** — the severity that holds a PR back from merging, default P1.
  Findings at or above it become holds and escalations, not merges.
- **`--merge-method squash|merge|rebase`** — how PRs merge, default squash. Rebase rewrites
  PR refs and fights the pump's own branch updates; prefer squash or merge.
- **`--workers N`** — cap on live worker agents, default 2. More than 3–4 only moves the
  bottleneck into the review-and-merge pipeline; raise it on explicit instruction.
- **`--kind opencode|codex`** — worker and reviewer kind, default opencode. opencode is
  preferred because `work-issue` and `review-code` resolve as skills there; codex is driven by
  pointing the prompt at the skill files (see [REFERENCE.md](REFERENCE.md)).
- **`--dry-run`** — run both scripts, show the spawn plan and merge plan, touch nothing.
- **`--no-review`** — workers only; in autonomous mode PRs merge on CI green alone, in
  human-review mode they stay draft.

## Step 1 — Resolve the fan-out plan

```bash
uv run --no-project "$RESOLVE" <epic-n>   # add --repo owner/name only if the user said so
```

- **Exit 2 "not an epic"** — stop and hand it to `work-issue`; orchestration over one issue is
  overhead with no payoff.
- **Exit 1** — relay the stderr message and stop.
- **Exit 0** — `eligible` is the spawn order (priority-sorted, oldest tie-break), `skipped`
  names every open child left behind with its reason, `counts` sums them. `mainCheckout` is
  the primary worktree and `defaultBranch` the origin HEAD — use them everywhere below
  instead of assuming the orchestrator's own `$PWD` is the main checkout; this is what keeps
  an orchestrator running inside a worktree from nesting worktrees under it.

Under `--dry-run`, print the plan and the merge plan (Step 6) and stop there.

Before spawning, subtract what is already delivered: run the merge-pass script once here and
**skip any eligible child that `pr_state.py` already maps to an open PR** — it is in review,
and respawning it costs a resume-and-duplicate.

An empty `eligible` is meaningful either way: all-blocked, all-untriaged, all-claimed, or a
finished epic. Say which, from `counts`, and — for a finished epic where every child is
closed — escalate that a human should close it, exactly as `work-issue` requires. Do not
close it here.

## Step 2 — Capacity

```bash
herdr agent list
```

Live workers are the agents this orchestrator spawned, named `we-<issue>` (reviewers: `wr-<pr>`).
Open slots are `--workers` minus live `we-*` names. If reaping hasn't freed any, wait on the
live set (Step 4) instead of spawning. Name-ownership is also the coordination rule:
**never close or reassign agents/workspaces you did not spawn** — other orchestrators working the
same repo are safe precisely because each owns its `we-`/`wr-` prefix and `hew start`'s exit-3
lock is the authority on claims.

## Step 3 — Spawn workers

First bring the main checkout up to date, so new worktrees branch off what has actually
merged:

```bash
git -C "$MAIN" fetch origin
git -C "$MAIN" merge --ff-only "origin/$DEFAULT"
```

`$MAIN` and `$DEFAULT` come from the resolver's `mainCheckout`/`defaultBranch` (fall back to
`$PWD` only when the resolver could not determine them). A failed ff-only means the local
default branch has diverged — escalate; never rebase or reset it.

For each eligible child up to the open slots:

```bash
# opencode workers: spawn in the main checkout; the opencode-worktree plugin isolates the session
herdr workspace create --cwd "$MAIN" --label "we-<n>" --no-focus
# codex workers: explicit isolation, since there is no plugin catching them
herdr worktree create --cwd "$MAIN" --label "we-<n>" --no-focus
```

Read the pane id from the creation response (`workspace create` documents
`.result.root_pane.pane_id`; for the worktree variant, read the new pane from the JSON response
rather than predicting its shape — same rule the herdr skill applies to all IDs).
Prepare the outcome path, then start and prompt:

```bash
TMP="${TMPDIR:-/tmp}"; TMP="${TMP%/}"
OUTDIR="$TMP/opencode/work-epic-<epic-n>"
mkdir -p "$OUTDIR"
herdr agent start we-<n> --kind <kind> --pane <pane-id>
herdr agent prompt we-<n> "<prompt from REFERENCE.md, pointing at
  work-issue <n> --non-interactive --json '$OUTDIR/we-<n>.json'>"
```

`$OUTDIR` sits under opencode's own temp directory (`${TMPDIR:-/tmp}/opencode`), which opencode
pre-approves for external directory access. Each worker and reviewer runs in its own session with
its own approval state, so an outcome path outside that whitelist costs one permission dialog per
agent — never point `OUTDIR` at `/tmp` directly.

Submit prompts **without `--wait`** — fire the whole spawn set, then reap (Step 4). If an agent
for `<n>` already exists under this prefix, skip it; the claim is live and the resolver's next
pass will re-detect whatever this one produces. A spawn that fails (`agent_not_ready`, pane not
available) costs only that child — continue with the rest and report it.

## Step 4 — Reap settled workers

For each live worker, wait for a settled state per the budget rules in
[REFERENCE.md](REFERENCE.md):

```bash
herdr agent wait we-<n>   # re-loop on timeout while state is still `working`
```

What settled means, per state:

- **`idle` / `done`** — read the outcome file (`$OUTDIR/we-<n>.json`). A missing or unreadable
  file is an `error`, never an inference from terminal output — the whole point of `--json` is
  that lifecycle settles prove the agent stopped, the file says what happened. Then:

  | outcome | action here |
  |---|---|
  | `delivered` | note the PR for Step 5; close the workspace |
  | `failed` | report; leave the issue claimed; do **not** respawn it |
  | `no_ready_work` / `not_eligible` | report verbatim, with the skipped counts — a queue of issues claimed by a dead agent reads as drained and hides the stall |
  | `error` | **halt the pump**: finish reaping what's live, spawn nothing new, escalate — un-auth or dirty trees are an outage, not an empty queue |

  On any settled read: `herdr workspace close <id>` — but only a workspace this run created.

- **`blocked`** — the agent sits at a permission/question dialog. Notify rather than answer:

  ```bash
  herdr notification show "work-epic: we-<n> blocked on #<n>" --sound request
  ```

  A blocked worker still counts against capacity — otherwise the pump spawns past its own stuck
  worker and buries the escalation. Never answer the dialog on the user's behalf.

- **Agent process exited outright** (name no longer resolves in `agent list`) — treat like
  settled-without-file: escalate or report `error`, close the workspace.

## Step 5 — Review delivered PRs (skip under `--no-review`)

One reviewer per delivered PR, prompt per [REFERENCE.md](REFERENCE.md):

```bash
herdr workspace create --cwd "$MAIN" --label "wr-<pr>" --no-focus
herdr agent start wr-<pr> --kind <kind> --pane <pane-id>
herdr agent prompt wr-<pr> "<reviewer prompt>"
```

The reviewer checks out the PR head itself (the prompt says how), so `review-code`'s default
branch-vs-default scope *is* the PR diff. Consume the findings file:

- **Missing/unreadable findings file** — escalate; an unread review is not a clean review.

In autonomous mode, findings become tracked work rather than comments:

- **Clean, or P3-only** — relay any P3s as a single informational PR comment, `gh pr ready <pr>`,
  notify. The merge pass takes it from here.
- **Any P1/P2** — file each finding as an epic child via the raise-issues flow: convert the
  findings file with `findings_to_plan.py --parent <epic> --reviewed-issue <n>
  --reviewed-pr <pr>` (flow and dedup rules in [REFERENCE.md](REFERENCE.md)), dry-run, then
  `hew apply`. P1 findings are additionally relayed as a PR comment with the
  `reviewed-head:` marker (template in REFERENCE) and the human is notified — that
  comment is the hold's public reason. The PR stays draft; the P1 finding holds it.

In `--human-review` mode nothing is filed or merged: any P1/P2 is relayed verbatim as a PR
comment, the PR stays draft, and the human is notified — findings are never fixed into a PR
a human is about to read.

## Step 6 — Merge pass (autonomous mode)

Skip under `--human-review` (its Step 7 is the throwaway integration branch instead).

Every open PR of this epic goes through `pr_state.py` — not only this run's deliveries; PRs
delivered by earlier runs or other orchestrators are merged by the same plan or left alone:

```bash
uv run --no-project "$PRSTATE" <epic-n> --block-on <block-on> [--no-review]
```

Execute each PR's `action` exactly as classified — the planner is the decision, the pass is
the hands (commands and CI-wait budgets in [REFERENCE.md](REFERENCE.md)):

| action | what the pass does |
|---|---|
| `ready_and_merge` | `gh pr ready` when still draft, then `gh pr merge --<merge-method> --delete-branch`; notify; then fast-forward main (below) |
| `update_branch` | `git fetch origin && git merge --no-edit "origin/$DEFAULT"` on the PR branch, push; a conflict here is a `conflict`, never resolved by hand |
| `re_review` | spawn a fresh reviewer (Step 5) for the new head |
| `conflict` | file the coupling (`hew search` first, then `hew create --discovered-from <n>`), notify, leave the PR — never resolve a conflict into a PR a human hasn't seen |
| `hold_p1` | notify; the human resolves it by closing the finding child (accepted) or fixing the branch themselves — the pump never un-holds |
| `escalate` | notify; two review rounds produced no convergence — a third automated round is spam, not diligence |
| `wait` | nothing; it rolls into the CI-wait loop |

After any merge, fast-forward the main checkout the same way as Step 3, so the next spawn
wave and every new worktree carry the merged code. A failed ff-only is an escalation.

Re-run the pass after its own writes — a merge unblocks the next PR, a push changes every
`BEHIND`, and a fresh `pr_state.py` read is what keeps the sequence deterministic rather
than remembered. Stop re-running when every PR reads `wait`; those become the CI-wait loop:
poll on a ~2-minute cadence with a hard per-PR budget (~60 minutes of no progress), then
notify and move on. CI waiting must never block spawning — Step 8's re-pump runs while PRs
settle, and the next pass reaps whatever went green.

The pump never merges a PR whose issue is not this epic's child (`outside_epic`), never
passes `--admin`, never force-pushes, and never merges with failing checks — the planner
will not classify those as `ready_and_merge`, and overriding it is how the bounds fall off.

## Step 7 — Integration pass (`--human-review` only)

Only when this run delivered two or more PRs. Separate worker isolation means no tree ever held
two of these changes at once, so the coupling check work-issue's `--batch` gets within one run
must be re-created explicitly:

```bash
git checkout -B integration/epic-<epic> origin/<default>
git merge --no-ff <branch-1>   # one at a time, in resolution order
git merge --no-ff <branch-2>
```

Then the quality gate the union of changed files selects (table in `work-issue`'s REFERENCE —
same table, same rule). Sequential merges name the clashing pair; a gate failure names the
culprit pair. On failure, file the coupling — `hew search` per the primer's dedup sequence, then
`hew create --discovered-from <a> --discovered-from <b>` — and report `integration_failed` as in
work-issue's taxonomy. On pass, state it plainly: the independence the per-issue PRs assume is
now evidence. Nothing pushed, no PR off this branch.

Autonomous mode has no throwaway branch: main itself is the integration surface, the
`update_branch` step re-bases every PR onto the current default before merge, and CI plus the
merge-time gate re-run is what catches cross-PR coupling — at merge time, on the tree that
actually ships, instead of on a replica.

## Step 8 — Re-pump and stop

After each settled worker and each merge pass, return to Step 1 — the resolver re-reads the
tracker, merges by the human unblock children between visits, and findings filed as children
enter `eligible` as their blockers clear (a P2 finding's child is blocked by the PR's issue
until the merge closes it). The pump stops when the resolver's `eligible` is empty, no `we-*`
worker is in flight, **and** the merge pass has no `ready_and_merge`, `update_branch`, or
`re_review` left — PRs parked on `wait` are still moving; report them, don't abandon them.

Then report:

- per worker: issue, outcome, PR number, reviewer verdict, findings filed
- per merge-pass action: PR, what was done (merged / updated / held / conflicted)
- per skip: number and reason (blocked/untriaged/claimed), from the resolver's last pass
- `hew epic status <epic>` — the progress line the human reads
- remaining `eligible` count and open-PR count, so "stopped" is distinguishable from "drained"
- every escalation raised, with its notification

Never `hew close`. Never `hew start --force`. Never merge a PR for an issue outside this
epic. Never answer a worker's dialog. Never fix findings into the PR the finding came from —
the fix is a child issue, and its worker branches fresh. Each of those is a human gate the
pump keeps; autonomous mode moved the *merge* off the list, not the judgement.

## Anti-patterns

- Sorting or filtering `hew list --epic` output yourself instead of running the resolver
- Merging on your own read of CI state instead of executing `pr_state.py`'s actions
- Spawning a worker for a child that already has an open PR, or for an issue already claimed
  (the claim is the authority — let exit 3 arbitrate, never `--force`)
- Treating a settled agent as a delivered issue without reading its outcome file
- Spawning past a `blocked` worker instead of accounting it as used capacity
- `gh pr merge --admin`, merging with failing checks, or merging a PR the planner held
- Auto-resolving a `DIRTY` merge, rebasing main, or force-pushing a PR branch
- Fixing reviewer findings into the PR that produced them, or re-reviewing past two rounds
- Filing findings without the converter (hand-composed bodies lose the `review-of:` marker
  the merge pass keys holds off) — run `findings_to_plan.py`, then dedup, then `hew apply`
- Running the human-review integration branch's merges all-at-once (octopus)
- Closing workspaces or agents this run did not create
- Closing the epic because its children are done — report it; a human closes it
- Putting outcome files directly under `/tmp` instead of `${TMPDIR:-/tmp}/opencode` — every agent
  that touches them prompts for external directory access
