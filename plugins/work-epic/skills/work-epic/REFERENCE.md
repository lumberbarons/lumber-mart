# Reference

Resolver and merge-pass schemas, the Orca Run/Task/worktree lifecycle, prompt templates, the
review-round comment, findings filing, naming, timeout budgets, and the report format for
`work-epic`.

## Agent roles and assignment

The pump is explicitly multi-agent. Each role can be a different agent id:

| Role | What it runs | Default | Chosen by |
|---|---|---|---|
| **Coordinator** | This skill: plans, spawns, reaps, merges, reports | The agent the human started the session in | The human; the pump never spawns a coordinator |
| **Implementer** | `work-issue` in the child's worktree | `opencode` | `--implementers`, deterministic by issue |
| **Reviewer** | `review-code` in a transient review worktree | `auto`: the implementer pool minus the implementer | `--reviewers`, deterministic by PR and round |
| **Reconciler** | The conflict-reconciliation contract in the child's worktree | The PR's implementer | `--reconciler` |

`--implementers`, `--reviewers`, and `--reconciler` accept only `opencode`, `codex`, and
`claude` because those are the prompt adapters this skill ships. `all` expands to
`opencode,claude,codex`. An unknown id is a usage error, not a silent fallback.

### Deterministic assignment

The assignment must be stable across runs; a pump that reviews the same PR with a different
agent each time cannot be reasoned about from its logs.

```
implementer(n)        = IMPLEMENTERS[n % len(IMPLEMENTERS)]
review_candidates(p)  = REVIEWERS minus implementer(p.issue)
                        if that would be empty: REVIEWERS
reviewer(p, round)    = review_candidates(p)[(p + round - 1) % len(review_candidates(p))]
reconciler(p)         = RECONCILER if set
                        else implementer(p.issue) if known
                        else IMPLEMENTERS[0]
```

`n` is the issue number, `p` the PR number, and `round` is 1-based (`reviewRounds + 1` from
`pr_state.py`). The formulas use the numbers, not the spawn order, so a skipped child or a
different `--workers` value does not reshuffle the pool.

With `--reviewers auto`, `REVIEWERS` is the implementer pool, so the first review of a PR is a
different agent from the implementer whenever that pool has at least two agents, and a re-review
moves to the next candidate when more than one remains (with a single candidate the same agent
reviews again). `--reviewers all` explicitly expands to the supported set, and an
explicit list may name an agent outside the implementer pool (for example
`--implementers opencode --reviewers claude`). An explicit `--reviewers codex` means "review with
codex"; if the implementer was also codex, the pump warns "same-agent review" and proceeds — the
human asked for that pairing. An explicit list with two or more agents still excludes the
implementer when another candidate remains.

The chosen agents are recorded in the Task title (`we-<n> · <implementer>`,
`wr-<pr> · <reviewer> · r<round>`, `wc-<pr> · <reconciler>`), the worktree marker,
`$OUTDIR/state.json`, and the report. The role key stays `we-<n>` / `wr-<pr>` / `wc-<pr>`; the
agent suffix is for humans and for a resumed pump, not for filtering.

### Agent adapters

| Agent id | Skill loading | Worker prompt | Reviewer prompt |
|---|---|---|---|
| `opencode` | by skill name | Worker — opencode or claude | Reviewer — opencode or claude |
| `claude` | by skill name | Worker — opencode or claude | Reviewer — opencode or claude |
| `codex` | by file path | Worker — codex | Reviewer — codex |

Adding another Orca agent id is an adapter change: add its prompt pair to this file and add it to
the supported set in SKILL.md's Arguments. The orchestration layer does not change. Model and
effort are whatever that agent's own Orca configuration uses; the pump does not pass `--model`
or `--effort` unless a future flag adds it.

### Availability

Orca's CLI does not expose a first-class installed/available agent list as of 1.4.x:

- `orca orchestration worker-start --help` and `orca agent launch --help` name known ids, but
  that is a static list of names the build understands, not a statement that an agent is
  installed, authenticated, or enabled on this host.
- `orca account list --json` reports managed accounts and rate limits for `opencode`, `devin`,
  `claude`, and `codex`; an empty account list does not mean the agent is absent (a
  locally-authenticated opencode or codex can work with no managed account).
- `orca status --json` reports runtime readiness and capabilities, not agents.
- The runtime's `agentSession.agents` (registered structured agents with capability records) and
  `agentSession.subscribeAvailability` (per-agent `available` / `refused` / `unknown`) are what
  the Orca app's new-agent picker uses; they are not exposed as CLI commands.
- `orca worktree list --json` rows carry `createdWithAgent` for worktrees that exist, which is
  historical evidence of what has run, not availability.

So the pool is an operator declaration. The pump validates ids against its adapters and uses the
pool. A failed `worker-start` is the availability signal for that agent: it names the agent and
returns `failedStage` / `residualResources` / recovery commands. Release the residual terminal,
report the child as unscheduled, and do not silently try a different agent — a different agent is
a different point of view, and the human chose the pool.

## Orca's model, and what the pump uses

| Orca concept | What it is | How work-epic uses it |
|---|---|---|
| **Run** | A durable namespace and mailbox, bound to the coordinator | One per pump invocation (or the bound previous Run under `--resume`); scopes every Task and every `check` |
| **Task** | A unit of work with a status | One per worker (title prefix `we-`), reviewer (`wr-`), or reconciler (`wc-`); Tasks are execution records, not a second epic plan |
| **Dispatch** | One authoritative attempt at a Task | The id used for `worker-show`, `worker-read`, `worker-release`, and recovery; never address a worker by terminal title |
| **Worktree** | A tracked checkout with metadata, terminals, and a board card | The durable unit per child: issue link, PR link, status, comment, checkout, and the place review/reconciliation happens |
| **Terminal** | A PTY or chat surface owned by a Dispatch | Never driven directly by the pump; `worker-read`, `worker-show`, and `worker-release` cover both terminals and chats |

The pump never uses `agent launch`, `worktree create --agent`, or `orchestration dispatch` to
start workers. Those are handoffs or unsupervised adoptions: they create no authoritative
Dispatch, so the pump cannot settle, release, or recover them. `worker-start` is the only spawn
path. The same rule applies to the worktree: `worker-start --worktree new-child` is Orca's
agent-first worktree creation, and `worktree set` is how the pump annotates it.

The planners remain the only decision layer. Orca Tasks are bookkeeping for what this pump
started; the epic's dependency graph and ordering live in hew and `resolve_ready.py`.

## Run binding and resume

Fresh run:

```bash
ORCA orchestration run-create --objective "work-epic #<epic>" --json
```

Read `result.run.id`. Store it in `$OUTDIR/run.json`:

```json
{ "epic": 12, "run": "run_abc123", "objective": "work-epic #12" }
```

Resume:

```bash
cat "$OUTDIR/run.json"                 # if the scratch dir survived
ORCA orchestration run-list --json     # otherwise, match the objective exactly
ORCA orchestration run-use --id "<run_id>" --json
```

- One exact objective match: bind it.
- No match: create a new Run, and say the resume identity was lost.
- More than one match: stop and ask which Run to resume; never guess between two live pumps.
- A Run already bound with a different objective: stop; do not rebind a coordinator that was
  used for something else.

## Pump state file

`$OUTDIR/state.json` is the pump's bookkeeping, not a planner. It survives a coordinator restart
in the same worktree and lets the merge pass find the child worktree for a PR without guessing.
Write it after every transition:

```json
{
  "epic": 12,
  "run": "run_abc123",
  "repo": "repo-id",
  "coordinator": "repo-id::/abs/coordinator",
  "mainCheckout": "/abs/main",
  "defaultBranch": "main",
  "children": {
    "21": {
      "worktree": "repo-id::/abs/we-21",
      "path": "/abs/we-21",
      "task": "task_...",
      "dispatch": "dispatch_...",
      "implementer": "opencode",
      "state": "delivered",
      "pr": 34,
      "review": "clean",
      "reviewer": "claude",
      "round": 1,
      "findings": [41]
    }
  },
  "reviewers": {
    "34": {
      "worktree": "repo-id::/abs/wr-34-r1",
      "task": "task_...",
      "dispatch": "dispatch_...",
      "agent": "claude",
      "round": 1,
      "state": "reviewed"
    }
  },
  "reconcilers": {
    "36": {
      "worktree": "repo-id::/abs/we-22",
      "task": "task_...",
      "dispatch": "dispatch_...",
      "agent": "opencode",
      "state": "resolved"
    }
  }
}
```

Outcome files (`.work-epic/we-<n>.json`, `wr-<pr>.json`, `wc-<pr>.json`) live inside the
worktree that produced them. Step 0 lists `.work-epic/` in the repository's shared
`info/exclude` (local, never committed), so they stay out of every worktree's `git status`.

The worktree comment is the durable fallback if `$OUTDIR` is lost; the issue link is the
durable selector (`ORCA worktree show --worktree "issue:<n>" --json`).

## Worktree conventions

### Names and identity

- **Child worktree** — `--name "we-<n>"`, display name `#<n> <short title> · <implementer>`.
  The worktree id (the full `<repo-id>::<path>`) is the identity; the display name is for
  humans. Never use a display name as a key.
- **Reviewer worktree** — `--name "wr-<pr>-r<round>"`, display name
  `Review PR #<pr> · <reviewer> (round <round>)`. Transient; one per review round.
- **Reconciler** — no new worktree when the Run holds the child; it runs in
  `--worktree "id:<child-id>"` with task title `wc-<pr> · <reconciler>`. A PR from another
  run/coordinator gets a transient worktree named `wc-<pr>-a<attempt>` (`<attempt>` is
  `reconcileFailures` plus one, so a tree kept from a failed attempt never collides with the
  next), display name `Reconcile PR #<pr> · <reconciler> (attempt <attempt>)`.
- **Task titles** — start with the role prefix and carry the chosen agent:
  `we-<n> · <implementer>`, `wr-<pr> · <reviewer> · r<round>`, `wc-<pr> · <reconciler>`.
  Filter on the prefix; the suffix is how a human or a resumed pump reads the role's agent
  from `task-list` without opening the state file. Task titles carry no uniqueness guarantee;
  the Run scopes them.

Create child worktrees from `origin/<default>` explicitly:

```bash
ORCA orchestration worker-start \
  --spec "<worker prompt>" \
  --task-title "we-<n> · <implementer>" \
  --worktree new-child \
  --repo "id:<repo-id>" \
  --name "we-<n>" \
  --display-name "#<n> <short title> · <implementer>" \
  --base-branch "origin/<default>" \
  --comment "work-epic #<epic> · <run-id> · we-<n> · <implementer> · worker started" \
  --setup inherit \
  --agent <implementer> \
  --json
```

`new-child` nests the worktree under the coordinator in Orca's sidebar. Repository setup runs
per worker under `inherit`; pass `--setup skip` only when the human has said the checkout does
not need it. Reviewers use `--setup skip` — they read a diff, they do not build the project.
A transient reconciler uses `--setup inherit` because it runs the quality gate; the child
reconciler reuses the setup the implementer already paid for.

### Comment marker

Every worktree the pump creates carries one line:

```
work-epic #<epic> · <run-id> · <role-key> · <agent> · <state>
```

The role key is `we-<n>`, `wr-<pr>`, or `wc-<pr>`; the Task title additionally carries the
agent (`we-<n> · <implementer>`), which is why the marker uses the role key rather than the
whole title. The coordinator's own worktree may be the human's, so its line is the shorter
`work-epic #<epic> · <run-id> · coordinator <state>`; the sweep and resume matcher read only
the first two tokens.

Examples:

```
work-epic #12 · run_abc123 · we-21 · opencode · worker started
work-epic #12 · run_abc123 · we-21 · opencode · PR #34 delivered; review pending
work-epic #12 · run_abc123 · we-21 · opencode · clean review by claude; ready to merge
work-epic #12 · run_abc123 · we-21 · opencode · HOLD: P1 finding #44 (reviewer claude)
work-epic #12 · run_abc123 · we-21 · opencode · reconciling PR #34 (reconciler opencode)
work-epic #12 · run_abc123 · we-21 · opencode · merged
work-epic #12 · run_abc123 · wr-34 · claude · reviewing round 1
work-epic #12 · run_abc123 · wc-34 · opencode · reconciled; re-review pending
work-epic #12 · run_abc123 · we-22 · claude · failed: gate red; branch pushed; human decision
```

Orca has no labels, so this comment is the pump's custom metadata as well as the human status
line. Keep the marker tokens verbatim; the orphan sweep and resume matching read them. Append
the gate after the fourth token; do not replace the marker with prose.

### Links, status, and unread

Set the issue link immediately after creation:

```bash
ORCA worktree set --worktree "id:<child-id>" \
  --issue <n> --workspace-status in-progress --json
```

Set the PR link at delivery:

```bash
ORCA worktree set --worktree "id:<child-id>" \
  --pr <pr> --workspace-status in-review \
  --comment "work-epic #<epic> · <run-id> · we-<n> · <implementer> · PR #<pr> delivered; review pending" --json
```

Status transitions:

| When | `--workspace-status` | Comment state |
|---|---|---|
| worktree created, worker starting | `in-progress` | `worker started` |
| PR delivered | `in-review` | `PR #<pr> delivered; review pending` |
| review clean, ready to merge | `in-review` | `clean review by <reviewer>; ready to merge` |
| review finding holds it | `in-review` + `--unread` | `HOLD: <severity> finding #<child>` |
| conflict / two-round escalation / protected | `in-review` + `--unread` | `CONFLICT`, `ESCALATE`, or `PROTECTED` |
| reconciling | `in-review` | `reconciling PR #<pr>` |
| worker failed / stalled | `in-progress` + `--unread` | `failed: <reason>; branch pushed` |
| merged | `completed` | `merged` |
| worker returned no work / not eligible | `completed` (then remove if clean) | `no ready work` / `not eligible` |

There is no blocked status. A worker parked on a dialog is `in-progress` with
`BLOCKED: <what>` and `--unread`; a PR gate is `in-review` with the gate named. The pump raises
the unread dot and never clears a human's dot; the human clears it.

Keep the role's `<agent>` token when you rewrite the trailing state: the comment is how a human
sees that `#21` was implemented by opencode and reviewed by claude, and how a resume tells the
roles apart without reading the state file.

Do not change a coordinator's display name, issue/PR links, or parent lineage unless the pump
created that worktree. The coordinator may be the human's own checkout.

### Lifecycle and cleanup

The child worktree is kept from spawn through review, reconciliation, and the final merge. That
is deliberate: the reconciler reuses the checkout and its setup, the reviewer gets a separate
checkout, and the human keeps a live card while the PR is open.

- **Delivered, PR open** — keep, `in-review`.
- **Held, conflicted, protected, escalating, failed, blocked** — keep, `--unread`, gate in the
  comment.
- **Merged** — only after `gh pr merge` has succeeded: set `completed`, record the merge in
  `$OUTDIR/state.json`, remove the worktree, then delete the remote and local branch. A merge
  that fails leaves the card, checkout, and state untouched. If the tree is dirty or removal
  fails, do not discard anything: keep the tree, mark it unread, report the path, and delete
  only the remote branch (the local one is still checked out).
- **No ready work / not eligible** — the tree did no work; release and remove it if clean.
- **Stalled (branch pushed, no PR)** — the branch is on origin; remove the tree if clean, keep
  it if dirty, and report the branch either way. The resolver treats it as `stalled`; a human
  decides, never a respawn.
- **Reviewer** — transient. Remove after the findings are read and archived; `--force` is safe
  because the reviewer changes no code. Delete the local `review/<pr>-r<round>` branch if Orca
  retained it.
- **Transient reconciler** — remove after a verified push; keep on failure if it has conflict
  markers or useful state, and report the path.
- **Archive hooks** — `worktree rm` skips repo-defined `orca.yaml` archive hooks unless
  `--run-hooks` is passed. The pump skips them by default; a repo that needs them can opt in in
  its own skill variant. A failed archive hook blocks removal; report and leave the tree.

Never remove a worktree with a live terminal, a blocked worker, uncommitted work, or an open
PR that is still being worked. Report retained paths in every stop.

### Resume and orphan sweep

At the start of `--resume` and before each spawn wave:

```bash
ORCA worktree list --json
ORCA orchestration task-list --run "<run-id>" --json
ORCA orchestration worker-list --run "<run-id>" --json
```

For every worktree whose comment carries `work-epic #<epic> · <run-id>`, except the
coordinator's own root worktree:

- **live Task** — adopt it; wait, do not spawn a duplicate.
- **settled Task with an outcome** — archive the outcome, apply the transition above, release
  any terminal still live, remove a transient tree or keep the child per policy.
- **marker, no Task** — a crashed run's leftover. Report it; remove only if clean, agentless,
  has no linked open PR, and not held. Never remove a worktree whose marker names a different
  Run.

A worktree whose marker names the same epic but a different Run is another pump. Skip it and
report it; do not adopt, release, or remove it.

## Resolver output

One JSON object from `scripts/resolve_ready.py <epic> [--repo owner/name] [--resume]
[--max-open-prs N]`:

```json
{
  "epic": 12,
  "title": "Epic title",
  "mainCheckout": "/abs/path/to/repo",
  "defaultBranch": "main",
  "eligible": [
    { "number": 21, "title": "child b", "priority": "P1", "type": "task",
      "where": 2, "doneWhen": 3, "large": false, "resume": false }
  ],
  "skipped": [
    { "number": 22, "title": "child c", "reason": "blocked", "detail": "blocked by #35" },
    { "number": 23, "title": "child d", "reason": "in_review", "detail": "PR #40 open" },
    { "number": 24, "title": "child e", "reason": "claimed", "own": true,
      "detail": "in progress @you — pass --resume to pick it up" }
  ],
  "counts": { "eligible": 1, "blocked": 1, "untriaged": 0, "claimed": 1,
              "in_review": 1, "stalled": 0, "closed": 4 },
  "spawnBudget": 2
}
```

- `mainCheckout` — the primary worktree (`git worktree list --porcelain`'s first entry). It is
  the fetch/fast-forward/integration anchor, not the spawn cwd: Orca creates child worktrees
  from `origin/<default>` explicitly. `null` when undeterminable — fall back to `$PWD` and say
  so in the report.
- `defaultBranch` — origin's HEAD branch, falling back to GitHub's default branch; `null` when
  neither answers. The base every child and every PR must target.
- `eligible` — spawn order: priority first (`P0` best, missing last), ties toward the oldest
  `createdAt`. `where`/`doneWhen` are bullet counts under the body's `### Where` /
  `### Done when` sections; `large` is work-issue's sizing rule (>3 paths, >5 done-when) —
  surfaced so the report can say why a large child might be worth a `--workers 1` moment.
  `resume` is true only for a child `--resume` brought back.
- `skipped` — open children left behind, `reason` one of:
  - `in_review` — an open PR's head branch carries the child's number. Delivered; the merge
    pass owns it now, whoever holds the claim.
  - `blocked` — open blockers.
  - `untriaged` — missing priority or type.
  - `claimed` — in progress by someone else, or by you with neither PR nor pushed branch
    (in flight, or a crashed run — `--resume` makes those eligible). Yours carry `own: true`.
  - `stalled` — in progress by you, a conventional branch pushed, no open PR: a worker failed
    verification or its PR was closed. Never eligible, even with `--resume`; a human decides.

  "You" is the current `gh api user` login; when it cannot be determined every in-progress
  child is treated as claimed by someone else (fail-safe).
- `spawnBudget` — `--max-open-prs` minus the epic's open PRs (`in_review`) minus your own bare
  claims (`claimed` with `own: true` — workers in flight, each a PR on its way), floored at
  zero; `null` without the flag. Parked PRs count. A crashed run's leftover claims count too
  until `--resume` picks them up — the fail-safe direction, spawning less.
- The PR and branch reads fail the whole run rather than degrade: without them a delivered or
  failed child would read as eligible.
- Exit codes: `0` success (eligible may be empty), `1` runtime error, `2` usage error or
  "not an epic".

## Merge-pass output

One JSON object from `scripts/pr_state.py <epic> [--repo owner/name]
[--block-on P1|P2|none] [--no-review] [--allow-no-checks] [--resolve-conflicts]
[--reconciling <pr>]...` (flags in any position):

```json
{
  "epic": 12,
  "blockOn": "P1",
  "defaultBranch": "main",
  "mainCheckout": "/abs/path/to/repo",
  "queueHead": 34,
  "reconcileHead": null,
  "prs": [
    { "number": 34, "issue": 21, "issueState": "open", "branch": "fix/21-child-b",
      "head": "9f2c…", "draft": false, "mergeState": "CLEAN", "mergeable": "MERGEABLE",
      "checks": "pass", "behindBy": 2, "reviewRounds": 1, "reviewedHead": "9f2c…",
      "reconcileFailures": 0, "worstOpenFinding": "P2", "action": "update_branch",
      "note": "2 commits behind" },
    { "number": 35, "issue": 22, "issueState": "open", "branch": "feat/22-child-c",
      "head": "1d7e…", "draft": false, "mergeState": "CLEAN", "mergeable": "MERGEABLE",
      "checks": "pass", "behindBy": 2, "reviewRounds": 1, "reviewedHead": "1d7e…",
      "reconcileFailures": 0, "worstOpenFinding": null, "action": "queued",
      "note": "queued behind PR #34" }
  ],
  "unmatched": [ { "number": 99, "scrapedIssue": null,
                   "reason": "no issue number in the head branch", "action": "outside_epic" } ],
  "counts": { "update_branch": 1, "queued": 1, "outside_epic": 1 }
}
```

- PRs are matched to children by scraping the conventional issue number off the head branch
  (`fix|feat|chore/<n>-…`, work-issue's naming rule). A PR that scrapes to nothing, to an issue
  that is not this epic's child, or that targets a base other than the default branch lands in
  `unmatched` with its `reason` — listed for visibility, never touched.
- `checks` collapses `statusCheckRollup`: `pass`, `fail`, `pending`, or `none`. `none` is green
  only under `--allow-no-checks`; otherwise it is CI that has not reported yet.
- `mergeable` is GitHub's conflict verdict, which — unlike `mergeState` — a draft does not mask.
- `behindBy` is how many default-branch commits the PR head lacks, from the compare API
  (`gh api repos/<owner>/<repo>/compare/<default>...<head>`); `null` when the call fails.
  GitHub's own `BEHIND` appears only under a "require branches to be up to date" rule, so
  without this a stale PR on an unprotected repo reads `CLEAN` and merges on old CI. A ready PR
  with `behindBy` unknown never merges.
- `inFlight: true` marks a ready, current PR whose checks are pending or not yet reported —
  the CI run the queue waits on. Absent otherwise.
- `reviewRounds` counts the review-round comments on the PR (bodies containing the
  reviewer-agent marker); `reviewedHead` is the head SHA recorded in the latest one, matched by
  prefix so an abbreviated SHA still counts. A draft whose head moved past it is stale.
- `reconcileFailures` counts the failed-reconciler comments on the PR (bodies containing the
  reconciler-agent failure marker). The planner parks a conflicted PR on `conflict` after two —
  the same two-strikes bound the review rounds get.
- `worstOpenFinding` is the worst severity among open findings children carrying
  `review-of: #<issue>` in their body (see the filing flow below). At or above `--block-on`
  it blocks; below, it just becomes tracked work. `--block-on none` blocks on nothing.
- `note` says why, on `wait` and the gated actions.
- Decision order, first match wins: issue closed → `wait` · comments unreadable → `wait` ·
  `DIRTY` or `CONFLICTING` → `reconcile` when `--resolve-conflicts` is set, no review-enforced
  blocker is open, and fewer than two failed attempts are recorded — `wait` instead when the
  comments that record those attempts are unreadable, even under `--no-review`; otherwise
  `conflict` · two rounds with an open blocker → `escalate` · open blocker → `hold` · ready PR
  behind (`behindBy` > 0 or `BEHIND`) → `update_branch` · stale draft → `re_review` · no review
  round → `wait` · checks not green → `wait` · draft → `mark_ready` · `behindBy` unknown →
  `wait` · `CLEAN | HAS_HOOKS` → `merge` · `BLOCKED` → `protected` · otherwise `wait`. A hold
  comes before `update_branch` on purpose, and drafts are never updated: moving a held or draft
  PR's head spends a review round on nothing but a merge from main, for a PR that is not next
  to merge anyway. Under `--no-review` the review rows are skipped and CI is the only gate —
  findings don't suppress `reconcile` either.
- Then the merge queue: `queueHead` is the lowest-numbered `merge`; else the lowest-numbered
  `inFlight` PR; else the `update_branch` PR whose checks last passed, lowest number first; else
  `null`. Every other `merge` and `update_branch` becomes `queued`. One PR moves toward main at
  a time because each merge puts every other PR behind again — parallel updates are CI spent
  on results the next merge discards, and two merges from one plan land the second on CI that
  never saw the first. A failing PR is never `inFlight`, so it cannot stall the queue.
- Reconciliations ride the same discipline: `reconcileHead` is the lowest-numbered `reconcile`
  candidate and exists only while `queueHead` is `null` — a merge in flight would re-conflict
  the reconciliation, and reconciliations done side by side are invalidated by the first merge.
  Every other candidate becomes `queued`, behind the reconciliation head or behind the PR whose
  merge is in flight.
- `--reconciling <pr>` (repeatable) names the PRs whose `wc-<pr>` Task is live — the pump
  passes every one, from `task-list`/`worker-list`, because the planner re-runs while the
  reconciler works and GitHub shows nothing of it. While any is live the plan freezes around it: that PR
  is `wait` ("reconciler wc-<pr> in flight") whatever GitHub reads, `reconcileHead` is the
  lowest live one, `queueHead` is `null`, and every other `merge`, `update_branch`, and
  `reconcile` is `queued` behind it.
- Exit codes: `0` success (prs may be empty), `1` runtime error, `2` usage error or "not an
  epic".
- A live `wr-<pr>` reviewer is a pump-side hold the planner cannot see. Before executing
  `merge`, skip a PR with a live reviewer Task, wait for its `worker_done`, and re-run the
  planner; an in-flight review is not a completed round.

## Prompt templates

Substitute `<n>` (issue), `<pr>` (PR number), `<round>` (review round), `<default>` (origin's
default branch), `<branch>` (the PR's head branch from `pr_state.py`), and `<work-issue dir>` /
`<review-code dir>`: the installed skill directories, resolved the same way as this skill's own
(the directory holding that skill's `SKILL.md`; work-issue ships in the hew plugin, review-code
in critique). The worker and reviewer prompts need them only for codex, which has no skill
loader — the skills load by name inside opencode and claude, by file path inside codex; the
reconciler loads no skill and needs `<work-issue dir>` for both kinds.

### Worker — opencode or claude

```text
Use the work-issue skill. Work issue #<n> exactly as it specifies, with flags
--non-interactive --json '.work-epic/we-<n>.json'. When it finishes, create `.work-epic/`
if needed and write that file; do not commit it. Then send the worker_done message the
orchestration preamble specifies, with --outcome succeeded only if the file's status is
delivered, otherwise failed, and --report-path '.work-epic/we-<n>.json'. Do not ask
questions and do not interact with the user.
```

### Worker — codex

```text
Read <work-issue dir>/SKILL.md and its REFERENCE.md. Follow them exactly for issue #<n>
with flags --non-interactive --json '.work-epic/we-<n>.json'. Ask nothing. When it
finishes, create `.work-epic/` if needed and write that file; do not commit it. Then send
the worker_done message the orchestration preamble specifies, with --outcome succeeded only
if the file's status is delivered, otherwise failed, and --report-path
'.work-epic/we-<n>.json'.
```

### Reviewer — opencode or claude

```text
Check out PR #<pr>'s head in this worktree:
`gh pr checkout <pr> --branch review/<pr>-r<round>` (fallback:
`git fetch origin pull/<pr>/head && git switch -c review/<pr>-r<round> FETCH_HEAD`).
Then use the review-code skill with flags --non-interactive --json
'.work-epic/wr-<pr>.json' — its default branch-vs-default scope is exactly this PR's diff.
Do not modify code. When it finishes, create `.work-epic/` if needed and write that file;
do not commit it. Then send the worker_done message the orchestration preamble specifies,
with --outcome succeeded only if the file's status is reviewed, otherwise failed, and
--report-path '.work-epic/wr-<pr>.json'. Do not interact with the user.
```

### Reviewer — codex

```text
gh pr checkout <pr> --branch review/<pr>-r<round> (fallback: git fetch origin
pull/<pr>/head && git switch -c review/<pr>-r<round> FETCH_HEAD). Then read
<review-code dir>/SKILL.md and its REFERENCE.md and run it with --non-interactive
--json '.work-epic/wr-<pr>.json'. Do not modify code. Write the file, do not commit it,
then send the worker_done message the orchestration preamble specifies, with --outcome
succeeded only if the file's status is reviewed, otherwise failed, and --report-path
'.work-epic/wr-<pr>.json'.
```

### Reconciler — child worktree (the pump holds the checkout)

There is no reconciler skill to load: the prompt carries the whole contract, and opencode,
claude, and codex receive the same literal text.

```text
Reconcile PR #<pr>'s conflict with origin/<default>. Issue #<n> is the change the PR
carries; read it with `hew show <n>` when its intent is not clear from the diff.

This worktree is already on the PR's issue branch. Bring it to the PR head first:
1. `git fetch origin`
2. `git merge --ff-only origin/<branch>`
If the fast-forward fails, stop and write status "error" with the reason; do not reset,
rebase, or force anything.

Then:
3. `git merge origin/<default>`.
4. For each conflicted file, reconcile both sides' intent: the PR side is issue #<n>'s
   change, the incoming side is already-merged work. Combine both when they are compatible;
   when they contradict each other in behaviour — not just in text — stop and write status
   "irreconcilable" with the clashing files and why. Never drop one side wholesale, never
   guess.
5. Run the quality gate the changed files select (the table in <work-issue dir>/REFERENCE.md)
   over the union of files the merge touched. A failing gate is "irreconcilable"; do not
   push.
6. Commit the merge and `git push origin HEAD:<branch>`. Never --force, never rebase, never
   push to a ref other than this PR's <branch>.
7. Write '.work-epic/wc-<pr>.json' as JSON:
   { "status": "resolved" | "irreconcilable" | "error", "head": "<sha after the push>",
     "reason": "<why, when not resolved>", "gate": "<command and result>" }
   Do not commit it.
8. Send the worker_done message the orchestration preamble specifies, with --outcome
   succeeded only if status is "resolved", otherwise failed, and --report-path
   '.work-epic/wc-<pr>.json'. Ask nothing and do not interact with the user.
```

### Reconciler — transient worktree (PR from another run)

Same contract, with a checkout step in place of the fast-forward:

```text
This worktree is not the PR's checkout. Fetch and check it out on a local branch:
1. `git fetch origin`
2. `gh pr checkout <pr> --branch <branch>` (fallback: `git fetch origin pull/<pr>/head &&
   git switch -c <branch> FETCH_HEAD`)
3. `git merge origin/<default>`.
... then steps 4-8 above.
```

The prompt trusts only the outcome file: the head is verified, the PR is un-readied, and the
new head re-reviewed.

## Review-round comment

Every `reviewed` findings file — clean or not, in either mode — becomes exactly one comment:

```bash
gh pr comment <pr> --body "$(cat <<'EOF'
review-code findings (work-epic reviewer agent):

### P1 — <finding title>
<location> — <consequence>. Fix: <prescription>. Filed as #<child>.

### P3 — <finding title>
<location> — <consequence>. Fix: <prescription>. Not filed.

reviewed-head: <HEAD_SHA recorded when the reviewer was spawned>
EOF
)"
```

A clean review says so in one line in place of the finding blocks. Keep each finding's own
title/location/fix text; the comment is a relay, not a rewrite. The first line and the
`reviewed-head:` line are identity, like `review-key:` — `pr_state.py` counts rounds by the
first and detects a stale review by the second, so both must survive verbatim. A missing round
comment reads as "never reviewed" and the PR is never merged. At two rounds with a still-open
blocker the planner says `escalate` and the pump stops automating.

`reviewed-head` is the head recorded *before* the reviewer spawned, not the head when the
comment is posted: if the branch moved mid-review, the recorded SHA is older and the next pass
re-reviews — the safe direction.

## Reconciliation comments

The pump posts exactly one comment per reconciler run — never the agent — from its outcome
file, before acting on it:

```bash
# resolved — the success record; the planner doesn't count it
gh pr comment <pr> --body "$(cat <<'EOF'
work-epic conflict reconciliation (reconciler agent):

Reconciled against origin/<default> — gate: <command and result>.
reconciled-head: <head from the outcome file>
EOF
)"

# anything but a verified resolved push — irreconcilable, error, no outcome file, a spent
# budget, a head mismatch; the planner counts these toward the two-attempt cap
gh pr comment <pr> --body "$(cat <<'EOF'
work-epic conflict reconciliation failed (reconciler agent):

<reason>

attempt-head: <head at the attempt>
EOF
)"
```

The failure comment's first line is identity, like the review round's: `pr_state.py` counts
these and parks the PR on `conflict` after two. The success comment is the timeline's record;
the un-ready and the moved head are what put the PR back into review, and the next pass's
`re_review` supplies the round comment.

## Findings filing (autonomous mode)

The reviewer's findings file (critique's FINDINGS.md shape) becomes epic children:

```bash
uv run --no-project <raise-issues skill dir>/scripts/findings_to_plan.py \
  "$OUTDIR/outcomes/wr-<pr>.json" --parent <epic> --reviewed-issue <n> --reviewed-pr <pr> \
  --at-or-above P2 --out "$OUTDIR/wr-<pr>.plan.jsonl"
hew apply "$OUTDIR/wr-<pr>.plan.jsonl" --dry-run
hew apply "$OUTDIR/wr-<pr>.plan.jsonl"
```

The converter derives each line's `review-key: <skill>/<pattern>/<scope>` mechanically,
stamps `review-of: #<n> (PR #<pr>)` into `where`, and — with `--at-or-above P2` — leaves P3s
to the round comment. Exit 3 means the file's status is not `reviewed`; Step 5 has already
escalated that case, so it should never reach here. Before applying, apply raise-issues' Step 3
dedup table against the emitted keys — `hew search "review-key: <key>"` spans open and closed,
so a finding whose fix merged before is re-filed as a regression (`--discovered-from`), and one
a human declined stays suppressed. Drop suppressed lines from the plan before `hew apply`.

Each findings child is filed `blocked-by` the reviewed issue, so a below-`--block-on` finding's
fix unblocks exactly when the PR merges and the defect exists on main. An at-or-above
`--block-on` finding additionally holds its PR until the human closes the finding child —
after fixing the branch, or accepting the finding as is. Fixing the branch alone does not lift
the hold; the open child is what holds. Once it closes, the next pass re-reviews the draft's
new head (or, if the head never moved, readies and merges it).

## Timeout budgets

`check --wait` is the pump's clock. Size the loop like this:

- **Single `check --wait` timeout:** ~10 minutes. On timeout, enumerate `worker-list`, handle
  any `agentWait`/attention row, then run the merge pass. Do not treat the timeout as failure.
- **Settled with no outcome file:** poll the path for 60–120s, a few seconds between reads,
  before treating it as an `error` — the write can trail the state change. A file still missing
  past the grace period is an `error`, never an inference from terminal output.
- **Hard per-worker budget:** ~2 hours of continuous `working`. Beyond it, `worker-read` the
  worker, mark its worktree `--unread` with the budget in the comment, and escalate. Keep it
  un-released rather than killing a run that may be legitimately long.
- **Hard per-reviewer budget:** ~1 hour of continuous `working`, handled the same way. A
  review is read-only and bounded by one PR's diff; one running this long is stuck.
- **Hard per-reconciler budget:** ~1 hour of continuous `working`, handled the same way, and
  its failure comment posted then — an uncounted hang is respawned by every later run. A
  reconciliation is bounded by one PR's conflict plus the gate; one running this long is stuck.
  Left un-released, it stays `--reconciling` and keeps the queue held until the human closes it.
- **`agentWait`:** poll it on each `check` timeout and whenever `worker-list` says attention is
  required. A non-null value is a human gate; notify once per Dispatch and never answer. A
  soft/idle agent still producing output re-enters the wait loop under its budget. An absent
  field is "Orca never looked", not "not waiting".
- **`unverifiable` liveness:** never counts as settled. Inspect with `worker-show`/`worker-read`
  and keep waiting; absence never authorises stop, abandon, retry, or release.
- **`exited` liveness with no `worker_done`:** positive proof the agent stopped. Read the
  outcome file (with the grace period); if it exists, treat it as a settled report. If it is
  missing, follow the orchestration recovery reference — `worker-stop` only on proven exit,
  `worker-abandon` for `outcome_unknown` when the guide says so; never invent a kill from a
  timeout.
- **CI wait (merge pass):** poll `pr_state.py` on a ~2-minute cadence; a PR with no state
  change for ~60 minutes of continuous `wait` is escalated, its worktree marked unread, and set
  aside — the pump moves on and the next pass reaps it if CI recovers. `queued` is not a
  `wait`: it has no budget of its own and moves or parks with the queue head.

## Orca commands used

- `ORCA worktree current --json` — the coordinator worktree, repo id, and path
- `ORCA status --json` — runtime readiness
- `ORCA repo list --json` — confirm the target repo is registered; map `--repo owner/name`
- `ORCA repo add --path <mainCheckout> --json` — register a repo the human wants Orca to own (a human action, not a pump mutation)
- `ORCA orchestration run-create|run-use|run-current|run-list` — bind and resume the Run
- `ORCA orchestration worker-start` — create a child/reviewer worktree and its supervised worker
- `ORCA orchestration task-list --run <id> --json` — live writers, reviewers, reconcilers
- `ORCA orchestration worker-list --run <id> --json` — liveness, attention, reclaimable terminals
- `ORCA orchestration worker-show --dispatch <id> --json` — `observation.agentWait` and details
- `ORCA orchestration worker-read --dispatch <id> --source auto --json` — bounded output
- `ORCA orchestration worker-release --dispatch <id> --json` — archive and close a settled agent
- `ORCA orchestration worker-retain --dispatch <id> --json` — explicitly keep a settled terminal live for debugging, only on the human's instruction
- `ORCA orchestration check --wait --types "worker_done,escalation,question"` — the pump's inbox
- `ORCA orchestration check --ack <delivery-id> --json` — acknowledge a processed batch
- `ORCA orchestration check --unread` / `--all` — drain a resumed Run
- `ORCA orchestration worker-stop|worker-abandon` — recovery only, per the orchestration guide
- `ORCA worktree set` — issue/PR links, status, comment, unread
- `ORCA worktree show --worktree "issue:<n>"` — the durable child selector
- `ORCA worktree list --json` — the run-marker sweep
- `ORCA worktree rm` — remove a completed or transient worktree
- `ORCA worktree ps --json` — optional cross-check of live worktree terminals

Not used: `agent launch`, `worktree create --agent`, `orchestration dispatch`, and direct
`terminal create/send/wait`. They are handoffs or unsupervised adoptions; work-epic needs the
Task/Dispatch lifecycle.

Not an availability check: `ORCA agent-context --json` lists command schemas, not agents;
`ORCA account list --json` lists managed accounts and rate limits, not installed binaries. The
pool flags are the declaration; a failed `worker-start` is the signal.

## Merge-pass commands

Per `pr_state.py` action. None of them checks out a PR branch in `$MAIN`:

```bash
# mark_ready — flips the draft so the next pass sees the real mergeState
gh pr ready <pr>

# merge — the planner already verified checks, mergeState, and holds. No --delete-branch:
# the child worktree still has the branch checked out. A failure touches nothing else.
gh pr merge <pr> --<method>

# after a successful merge only — finish the child, then the branches
ORCA worktree set --worktree "id:<child-id>" --workspace-status completed \
  --comment "work-epic #<epic> · <run> · we-<n> · <implementer> · merged" --json
ORCA worktree rm --worktree "id:<child-id>" --json          # only when clean
gh api -X DELETE "repos/{owner}/{repo}/git/refs/heads/<branch>"   # 422 = already gone
git -C "$MAIN" branch -D "<branch>"                         # skip if the worktree was kept
# worktree rm deletes the local branch only when it can prove it merged, which a squash or
# rebase merge defeats — hence the explicit branch -D (the PR is merged; nothing unique is lost)

# update_branch — GitHub merges the base into the PR branch server-side
gh pr update-branch <pr>

# reconcile (--resolve-conflicts) — after the reconciler's push, on a non-draft PR
gh pr ready --undo <pr>       # back to draft, so the next pass re-reviews the new head

# post-merge main fast-forward, only while $MAIN is on the default branch
test "$(git -C "$MAIN" symbolic-ref --short HEAD)" = "$DEFAULT" &&
  git -C "$MAIN" fetch origin &&
  git -C "$MAIN" merge --ff-only "origin/$DEFAULT"
```

`--method` is `--merge-method`'s value (default `squash`); `--resolve-conflicts` refuses to run
with `rebase`, because the reconciliation is a hand-edited merge commit and a rebase-and-merge
would drop those edits. A failed `update-branch` is re-planned, not filed blind: the next pass
reads the PR `DIRTY` and, under `--resolve-conflicts`, the `reconcile` row owns it — without
the flag it is filed and notified as the `conflict` row says. A failed `gh pr merge` (a required
check appeared, the base moved between read and merge) is not retried blind — re-run the
planner, which classifies the PR's new state; a second merge failure on the same head is an
escalation. `gh pr merge --auto` would delegate the final trigger to GitHub, but it requires
repo-level auto-merge and forfeits the merge queue and the escalation budgets; keep the
explicit loop. GitHub's own merge queue does the same job where the plan allows it, but it is
not available on every repository, and the pump must work on all of them.

## gh commands used

- `gh api user --jq .login` — resolver's claim-ownership check (read-only)
- `gh api repos/<owner>/<repo>/branches` — resolver's pushed-branch read (stalled workers)
- `gh repo view --json defaultBranchRef` — default-branch fallback when origin/HEAD is unset
- `gh pr list --state open --limit 1000 --json …` / `gh pr view <pr> --json comments,headRefOid`
  — the planners' reads, and the head recorded before each review
- `gh api repos/<owner>/<repo>/compare/<default>...<head> --jq .behind_by` — the merge planner's
  `behindBy`, independent of branch protection
- `gh pr checkout <pr> --branch review/<pr>-r<round>` — the reviewer's checkout in its own
  worktree; the fallback is `git fetch origin pull/<pr>/head && git switch -c …`
- `gh pr comment <pr> --body ...` — the review-round and reconciliation comments
- `gh pr ready <pr>` — draft→ready, after a passing review or on `mark_ready`
- `gh pr ready --undo <pr>` — back to draft after a reconciliation, so the new head is re-reviewed
- `gh pr update-branch <pr>` — bring the queue head up to date, server-side
- `gh pr merge <pr> --<method>` — the bounded merge
- `gh api -X DELETE repos/{owner}/{repo}/git/refs/heads/<branch>` — the remote branch delete,
  after the merge has succeeded

## Report format

One block per worker, one per reviewer, one per reconciler run, one per merge-pass action,
then the stopped/drained distinction, retained worktrees, and escalations:

```
Epic #12 pumped (Run run_abc123, implementers opencode,claude,codex, reviewers auto,
reconciler auto, 2 workers, max 4 open PRs, block-on P1, squash, resolve-conflicts):
  coordinator: <worktree-id> · in-review
  #21 we-21 (opencode): delivered → PR #34; clean review by claude, merged (squash),
    main ff'd; worktree removed
  #22 we-22 (claude): delivered → PR #35; P2 finding filed as #41 (blocked by #22);
    reviewed by codex; worktree <id> in-review
  #23 skipped: blocked (blocked by #35)
  #24 we-24 (opencode): delivered → PR #36; P1 finding #44 filed — PR held, worktree <id> unread,
    reviewed by claude
  #26 skipped: stalled (branch fix/26-retry-budget pushed, no open PR)
  PR #34 wr-34-r1 (claude): clean (reviewed-head 9f2c…); reviewer worktree removed
  PR #36 wc-36 (opencode): reconciled vs origin/main in child worktree (gate: go test ./... —
    passed) — re-drafted, reviewer claude spawned
  PR #38 wc-38 (opencode): irreconcilable (pkg/api rename vs #33's call sites) — coupling filed
    #46, PR parked, worktree <id> retained
  merge pass: 2 merged, 1 update_branch, 1 conflict (PR #37, filed #45), 1 held
  skipped totals: blocked 1, untriaged 0, claimed 0, in_review 0, stalled 1
  epic progress: 5/8 children closed — 0 eligible remain, spawn budget 2; pump stopped, not drained
  retained worktrees: #24 <id> (held); #38 <id> (conflict); 0 reclaimable terminals
  escalations: we-25 <worktree-id> (claude) blocked on a permission dialog (unread)
               PR #37 <worktree-id> conflicts with #23's branch — reconciliation attempts spent,
               filed #45, parked
```

If the pool leaves only one reviewer candidate, the header says `reviewers same-agent (<id>)`
instead of a mixed rotation. A run that names an explicit reviewer list prints it verbatim.

"0 eligible remain" without "stopped, not drained" reads as a finished epic; the resolver's
`counts` is what keeps the two apart, which is the same distinction work-issue's
`no_ready_work` vs `not_eligible` protects. Likewise "N eligible remain, spawn budget 0" is a
full backlog, not an empty queue. PRs set aside on a spent CI budget when the pump stops are
listed so the next run — or the human — knows what is still in flight. A retained worktree with
no reason is an omission: every one is either held, conflicted, failed, blocked, or kept for a
human's inspection.

## Script tests

The decision logic of the scripts — `pr_state.plan_pr`, `pr_state.schedule`,
`resolve_ready.classify` — is pure over hew and gh JSON and covered by stdlib `unittest` files
beside them:

```bash
python3 -m unittest discover <this skill's directory>/scripts
```

A change to a decision table, a skip reason, or a parser lands with the test case that pins it,
before the pump that depends on it is trusted.

## Worktree reliability notes

- **The start receipt is the source of ids.** Read `taskId`, `dispatchId`, the worktree
  id/path, and the launch outcome from the JSON; never predict a path or derive a selector from
  a display name. If an older host omits the worktree id, find the row by the unique comment
  marker in `worktree list --json` and record it then.
- **`worker-start` failure still owns a terminal.** Use the receipt's `residualResources` and
  recovery commands; release that terminal before deciding whether the worktree is safe to
  remove. One failed start costs one child, not the pump.
- **The child worktree's branch is work-issue's.** Orca creates the worktree with a base
  branch; work-issue may create its conventional `fix|feat|chore/<n>-…` branch inside it. That
  is the checkout the reconciler reuses. If the worktree ends up with an unused Orca base
  branch, clean it up only when it has no unique commits and the worktree is being removed.
- **The reviewer must not use detached HEAD.** review-code's scope discovery refuses detached
  HEAD; use a named `review/<pr>-r<round>` branch. The name also keeps the reviewer off the
  child's issue branch.
- **A server-side `update_branch` moves the PR branch, not the child checkout.** A later
  reconciler must fast-forward the child to `origin/<branch>` before merging main; a
  fast-forward failure is an `error`, not a reset.
- **Agent availability is declared, not queried.** Orca has no CLI `agent list`; the runtime's
  `agentSession.agents` / `subscribeAvailability` are app-internal. A failed `worker-start` names
  the agent that could not launch, with recovery commands; release the residual terminal,
  report the child as unscheduled, and do not silently substitute a different agent.
- **The reviewer rotation is deterministic.** Use the PR and round numbers, not spawn order, and
  keep the round suffix on both the review branch and the worktree name. Rotating on re-review is
  intentional: when more than one candidate remains, the second round is a second point of view,
  not a repeat of the first.
- **The role's agent is part of the record.** Keep `<agent>` in the Task title, the worktree
  marker, `$OUTDIR/state.json`, and the report. Do not infer it from a terminal title; the task
  title and the marker carry it explicitly.
