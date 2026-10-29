---
name: work-epic
description: Burn through a hew epic or a set of issues end to end with Orca-managed worktrees and supervised agents — resolve the ready issues, create one Orca worktree per issue, start a supervised implementer running work-issue in it, have a different agent review each delivered PR and fix what it finds in that same session, file every finding as an issue for the paper trail, repair merge conflicts and red CI, and merge PRs once CI is green. Runs unattended and stops only for a decision a human has to make. Use whenever the user wants issues worked by orchestrating agents — "work on this epic", "drain epic 12", "work issues 21 22 25", "fix all the bugs in the parser", "orchestrate #42", "pump the epic and merge it". Not for a single issue (that goes to work-issue) and never for closing issues or the epic itself.
argument-hint: "Issue numbers, an epic number, or a description of the work (e.g. 'fix all the bugs in the importer'). Flags: --workers N (default 2), --dry-run, --resume"
---

# Work Epic

A set of issues, burned down: resolve the ready ones, create an Orca worktree per issue, start a
supervised implementer in it, review each delivered PR with a different agent that fixes what it
finds in the same session, repair conflicts and red CI, merge on green, and re-pump. This skill
orchestrates; it never implements, reviews, or fixes by hand.

**The roles are separate agents.** The implementer runs `work-issue`; the reviewer runs
`review-code` and then fixes what it found; the repairer resolves a conflict or a red CI run; the
coordinator is the agent running this skill. The reviewer is a **different** agent from the
implementer — a second point of view — and the fix happens in the session that found the problem,
so nothing has to be re-reviewed: a PR is reviewed once.

**Orca is the execution layer.** A Run is this pump's identity and inbox. Each issue is a Task and
a durable Orca worktree; each attempt is a Dispatch. The worktree — not an agent name or a
terminal handle — is the unit the pump creates, annotates, keeps, reviews and repairs in, and
finally removes. Orca's worktree metadata (issue link, PR link, status, comment, unread dot) is
the live board.

**Unattended, with a short list of reasons to stop.** The pump merges on CI green. It parks an
item and keeps draining everything independent of it, and it stops for a human only for the
decisions in [What stops the pump](#what-stops-the-pump). Everything else — a review finding it
can fix, a conflict, a red check — it handles itself.

**Hard gates.** The pump never closes an issue or an epic (the one exception: it closes a review
finding it filed after the reviewer fixed it), never force-claims, never answers a worker's
dialog, never edits code itself, and never merges a PR outside the scope it was given. Escalations
reach the human through the worktree's status, comment, and unread dot, and the final report.

> [!IMPORTANT]
> [REFERENCE.md](REFERENCE.md) carries the scripts' output schemas, the lifecycle and comment
> states, the worker, reviewer, and repairer prompts, the round and repair comments, the
> findings-filing flow, timeout budgets, the merge-pass command list, and the report format. Read
> it before the reaping step.

## Agents

The agents are fixed — a golden path, not a pool:

```text
IMPLEMENTER = opencode      # runs work-issue
REVIEWER    = claude        # runs review-code, then fixes what it found
REPAIRER    = opencode      # the implementer; repairs conflicts and red CI
```

They are the only place an agent id appears; to change one, edit this block. Both must load
skills by name, `work-issue` installed for the implementer and `review-code` for the reviewer,
and both must be able to read the work-issue skill directory (the quality-gate table). Model and
effort are whatever the agent's own Orca configuration uses. A failed `worker-start` names the
agent that could not launch; report it for that issue and never silently swap in another agent.

## The scripts

Spawn and merge decisions come from scripts, not from hew or gh JSON sorted in your head — a pump
that picks differently on each run cannot be reasoned about from its logs. Resolve them once
against this skill's own directory:

```bash
RESOLVE="<this skill's directory>/scripts/resolve_ready.py"
PRSTATE="<this skill's directory>/scripts/pr_state.py"
```

They are read-only (hew, git and gh reads, never writes) and decide nothing a human owns — they
filter, sort, size, and classify; the skill acts. `resolve_ready.py` is the only scheduler and
`pr_state.py` the only merge classifier. Both take the same scope, so `<scope>` below is the issue
numbers exactly as Step 0 settled them.

## Prerequisites

This skill drives Orca, so first prove it is running inside an Orca-managed terminal and worktree:

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
`orca-dev`, `orca-ide`, or `orca`). Substitute it before running; never hardcode `orca` on a Linux
host where that name is the screen reader.

The target repository must be registered in Orca and the coordinator's worktree must belong to it.
`worktree current` gives the `repoId`; `ORCA repo list --json` confirms the path. If the
resolver's `mainCheckout` is not a registered Orca repo, stop and tell the human to register it
(`ORCA repo add --path "$MAIN" --json`) — do not create worktrees in a repo Orca does not own.

`hew` on PATH and authenticated — exit code 4 from any `hew` command means run `gh auth login`,
and here that halts the whole pump as an `error`, not as an empty queue. The repository needs CI:
a PR with no checks reads as "CI has not reported yet" and is never merged.

The skills this pump drives must resolve where each role runs: `work-issue` (hew plugin) for the
implementer, `review-code` (critique plugin) for the reviewer, and raise-issues'
`findings_to_plan.py` in the coordinator.

The coordinator's worktree is the escalation surface. Prefer a dedicated Orca worktree for it: the
pump writes its `.work-epic/` scratch directory and status comment there. Prove it is writable
once at startup (Step 0); if the write fails, report it and stop. Orca has no push-notification
command: an escalation lands as the worktree's unread dot plus its comment and status, and as the
final report.

## Arguments

Strip flags; what remains is the scope.

- **Scope** — one or more issue numbers (`21 22 25`, `#21,#22`), an epic number (which stands for
  its children), or a description of the work. A description is settled in Step 0 before anything
  else happens.
- **`--workers N`** — cap on live writer workers (implementers and repairers), default 2. More
  than 3–4 only moves the bottleneck into the review-and-merge pipeline. Reviewers do not count
  against it. Open PRs plus workers in flight never exceed twice this: once the backlog is full the
  pump stops spawning and lets the merge pass drain, because every open PR drifts further behind
  main with each merge.
- **`--dry-run`** — run both planners, show the planned Run, Tasks, worktrees, and merge plan,
  touch nothing. No Run exists, so capacity is not read from Orca: assume every `--workers` slot is
  free and say so in the plan.
- **`--resume`** — pass through to the resolver to pick up this user's own claims that have
  neither a PR nor a pushed branch, bind the previous Run, adopt its live Tasks and worktrees,
  and drain its mailbox. Explicit instruction only.

There are no other flags. The merge method is squash, a finding at P1 or above that the reviewer
could not fix holds its PR, and conflicts are repaired — these are the policy, not options.

## What stops the pump

The pump halts for a human only when one of these is true, and says which in the report:

1. **An unfixed P1.** The reviewer could not fix a P1 safely — it needs a design decision, reaches
   outside the PR, or its fix failed the gate. It is filed open; the open finding holds the PR
   until the human closes it (after fixing the branch, or accepting the finding as is).
2. **A repair that failed twice.** A conflict or a red CI run that two repair attempts could not
   resolve — or a failure the repairer found is not the PR's fault (a flaky test, main already
   red).
3. **An outage.** Un-auth, a dirty tree where a clean one is required, a worker that errored, or
   a worker parked on a permission dialog or a question only a human can answer.
4. **A review that did not run.** A missing or unreadable outcome, or a status other than
   `reviewed`: an unreviewed PR is never merged and never read as clean.
5. **Protected.** Branch protection wants something the pump cannot give, typically an approving
   review.

The first, second, fourth and fifth *park* the item: its worktree is marked unread with the gate in
the comment, and the pump keeps draining everything independent of it. Only the third halts the
pump — finish reaping what is live, spawn nothing new, escalate. The pump ends when nothing else
can move, then reports every parked item as a decision needed.

## Step 0 — Settle the scope, bind the Run

**A described scope.** If the arguments are a description rather than numbers ("fix all the bugs
in the importer"), turn it into issue numbers read-only, then confirm before doing anything:

- Search with `hew search <terms>` and `hew list --label <area>` — never `hew triage`.
- Show the user the candidate list (number, title, priority, type, blockers) and what the run will
  do with it: implement each, review each with a different agent, fix what the review finds, merge
  on CI green.
- Wait for the user's go-ahead. They may drop or add issues. The confirmed list is the scope for
  the whole run; the pump never widens it. Epic and issue-number scopes are explicit and need no
  confirmation.

**The Run.** The Run scopes every Task, Dispatch, and mailbox read. Bind it before planning so a
resumed run reuses the same identity.

```bash
ORCA orchestration run-create --objective "work-epic #<n> #<n> …" --json
```

Read `result.run.id`. On `--resume`, rebind the previous Run instead of creating one, and stop on
any ambiguity rather than guess between two live pumps
([REFERENCE.md](REFERENCE.md#run-binding-and-resume)).

Prepare the pump's scratch directory in the coordinator's own worktree, so it is writable by
whichever agent is coordinating and survives a resume:

```bash
OUTDIR="<coord-worktree-path>/.work-epic/coordinator"
mkdir -p "$OUTDIR"
```

It is pump scratch, not a deliverable: do not commit it, and do not point a spawned agent at it.
Workers, reviewers, and repairers also write their outcome files into a `.work-epic/` directory in
their own worktrees. Keep every such directory out of `git status` by listing it in the
repository's shared exclude file, which every worktree reads and which is never committed:

```bash
EXCL="$(git -C "<coord-worktree-path>" rev-parse --path-format=absolute --git-path info/exclude)"
grep -qxF '.work-epic/' "$EXCL" || echo '.work-epic/' >> "$EXCL"
```

Record the coordinator's worktree id, repo id, path, and the Run id in `$OUTDIR/state.json`
(schema in [REFERENCE.md](REFERENCE.md#pump-state-file)). Then set the coordinator's status line:

```bash
ORCA worktree set --worktree "id:<coord-worktree-id>" \
  --comment "work-epic · <run-id> · coordinator starting" \
  --workspace-status in-progress --json
```

Do not change the coordinator's display name, issue link, PR link, or parent lineage; that
worktree may be the human's own. Under `--dry-run`, create no Run, scratch directory, exclude
entry, or comment: print the objective, each eligible issue with its `we-` task and worktree name,
and the merge plan; stop after Step 1 and Step 6's plan.

## Step 1 — Resolve the fan-out plan

```bash
uv run --no-project "$RESOLVE" <scope> --workers <workers> [--resume]
# add --repo owner/name only if the user said so
```

- **Exit 1** — relay the stderr message and stop.
- **Exit 0** — `eligible` is the spawn order (priority-sorted, oldest tie-break), `skipped` names
  every open issue left behind with its reason, `counts` sums them. `mainCheckout` is the primary
  worktree and `defaultBranch` the origin default (schema:
  [REFERENCE.md](REFERENCE.md#resolver-output)).

An `eligible` issue with `large: true` exceeds work-issue's sizing rule. Spawn it as usual, but
name it in the report as large, so a human can see why it ran long or stalled.

`mainCheckout` is the fetch/fast-forward anchor, not the spawn cwd: Orca creates each child
worktree from `origin/<default>` explicitly, so the human's main checkout may be on any branch.
The resolver already keeps out what this pump has touched: an issue with an open PR is
`in_review`, one whose worker failed (branch pushed, no PR) is `stalled`, and one claimed by you
with neither is `claimed` unless `--resume` was given. Spawn only from `eligible`.

An empty `eligible` is meaningful either way: all-blocked, all-untriaged, all-claimed,
all-in-review, or finished. Say which, from `counts` — and when every issue in an epic's scope is
closed, escalate that a human should close the epic. Do not close it here.

## Step 2 — Capacity and existing worktrees

Capacity is Orca state, not a guess:

```bash
ORCA orchestration task-list --run "<run-id>" --json
ORCA orchestration worker-list --run "<run-id>" --json
```

Writers are Tasks whose title starts `we-` or `wc-`, whose status is `dispatched`, **and** whose
Dispatch is still live. Reviewers (`wr-`) don't count. A Task left `dispatched` with an `exited`
worker is a stall to reap, not capacity. Open slots are the smaller of `--workers` minus live
writers and the resolver's `spawnBudget`. If reaping hasn't freed a slot, wait on the live set
(Step 4); if the budget is zero, spawn nothing and go to the merge pass (Step 6) — the backlog
drains before it grows.

Before creating anything, ask Orca whether this issue already has a worktree:

```bash
ORCA worktree show --worktree "issue:<n>" --json
```

- **A worktree with this Run's marker** — adopt it. If its Task is live, wait on it; if settled,
  go to Step 4's outcome handling. Never create a second worktree for the same issue in a Run.
- **A `work-epic` worktree with a different run marker** — another pump owns this issue. Skip it
  and report the worktree id; do not touch, release, or remove it.
- **A worktree with no `work-epic` marker** — a human or another tool is using it for this issue.
  Treat the issue as claimed by someone else, skip it, and say why.
- **None** — free to spawn, subject to the resolver and the slot budget.

**The marker.** Every worktree the pump creates carries one comment line:
`work-epic · <run-id> · we-<n> · <agent> · <state>`. The later steps name only the `<state>`; the
states, their `--workspace-status`, and when `--unread` is raised are the table in
[REFERENCE.md](REFERENCE.md#links-status-and-unread). Keep the first four tokens verbatim when
rewriting the state — the sweep and resume read them. The issue link is the durable selector: set
`--issue <n>` right after creating a worktree, so `issue:<n>` works on every later run.

Ownership is Run-scoped: **never act on a Task, Dispatch, terminal, or worktree with a marker from
a different Run**. Run scoping is not a lock either: two orchestrators on the same `gh` login only
get `hew start` exit 5 ("the claim is yours"), so do not run two pumps over the same issues.

## Step 3 — Create worktrees and start implementers

`$MAIN` and `$DEFAULT` come from the resolver. Bring the main checkout's view of origin up to date
once per run:

```bash
git -C "$MAIN" fetch origin
```

If `$MAIN` is on `$DEFAULT`, fast-forward it so the human's checkout sees what has merged:

```bash
test "$(git -C "$MAIN" symbolic-ref --short HEAD)" = "$DEFAULT" &&
  git -C "$MAIN" merge --ff-only "origin/$DEFAULT"
```

If it is on another branch, skip the ff and say so in the report — never switch the human's
checkout. A failed ff-only is an escalation; never rebase or reset it.

Create the worktree and the supervised worker in one call:

```bash
ORCA orchestration worker-start \
  --spec "<worker prompt from REFERENCE.md, pointing at
    work-issue <n> --non-interactive --json '.work-epic/we-<n>.json'>" \
  --task-title "we-<n> · opencode" \
  --worktree new-child \
  --repo "id:<repo-id>" \
  --name "we-<n>" \
  --display-name "#<n> <short title>" \
  --base-branch "origin/$DEFAULT" \
  --comment "work-epic · <run-id> · we-<n> · opencode · worker started" \
  --setup inherit \
  --agent opencode \
  --json
```

`worker-start` is the only spawn path; `agent launch`, `worktree create --agent`,
`orchestration dispatch`, and direct terminal commands bypass Task/Dispatch settlement
([REFERENCE.md](REFERENCE.md#orcas-model-and-what-the-pump-uses)). `new-child` nests the worktree
under the coordinator in Orca's sidebar. Read the start receipt: the `taskId`, the `dispatchId`,
the worktree id/path, the `branch` Orca created, and the launch outcome. Never predict a path; if
an older host omits the worktree id, resolve it from `ORCA worktree list --json` by the unique
comment marker. Then link the issue and mark the card live:

```bash
ORCA worktree set --worktree "id:<child-worktree-id>" \
  --issue <n> --workspace-status in-progress --json
```

Record `{task, dispatch, worktree, path, branch, state: "running"}` for the issue in
`$OUTDIR/state.json`. Record the receipt `branch` the same way for every worktree the pump starts
— it is never predicted, because removal leaves it behind
([REFERENCE.md](REFERENCE.md#lifecycle-and-cleanup)).

The worker runs `work-issue` in its own checkout; `work-issue` may create its conventional issue
branch (`fix/<n>-…`) inside the Orca worktree, which is then the issue's home for the rest of its
life — the reviewer and the repairer work in it too. The outcome file is written only at the end,
after the commit and push, into `.work-epic/` so it never dirties the tree during `work-issue`'s
clean-tree checks. No worker needs access to `$OUTDIR`.

Submit prompts without waiting for them to finish; `worker-start` returns when the worker is
ready. A spawn that fails still owns the terminal it created: read `failedStage`,
`residualResources`, and the recovery commands from the receipt, release that terminal, and decide
whether the worktree is safe to remove (clean and agentless: remove; otherwise keep and report).
One failed spawn costs only that issue — continue with the rest and report it.

## Step 4 — Reap settled workers

Wait on the Run's mailbox, not on each terminal:

```bash
ORCA orchestration check --run "<run-id>" --wait \
  --types "worker_done,escalation,question" --timeout-ms <budget> --json
```

The check returns the Run's oldest unacknowledged FIFO batch. Process **every** message in it, then
acknowledge the whole batch with
`ORCA orchestration check --run "<run-id>" --ack <delivery-id> --json` and wait again — a bound Run
replays a Delivery until it is acknowledged. Heartbeats and status messages are acknowledgements,
not work; `--wait` also emits `_keepalive` lines on stderr, which are not messages. Budgets are in
[REFERENCE.md](REFERENCE.md#timeout-budgets).

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
for a failed, stopped, or unknown attempt; do not improvise cleanup from a timeout. A valid
settlement already completes the Task, so never mark one completed after `worker_done`.

For a settled worker, read its outcome file from the child worktree before doing anything else.
The `worker_done` message's `--outcome` is a hint; the file is the authority. If they disagree,
report the mismatch and treat the file's status. A missing or unreadable file is re-checked for
60–120s on a few-seconds cadence before it becomes an `error`: the write can trail the state
change. Past that grace a missing file is an `error` all the same — never an inference from
terminal output. Then:

| outcome | action here |
|---|---|
| `delivered` | archive the outcome to `$OUTDIR/outcomes/we-<n>.json`, then remove it from the worktree so no stale outcome sits in the checkout the reviewer will reuse; note the PR; set the worktree `--pr <pr> --workspace-status in-review`, state `PR #<pr> delivered; review pending`; release the worker; keep the worktree; start the reviewer (Step 5) |
| `failed` | report; leave the issue claimed; do **not** respawn it — its pushed branch makes it `stalled` on every later resolver pass. Keep the worktree, mark it `--unread`, state `failed: <reason>`; release the worker |
| `no_ready_work` / `not_eligible` | report verbatim, with the skipped counts — a queue of issues claimed by a dead agent reads as drained and hides the stall; release the worker and remove the clean, workless worktree |
| `error` | **halt the pump**: finish reaping what's live, spawn nothing new, escalate. Keep the worktree, mark it unread, state `error: <reason>`, release the worker |

Release a settled worker with:

```bash
ORCA orchestration worker-release --dispatch "<dispatch-id>" --json
```

Release archives the terminal output and closes only that Dispatch's terminal; the worktree stays.
Never release before the outcome is read and archived. Never release because of a timeout, TUI
idle, heartbeat, question, or escalation — those are still work or human gates. If a release
reports `release_unknown`, follow its exact recovery action; if it reports `release_pending`,
retry that same release later; if it reports `retained`, leave it alone and report why.

A worker that is parked on a permission prompt or a question only a human can answer shows up in
`worker-show`:

```bash
ORCA orchestration worker-show --dispatch "<dispatch-id>" --json
ORCA orchestration worker-read --dispatch "<dispatch-id>" --source auto --json
```

A non-null `observation.agentWait` names a worker parked on a prompt only a human can answer, with
the evidence that proved it. Throw the escalation once per Dispatch — worktree `--unread`, state
`BLOCKED: <what>` — and **never answer it**. An absent `agentWait` means Orca never looked (older
host, unverifiable identity, unreadable pane), not that the worker is free; keep inspecting or
waiting. A soft/idle agent still producing output is not a dialog: re-enter the wait loop under
its budget. A `question` Delivery is the same gate from the other side: report it with its message
id so the human can `ORCA orchestration reply --id <message-id> --body "..."`; the pump never
replies. The worker stays live and counts against `--workers` until the human or the worker
settles it.

Reviewers and repairers settle by the same rules: a reviewer's outcome lives in
`.work-epic/wr-<pr>.json`, a repairer's in `.work-epic/wc-<pr>.json`. Archive, release, and leave
the worktree for the next step. Never remove a worktree that still has a live terminal, a blocked
worker, uncommitted work, or a parked PR. Keep it, mark it unread, and report its path.

## Step 5 — Review and fix, in one session

One reviewer per delivered PR, started as soon as the worker is reaped. The reviewer works in the
**issue's own worktree** — the implementer has finished and been released, so the checkout is free
— and it does the whole job there: review the PR, fix what it can, gate, and push. If a `wr-<pr>`
Task is already live for the PR, adopt it and wait — never start a second one. A PR this Run holds
no worktree for (delivered by an earlier run or another orchestrator) is reported as `unreviewed`,
not reviewed here.

```bash
ORCA worktree set --worktree "id:<child-worktree-id>" \
  --comment "work-epic · <run-id> · we-<n> · opencode · reviewing by claude" --json
ORCA orchestration worker-start \
  --spec "<reviewer prompt from REFERENCE.md>" \
  --task-title "wr-<pr> · claude" \
  --worktree "id:<child-worktree-id>" \
  --agent claude \
  --json
```

The child's checkout must be clean (`git status --porcelain`) first; a dirty checkout is an
escalation, not a stash. The prompt fast-forwards the checkout to the PR head (a server-side
`update-branch` may have moved it), runs `review-code` over the branch-vs-default scope — exactly
this PR's diff — and then, for each finding at P2 or above (a P0 files as P1), makes the smallest
fix inside the PR's own files, runs the quality gate, commits, and records `fixed` and `fixedIn` on
that finding. A finding it cannot fix safely stays unfixed with a reason. P3s are left alone. It
pushes once, to the PR's own ref, never with force.

Reap the reviewer like a worker — same `check --wait` batch, same `agentWait` gate — and release it
as soon as its file is read. Archive the file to `$OUTDIR/outcomes/wr-<pr>.json` and remove it from
the worktree. Read it before anything else:

- **Missing or unreadable** — escalate; an unread review is not a clean review.
- **`status` other than `reviewed`** (`no_scope`, `error`) — escalate with its `reason`. The review
  did not run, and its empty `findings` array means nothing; reading it as clean merges an
  unreviewed PR.

A `reviewed` file always produces exactly one **review-round comment** on the PR (template in
[REFERENCE.md](REFERENCE.md#review-round-comment)), clean or not: it carries the marker
`pr_state.py` reads as "reviewed". A PR with no round comment is one the planner treats as
unreviewed and never merges.

**File first, close second, comment last.** The round comment is what makes a PR mergeable, and an
open P1 finding is what holds it. Posting the comment first leaves a window — a crashed pump, a
failed `hew apply` — where the planner sees a review and no blocker and merges a PR whose unfixed P1
was never filed. Filed first, the worst a crash leaves is a PR with no round, which the planner
never merges; the review-key dedup keeps a repeat filing from duplicating issues. So:

1. **File** every finding at P2 or above through
   `findings_to_plan.py --reviewed-issue <n> --reviewed-pr <pr> --at-or-above P2`, dry-run, then
   `hew apply` (flow and dedup rules: [REFERENCE.md](REFERENCE.md#findings-filing)). Always through
   the converter — hand-composed bodies lose the `review-of:` marker the hold keys on, and the
   `fixed-in:` line the close keys on. Findings are filed with no parent: they are the paper trail
   of this review, not part of the scope. P3s are not filed; the round comment carries them. A
   filing that fails is an escalation — post no round comment over it.
2. **Close** the findings the reviewer fixed: every open issue carrying this PR's `review-of:` and
   a `fixed-in:` line is closed `--completed` with the commit as its reason. Only fixed findings
   carry `fixed-in:`, so an unfixed one stays open. The command is in
   [REFERENCE.md](REFERENCE.md#findings-filing); it is safe to repeat.
3. **Post the round comment**, with the filed issues' numbers and which were fixed.

Then decide what the PR does next. There is nothing to un-ready or re-review:

- **No unfixed P1** — the PR proceeds. Set the worktree to the state
  `reviewed by claude; <n> fixed, <m> filed open; ready to merge`. The merge pass readies it and
  merges it on green.
- **An unfixed finding at P1 or above** — the PR stays a draft and the finding is open, which is
  what holds it. Mark the worktree `--unread` with state
  `HOLD: P1 finding #<issue> not fixed (reviewer claude)`. This is a decision for the human; the
  pump parks the PR and keeps going.

Record the reviewer's verdict (`clean`, `fixed`, `hold`, or `escalated`) and the filed issues in
the issue's state entry.

## Step 6 — Merge pass

Every open PR in scope goes through `pr_state.py` — not only this run's deliveries; PRs delivered
by earlier runs or other orchestrators are merged by the same plan or left alone:

```bash
uv run --no-project "$PRSTATE" <scope> [--reviewing <pr>]... [--repairing <pr>]...
```

Pass one `--reviewing <pr>` for every `wr-<pr>` Task in this Run that is still live, and one
`--repairing <pr>` for every live `wc-<pr>`. GitHub cannot see an agent at work, and the planner
runs on every pass while one does: without the lists it would start a second repairer, merge main
out from under the first, or treat a review in progress as finished. Read the live sets from
`task-list`/`worker-list`, not from a remembered list.

Execute each PR's `action` exactly as classified — the planner is the decision, the pass is the
hands (decision order, commands, and CI-wait budgets in
[REFERENCE.md](REFERENCE.md#merge-pass-output) and
[REFERENCE.md](REFERENCE.md#merge-pass-commands)):

| action | what the pass does |
|---|---|
| `merge` | `gh pr merge --squash`; only once it succeeds, finish the issue's worktree and delete the branches (see "Merge order"); fast-forward main |
| `mark_ready` | `gh pr ready` — a draft's merge state reads `DRAFT` until then, hiding `BEHIND` or `BLOCKED`; the next pass sees the real state |
| `update_branch` | `gh pr update-branch <pr>` — GitHub merges the default branch in server-side; a failure re-runs the planner, whose next pass sees `DIRTY` and hands it to `repair` |
| `repair` | start a repairer (`wc-<pr>`) — see "Repairing" |
| `queued` | nothing; it waits its turn behind `queueHead` or behind the repair head, and spends no CI budget of its own |
| `conflict` | file the coupling (`hew search` first, then `hew create --discovered-from <n>`), mark the worktree unread with state `CONFLICT`, and leave the PR — repair attempts are spent or an open finding owns the PR |
| `ci_failed` | mark the worktree unread with state `CI FAILED: <failing check>`; repair attempts are spent. Leave the PR |
| `hold` | mark the worktree unread with state `HOLD: <severity> finding #<issue>`; the human lifts it by closing the finding — once fixed on the branch, or accepted as is. Fixing the branch alone does not lift it, and the pump never un-holds |
| `protected` | unread, state `PROTECTED: <what branch protection wants>` (typically an approving review) |
| `wait` | nothing; it rolls into the CI-wait loop |

Notify (unread dot plus comment) once per PR per action, not on every pass.

**The merge queue.** At most one PR moves toward main per pass — the planner's `queueHead`, the
only PR that gets `merge` or `update_branch`. Every merge puts every other open PR behind again, so
updating them side by side spends a CI run each on a result the next merge throws away, and
merging two from one plan lands the second on CI that never saw the first. So every merge is of a
PR whose CI ran on current main, whatever the repository's protection settings (how "behind" is
counted: [REFERENCE.md](REFERENCE.md#merge-pass-output)). Drafts and held PRs are never updated.

**Merge order and the worktree.** The worktree is the card the human has been watching; it is also
a checkout of the branch being merged, so it outlives the merge call. Merge first, and without
`--delete-branch` — gh would try to delete a local branch that is still checked out in that
worktree. A merge that fails changes nothing here: the card, the checkout, and
`$OUTDIR/state.json` still describe an open PR, and the planner re-classifies it on the next pass.
Only once the merge has succeeded, finish the issue: set it `completed` (state `merged`), record
the merge in `$OUTDIR/state.json`, remove the worktree if clean, then delete the remote branch, the
local PR branch, and Orca's own branch — the exact commands, and why each branch delete is shaped
as it is, are in [REFERENCE.md](REFERENCE.md#merge-pass-commands). If the worktree is dirty or
removal fails, keep it, mark it unread, report the path, and run only the remote delete. A failure
in branch cleanup after a successful merge is reported, never an escalation. After any merge,
fast-forward the main checkout the same way as Step 3 (branch check included).

**Repairing.** The planner emits at most one `repair` — its `repairHead` — and only while
`queueHead` is `null`: a merge landing mid-repair would re-conflict it. It means either a conflict
with the default branch or a red CI run, and the repairer handles both with one contract. Start
`wc-<pr>` in the issue's own worktree, which the Run still holds:

```bash
ORCA orchestration worker-start --task-title "wc-<pr> · opencode" \
  --worktree "id:<child-id>" --agent opencode \
  --spec "<repairer prompt from REFERENCE.md>" --json
```

Resolve the worktree from the PR's `issue` in `$OUTDIR/state.json` or
`ORCA worktree show --worktree "issue:<n>"`. Check it is clean first; a dirty checkout is an
escalation. A PR this Run holds no worktree for is not repaired — treat its `repair` as `conflict`
and file and escalate it. While the repairer runs, set the worktree's state to
`repairing PR #<pr> (opencode)`. The prompt fast-forwards to the PR head, merges
`origin/$DEFAULT` when there is a conflict, diagnoses the failing check when CI is red, fixes it,
gates, and pushes. Archive its outcome to `$OUTDIR/outcomes/wc-<pr>.json` and remove it from the
worktree before the checkout is used again. Then, from the file:

- **`resolved`** — verify the outcome's `head` is the PR's new head
  (`gh pr view <pr> --json headRefOid`); a mismatch is an escalation, not a merge. Post the success
  comment, notify, release the repairer, keep the worktree. The PR is **not** un-readied and not
  re-reviewed: CI on the new head is the check, and the next pass reads it.
- **`blocked`** — the repairer found something it should not fix: an irreconcilable conflict, a
  failing check that is not caused by this PR, a gate it cannot pass. Post the failure comment,
  which is what `pr_state.py` counts; after two, the PR parks on `conflict` or `ci_failed`. Keep the
  worktree unread with the reason in its comment, and leave the branch alone.
- **`error`, a missing file, a spent budget, or a `head` mismatch** — post the failure comment too:
  every run that does not end in a verified push counts toward the cap, or a repairer that always
  hangs is respawned by every later run. Then the worker rules: escalate, spawn nothing new.

Comment templates: [REFERENCE.md](REFERENCE.md#repair-comments). A repair is a fast-forward push —
never a rebase, never a force-push.

When every PR reads `wait`, `queued`, or a parked action, the waits become the CI-wait loop: poll on
a ~2-minute cadence with a hard per-PR budget (~60 minutes of no progress), then notify, mark the
PR's worktree unread, and set that PR aside. A queue head set aside on a spent budget parks the PRs
queued behind it — report them with it. CI waiting must never block spawning — Step 7's re-pump
runs while PRs settle, and the next pass reaps whatever went green.

The planner never classifies a PR outside the scope, with failing or absent checks, or under a hold
as `merge`; the pass never passes `--admin` and never force-pushes. Overriding the planner is how
the bounds fall off.

## Step 7 — Re-pump, sweep, stop

After each settled worker and each merge pass, return to Step 1 — the resolver re-reads the tracker,
and merges unblock issues between visits.

Before spawning, run the resume-and-orphan sweep
([REFERENCE.md](REFERENCE.md#resume-and-orphan-sweep)): every worktree whose comment carries
`work-epic · <run-id>`, except the coordinator's own, is this pump's to adopt, settle, or report —
and never remove a worktree whose marker names a different Run. Re-run the close step from Step 5
for every reviewed PR: it is idempotent, and it finishes a close a crash interrupted.

On `--resume`, also drain the Run's mailbox before planning:
`ORCA orchestration check --run "<run-id>" --unread --json`, process every message, then acknowledge
it. A `worker_done` from a crashed coordinator is a report to reconcile with the resolver, not a
reason to spawn again.

Then recover the review gap a crashed run can leave: for every issue in `$OUTDIR/state.json` with
`state: "delivered"`, a `pr`, and no review entry, start the reviewer (Step 5) before planning. If
the state file is lost, a PR with no review round is reported as unreviewed — do not auto-review a PR
another run may be handling. A review entry of `failed` or `error` is an escalation, not a retry.

The pump stops when all of these hold: nothing can spawn (the resolver's `eligible` is empty, or its
`spawnBudget` is zero), no Task whose title starts `we-`, `wr-`, or `wc-` is in flight and no
`repair` is waiting for a free writer slot, every open PR is parked — `hold`, `conflict`,
`ci_failed`, `protected`, a `wait` that has spent its CI budget, `queued` behind a head that is one
of those, or a PR this Run did not deliver with no review round (reported as `unreviewed`) — and no
terminal is `reclaimable`:

```bash
ORCA orchestration worker-list --run "<run-id>" --terminal-state reclaimable --json
```

Release or explicitly retain every settled terminal before reporting. A `wait` still inside its
budget is still moving; keep polling it rather than stopping around it. A stop with eligible issues
and a zero budget is a full backlog of parked PRs — say so; it clears only when a human unparks
them.

Leave the worktree board honest: every kept worktree carries its gate in the comment and `--unread`
if it needs a human; every removed one is gone from the board. Then set the coordinator's status:

```bash
ORCA worktree set --worktree "id:<coord-worktree-id>" \
  --comment "work-epic · <run-id> · coordinator stopped: <reason>" \
  --workspace-status in-review --json
# add --unread when any decision is outstanding
```

Report in the format in [REFERENCE.md](REFERENCE.md#report-format). Always include: the Run id and
scope; per issue, the outcome, PR, and worktree (kept or removed), "large" when flagged; per PR, the
review's result — what the reviewer fixed, what it filed open; each repair's gate result and new
head; each merge-pass action; each skip with its reason; `hew epic status` when the scope is an
epic; the remaining `eligible` count, `spawnBudget`, and open-PR count, so "stopped" is
distinguishable from "drained"; and **the decisions needed**: every parked item, its worktree
comment, and what the human has to decide.

## Anti-patterns

The steps above state each rule once; these are the ones that are easiest to break by improvising:

- Sorting or filtering `hew list` output yourself, or merging on your own read of CI state, instead
  of executing the scripts' output
- Spawning for an issue the resolver skipped — the claim is the authority; let exit 3 arbitrate,
  never `--force`
- Widening the scope mid-run, or working a finding issue the run filed: findings are fixed by the
  reviewer in its own session or handed to the human, never picked up by a later session
- Re-reviewing a PR whose head moved. A PR is reviewed once; the reviewer's fixes, a repair, and a
  human's edits are checked by the gate and by CI
- Treating a settled worker as a delivered issue without reading its outcome file, or a findings
  file whose `status` is not `reviewed` as a clean review
- Marking a finding fixed that the reviewer did not fix, or closing an open finding to lift a hold —
  only the human lifts a hold
- Using the implementer as the reviewer, or silently substituting a different agent when a
  `worker-start` fails
- `gh pr merge --admin`, merging with failing checks, or merging a PR the planner held, queued, or
  has a live reviewer on
- Checking out a PR branch in `$MAIN`; fast-forwarding `$MAIN` when it is not on the default branch
- Marking a worktree `completed` or removing it before `gh pr merge` has succeeded, or passing
  `--delete-branch` while the worktree has the branch checked out
- Closing the epic because its children are done — report it; a human closes it
