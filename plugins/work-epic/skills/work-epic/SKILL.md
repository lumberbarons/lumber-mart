---
name: work-epic
description: Fan a hew epic out to herdr-managed agents — resolve the epic's ready children deterministically, spawn one worker agent per child running work-issue, spawn a reviewer agent running review-code on each resulting PR, and stop at the human merge gate. Use whenever the user wants an epic worked by orchestrating agents rather than by hand — "work on this epic", "drain epic 12", "orchestrate #42", "fan out this epic to workers", "spawn agents on the epic". Not for a single issue (that goes to work-issue) and never for closing, merging, or re-triaging — those stay with the human.
argument-hint: "Epic number. Flags: --workers N (default 2), --kind opencode|codex (default opencode), --dry-run, --no-review"
---

# Work Epic

One epic, pumped: resolve its ready children, spawn a herdr agent per child, review each
delivered PR with a second agent, and stop. This skill orchestrates; it never implements,
reviews-by-hand, merges, or closes. The merge gate stays human — the reviewer stage pre-digests
PRs so the human's queue says more than "draft".

> [!IMPORTANT]
> [REFERENCE.md](REFERENCE.md) carries the resolver's output schema, the worker and reviewer
> prompt templates, naming rules, timeout budgets, and the report format. Read it before the
> reaping step.

## The script

Spawn decisions come from a script, not from hew JSON sorted in your head — the same discipline
work-issue applies to its own selection, because a pump that picks differently on each run cannot
be reasoned about from its logs. Resolve it once against this skill's own directory:

```bash
RESOLVE="<this skill's directory>/scripts/resolve_ready.py"
```

It is read-only (two `hew` reads, one `gh api user` read), and it never decides anything a human
owns — it filters, sorts, and sizes; the skill acts.

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
- **`--workers N`** — cap on live worker agents, default 2. More than 3–4 only moves the
  bottleneck into the human's review queue; raise it on explicit instruction, not initiative.
- **`--kind opencode|codex`** — worker and reviewer kind, default opencode. opencode is preferred
  because `work-issue` and `review-code` resolve as skills there; codex is driven by pointing the
  prompt at the skill files (see [REFERENCE.md](REFERENCE.md)).
- **`--dry-run`** — run the resolver, show the spawn plan and skip reasons, touch nothing.
- **`--no-review`** — workers only; delivered PRs stay draft without a reviewer pass.

## Step 1 — Resolve the fan-out plan

```bash
uv run --no-project "$RESOLVE" <epic-n>   # add --repo owner/name only if the user said so
```

- **Exit 2 "not an epic"** — stop and hand it to `work-issue`; orchestration over one issue is
  overhead with no payoff.
- **Exit 1** — relay the stderr message and stop.
- **Exit 0** — `eligible` is the spawn order (priority-sorted, oldest tie-break), `skipped`
  names every open child left behind with its reason, `counts` sums them. Under `--dry-run`,
  print the plan and stop here.

An empty `eligible` is meaningful either way: all-blocked, all-untriaged, all-claimed, or a
finished epic. Say which, from `counts`, and — for a finished epic where every child is closed —
escalate that a human should close it, exactly as `work-issue` requires. Do not close it here.

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

For each eligible child up to the open slots:

```bash
# opencode workers: spawn in the main checkout; the opencode-worktree plugin isolates the session
herdr workspace create --cwd "$PWD" --label "we-<n>" --no-focus
# codex workers: explicit isolation, since there is no plugin catching them
herdr worktree create --cwd "$PWD" --label "we-<n>" --no-focus
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
herdr workspace create --cwd "$PWD" --label "wr-<pr>" --no-focus
herdr agent start wr-<pr> --kind <kind> --pane <pane-id>
herdr agent prompt wr-<pr> "<reviewer prompt>"
```

The reviewer checks out the PR head itself (the prompt says how), so `review-code`'s default
branch-vs-default scope *is* the PR diff. Consume the findings file:

- **Missing/unreadable findings file** — escalate; an unread review is not a clean review.
- **Clean, or P3-only** — `gh pr ready <pr>`: draft→ready is the pump's "agent-reviewed,
  awaiting human" signal. Notify.
- **Any P1/P2** — post the findings as a PR comment (format in [REFERENCE.md](REFERENCE.md)),
  leave the PR a draft, notify the human. **Never fix findings into the PR** — that is
  unreviewed scope in something a human is about to read, same rule work-issue applies to
  discovered work.

## Step 6 — Integration pass

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

## Step 7 — Re-pump and stop

After each settled worker, return to Step 1 — the resolver re-reads the tracker, and merges by
the human unblock children between visits. The pump stops when the resolver's `eligible` is empty
**and** no `we-*` worker is still in flight. Then report:

- per worker: issue, outcome, PR number, reviewer verdict
- per skip: number and reason (blocked/untriaged/claimed), from the resolver's last pass
- `hew epic status <epic>` — the progress line the human reads
- remaining `eligible` count, so "stopped" is distinguishable from "drained"
- every escalation raised, with its notification

Never `hew close`. Never `hew start --force`. Never merge a PR. Never click through a worker's
dialog. Never close a finished epic. Each of those is a human gate the pump keeps — the pump
accelerates everything up to them, not through them.

## Anti-patterns

- Sorting or filtering `hew list --epic` output yourself instead of running the resolver
- Spawning a worker for an issue already claimed (the resolver's cheap pre-filter; the claim is
  the authority — let exit 3 arbitrate, never `--force`)
- Treating a settled agent as a delivered issue without reading its outcome file
- Spawning past a `blocked` worker instead of accounting it as used capacity
- `gh pr merge` or any auto-merge — the human gate is the design, not friction
- Auto-fixing reviewer findings into a PR, or flipping a draft to ready with P1/P2 findings
- Running the integration branch's merges all-at-once (octopus) — that erases the pair-naming
- Closing workspaces or agents this run did not create
- Closing the epic because its children are done — report it; a human closes it
- Putting outcome files directly under `/tmp` instead of `${TMPDIR:-/tmp}/opencode` — every agent
  that touches them prompts for external directory access
