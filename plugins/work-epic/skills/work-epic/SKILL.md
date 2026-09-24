---
name: work-epic
description: Pump a hew epic end to end with herdr-managed agents — resolve the epic's ready children, spawn one worker agent per child running work-issue, review each delivered PR with a reviewer agent running review-code, file the findings as epic children, and merge PRs once CI is green — delegating conflicts to a reconciler agent under `--resolve-conflicts`. Autonomous mode (the default) merges on green; `--human-review` stops at drafts and leaves every merge to a human. Use whenever the user wants an epic worked by orchestrating agents — "work on this epic", "drain epic 12", "orchestrate #42", "fan out this epic to workers", "pump the epic and merge it". Not for a single issue (that goes to work-issue) and never for closing issues or the epic itself.
argument-hint: "Epic number. Flags: --human-review, --block-on P1|P2|none (default P1), --merge-method squash|merge|rebase (default squash), --workers N (default 2), --max-open-prs N (default 2 × workers), --kind opencode|codex, --dry-run, --no-review, --allow-no-checks, --resolve-conflicts, --resume"
---

# Work Epic

One epic, pumped: resolve its ready children, spawn a herdr agent per child, review each
delivered PR with a second agent, file the findings, merge on green, and re-pump. This skill
orchestrates; it never implements or reviews by hand.

**Modes.** In autonomous mode (the default) the merge gate is CI green plus reviewer
severity: PRs whose checks pass and whose review surfaced nothing at or above `--block-on`
are marked ready and merged, main is fast-forwarded, and the pump continues into the freed
work. `--human-review` restores the older contract: every PR stays a draft and every merge
is a human's click.

**Hard gates, in every mode.** The pump never closes an issue or an epic, never
force-claims, never answers a worker's dialog, never edits a conflicted branch itself, never
fixes a finding into the PR it came from, and never merges a PR outside the epic it was
given. Without `--resolve-conflicts` a conflict is filed and escalated like any other human
gate; with it, the edit is delegated to a reconciler agent and its new head earns its own
review round — the pump itself never reconciles one. Escalations reach the human through
`herdr notification show`; the pump stops and reports rather than route around a gate.
Autonomous mode moved the *merge* off the human's list, not the judgement.

> [!IMPORTANT]
> [REFERENCE.md](REFERENCE.md) carries the scripts' output schemas, the worker, reviewer, and
> reconciler prompt templates, the review-round and reconciliation comments, the
> findings-filing flow, naming rules, timeout budgets, the merge-pass command list, and the
> report format. Read it before the reaping step.

## The scripts

Spawn and merge decisions come from scripts, not from hew or gh JSON sorted in your head —
a pump that picks differently on each run cannot be reasoned about from its logs. Resolve
them once against this skill's own directory:

```bash
RESOLVE="<this skill's directory>/scripts/resolve_ready.py"
PRSTATE="<this skill's directory>/scripts/pr_state.py"
```

They are read-only (hew, git and gh reads, never writes) and decide nothing a human owns —
they filter, sort, size, and classify; the skill acts.

## Prerequisites

This skill controls herdr, so first check it is running inside herdr at all:

```bash
test "${HERDR_ENV:-}" = 1
```

If the check fails, say so and stop — do not spawn agents into a session you cannot observe. The
herdr skill should be in context; if not, run `herdr --skill` first and follow its CLI-discovery
rule (`--help` over probing).

Every agent this run spawns opens as a tab in the orchestrator's own workspace,
`$HERDR_WORKSPACE_ID`, so a run occupies one sidebar entry however many agents it fans out.
Closing that workspace ends every agent in it — leave it open until the pump reports.

`hew` on PATH and authenticated — exit code 4 from any `hew` command means run `gh auth login`,
and here that halts the whole pump as an `error`, not as an empty queue.

## Arguments

Strip flags; what remains is the epic number.

- **`<epic-n>`** — the epic to pump. A non-epic number is redirected to `work-issue`.
- **`--human-review`** — no merges, no findings filing: PRs stay draft with findings relayed
  as comments, the integration pass runs, and the human merge gate is absolute.
- **`--block-on P1|P2|none`** — the severity that holds a PR back from merging, default P1.
  Findings at or above it become holds and escalations, not merges; `none` holds on nothing.
- **`--merge-method squash|merge|rebase`** — how PRs merge, default squash. Rebase rewrites
  PR refs and fights the pump's own branch updates; prefer squash or merge.
- **`--workers N`** — cap on live worker agents, default 2. More than 3–4 only moves the
  bottleneck into the review-and-merge pipeline; raise it on explicit instruction.
- **`--max-open-prs N`** — cap on the epic's PR backlog, default twice `--workers`. Open PRs
  plus workers in flight never exceed it: once the backlog is full, the pump stops spawning
  and lets the merge pass drain. Every open PR drifts further behind main with each merge, so
  this is the bound on how stale the backlog gets. Held and conflicted PRs count — a backlog
  that cannot merge is the one not to grow.
- **`--kind opencode|codex`** — worker and reviewer kind, default opencode. opencode is
  preferred because `work-issue` and `review-code` resolve as skills there; codex is driven by
  pointing the prompt at the skill files (see [REFERENCE.md](REFERENCE.md)).
- **`--dry-run`** — run both planners, show the spawn plan and merge plan, touch nothing.
- **`--no-review`** — workers only; in autonomous mode PRs merge on CI green alone, in
  human-review mode they stay draft.
- **`--allow-no-checks`** — treat a PR with no CI checks at all as green. Without it, "no
  checks" reads as "CI has not reported yet", which is what it usually means straight after a
  push. Only for repositories that genuinely have no CI, and only on explicit instruction.
- **`--resolve-conflicts`** — delegate a PR's conflict with the default branch to a reconciler
  agent (`wc-<pr>`) instead of filing and parking it. Off by default: the human gate stands
  unless a run is told otherwise. One reconciler at a time, only while the merge queue is idle
  (a merge landing mid-reconciliation would re-conflict it), occupying a `--workers` slot.
  Refused together with `--merge-method rebase` — the reconciliation is a hand-edited merge
  commit and a rebase-and-merge would drop its edits — and with `--human-review`, which runs
  no merge pass for it to act in. A resolved head is un-readied and re-reviewed; two failed
  attempts park the PR for the human like any other conflict.
- **`--resume`** — pass through to the resolver to pick up this user's own claims that have
  neither a PR nor a pushed branch — a crashed earlier run. Explicit instruction only.

## Step 1 — Resolve the fan-out plan

```bash
uv run --no-project "$RESOLVE" <epic-n> --max-open-prs <max-open-prs>
# add --repo owner/name only if the user said so
```

- **Exit 2 "not an epic"** — stop and hand it to `work-issue`; orchestration over one issue is
  overhead with no payoff.
- **Exit 1** — relay the stderr message and stop.
- **Exit 0** — `eligible` is the spawn order (priority-sorted, oldest tie-break), `skipped`
  names every open child left behind with its reason, `counts` sums them. `mainCheckout` is
  the primary worktree and `defaultBranch` the origin default — use them everywhere below
  instead of assuming the orchestrator's own `$PWD` is the main checkout; this is what keeps
  an orchestrator running inside a worktree from nesting worktrees under it.

The resolver already keeps out what this pump has touched: a child with an open PR is
`in_review`, one whose worker failed (branch pushed, no PR) is `stalled`, and one claimed by
you with neither is `claimed` unless `--resume` was given. Spawn only from `eligible`.

Under `--dry-run`, print the plan and the merge plan (Step 6) and stop there.

An empty `eligible` is meaningful either way: all-blocked, all-untriaged, all-claimed,
all-in-review, or a finished epic. Say which, from `counts`, and — for a finished epic where
every child is closed — escalate that a human should close it, exactly as `work-issue`
requires. Do not close it here.

## Step 2 — Capacity

```bash
herdr agent list
```

Live writers are the agents this orchestrator spawned, named `we-<issue>` (reconcilers:
`wc-<pr>`); reviewers (`wr-<pr>`) don't count. Open slots are the smaller of `--workers` minus
live `we-*` and `wc-*` names and the resolver's
`spawnBudget` — the room left under `--max-open-prs` once open PRs and workers in flight are
counted. If reaping hasn't freed a worker slot, wait on the live set (Step 4); if the budget is
zero, spawn nothing and go to the merge pass (Step 6) — the backlog drains before it grows.
Name-ownership is also the coordination rule:
**never close or reassign agents/tabs you did not spawn**. Agent names are unique within
a herdr server, so a live `we-<n>` stops a second orchestrator there from spawning the same
child; across users, `hew start`'s exit-3 lock arbitrates. Two orchestrators sharing one gh
login in different herdr servers have neither guard — `hew start` answers them exit 5, "the
claim is yours" — so do not run them over the same epic.

## Step 3 — Spawn workers

`$MAIN` and `$DEFAULT` come from the resolver's `mainCheckout`/`defaultBranch` (fall back to
`$PWD` only when the resolver could not determine them, and say so in the report). New
worktrees branch off what `$MAIN` has checked out, so first confirm that is the default branch:

```bash
test "$(git -C "$MAIN" symbolic-ref --short HEAD)" = "$DEFAULT"
```

If it is not — the human is working on a branch in their main checkout — stop and say so.
Workers would branch off the human's branch, and the fast-forward below would move it. Never
switch the human's checkout yourself. Then bring it up to date, so new worktrees branch off what
has actually merged:

```bash
git -C "$MAIN" fetch origin
git -C "$MAIN" merge --ff-only "origin/$DEFAULT"
```

A failed ff-only means the local default branch has diverged — escalate; never rebase or
reset it.

Prepare the outcome path once per run:

```bash
TMP="${TMPDIR:-/tmp}"; TMP="${TMP%/}"
OUTDIR="$TMP/opencode/work-epic-<epic-n>"
mkdir -p "$OUTDIR"
```

For each eligible child up to the open slots, open a tab in the orchestrator's workspace:

```bash
# opencode workers: spawn in the main checkout; the opencode-worktree plugin isolates the session
herdr tab create --workspace "$HERDR_WORKSPACE_ID" --cwd "$MAIN" --label "we-<n>" --no-focus
# codex workers: explicit isolation, since there is no plugin catching them
git -C "$MAIN" worktree add --detach "$OUTDIR/wt/we-<n>" "origin/$DEFAULT"
herdr tab create --workspace "$HERDR_WORKSPACE_ID" --cwd "$OUTDIR/wt/we-<n>" --label "we-<n>" --no-focus
```

The codex worktree starts detached, so `work-issue` takes its not-isolated path and branches
off the default branch itself. `herdr worktree create` is not used: it opens every worktree as
a workspace of its own, which is the sidebar sprawl tabs avoid.

Read the tab id (`.result.tab`) and the pane id (`.result.root_pane.pane_id`) from the creation
response rather than predicting their shape — same rule the herdr skill applies to all IDs.
Keep the tab id: it is what Step 4 closes. Then start and prompt:

```bash
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
[REFERENCE.md](REFERENCE.md). A live reconciler (`wc-<pr>`, spawned by Step 6's `reconcile`
row) waits the same way; its outcome table lives in Step 6:

```bash
herdr agent wait we-<n>   # re-loop on timeout while state is still `working`
```

What settled means, per state:

- **`idle` / `done`** — read the outcome file (`$OUTDIR/we-<n>.json`). A missing or unreadable
  file is an `error`, never an inference from terminal output — the whole point of `--json` is
  that lifecycle settles prove the agent stopped, the file says what happened. Then:

  | outcome | action here |
  |---|---|
  | `delivered` | note the PR for Step 5; close the tab |
  | `failed` | report; leave the issue claimed; do **not** respawn it — its pushed branch makes it `stalled` on every later resolver pass |
  | `no_ready_work` / `not_eligible` | report verbatim, with the skipped counts — a queue of issues claimed by a dead agent reads as drained and hides the stall |
  | `error` | **halt the pump**: finish reaping what's live, spawn nothing new, escalate — un-auth or dirty trees are an outage, not an empty queue |

  On any settled read: `herdr tab close <tab-id>` — but only a tab this run created. For a
  codex worker, then `git -C "$MAIN" worktree remove "$OUTDIR/wt/we-<n>"`, without `--force`:
  a refusal means uncommitted work, so leave the checkout and report its path. Removing it also
  frees the worker's branch — git will not check a branch out in two worktrees, and the
  reviewer's `gh pr checkout` needs it.

- **`blocked`** — the agent sits at a permission/question dialog. Notify rather than answer:

  ```bash
  herdr notification show "work-epic: we-<n> blocked on #<n>" --sound request
  ```

  A blocked worker still counts against capacity — otherwise the pump spawns past its own stuck
  worker and buries the escalation. Never answer the dialog on the user's behalf.

- **Agent process exited outright** (name no longer resolves in `agent list`) — treat like
  settled-without-file: escalate or report `error`, close the tab (and remove a codex worktree
  as above).

## Step 5 — Review delivered PRs (skip under `--no-review`)

One reviewer per delivered PR (and per `re_review` from Step 6). Record the head being
reviewed first — it becomes the round's `reviewed-head:` — then spawn, isolated like a worker
of the same kind, so the reviewer's checkout never lands in `$MAIN`:

```bash
HEAD_SHA=$(gh pr view <pr> --json headRefOid --jq .headRefOid)
# opencode
herdr tab create --workspace "$HERDR_WORKSPACE_ID" --cwd "$MAIN" --label "wr-<pr>" --no-focus
# codex
git -C "$MAIN" worktree add --detach "$OUTDIR/wt/wr-<pr>" "origin/$DEFAULT"
herdr tab create --workspace "$HERDR_WORKSPACE_ID" --cwd "$OUTDIR/wt/wr-<pr>" --label "wr-<pr>" --no-focus
herdr agent start wr-<pr> --kind <kind> --pane <pane-id>
herdr agent prompt wr-<pr> "<reviewer prompt, --json '$OUTDIR/wr-<pr>.json'>"
```

A re-review reuses the name and path, so close the previous `wr-<pr>` tab this run created
before spawning. Reap reviewers exactly like workers — same `herdr agent wait` loop, same
`blocked` notification, reviewer budget in [REFERENCE.md](REFERENCE.md) — and close the tab
once its file is read. A codex reviewer's worktree goes with it,
`git -C "$MAIN" worktree remove --force "$OUTDIR/wt/wr-<pr>"` — the reviewer changes no code,
so nothing there is worth keeping. Reviewers do not count against `--workers`.

The reviewer checks out the PR head itself (the prompt says how), so `review-code`'s default
branch-vs-default scope *is* the PR diff. Read the findings file before anything else:

- **Missing or unreadable** — escalate; an unread review is not a clean review.
- **`status` other than `reviewed`** (`no_scope`, `error`) — escalate with its `reason`. The
  review did not run, and its empty `findings` array means nothing; reading it as clean merges
  an unreviewed PR.

A `reviewed` file always produces exactly one **review-round comment** on the PR (template in
[REFERENCE.md](REFERENCE.md)), clean or not: it carries the marker `pr_state.py` counts rounds
by and `reviewed-head: $HEAD_SHA`. A PR with no round comment is one the planner treats as
unreviewed and never merges. Then, in autonomous mode:

- **Findings at P2 or above** — file them as epic children through the raise-issues flow:
  `findings_to_plan.py --parent <epic> --reviewed-issue <n> --reviewed-pr <pr>
  --at-or-above P2` (flow and dedup rules in [REFERENCE.md](REFERENCE.md)), dry-run, then
  `hew apply`. P3s are not filed; the round comment carries them.
- **Nothing at or above `--block-on`** — `gh pr ready <pr>`, notify. The merge pass takes it
  from here; filed findings below the bar are tracked work that unblocks when this PR merges.
- **Anything at or above `--block-on`** — the PR stays draft and the human is notified; the
  open finding child holds it (the round comment is the hold's public reason).

In `--human-review` mode nothing is filed or merged: the round comment relays every finding,
the PR stays draft, and the human is notified — findings are never fixed into a PR a human is
about to read.

## Step 6 — Merge pass (autonomous mode)

Skip under `--human-review` (its Step 7 is the throwaway integration branch instead).

Every open PR of this epic goes through `pr_state.py` — not only this run's deliveries; PRs
delivered by earlier runs or other orchestrators are merged by the same plan or left alone:

```bash
uv run --no-project "$PRSTATE" <epic-n> --block-on <block-on> [--no-review]
  [--allow-no-checks] [--resolve-conflicts] [--reconciling <pr>]...
```

Pass one `--reconciling <pr>` for every live `wc-<pr>` in `herdr agent list`. GitHub cannot
see a reconciler at work, and the planner runs on every pass while one does: without the list
it would start a second reconciler, or merge main out from under the first.

Execute each PR's `action` exactly as classified — the planner is the decision, the pass is
the hands (commands, CI-wait budgets, and merge-failure handling in
[REFERENCE.md](REFERENCE.md)):

| action | what the pass does |
|---|---|
| `merge` | `gh pr merge --<merge-method> --delete-branch`; notify; then fast-forward main (below) |
| `mark_ready` | `gh pr ready` — a draft's merge state reads `DRAFT` until then, hiding `BEHIND` or `BLOCKED`; the next pass sees the real state |
| `update_branch` | `gh pr update-branch <pr>` — GitHub merges the default branch in server-side; a failure re-runs the planner, whose next pass sees `DIRTY` and hands it to `reconcile` under `--resolve-conflicts` (or to `conflict`) |
| `reconcile` | spawn a reconciler agent (`wc-<pr>`, prompt in [REFERENCE.md](REFERENCE.md)) for the planner's single `reconcileHead`; the planner emits one only while `queueHead` is null and no `--reconciling` is live |
| `queued` | nothing; it waits its turn behind `queueHead` or behind the reconciliation head, and spends no CI budget of its own |
| `re_review` | spawn a fresh reviewer (Step 5) for the new head |
| `conflict` | file the coupling (`hew search` first, then `hew create --discovered-from <n>`), notify, leave the PR — the pump never reconciles one itself, so without `--resolve-conflicts` or after two failed attempts it parks here |
| `hold` | notify; the human lifts it by closing the finding child — once fixed on the branch, or accepted as is. Fixing the branch alone does not lift it, and the pump never un-holds |
| `escalate` | notify; two review rounds produced no convergence — a third automated round is spam, not diligence |
| `protected` | notify; branch protection wants something the pump cannot give (typically an approving review) |
| `wait` | nothing; it rolls into the CI-wait loop |

**The merge queue.** At most one PR moves toward main per pass — the planner's `queueHead`,
the only PR that gets `merge` or `update_branch`. Every merge puts every other open PR behind
again, so updating them side by side spends a CI run each on a result the next merge throws
away, and merging two from one plan lands the second on CI that never saw the first. "Behind"
is the planner's own count of default-branch commits a PR lacks (`behindBy`), not GitHub's
`BEHIND`, which only appears when branch protection requires up-to-date branches; without that
rule a stale PR reads `CLEAN`. So every merge is of a PR whose CI ran on current main,
whatever the repository's protection settings. Drafts and held PRs are never updated: they are
not next to merge, and moving a draft's head spends a review round.

**Resolving conflicts (`--resolve-conflicts`).** The planner emits at most one `reconcile` —
its `reconcileHead` — and only while `queueHead` is `null`: a merge landing mid-reconciliation
would re-conflict it. Spawn `wc-<pr>` for it exactly like a worker of the same kind (Step 3's
isolation and prompt shapes, outcome file `$OUTDIR/wc-<pr>.json`) and reap it with Step 4's
loop; it occupies a `--workers` slot while it runs. Until it is reaped, every pass hands its
PR number to the planner as `--reconciling`, which holds that PR at `wait` and queues every
other merge, update, and reconciliation behind it. The prompt is the reconciler's whole
contract: it merges `origin/$DEFAULT` (freshly fetched) into the PR branch, reconciles both
sides' intent, runs the gate, and pushes — never `$MAIN`, never `--force`, never rebase.
Then, from its outcome file:

- **`resolved`** — verify the outcome's `head` is the PR's new head
  (`gh pr view <pr> --json headRefOid`); a mismatch is an escalation, not a merge. Post the
  success comment, then `gh pr ready --undo <pr>` unless the PR is already a draft or
  `--no-review` is on. The next pass sees a stale draft and `re_review` puts the new head
  through a fresh reviewer — nothing reconciled merges without that round. Notify, close the
  tab (a codex reconciler's worktree with it, `worktree remove --force`: the agent changes
  nothing worth keeping beyond the pushed commit).
- **`irreconcilable`** — post the failure comment, which is what `pr_state.py` counts; after
  two, the PR parks on `conflict`. Do that row's filing and notification, and leave the branch
  alone.
- **`error`, a missing file, a spent budget, or a `head` mismatch** — post the failure comment
  too, with what went wrong as its reason: every run that does not end in a verified push
  counts toward the cap, or a reconciler that always hangs is respawned by every later run.
  Then the worker rules: escalate, spawn nothing new.

An outcome that could not reconcile both sides' intent, or that fails the gate, is
`irreconcilable`, not a guess: the pump files the coupling and the human decides.

Notify once per PR per action, not on every pass. After any merge, fast-forward the main
checkout the same way as Step 3 (branch check included), so the next spawn wave and every new
worktree carry the merged code. A failed ff-only is an escalation.

Re-run the pass after its own writes — a merge moves the queue to its next PR and puts the
rest behind, and a fresh `pr_state.py` read is what keeps the sequence deterministic rather
than remembered. When every PR reads `wait`, `queued`, or a parked action, the waits become the
CI-wait loop: poll on a ~2-minute cadence with a hard per-PR budget (~60 minutes of no
progress), then notify and set that PR aside. A queue head set aside on a spent budget parks
the PRs queued behind it — report them with it. CI waiting must never block spawning — Step 8's re-pump runs
while PRs settle, and the next pass reaps whatever went green.

The planner never classifies a PR outside the epic, with failing or absent checks, or under a
hold as `merge`; the pass never passes `--admin` and never force-pushes. Overriding the planner
is how the bounds fall off.

## Step 7 — Integration pass (`--human-review` only)

Only when this run delivered two or more PRs. Separate worker isolation means no tree ever held
two of these changes at once, so the coupling check work-issue's `--batch` gets within one run
must be re-created explicitly — in a throwaway worktree, never in `$MAIN`:

```bash
INT="$OUTDIR/integration"
git -C "$MAIN" fetch origin
git -C "$MAIN" worktree add --detach "$INT" "origin/$DEFAULT"
git -C "$INT" checkout -B "integration/epic-<epic>"
git -C "$INT" merge --no-ff "origin/<branch-1>"   # one at a time, in resolution order
git -C "$INT" merge --no-ff "origin/<branch-2>"
```

Then the quality gate the union of changed files selects, run in `$INT` (table in
`work-issue`'s REFERENCE — same table, same rule). Sequential merges name the clashing pair; a
gate failure names the culprit pair. On failure, file the coupling — `hew search` per the
primer's dedup sequence, then `hew create --discovered-from <a> --discovered-from <b>` — and
report `integration_failed` as in work-issue's taxonomy. On pass, state it plainly: the
independence the per-issue PRs assume is now evidence. Nothing pushed, no PR off this branch;
afterwards `git -C "$MAIN" worktree remove --force "$INT"` and delete the local branch.

Autonomous mode has no throwaway branch: main itself is the integration surface, the merge
queue brings each PR up to date with the default branch just before it merges, and CI plus
the merge-time gate re-run is what catches cross-PR coupling — at merge time, on the tree that
actually ships, instead of on a replica.

## Step 8 — Re-pump and stop

After each settled worker and each merge pass, return to Step 1 — the resolver re-reads the
tracker, merges unblock children between visits, and findings filed as children enter
`eligible` as their blockers clear (a finding's child is blocked by the PR's issue until the
merge closes it).

The pump stops when all of these hold: nothing can spawn (the resolver's `eligible` is empty,
or its `spawnBudget` is zero), no `we-*`, `wr-*`, or `wc-*` agent is in flight and no
`reconcile` is waiting for a free writer slot, and every open PR is
parked — `hold`, `escalate`, `conflict`, `protected`, a `wait` that has spent its CI budget,
or `queued` behind a head that is one of those. A `wait` still inside its budget is still
moving; keep polling it rather than stopping around it. A stop with eligible children and a
zero budget is a full backlog of parked PRs — say so; it clears only when a human unparks them.

Then report:

- per worker: issue, outcome, PR number, reviewer verdict, findings filed
- per reconciler: PR, outcome, gate result, new head, and whether re-review was spawned
- per merge-pass action: PR, what was done (merged / updated / queued / reconciled / held /
  conflicted / protected)
- per skip: number and reason (blocked/untriaged/claimed/in_review/stalled), from the resolver's last pass
- `hew epic status <epic>` — the progress line the human reads
- remaining `eligible` count, `spawnBudget`, and open-PR count, so "stopped" is
  distinguishable from "drained" and a full backlog from an empty queue
- every escalation raised, with its notification

## Anti-patterns

- Sorting or filtering `hew list --epic` output yourself instead of running the resolver
- Merging on your own read of CI state instead of executing `pr_state.py`'s actions
- Spawning a worker for a child the resolver skipped — `in_review`, `stalled`, or `claimed`
  (the claim is the authority — let exit 3 arbitrate, never `--force`)
- Treating a settled agent as a delivered issue without reading its outcome file
- Reading a findings file whose `status` is not `reviewed` as a clean review
- Reviewing without posting the round comment, or posting it without `reviewed-head:`
- Spawning past a `blocked` worker instead of accounting it as used capacity
- Spawning past a zero `spawnBudget` because worker slots are free — slots bound agents, the
  budget bounds the backlog that goes stale
- Updating or merging a PR the planner `queued` — the queue is what keeps every merge on CI
  that saw current main
- `gh pr merge --admin`, merging with failing checks, or merging a PR the planner held
- Checking out a PR branch, or running the integration merges, in `$MAIN` — `update_branch` is
  `gh pr update-branch`; reviewers, reconcilers, and the integration pass get their own worktree
- Fast-forwarding `$MAIN` when it is not on the default branch
- Reconciling a `DIRTY` merge by hand — the planner's `reconcile` row owns the edit, and only
  under `--resolve-conflicts`
- Rebasing main, or force-pushing a PR branch — a reconciliation is a fast-forward push of a
  merge commit
- Spawning a second reconciler, or resolving while the merge queue is moving main — the planner
  emits at most one, only for an idle queue, and holds the queue while one is live; running it
  without every live `wc-*` as `--reconciling` hides that one from it
- Merging a reconciled head before its fresh review round, or running `--resolve-conflicts`
  with `--merge-method rebase` — a rebase-and-merge drops the reconciliation's edits
- Fixing reviewer findings into the PR that produced them, or re-reviewing past two rounds
- Filing findings without the converter (hand-composed bodies lose the `review-of:` marker
  the merge pass keys holds off) — run `findings_to_plan.py`, then dedup, then `hew apply`
- Running the human-review integration branch's merges all-at-once (octopus)
- Closing tabs or agents this run did not create, or the orchestrator's own workspace
- Closing the epic because its children are done — report it; a human closes it
- Putting outcome files directly under `/tmp` instead of `${TMPDIR:-/tmp}/opencode` — every agent
  that touches them prompts for external directory access
