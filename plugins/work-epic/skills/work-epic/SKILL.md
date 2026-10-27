---
name: work-epic
description: Pump a hew epic end to end with Orca-managed worktrees and supervised agents — resolve the epic's ready children, create one Orca worktree per child, start a supervised implementer running work-issue in it, review each delivered PR in a transient review worktree running review-code, file the findings as epic children, reconcile conflicts in the child's own worktree, and merge PRs once CI is green. Implementers and reviewers are chosen independently from an agent pool, so a PR can be implemented by one agent and reviewed by a different one. Autonomous mode (the default) merges on green; `--human-review` stops at drafts and leaves every merge to a human. Use whenever the user wants an epic worked by orchestrating agents — "work on this epic", "drain epic 12", "orchestrate #42", "fan out this epic to workers", "pump the epic and merge it". Not for a single issue (that goes to work-issue) and never for closing issues or the epic itself.
argument-hint: "Epic number. Flags: --human-review, --block-on P1|P2|none (default P1), --merge-method squash|merge|rebase (default squash), --workers N (default 2), --max-open-prs N (default 2 × workers), --implementers <list> (default opencode; all = opencode,claude,codex), --reviewers <list|auto> (default auto: implementer pool minus the implementer), --reconciler <id|auto> (default auto: the child's implementer), --dry-run, --no-review, --allow-no-checks, --resolve-conflicts, --resume"
---

# Work Epic

One epic, pumped: resolve its ready children, create an Orca worktree per child, start one
supervised implementer in it, review each delivered PR from its own transient worktree, file
the findings, merge on green, and re-pump. This skill orchestrates; it never implements or
reviews by hand.

**The roles are separate agents.** The implementer runs `work-issue`; the reviewer runs
`review-code`; the reconciler resolves a conflict; the coordinator is the agent running this
skill. The implementer and reviewer are chosen independently from an agent pool, and the default
reviewer is a **different** agent from the implementer whenever the implementer pool has another
agent, or an explicit reviewer pool names one. That is the point: a Claude implementation gets a
Codex or opencode review, an opencode implementation gets a Claude review, and a re-review moves
to another reviewer whenever the pool leaves one. The role is recorded on the Task, the worktree
comment, and the report, so a mixed run is traceable rather than guessed from terminal titles.

**Orca is the execution layer.** A Run is this pump's identity and inbox. Each child is a Task
and a durable Orca worktree; each attempt is a Dispatch; each PR review is a transient
worktree. The worktree — not an agent name or a terminal handle — is the unit the pump creates,
annotates, keeps, reconciles in, and finally removes. Orca's worktree metadata (issue link, PR
link, status, comment, unread dot, parent lineage) is the epic's live board.

**Modes.** In autonomous mode (the default) the merge gate is CI green plus reviewer
severity: PRs whose checks pass and whose review surfaced nothing at or above `--block-on`
are marked ready and merged, main is fast-forwarded, and the pump continues into the freed
work. `--human-review` restores the older contract: every PR stays a draft and every merge is
a human's click.

**Hard gates, in every mode.** The pump never closes an issue or an epic, never force-claims,
never answers a worker's dialog, never edits a conflicted branch itself, never fixes a finding
into the PR it came from, and never merges a PR outside the epic it was given. Without
`--resolve-conflicts` a conflict is filed and escalated like any other human gate; with it, the
edit is delegated to a reconciler worker in the child's own worktree and its new head earns its
own review round — the pump itself never reconciles one. Escalations reach the human through
the worktree's status, comment, and unread dot; the pump stops and reports rather than route
around a gate. Autonomous mode moved the *merge* off the human's list, not the judgement.

> [!IMPORTANT]
> [REFERENCE.md](REFERENCE.md) carries the scripts' output schemas, the Run/Task/worktree
> lifecycle, the worker, reviewer, and reconciler prompt templates, the review-round and
> reconciliation comments, the findings-filing flow, worktree naming and cleanup, timeout
> budgets, the merge-pass command list, and the report format. Read it before the reaping step.

## The scripts

Spawn and merge decisions come from scripts, not from hew or gh JSON sorted in your head —
a pump that picks differently on each run cannot be reasoned about from its logs. Resolve
them once against this skill's own directory:

```bash
RESOLVE="<this skill's directory>/scripts/resolve_ready.py"
PRSTATE="<this skill's directory>/scripts/pr_state.py"
```

They are read-only (hew, git and gh reads, never writes) and decide nothing a human owns —
they filter, sort, size, and classify; the skill acts. Orca is not a second planner: the Run,
Tasks, and worktrees record execution, while `resolve_ready.py` remains the only scheduler and
`pr_state.py` the only merge classifier.

## Prerequisites

This skill drives Orca, so first prove it is running inside an Orca-managed terminal and
worktree:

```bash
ORCA worktree current --json
ORCA status --json
```

`worktree current` must name the coordinator's worktree (`result.worktree.id`, `repoId`, `path`)
and `status` must report the runtime ready. If either fails, say so and stop — do not spawn
worktrees or workers into a session you cannot observe. The `orca-cli` and `orchestration` skills
should be in context; if not, run `ORCA skills get orchestration` first and follow its
CLI-discovery rule (`--help` over probing).

Throughout, `ORCA` is the executable resolved by the `orca-cli` skill (`ORCA_CLI_COMMAND`,
`orca-dev`, `orca-ide`, or `orca`). Substitute it before running; never hardcode `orca` on a
Linux host where that name is the screen reader.

The target repository must be registered in Orca and the coordinator's worktree must belong to
it. `worktree current` gives the `repoId`; `ORCA repo list --json` confirms the path and the
GitHub `projectId`. If the resolver's `mainCheckout` is not a registered Orca repo, stop and
tell the human to register it (`ORCA repo add --path "$MAIN" --json`) — do not create worktrees
in a repo Orca does not own.

`hew` on PATH and authenticated — exit code 4 from any `hew` command means run `gh auth login`,
and here that halts the whole pump as an `error`, not as an empty queue.

The skills this pump drives must resolve where each role runs: `work-issue` (hew plugin) for
implementers, `review-code` (critique plugin) for reviewers, and raise-issues'
`findings_to_plan.py` for filing in the coordinator. Install `work-issue` in each implementer's
skill loader and `review-code` in each reviewer's; a codex worker needs the files on disk because
its prompt points at them. Reconcilers load no skill, but they read the quality-gate table from
the work-issue skill directory, so that directory must be readable on the host. The pump ships
prompt adapters for opencode, claude, and codex: the first two load skills by name, codex receives their
file paths (see [REFERENCE.md](REFERENCE.md#agent-adapters)). Adding a fourth agent means adding
its adapter, not changing the orchestration.

Orca's CLI does not expose a first-class installed/available agent list today.
`worker-start --help` and `agent launch --help` name known ids, and `orca account list --json`
shows account/auth configuration for some agents, but neither proves an agent is installed or
enabled. The runtime's `agentSession.agents` and `agentSession.subscribeAvailability` RPCs are
what the Orca app's picker uses; they are not CLI commands. The pool is therefore an operator
declaration: the skill uses it, and a failed `worker-start` names the agent that could not
launch. Report that failure for that child and do not silently swap in another agent.
`--implementers all` and `--reviewers all` expand to `opencode,claude,codex`.

The coordinator's worktree is the escalation surface. Prefer a dedicated Orca worktree for the
coordinator: the pump writes its `.work-epic/` scratch directory and status comment there.
Prove that surface is writable once at startup by setting the comment and status (Step 0). If
that write fails, the human channel is not writable; report it and stop. Orca has no
push-notification command: an escalation lands as the worktree's unread dot plus its comment and
status, and as the final report. Nothing proceeds through a gate while it waits.

## Arguments

Strip flags; what remains is the epic number.

- **`<epic-n>`** — the epic to pump. A non-epic number is redirected to `work-issue`.
- **`--human-review`** — no merges, no findings filing: PRs stay draft with findings relayed
  as comments, the integration pass runs, and the human merge gate is absolute.
- **`--block-on P1|P2|none`** — the severity that holds a PR back from merging, default P1.
  Findings at or above it become holds and escalations, not merges; `none` holds on nothing.
- **`--merge-method squash|merge|rebase`** — how PRs merge, default squash. Rebase rewrites
  PR refs and fights the pump's own branch updates; prefer squash or merge.
- **`--workers N`** — cap on live writer workers (`we-*` and reconciling `wc-*`), default 2.
  More than 3–4 only moves the bottleneck into the review-and-merge pipeline; raise it on
  explicit instruction. Reviewers do not count against it.
- **`--max-open-prs N`** — cap on the epic's PR backlog, default twice `--workers`. Open PRs
  plus workers in flight never exceed it: once the backlog is full, the pump stops spawning
  and lets the merge pass drain. Every open PR drifts further behind main with each merge, so
  this is the bound on how stale the backlog gets. Held and conflicted PRs count — a backlog
  that cannot merge is the one not to grow.
- **`--implementers <list>`** — comma-separated implementer pool for `work-issue`, default
  `opencode`; `all` expands to `opencode,claude,codex`. Child `n` is implemented by
  `implementers[n % len(implementers)]`, so a mixed run is deterministic across invocations.
  This is the "different points of view" knob for implementation.
- **`--reviewers <list|auto>`** — comma-separated reviewer pool for `review-code`, default
  `auto`: the implementer pool **minus** the child's implementer, or the implementer pool
  itself when that would be empty. The candidate is chosen by
  `(pr + round - 1) % len(candidates)`. An explicit list may name agents outside the
  implementer pool (that is how `--implementers opencode --reviewers claude` works); the pump
  still prefers a different agent when the list contains one, and warns when it does not.
  `all` expands to `opencode,claude,codex`. A re-review moves to the next candidate, so
  round 2 is a different reviewer from round 1 whenever more than one candidate remains; a
  single-candidate set reviews with the same agent again.
- **`--reconciler <id|auto>`** — agent for a conflict reconciliation, default `auto`: the
  child's implementer. Set it to a different agent when you want the conflict resolution itself
  written by someone other than the implementer. A reconciler from another run's PR defaults to
  the first implementer in the pool.
- **Supported agent ids** are `opencode`, `codex`, and `claude`, because those are the prompt
  adapters this skill ships (opencode/claude load skills by name; codex by file path). Other
  Orca ids are refused at parse time. Adding one is a REFERENCE-level adapter change, not an
  orchestration change.
- **Availability is declared, not queried.** Orca's CLI has no `agent list`; the pool is the
  operator's statement of what is installed and enabled. A `worker-start` failure names the
  agent that could not launch and costs only that child; the pump reports it and never silently
  retries with another agent.
- **`--dry-run`** — run both planners, show the planned Orca Run, Tasks, worktrees, and merge
  plan, touch nothing.
- **`--no-review`** — workers only; in autonomous mode PRs merge on CI green alone, in
  human-review mode they stay draft.
- **`--allow-no-checks`** — treat a PR with no CI checks at all as green. Without it, "no
  checks" reads as "CI has not reported yet", which is what it usually means straight after a
  push. Only for repositories that genuinely have no CI, and only on explicit instruction.
- **`--resolve-conflicts`** — delegate a PR's conflict with the default branch to a reconciler
  worker (`wc-<pr>`) instead of filing and parking it. It runs in the child's own worktree when
  this Run still holds one, otherwise in a transient worktree. Off by default: the human gate
  stands unless a run is told otherwise. One reconciler at a time, only while the merge queue
  is idle (a merge landing mid-reconciliation would re-conflict it), occupying a `--workers`
  slot. Refused together with `--merge-method rebase` — the reconciliation is a hand-edited
  merge commit and a rebase-and-merge would drop its edits — and with `--human-review`, which
  runs no merge pass for it to act in. A resolved head is un-readied and re-reviewed; two
  failed attempts park the PR for the human like any other conflict.
- **`--resume`** — pass through to the resolver to pick up this user's own claims that have
  neither a PR nor a pushed branch, bind the previous Run, adopt its live Tasks and worktrees,
  and drain its mailbox. Explicit instruction only.

**Choosing agents.** For a mixed run, the useful default is
`--implementers all --reviewers auto` (or the explicit
`--implementers opencode,claude,codex --reviewers auto`): children rotate implementers and each
PR is reviewed by an agent that did not write it. For a fixed pairing, name both —
`--implementers claude --reviewers codex`. For the strongest separation, put the reviewer in a
third family: `--implementers opencode,claude --reviewers codex`. A single-agent implementer pool
with `--reviewers auto` reviews with that same agent; the pump says "same-agent review" in the
report rather than pretending otherwise.

## Step 0 — Bind the Run and the coordinator worktree

The Run is this pump's namespace: it scopes every Task, every Dispatch, and every mailbox read.
Bind it before planning so a resumed run reuses the same identity.

On a fresh run:

```bash
ORCA orchestration run-create --objective "work-epic #<epic-n>" --json
```

Read `result.run.id`. On `--resume`, read the run id stored in the pump's scratch
`run.json`; if it is gone, `ORCA orchestration run-list --json` and match the objective
`work-epic #<epic-n>` exactly. One match: `ORCA orchestration run-use --id <run-id> --json`.
Zero: create a new Run, but say the resume identity was lost. More than one: stop and ask which
Run to resume — never guess between two live pumps.

An already-bound Run with a different objective is a coordinator that was used for something
else. Do not rebind it silently; stop and report.

Prepare the pump's scratch directory in the coordinator's own worktree, so it is writable by
whichever agent is coordinating and survives a resume:

```bash
OUTDIR="<coord-worktree-path>/.work-epic/<epic-n>"
mkdir -p "$OUTDIR"
```

It is pump scratch, not a deliverable: do not commit it, and do not point a spawned agent at it.
Workers, reviewers, and reconcilers also write their outcome files into a `.work-epic/` directory
in their own worktrees. Keep every such directory out of `git status` by listing it in the
repository's shared exclude file, which every worktree reads and which is never committed:

```bash
EXCL="$(git -C "<coord-worktree-path>" rev-parse --path-format=absolute --git-path info/exclude)"
grep -qxF '.work-epic/' "$EXCL" || echo '.work-epic/' >> "$EXCL"
```

Ignored, an outcome file neither fails a clean-tree check (including the one before a reconciler
starts in a child worktree) nor gets swept into a commit by a stray `git add -A`.
Record the coordinator's worktree id, repo id, path, and the Run id in `$OUTDIR/state.json`
(schema in [REFERENCE.md](REFERENCE.md)). Then set the coordinator's status line:

```bash
ORCA worktree set --worktree "id:<coord-worktree-id>" \
  --comment "work-epic #<epic-n> · <run-id> · coordinator starting" \
  --workspace-status in-progress --json
```

Do not change the coordinator's display name, issue link, PR link, or parent lineage; that
worktree may be the human's own. Under `--dry-run`, create no Run, scratch directory, exclude entry, or
comment: print the objective, each eligible child with its `we-`/implementer task and worktree
name, the reviewer rotation for the open PRs, and the merge plan; stop after Step 1 and Step 6's
plan.

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
  the primary worktree and `defaultBranch` the origin default.

An `eligible` child with `large: true` exceeds work-issue's sizing rule. Spawn it as usual, but
name it in the report as large, so a human can see why it ran long or stalled.

`mainCheckout` is now the fetch/fast-forward/integration anchor, not the spawn cwd: Orca creates
each child worktree from `origin/<default>` explicitly, so the human's main checkout may be on
any branch. The resolver already keeps out what this pump has touched: a child with an open PR
is `in_review`, one whose worker failed (branch pushed, no PR) is `stalled`, and one claimed by
you with neither is `claimed` unless `--resume` was given. Spawn only from `eligible`.

An empty `eligible` is meaningful either way: all-blocked, all-untriaged, all-claimed,
all-in-review, or a finished epic. Say which, from `counts`, and — for a finished epic where
every child is closed — escalate that a human should close it, exactly as `work-issue`
requires. Do not close it here.

## Step 2 — Capacity and existing worktrees

Capacity is Orca state, not a guess:

```bash
ORCA orchestration task-list --run "<run-id>" --json
ORCA orchestration worker-list --run "<run-id>" --json
```

Writers are Tasks whose title starts `we-` or `wc-`, whose status is `dispatched`, **and**
whose Dispatch is still live. Reviewers (title prefix `wr-`) don't count. A Task left `dispatched` with an
`exited` worker is a stall to reap, not capacity. Open slots are the smaller of `--workers`
minus live writers and the resolver's `spawnBudget` — the room left under `--max-open-prs` once
open PRs and workers in flight are counted. If reaping hasn't freed a slot, wait on the live set
(Step 4); if the budget is zero, spawn nothing and go to the merge pass (Step 6) — the backlog
drains before it grows.

Before creating anything, ask Orca whether this child already has a worktree:

```bash
ORCA worktree show --worktree "issue:<n>" --json
```

- **A worktree with this Run's marker** — adopt it. If its Task is live, wait on it; if its Task
  is settled, go to Step 4's outcome handling. Never create a second worktree for the same
  child in the same Run.
- **A `work-epic` worktree with a different run marker** — another pump owns this child. Skip
  it and report the worktree id; do not touch, release, or remove it.
- **A worktree with no `work-epic` marker** — a human or another tool is using it for this
  issue. Treat the child as claimed by someone else, skip it, and say why.
- **None** — the child is free to spawn, subject to the resolver and the slot budget.

The marker lives in the worktree comment:
`work-epic #<epic-n> · <run-id> · <role-key> · <agent> · <state>`, where the role key is
`we-<n>`, `wr-<pr>`, or `wc-<pr>`. The agent token is the role's chosen agent (`opencode`,
`claude`, or `codex`), so the sidebar and the report say who did what. The issue link is the durable selector: set `--issue <n>` immediately after creating
a child worktree, so `issue:<n>` works on every later run.

Ownership is Run-scoped. There are no unique agent names to collide; instead, **never act on a
Task, Dispatch, terminal, or worktree with a marker from a different Run**. The `we-`/`wr-`/
`wc-` task titles are reporting conventions, not the lock. Run scoping is not an epic lock:
two orchestrators on the same `gh` login still only get `hew start` exit 5 ("the claim is
yours"), so do not run two pumps over the same epic.

## Step 3 — Create child worktrees and start workers

`$MAIN` and `$DEFAULT` come from the resolver. Bring the main checkout's view of origin up to
date once per run:

```bash
git -C "$MAIN" fetch origin
```

If `$MAIN` is on `$DEFAULT`, fast-forward it so the human's checkout and the integration pass
see what has merged:

```bash
test "$(git -C "$MAIN" symbolic-ref --short HEAD)" = "$DEFAULT" &&
  git -C "$MAIN" merge --ff-only "origin/$DEFAULT"
```

If it is on another branch, skip the ff and say so in the report — never switch the human's
checkout. Orca bases every new child on `origin/$DEFAULT`, so spawning is safe either way. A
failed ff-only is an escalation; never rebase or reset it.

The pump's scratch directory is the one Step 0 created in the coordinator's worktree. Spawned
agents write their outcome files inside their own worktrees, so no worker needs access to
`$OUTDIR` and no one prompts for an external directory.

Pick the implementer deterministically before spawning:
`IMPLEMENTERS[n % len(IMPLEMENTERS)]`. The same issue gets the same implementer on every run,
even if an earlier child was skipped or a different number of workers was free. Record the
choice in the state file and on the worktree. Then create the worktree and the supervised
worker in one call:

```bash
ORCA orchestration worker-start \
  --spec "<worker prompt from REFERENCE.md, pointing at
    work-issue <n> --non-interactive --json '.work-epic/we-<n>.json'>" \
  --task-title "we-<n> · <implementer>" \
  --worktree new-child \
  --repo "id:<repo-id>" \
  --name "we-<n>" \
  --display-name "#<n> <short title> · <implementer>" \
  --base-branch "origin/$DEFAULT" \
  --comment "work-epic #<epic-n> · <run-id> · we-<n> · <implementer> · worker started" \
  --setup inherit \
  --agent <implementer> \
  --json
```

`new-child` makes the worktree a child of the coordinator's worktree in Orca's sidebar, and
Orca's agent-first creation starts the worker without a stray shell terminal. Read the start
receipt: the `taskId`, the `dispatchId`, the worktree id/path, and the launch outcome. If an
older host does not return a worktree id, resolve it with
`ORCA worktree list --json` by the unique comment marker — never predict a path. Then link the
issue and mark the card live:

```bash
ORCA worktree set --worktree "id:<child-worktree-id>" \
  --issue <n> --workspace-status in-progress --json
```

Record `{task, dispatch, worktree, path, implementer, state: "running"}` for the child in
`$OUTDIR/state.json`.

The worker runs `work-issue` in its own checkout. `work-issue` may create its conventional
issue branch (`fix/<n>-…`) inside the Orca worktree; that checkout is the child's home for the
rest of its life. The outcome file is written only at the end, after the commit and push, into
`.work-epic/` so it never dirties the tree during `work-issue`'s clean-tree checks.

Submit prompts without waiting for them to finish; `worker-start` returns when the worker is
ready. A spawn that fails still owns the terminal it created: read `failedStage`,
`residualResources`, and the recovery commands from the receipt, release that terminal, and
decide whether the worktree is safe to remove (clean and agentless: remove; otherwise keep and
report). One failed spawn costs only that child — continue with the rest and report it.

## Step 4 — Reap settled workers and reviewers

Wait on the Run's mailbox, not on each terminal:

```bash
ORCA orchestration check --run "<run-id>" --wait \
  --types "worker_done,escalation,question" --timeout-ms <budget> --json
```

The check returns the Run's oldest unacknowledged FIFO batch. Process **every** message in it,
then acknowledge the whole batch with
`ORCA orchestration check --run "<run-id>" --ack <delivery-id> --json` and wait again.
Heartbeats and status messages are acknowledgements, not work; `--wait` also emits `_keepalive`
lines on stderr, which are not messages. Process the whole Delivery before acknowledging it —
a bound Run replays it until then.

A `check` timeout is a tick, not a failure: enumerate the live set and run the merge pass before
waiting again. This is how CI polling and worker settlement share one loop.

```bash
ORCA orchestration worker-list --run "<run-id>" --json
```

For each row, read `projection.liveness`, `projection.attention.requiresAction`,
`projection.attention.categories`, and the literal `projection.nextAction` argv. Only positive
proof ends a wait: a `worker_done` Delivery, an `exited` liveness verdict, or the worker's own
transcript ending without one. `unverifiable` is absence — keep waiting or inspect; it never
authorises stop, abandon, retry, or release. Follow the orchestration guide's recovery reference
for a failed, stopped, or unknown attempt; do not improvise cleanup from a timeout.

For a settled worker, read its outcome file from the child worktree before doing anything else.
The `worker_done` message's `--outcome` is a hint; the file is the authority. If they disagree,
report the mismatch and treat the file's status. A missing or unreadable file is re-checked for
60–120s on a few-seconds cadence before it becomes an `error`: the write can trail the state
change, so the settle alone does not prove the outcome is absent. Past that grace a missing file
is an `error` all the same — never an inference from terminal output. Then:

| outcome | action here |
|---|---|
| `delivered` | archive the outcome to `$OUTDIR/outcomes/we-<n>.json`, then remove it from the worktree so no stale outcome sits in the checkout a reconciler will reuse; note the PR; set the child worktree `--pr <pr> --workspace-status in-review --comment "work-epic #<epic-n> · <run-id> · we-<n> · <implementer> · PR #<pr> delivered; review pending"`; release the worker; keep the worktree for review and reconciliation; spawn the reviewer (Step 5) |
| `failed` | report; leave the issue claimed; do **not** respawn it — its pushed branch makes it `stalled` on every later resolver pass. Keep the worktree, mark it `--unread`, and put `work-epic #<epic-n> · <run-id> · we-<n> · <implementer> · failed: <reason>` in its comment; release the worker |
| `no_ready_work` / `not_eligible` | report verbatim, with the skipped counts — a queue of issues claimed by a dead agent reads as drained and hides the stall; release the worker and remove the clean, workless worktree |
| `error` | **halt the pump**: finish reaping what's live, spawn nothing new, escalate — un-auth or dirty trees are an outage, not an empty queue. Keep the worktree, mark it unread, set its comment to `... · <implementer> · error: <reason>`, release the worker |

Release a settled worker with:

```bash
ORCA orchestration worker-release --dispatch "<dispatch-id>" --json
```

Release archives the terminal output and closes only that Dispatch's terminal; the worktree
stays. Never release before the outcome is read and archived. Never release because of a
timeout, TUI idle, heartbeat, question, or escalation — those are still work or human gates.
If a release reports `release_unknown`, follow its exact recovery action; if it reports
`release_pending`, retry that same release later; if it reports `retained`, leave it alone and
report why.

A worker that is parked on a permission prompt or a question only a human can answer shows up
in `worker-show`:

```bash
ORCA orchestration worker-show --dispatch "<dispatch-id>" --json
ORCA orchestration worker-read --dispatch "<dispatch-id>" --source auto --json
```

A non-null `observation.agentWait` names a worker parked on a prompt only a human can answer,
with the evidence that proved it. Throw the escalation once per Dispatch — set the child
worktree `--unread` and set its comment to
`work-epic #<epic-n> · <run-id> · we-<n> · <implementer> · BLOCKED: <what>` — and **never
answer it**. An absent `agentWait` means Orca never looked (older host, unverifiable identity,
unreadable pane), not that the worker is free; keep inspecting or waiting. A soft/idle agent
still producing output is not a dialog: re-enter the wait loop under its budget.

A `question` Delivery is the same gate from the other side: report it with its message id so the
human can `ORCA orchestration reply --id <message-id> --body "..."`; the pump never replies.
The worker stays live and counts against `--workers` until the human or the worker settles it.

For a reviewer or reconciler, the same settlement rules apply. A reviewer's outcome lives in
`.work-epic/wr-<pr>.json`; a reconciler's in `.work-epic/wc-<pr>.json`. Archive, release, and
then remove the transient worktree per Step 5/6. A reviewer does not count against `--workers`.

Never remove a worktree that still has a live terminal, a blocked worker, uncommitted work, or a
held/conflicted PR. Keep it, mark it unread, and report its path.

## Step 5 — Review delivered PRs (skip under `--no-review`)

One reviewer per delivered PR (and per `re_review` from Step 6). If a `wr-<pr>` Task is already
live for that PR, adopt it and wait — do not spawn a second reviewer. Record the head being
reviewed first — it becomes the round's `reviewed-head:` — then choose the reviewer and create a
transient review worktree. The round is `pr_state.py`'s `reviewRounds + 1` for a `re_review`,
and 1 for a freshly delivered PR. The reviewer must not share the child's checkout: the child
stays on its issue branch for reconciliation, so the reviewer gets its own worktree and a
**named review branch**. Detached HEAD is not an option: review-code's scope discovery refuses
it.

Pick the reviewer deterministically, and make it different from the implementer whenever the
pool allows:

```
candidates = REVIEWERS minus the PR's implementer   # or REVIEWERS if that is empty
reviewer(pr, round) = candidates[(pr + round - 1) % len(candidates)]
```

With `--reviewers auto`, `REVIEWERS` is the implementer pool, so round 1 is a different agent
from the implementer whenever the pool has more than one, and a re-review moves to the next
candidate when more than one remains. An
explicit reviewer list may name an agent outside the implementer pool; the pump still removes
the implementer from the candidate set when another agent remains. A single-candidate set is
allowed; the report says "same-agent review" rather than pretending otherwise. Record the
reviewer in the state file and on the worktree.

```bash
HEAD_SHA=$(gh pr view <pr> --json headRefOid --jq .headRefOid)
ORCA orchestration worker-start \
  --spec "<reviewer prompt from REFERENCE.md, including review-code
    --non-interactive --json '.work-epic/wr-<pr>.json'>" \
  --task-title "wr-<pr> · <reviewer> · r<round>" \
  --worktree new-child \
  --repo "id:<repo-id>" \
  --name "wr-<pr>-r<round>" \
  --display-name "Review PR #<pr> · <reviewer> (round <round>)" \
  --base-branch "origin/$DEFAULT" \
  --comment "work-epic #<epic-n> · <run-id> · wr-<pr> · <reviewer> · reviewing round <round>" \
  --setup skip \
  --agent <reviewer> \
  --json
ORCA worktree set --worktree "id:<review-worktree-id>" \
  --pr <pr> --workspace-status in-progress --json
```

The prompt checks out the PR head onto a local review branch:

```bash
gh pr checkout <pr> --branch "review/<pr>-r<round>"
# fallback: git fetch origin pull/<pr>/head && git switch -c "review/<pr>-r<round>" FETCH_HEAD
```

That branch is not the child's issue branch, so the two worktrees never fight over a checkout;
`review-code` sees a named branch and its default branch-vs-default scope is exactly the PR's
diff. A re-review uses a new round suffix and a new transient worktree; remove the previous one
once its findings are read.

Reap reviewers exactly like workers — same `check --wait` batch, same `worker-show.agentWait`
gate, reviewer budget in [REFERENCE.md](REFERENCE.md) — and release the reviewer as soon as its
file is read. Then remove the review worktree with `ORCA worktree rm --worktree "id:<id>"`
(use `--force` for a review-only worktree; it changed no code). Delete the local review branch
if Orca retained it, so the next round starts clean.

Read the findings file before anything else:

- **Missing or unreadable** — escalate; an unread review is not a clean review.
- **`status` other than `reviewed`** (`no_scope`, `error`) — escalate with its `reason`. The
  review did not run, and its empty `findings` array means nothing; reading it as clean merges
  an unreviewed PR.

A `reviewed` file always produces exactly one **review-round comment** on the PR (template in
[REFERENCE.md](REFERENCE.md)), clean or not: it carries the marker `pr_state.py` counts rounds
by and `reviewed-head: $HEAD_SHA`. A PR with no round comment is one the planner treats as
unreviewed and never merges.

**File first, comment second.** The round comment is what makes a PR mergeable, and the open
finding child is what holds it. Posting the comment first leaves a window — a crashed pump, a
failed `hew apply` — where the planner sees a current review and no blocker and merges a PR whose
P1 was never filed. Filed first, the worst a crash leaves is a PR with no round, which the planner
never merges; Step 8 re-reviews it, and the review-key dedup keeps the repeat filing from
duplicating children. The comment also quotes each child's number
(`Filed as #<child>`), which only exists once the filing has run. So, in autonomous mode:

1. **Findings at P2 or above** — file them as epic children through the raise-issues flow:
   `findings_to_plan.py --parent <epic> --reviewed-issue <n> --reviewed-pr <pr>
   --at-or-above P2` (flow and dedup rules in [REFERENCE.md](REFERENCE.md)), dry-run, then
   `hew apply`. P3s are not filed; the round comment carries them. A filing that fails is an
   escalation — post no round comment over it.
2. **Post the round comment**, with the filed children's numbers.
3. **Decide readiness** from the filed findings:

- **Nothing at or above `--block-on`** — `gh pr ready <pr>`, set the child worktree to
  `work-epic #<epic-n> · <run-id> · we-<n> · <implementer> · clean review by <reviewer>;
  ready to merge`, and notify. The merge pass takes it from here; filed findings below the bar
  are tracked work that unblocks when this PR merges.
- **Anything at or above `--block-on`** — the PR stays draft, the child worktree is marked
  `--unread` with
  `work-epic #<epic-n> · <run-id> · we-<n> · <implementer> · HOLD: <severity> finding #<child>
  (reviewer <reviewer>)`, and the human is notified. The open finding child holds it (the round
  comment is the hold's public reason).

Record the reviewer, round, verdict (`clean`, `hold`, or `escalated`), and findings children in
the child's state entry. In `--human-review` mode nothing is filed or merged: the round comment
relays every finding, the PR stays draft, the child worktree stays `in-review` with the findings
in its comment, and the human is notified — findings are never fixed into a PR a human is about
to read.

## Step 6 — Merge pass (autonomous mode)

Skip under `--human-review` (its Step 7 is the throwaway integration branch instead).

Every open PR of this epic goes through `pr_state.py` — not only this run's deliveries; PRs
delivered by earlier runs or other orchestrators are merged by the same plan or left alone:

```bash
uv run --no-project "$PRSTATE" <epic-n> --block-on <block-on> [--no-review]
  [--allow-no-checks] [--resolve-conflicts] [--reconciling <pr>]...
```

Pass one `--reconciling <pr>` for every `wc-<pr>` Task in this Run that is still live. GitHub
cannot see a reconciler at work, and the planner runs on every pass while one does: without the
list it would start a second reconciler, or merge main out from under the first. Read the live
set from `task-list`/`worker-list`, not from a remembered list.

A live `wr-<pr>` reviewer also holds that PR: its round is not complete, even if an older round
comment matches the head. Before executing a `merge`, skip that PR and wait for the reviewer's
`worker_done`, then re-run the planner. The planner cannot see an in-flight review; the Run can.

Execute each PR's `action` exactly as classified — the planner is the decision, the pass is
the hands (commands, CI-wait budgets, and merge-failure handling in
[REFERENCE.md](REFERENCE.md)):

| action | what the pass does |
|---|---|
| `merge` | `gh pr merge --<merge-method>`; only once it succeeds, finish the child worktree and delete the branch (Step 6's merge order); notify; fast-forward main |
| `mark_ready` | `gh pr ready` — a draft's merge state reads `DRAFT` until then, hiding `BEHIND` or `BLOCKED`; the next pass sees the real state |
| `update_branch` | `gh pr update-branch <pr>` — GitHub merges the default branch in server-side; a failure re-runs the planner, whose next pass sees `DIRTY` and hands it to `reconcile` under `--resolve-conflicts` (or to `conflict`) |
| `reconcile` | start a reconciler worker (`wc-<pr>`) in the child's own worktree when this Run holds one, otherwise in a transient worktree; the planner emits one only while `queueHead` is null and no `--reconciling` is live |
| `queued` | nothing; it waits its turn behind `queueHead` or behind the reconciliation head, and spends no CI budget of its own |
| `re_review` | spawn a fresh reviewer (Step 5) for the new head |
| `conflict` | file the coupling (`hew search` first, then `hew create --discovered-from <n>`), mark the child worktree unread with `work-epic #<epic-n> · <run-id> · we-<n> · <implementer> · CONFLICT` in its comment, and leave the PR — the pump never reconciles one itself, so without `--resolve-conflicts` or after two failed attempts it parks here |
| `hold` | mark the child worktree unread with `... · <implementer> · HOLD: <severity> finding #<child>` in its comment; the human lifts it by closing the finding child — once fixed on the branch, or accepted as is. Fixing the branch alone does not lift it, and the pump never un-holds |
| `escalate` | notify; set the child worktree unread with `... · <implementer> · ESCALATE: two review rounds`; a third automated round is spam, not diligence |
| `protected` | notify; set the child worktree unread with `... · <implementer> · PROTECTED: <what branch protection wants>` (typically an approving review) |
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

**Merge order and the worktree.** The child worktree is the card the human has been watching;
it is also a checkout of the branch being merged, so it outlives the merge call. Merge first,
and without `--delete-branch` — gh would try to delete a local branch that is still checked out
in that worktree:

```bash
gh pr merge <pr> --<merge-method>
```

A merge that fails changes nothing here: the card, the checkout, and `$OUTDIR/state.json` still
describe an open PR, and the planner re-classifies it on the next pass. Only once the merge has
succeeded, finish the child:

```bash
ORCA worktree set --worktree "id:<child-worktree-id>" \
  --workspace-status completed \
  --comment "work-epic #<epic-n> · <run-id> · we-<n> · <implementer> · merged" --json
ORCA worktree rm --worktree "id:<child-worktree-id>" --json      # only if clean
gh api -X DELETE "repos/{owner}/{repo}/git/refs/heads/<branch>"  # 422 = already gone
git -C "$MAIN" branch -D "<branch>"                              # if it still exists locally
```

Record the merge in `$OUTDIR/state.json`. `worktree rm` deletes the local branch only when it
can prove the branch merged, which a squash or rebase merge defeats, hence the explicit
`branch -D`; the PR is merged, so the branch holds nothing that is not on the default branch. If
the worktree is dirty **or removal fails**, do **not** discard the work: keep the worktree, mark
it unread, report the path, and skip the local branch delete (it is still checked out); the
remote branch delete still runs. Branch cleanup failing after a successful merge is reported,
never an escalation. A worktree already removed, or a PR from another run with no child
worktree here, needs only the branch deletes.

**Resolving conflicts (`--resolve-conflicts`).** The planner emits at most one `reconcile` —
its `reconcileHead` — and only while `queueHead` is `null`: a merge landing mid-reconciliation
would re-conflict it. Pick the reconciler deterministically: `--reconciler` when set, otherwise
the PR's implementer, otherwise `IMPLEMENTERS[0]`. Record it on the worktree and in the state
file. Then resolve the child from the PR's `issue` in `$OUTDIR/state.json` or
`ORCA worktree show --worktree "issue:<n>"`:

- **This Run has a child worktree** — start `wc-<pr>` in it with
  `ORCA orchestration worker-start --task-title "wc-<pr> · <reconciler>" --worktree "id:<child-id>"
  --agent <reconciler> --spec "<reconciler prompt, child-worktree variant>" --json`.
  The checkout is already on the issue branch; the prompt fast-forwards to the PR head, merges
  `origin/$DEFAULT`, reconciles, gates, and pushes. No second checkout, no branch lock, and the
  repository setup the worker already paid for is still there. Check the child worktree is
  clean (`git status --porcelain`) before starting; a dirty checkout is an escalation, not a
  stash.
- **No child worktree (PR from an earlier run or another orchestrator)** — start a transient
  reconciler in one call:

  ```bash
  ORCA orchestration worker-start \
    --task-title "wc-<pr> · <reconciler>" \
    --worktree new-child \
    --repo "id:<repo-id>" \
    --name "wc-<pr>-a<attempt>" \
    --display-name "Reconcile PR #<pr> · <reconciler> (attempt <attempt>)" \
    --base-branch "origin/$DEFAULT" \
    --comment "work-epic #<epic-n> · <run-id> · wc-<pr> · <reconciler> · reconciling" \
    --setup inherit \
    --agent <reconciler> \
    --spec "<reconciler prompt, transient variant>" \
    --json
  ```

  `<attempt>` is the planner's `reconcileFailures` plus one, so a worktree kept from a failed
  attempt never collides with the next one's name. Link the card with
  `ORCA worktree set --worktree "id:<id>" --pr <pr> --workspace-status in-review`. The prompt checks out the PR branch itself, reconciles, runs
  the gate, and pushes to the PR ref; remove the worktree afterward.

Update the child worktree's comment to
`work-epic #<epic-n> · <run-id> · we-<n> · <implementer> · reconciling PR #<pr> (<reconciler>)`
while it runs. Until the
reconciler is reaped, every pass hands its PR number to the planner as `--reconciling`, which
holds that PR at `wait` and queues every other merge, update, and reconciliation behind it.
Archive the reconciler's outcome to `$OUTDIR/outcomes/wc-<pr>.json` and remove it from the
worktree (child or transient) before the checkout is used again. Then, from its outcome file:

- **`resolved`** — verify the outcome's `head` is the PR's new head
  (`gh pr view <pr> --json headRefOid`); a mismatch is an escalation, not a merge. Post the
  success comment, then `gh pr ready --undo <pr>` unless the PR is already a draft or
  `--no-review` is on. The next pass sees a stale draft and `re_review` puts the new head
  through a fresh reviewer — nothing reconciled merges without that round. Notify, release the
  reconciler, keep the child worktree (`in-review` until the re-review/merge), and remove a
  transient reconciler worktree.
- **`irreconcilable`** — post the failure comment, which is what `pr_state.py` counts; after
  two, the PR parks on `conflict`. Do that row's filing and notification, keep the child
  worktree unread with the conflict in its comment, and leave the branch alone.
- **`error`, a missing file, a spent budget, or a `head` mismatch** — post the failure comment
  too, with what went wrong as its reason: every run that does not end in a verified push
  counts toward the cap, or a reconciler that always hangs is respawned by every later run.
  Then the worker rules: escalate, spawn nothing new. Keep the worktree for inspection.

An outcome that could not reconcile both sides' intent, or that fails the gate, is
`irreconcilable`, not a guess: the pump files the coupling and the human decides.

Notify once per PR per action, not on every pass. After any merge, fast-forward the main
checkout the same way as Step 3 (branch check included), so the integration pass and the
human's checkout carry the merged code. A failed ff-only is an escalation.

Re-run the pass after its own writes — a merge moves the queue to its next PR and puts the
rest behind, and a fresh `pr_state.py` read is what keeps the sequence deterministic rather
than remembered. When every PR reads `wait`, `queued`, or a parked action, the waits become the
CI-wait loop: poll on a ~2-minute cadence with a hard per-PR budget (~60 minutes of no
progress), then notify, mark the PR's worktree unread if it has one, and set that PR aside. A
queue head set aside on a spent budget parks the PRs queued behind it — report them with it.
CI waiting must never block spawning — Step 8's re-pump runs while PRs settle, and the next
pass reaps whatever went green.

The planner never classifies a PR outside the epic, with failing or absent checks, or under a
hold as `merge`; the pass never passes `--admin` and never force-pushes. Overriding the planner
is how the bounds fall off.

## Step 7 — Integration pass (`--human-review` only)

Only when this run delivered two or more PRs. Separate worker worktrees mean no tree ever held
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

This is a deliberate exception to Orca worktrees: the integration check hosts no agent, needs
no card, and is removed with `git worktree remove` as soon as it finishes. Then the quality gate
the union of changed files selects, run in `$INT` (table in `work-issue`'s REFERENCE — same
table, same rule). Sequential merges name the clashing pair; a gate failure names the culprit
pair. On failure, file the coupling — `hew search` per the primer's dedup sequence, then
`hew create --discovered-from <a> --discovered-from <b>` — and report `integration_failed` as
in work-issue's taxonomy. On pass, state it plainly: the independence the per-issue PRs assume
is now evidence. Nothing pushed, no PR off this branch; afterwards
`git -C "$MAIN" worktree remove --force "$INT"` and delete the local branch.

Autonomous mode has no throwaway branch: main itself is the integration surface, the merge
queue brings each PR up to date with the default branch just before it merges, and CI plus
the merge-time gate re-run is what catches cross-PR coupling — at merge time, on the tree that
actually ships, instead of on a replica.

## Step 8 — Re-pump, reconcile worktrees, stop

After each settled worker and each merge pass, return to Step 1 — the resolver re-reads the
tracker, merges unblock children between visits, and findings filed as children enter
`eligible` as their blockers clear (a finding's child is blocked by the PR's issue until the
merge closes it).

Before spawning, reconcile the Run's worktrees and tasks:

```bash
ORCA orchestration task-list --run "<run-id>" --json
ORCA orchestration worker-list --run "<run-id>" --json
ORCA worktree list --json
```

Every worktree whose comment carries `work-epic #<epic-n> · <run-id>` is this pump's, except the
coordinator's own worktree — that is the root, never a child to reap. For each child, reviewer,
or reconciler worktree:

- **live Task** — adopt it; do not spawn a duplicate.
- **settled Task with an outcome** — archive the outcome, apply Step 4's transition, release if
  it is somehow still live, and remove the transient worktree or keep the child per policy.
- **marker, no Task** — a crashed run's leftover. Report it; remove it only if it is clean, no
  terminal is live, and it has no linked open PR or held state. Never remove a worktree whose
  marker names a different Run.

On `--resume`, also drain the Run's mailbox before planning:
`ORCA orchestration check --run "<run-id>" --unread --json`, process every message, then
acknowledge it. A
worker_done from a crashed coordinator is a report to reconcile with the resolver, not a reason
to spawn again.

Then recover the review gap a crashed run can leave: for every child in `$OUTDIR/state.json`
with `state: "delivered"`, a `pr`, and no review entry — and `--no-review` off — spawn the
round-1 reviewer (Step 5) before planning. If the state file is lost, a PR with no review round is reported as
unreviewed — do not auto-review a PR another run may be handling. A review entry of `failed`
or `error` is an escalation, not a retry.

The pump stops when all of these hold: nothing can spawn (the resolver's `eligible` is empty,
or its `spawnBudget` is zero), no Task whose title starts `we-`, `wr-`, or `wc-` is in flight
and no `reconcile` is waiting for a free writer slot, every open PR is parked — `hold`, `escalate`, `conflict`,
`protected`, a `wait` that has spent its CI budget, `queued` behind a head that is one of
those, or a PR this Run did not deliver with no review round and no live reviewer (reported as
`unreviewed`) — and no terminal is `reclaimable`:

```bash
ORCA orchestration worker-list --run "<run-id>" --terminal-state reclaimable --json
```

Release or explicitly retain every settled terminal before reporting. A `wait` still inside its
budget is still moving; keep polling it rather than stopping around it. A stop with eligible
children and a zero budget is a full backlog of parked PRs — say so; it clears only when a
human unparks them. Under `--human-review`, a reviewed draft awaiting the human is parked by
definition — the skipped merge pass is the gate — and the integration pass is the last
automated step.

Leave the worktree board honest: every kept child worktree carries its gate in the comment and
`--unread` if it needs a human; every removed one is gone from the board. Then set the
coordinator's status:

```bash
ORCA worktree set --worktree "id:<coord-worktree-id>" \
  --comment "work-epic #<epic-n> · <run-id> · coordinator stopped: <reason>" \
  --workspace-status in-review --json
# add --unread when any escalation is outstanding
```

Report:

- **Run id**, objective, and coordinator worktree; the implementer pool, reviewer policy
  (`auto` or the explicit list), reconciler policy, and setup policy used.
- Per worker: issue, **implementer agent**, outcome, PR number, child worktree id/path/status
  (kept or removed), reviewer verdict, findings filed, and "large" when the resolver flagged it.
- Per PR: **implementer → reviewer(s)**, with the round number, so a mixed-agent run is
  auditable. Say "same-agent review" when the pool left no other reviewer.
- Per reviewer: PR, round, **reviewer agent**, worktree id (removed/kept), verdict.
- Per reconciler: PR, **reconciler agent**, worktree (child or transient), outcome, gate
  result, new head, and whether re-review was spawned.
- Per merge-pass action: PR, what was done (merged / updated / queued / reconciled / held /
  conflicted / protected).
- Per skip: number and reason (blocked/untriaged/claimed/in_review/stalled), from the
  resolver's last pass.
- `hew epic status <epic>` — the progress line the human reads.
- Remaining `eligible` count, `spawnBudget`, and open-PR count, so "stopped" is
  distinguishable from "drained" and a full backlog from an empty queue.
- Every retained worktree with its path and reason, and every escalation with its worktree
  comment/unread marker.

## Anti-patterns

- Sorting or filtering `hew list --epic` output yourself instead of running the resolver
- Merging on your own read of CI state instead of executing `pr_state.py`'s actions
- Spawning a worker for a child the resolver skipped — `in_review`, `stalled`, or `claimed`
  (the claim is the authority — let exit 3 arbitrate, never `--force`)
- Creating a second worktree for a child that already has one in this Run, or touching a
  worktree whose `work-epic` marker names another Run
- Treating a settled worker as a delivered issue without reading its outcome file
- Reading a findings file whose `status` is not `reviewed` as a clean review
- Reviewing without posting the round comment, or posting it without `reviewed-head:`
- Letting the implementer review its own PR when `--reviewers` offered a different agent —
  the point of the pool is a second point of view
- Silently substituting a different agent when a `worker-start` fails, or treating
  `orca account list` / `agent-context` as an availability check — neither proves an agent is
  installed, and the failed receipt names the agent that could not launch
- Using one agent for both roles when the pool has several, or reporting a mixed run without
  saying which agent implemented and which reviewed
- Spawning past a blocked worker instead of accounting it as used capacity
- Spawning past a zero `spawnBudget` because worker slots are free — slots bound agents, the
  budget bounds the backlog that goes stale
- Updating or merging a PR the planner `queued` — the queue is what keeps every merge on CI
  that saw current main
- `gh pr merge --admin`, merging with failing checks, or merging a PR the planner held
- Checking out a PR branch, or running the integration merges, in `$MAIN` — `update_branch` is
  `gh pr update-branch`; reviewers get a named review branch in their own worktree; reconcilers
  reuse the child or get a transient worktree
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
- Closing or releasing a Task, Dispatch, terminal, or worktree this Run did not create
- Marking a Task completed after `worker_done` — a valid settlement already does that
- Releasing a worker before reading and archiving its outcome, or removing its worktree while
  a terminal is live or the checkout is dirty
- Treating an absent `agentWait` as "not blocked" — absence means Orca never looked
- Driving workers with `terminal create/send/wait` or `agent launch` instead of `worker-start`
  and the orchestration verbs; those bypass Task/Dispatch ownership and settlement
- Putting worker outcomes outside the worker's own worktree, or committing them
- Deleting the local review branch while its reviewer is still reading it
- Marking a worktree `completed` or removing it before `gh pr merge` has succeeded — a merge
  that then fails leaves an open PR with no checkout and a card claiming it merged
- Passing `--delete-branch` while the child worktree still has the branch checked out
- Closing the epic because its children are done — report it; a human closes it
