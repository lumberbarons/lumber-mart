# Reference

Resolver and merge-pass schemas, the Orca Run/Task/worktree lifecycle, prompt templates, the
review-round and repair comments, findings filing, naming, timeout budgets, and the report format
for `work-epic`.

## Agents

| Role | What it runs | Agent |
|---|---|---|
| **Coordinator** | This skill: plans, spawns, reaps, merges, reports | The agent the human started the session in; the pump never spawns a coordinator |
| **Implementer** | `work-issue` in the issue's worktree | `opencode` |
| **Reviewer** | `review-code`, then fixes what it found, in the issue's worktree | `claude` |
| **Repairer** | The repair contract in the issue's worktree | `opencode` |

The agents are SKILL.md's `Agents` block and nowhere else. The reviewer is a different agent from
the implementer by construction: that is the second point of view. The implementer and reviewer
prompts load their skill by name, so both agents must have it installed; the repairer and the
reviewer's fix step read the quality-gate table from the work-issue skill directory, so it must be
readable on the host.

Orca's CLI does not expose an installed-agent list, so the choice is the operator's declaration.
`orca account list --json` reports managed accounts and rate limits, not installation; the
runtime's `agentSession.agents` powers the app's picker but is not a CLI command. A failed
`worker-start` is the availability signal: it names the agent and returns `failedStage` /
`residualResources` / recovery commands. Release the residual terminal, report the issue as
unscheduled, and do not silently try a different agent — a different agent is a different point of
view, and the human chose these.

## Orca's model, and what the pump uses

| Orca concept | What it is | How work-epic uses it |
|---|---|---|
| **Run** | A durable namespace and mailbox, bound to the coordinator | One per pump invocation (or the bound previous Run under `--resume`); scopes every Task and every `check` |
| **Task** | A unit of work with a status | One per implementer (title prefix `we-`), reviewer (`wr-`), or repairer (`wc-`); Tasks are execution records, not a second plan |
| **Dispatch** | One authoritative attempt at a Task | The id used for `worker-show`, `worker-read`, `worker-release`, and recovery; never address a worker by terminal title |
| **Worktree** | A tracked checkout with metadata, terminals, and a board card | The durable unit per issue: issue link, PR link, status, comment, checkout, and the place review and repair happen |
| **Terminal** | A PTY or chat surface owned by a Dispatch | Never driven directly by the pump; `worker-read`, `worker-show`, and `worker-release` cover both terminals and chats |

The pump never uses `agent launch`, `worktree create --agent`, or `orchestration dispatch` to start
workers. Those are handoffs or unsupervised adoptions: they create no authoritative Dispatch, so the
pump cannot settle, release, or recover them. `worker-start` is the only spawn path. The same rule
applies to the worktree: `worker-start --worktree new-child` is Orca's agent-first worktree
creation, `worker-start --worktree id:<child>` puts a reviewer or repairer in an existing one, and
`worktree set` is how the pump annotates it.

The planners remain the only decision layer. Orca Tasks are bookkeeping for what this pump started;
dependency order lives in hew and `resolve_ready.py`.

## Run binding and resume

Fresh run:

```bash
ORCA orchestration run-create --objective "work-epic #<n> #<n> …" --json
```

The objective is `work-epic` followed by each scope number as `#<n>`, in the order given. Read
`result.run.id` and store it as `run` in `$OUTDIR/state.json`.

Resume:

```bash
jq -r .run "$OUTDIR/state.json"        # if the scratch dir survived
ORCA orchestration run-list --json     # otherwise, match the objective exactly
ORCA orchestration run-use --id "<run_id>" --json
```

- One exact objective match: bind it.
- No match: create a new Run, and say the resume identity was lost.
- More than one match: stop and ask which Run to resume; never guess between two live pumps.
- A Run already bound with a different objective: stop; do not rebind a coordinator that was used
  for something else.

## Pump state file

`$OUTDIR/state.json` is the pump's bookkeeping, not a planner. It survives a coordinator restart in
the same worktree and lets the merge pass find the worktree for a PR without guessing. Write it
after every transition:

```json
{
  "scope": [21, 22, 25],
  "run": "run_abc123",
  "repo": "repo-id",
  "coordinator": "repo-id::/abs/coordinator",
  "mainCheckout": "/abs/main",
  "defaultBranch": "main",
  "issues": {
    "21": {
      "worktree": "repo-id::/abs/we-21",
      "path": "/abs/we-21",
      "branch": "lumberbarons/we-21",
      "task": "task_...",
      "dispatch": "dispatch_...",
      "state": "delivered",
      "pr": 34,
      "review": "fixed",
      "findings": [41, 42]
    }
  },
  "reviewers": {
    "34": { "task": "task_...", "dispatch": "dispatch_...", "state": "reviewed" }
  },
  "repairers": {
    "36": { "task": "task_...", "dispatch": "dispatch_...", "state": "resolved" }
  }
}
```

Outcome files (`.work-epic/we-<n>.json`, `wr-<pr>.json`, `wc-<pr>.json`) live inside the worktree
that produced them. Step 0 lists `.work-epic/` in the repository's shared `info/exclude` (local,
never committed), so they stay out of every worktree's `git status`.

The worktree comment is the durable fallback if `$OUTDIR` is lost; the issue link is the durable
selector (`ORCA worktree show --worktree "issue:<n>" --json`).

## Worktree conventions

### Names and identity

- **Issue worktree** — `--name "we-<n>"`, display name `#<n> <short title>`. The worktree id (the
  full `<repo-id>::<path>`) is the identity; the display name is for humans. Never use a display
  name as a key. The reviewer and the repairer run in this same worktree: no second checkout, no
  second setup, no branch to collide with.
- **Task titles** — start with the role prefix and carry the agent: `we-<n> · opencode`,
  `wr-<pr> · claude`, `wc-<pr> · opencode`. Filter on the prefix. Task titles carry no uniqueness
  guarantee; the Run scopes them.

Repository setup runs once per issue under `inherit`; pass `--setup skip` only when the human has
said the checkout does not need it. The reviewer and the repairer reuse the setup the implementer
already paid for.

### Comment marker

Every worktree the pump creates carries one line:

```
work-epic · <run-id> · we-<n> · <agent> · <state>
```

The coordinator's own worktree may be the human's, so its line is the shorter
`work-epic · <run-id> · coordinator <state>`; the sweep and resume matcher read only the first two
tokens. Example: `work-epic · run_abc123 · we-21 · opencode · reviewed by claude; 2 fixed; ready to
merge`.

Orca has no labels, so this comment is the pump's custom metadata as well as the human status line.
Keep the marker tokens verbatim; the orphan sweep and resume matching read them. Append the gate
after the fourth token; do not replace the marker with prose.

### Links, status, and unread

Set `--issue <n>` right after creating a worktree and `--pr <pr>` at delivery (SKILL.md Steps 3 and
4). Status transitions and the comment state each carries:

| When | `--workspace-status` | Comment state |
|---|---|---|
| worktree created, worker starting | `in-progress` | `worker started` |
| PR delivered | `in-review` | `PR #<pr> delivered; review pending` |
| reviewer running | `in-review` | `reviewing by <reviewer>` |
| reviewed, nothing held | `in-review` | `reviewed by <reviewer>; <n> fixed, <m> filed open; ready to merge` |
| unfixed P1 holds it | `in-review` + `--unread` | `HOLD: P1 finding #<issue> not fixed (reviewer <reviewer>)` |
| repairing | `in-review` | `repairing PR #<pr> (<repairer>)` |
| conflict / CI failed / protected | `in-review` + `--unread` | `CONFLICT`, `CI FAILED: <check>`, or `PROTECTED: <what>` |
| worker failed / stalled | `in-progress` + `--unread` | `failed: <reason>; branch pushed` |
| worker errored | `in-progress` + `--unread` | `error: <reason>` |
| worker parked on a dialog | `in-progress` + `--unread` | `BLOCKED: <what>` |
| merged | `completed` | `merged` |
| worker returned no work / not eligible | `completed` (then remove if clean) | `no ready work` / `not eligible` |

There is no blocked status: a PR gate is `in-review` with the gate named. The pump raises the
unread dot and never clears a human's dot; the human clears it. Keep the `<agent>` token when you
rewrite the trailing state. Do not change a coordinator's display name, issue/PR links, or parent
lineage unless the pump created that worktree.

### Lifecycle and cleanup

The issue's worktree is kept from spawn through review, repair, and the final merge. That is
deliberate: the reviewer and repairer reuse the checkout and its setup, and the human keeps a live
card while the PR is open.

- **Delivered, PR open** — keep, `in-review`.
- **Held, conflicted, CI-failed, protected, failed, blocked** — keep, `--unread`, gate in the
  comment.
- **Merged** — only after `gh pr merge` has succeeded; the sequence is under
  [Merge-pass commands](#merge-pass-commands). A merge that fails leaves the card, checkout, and
  state untouched.
- **No ready work / not eligible** — the tree did no work; release and remove it if clean.
- **Stalled (branch pushed, no PR)** — the branch is on origin; remove the tree if clean, keep it
  if dirty, and report the branch either way. The resolver treats it as `stalled`; a human decides,
  never a respawn.
- **Orca's own branch** — `worker-start --worktree new-child --name <n>` makes Orca create a branch
  for the worktree, `<user>/<n>` (for example `lumberbarons/we-21`), and report it as `branch` on
  the receipt. Record it. `work-issue` then switches to its `fix|feat|chore/<n>-…` branch, and
  `worktree rm` only deletes the branch that is checked out at removal, so Orca's own branch is
  left behind with nothing on it. Delete it after a successful removal with
  `git -C "$MAIN" branch -d "<orca-branch>"`: lowercase `-d` refuses a branch holding commits the
  default branch lacks, so it cannot discard work. A refusal, or a missing receipt `branch`, is
  reported with the worktree, never forced and never guessed from the name. When the agent never
  switched, Orca's branch is the checked-out one and `worktree rm` already handled it.
- **Archive hooks** — `worktree rm` skips repo-defined `orca.yaml` archive hooks unless
  `--run-hooks` is passed. The pump skips them by default. A failed archive hook blocks removal;
  report and leave the tree.

Never remove a worktree with a live terminal, a blocked worker, uncommitted work, or an open PR
that is still being worked. Report retained paths in every stop.

### Resume and orphan sweep

At the start of `--resume` and before each spawn wave:

```bash
ORCA worktree list --json
ORCA orchestration task-list --run "<run-id>" --json
ORCA orchestration worker-list --run "<run-id>" --json
```

For every worktree whose comment carries `work-epic · <run-id>`, except the coordinator's own root
worktree:

- **live Task** — adopt it; wait, do not spawn a duplicate.
- **settled Task with an outcome** — archive the outcome, apply the transition above, release any
  terminal still live, keep the worktree per policy.
- **marker, no Task** — a crashed run's leftover. Report it; remove only if clean, agentless, has
  no linked open PR, and not held. Never remove a worktree whose marker names a different Run.

A worktree whose marker names a different Run is another pump. Skip it and report it; do not adopt,
release, or remove it.

## Resolver output

One JSON object from `scripts/resolve_ready.py <issue-number>... [--repo owner/name] [--resume]
[--workers N]`:

```json
{
  "scope": [12],
  "mainCheckout": "/abs/path/to/repo",
  "defaultBranch": "main",
  "eligible": [
    { "number": 21, "title": "issue b", "priority": "P1", "type": "task",
      "where": 2, "doneWhen": 3, "large": false, "resume": false }
  ],
  "skipped": [
    { "number": 22, "title": "issue c", "reason": "blocked", "detail": "blocked by #35" },
    { "number": 23, "title": "issue d", "reason": "in_review", "detail": "PR #40 open" },
    { "number": 24, "title": "issue e", "reason": "claimed", "own": true,
      "detail": "in progress @you — pass --resume to pick it up" }
  ],
  "counts": { "eligible": 1, "blocked": 1, "untriaged": 0, "claimed": 1,
              "in_review": 1, "stalled": 0, "closed": 4 },
  "spawnBudget": 2
}
```

- `scope` — the issue numbers as given. An epic number expands to its children (open and closed);
  any other number is that issue. The same numbers go to `pr_state.py`.
- `mainCheckout` — the primary worktree (`git worktree list --porcelain`'s first entry). It is the
  fetch/fast-forward anchor, not the spawn cwd: Orca creates worktrees from `origin/<default>`
  explicitly. `null` when undeterminable — fall back to `$PWD` and say so in the report.
- `defaultBranch` — origin's HEAD branch, falling back to GitHub's default branch; `null` when
  neither answers. The base every worktree and every PR must target.
- `eligible` — spawn order: priority first (`P0` best, missing last), ties toward the oldest
  `createdAt`. `where`/`doneWhen` are bullet counts under the body's `### Where` /
  `### Done when` sections; `large` is work-issue's sizing rule (>3 paths, >5 done-when) — surfaced
  so the report can say why a large issue might be worth a `--workers 1` moment. Only `- ` bullets
  are counted, so a prose `### Where` reads `where: 0` and `large` can under-report; an absent flag
  is not proof the issue is small (tracked in #31). `resume` is true only for an issue `--resume`
  brought back.
- `skipped` — open issues left behind, `reason` one of:
  - `in_review` — an open PR's head branch carries the issue's number. Delivered; the merge pass
    owns it now, whoever holds the claim.
  - `blocked` — open blockers.
  - `untriaged` — missing priority or type.
  - `claimed` — in progress by someone else, or by you with neither PR nor pushed branch (in
    flight, or a crashed run — `--resume` makes those eligible). Yours carry `own: true`.
  - `stalled` — in progress by you, a conventional branch pushed, no open PR: a worker failed
    verification or its PR was closed. Never eligible, even with `--resume`; a human decides.

  "You" is the current `gh api user` login; when it cannot be determined every in-progress issue
  is treated as claimed by someone else (fail-safe).
- `counts` sums every skip reason plus `eligible` and `closed`.
- `spawnBudget` — twice `--workers` minus the scope's open PRs (`in_review`) minus your own bare
  claims (`claimed` with `own: true` — workers in flight, each a PR on its way), floored at zero.
  Parked PRs count. A crashed run's leftover claims count too until `--resume` picks them up — the
  fail-safe direction, spawning less.
- Review findings are not special here. The reviewer fixes what it can in its own session and the
  rest is a human's backlog; a finding issue that reaches the resolver (named in the scope, or an
  old epic child) is ordinary work.
- The PR and branch reads fail the whole run rather than degrade: without them a delivered or
  failed issue would read as eligible.
- Exit codes: `0` success (eligible may be empty), `1` runtime error, `2` usage error.

## Merge-pass output

One JSON object from `scripts/pr_state.py <issue-number>... [--repo owner/name]
[--reviewing <pr>]... [--repairing <pr>]...` (flags in any position):

```json
{
  "scope": [12],
  "defaultBranch": "main",
  "mainCheckout": "/abs/path/to/repo",
  "queueHead": 34,
  "repairHead": null,
  "prs": [
    { "number": 34, "issue": 21, "issueState": "open", "branch": "fix/21-issue-b",
      "head": "9f2c…", "draft": false, "mergeState": "CLEAN", "mergeable": "MERGEABLE",
      "checks": "pass", "behindBy": 2, "reviewed": true,
      "repairFailures": 0, "worstOpenFinding": "P2", "action": "update_branch",
      "note": "2 commits behind" },
    { "number": 35, "issue": 22, "issueState": "open", "branch": "feat/22-issue-c",
      "head": "1d7e…", "draft": false, "mergeState": "CLEAN", "mergeable": "MERGEABLE",
      "checks": "pass", "behindBy": 2, "reviewed": true,
      "repairFailures": 0, "worstOpenFinding": null, "action": "queued",
      "note": "queued behind PR #34" }
  ],
  "unmatched": [ { "number": 99, "scrapedIssue": null,
                   "reason": "no issue number in the head branch", "action": "outside_scope" } ],
  "counts": { "update_branch": 1, "queued": 1, "outside_scope": 1 }
}
```

- PRs are matched to scope issues by scraping the conventional issue number off the head branch
  (`fix|feat|chore/<n>-…`, work-issue's naming rule). A PR that scrapes to nothing, to an issue
  outside the scope, or that targets a base other than the default branch lands in `unmatched` with
  its `reason` — listed for visibility, never touched.
- `checks` collapses `statusCheckRollup`: `pass`, `fail`, `pending`, or `none`. `none` is CI that
  has not reported yet, never green: a repository without CI is not supported.
- `mergeable` is GitHub's conflict verdict, which — unlike `mergeState` — a draft does not mask.
- `behindBy` is how many default-branch commits the PR head lacks, from the compare API
  (`gh api repos/<owner>/<repo>/compare/<default>...<head>`); `null` when the call fails. GitHub's
  own `BEHIND` appears only under a "require branches to be up to date" rule, so without this a
  stale PR on an unprotected repo reads `CLEAN` and merges on old CI. A ready PR with `behindBy`
  unknown never merges.
- `inFlight: true` marks a ready, current PR whose checks are pending or not yet reported — the CI
  run the queue waits on. Absent otherwise.
- `reviewed` is true when the PR carries a review-round comment (a body containing the
  reviewer-agent marker). That comment is the whole review state: a PR is reviewed once, and a head
  that moves afterwards — the reviewer's own fixes, a repair, a human's edit — is not reviewed again.
- `repairFailures` counts the failed-repair comments on the PR (bodies containing the repair-agent
  failure marker). One counter covers conflicts and red CI together: after two, the PR parks.
- `worstOpenFinding` is the worst severity among open issues carrying `review-of: #<issue>` in their
  body (see Findings filing). The reviewer files what it fixed and closes it, so only a finding it
  could not fix is open. At P1 or above it holds the PR; below, it is tracked backlog.
- `note` says why, on `wait` and the gated actions.
- Decision order, first match wins: issue closed → `wait` · a live reviewer (`--reviewing`) →
  `wait` · comments unreadable → `wait` · `DIRTY` or `CONFLICTING` → `repair` when no blocker is
  open and fewer than two failed attempts are recorded, otherwise `conflict` · open blocker →
  `hold` · ready PR behind (`behindBy` > 0 or `BEHIND`) → `update_branch` · no review round →
  `wait` · checks failing → `repair` under the same two-attempt rule, otherwise `ci_failed` ·
  checks pending or absent → `wait` · draft → `mark_ready` · `behindBy` unknown → `wait` ·
  `CLEAN | HAS_HOOKS` → `merge` · `BLOCKED` → `protected` · otherwise `wait`. A hold comes before
  `update_branch` on purpose, and drafts are never updated.
- Then the merge queue: `queueHead` is the lowest-numbered `merge`; else the lowest-numbered
  `inFlight` PR; else the `update_branch` PR whose checks last passed, lowest number first; else
  `null`. Every other `merge` and `update_branch` becomes `queued`. One PR moves toward main at a
  time because each merge puts every other PR behind again — parallel updates are CI spent on
  results the next merge discards, and two merges from one plan land the second on CI that never
  saw the first. A failing PR is never `inFlight`, so it cannot stall the queue.
- Repairs ride the same discipline: `repairHead` is the lowest-numbered `repair` candidate and
  exists only while `queueHead` is `null` — a merge in flight would re-conflict the repair, and
  repairs done side by side are invalidated by the first merge. Every other candidate becomes
  `queued`, behind the repair head or behind the PR whose merge is in flight.
- `--repairing <pr>` (repeatable) names the PRs whose `wc-<pr>` Task is live — the pump passes
  every one, from `task-list`/`worker-list`, because the planner re-runs while the repairer works
  and GitHub shows nothing of it. While any is live the plan freezes around it: that PR is `wait`
  ("repairer wc-<pr> in flight") whatever GitHub reads, `repairHead` is the lowest live one,
  `queueHead` is `null`, and every other `merge`, `update_branch`, and `repair` is `queued` behind
  it.
- `--reviewing <pr>` (repeatable) names the PRs whose `wr-<pr>` Task is live. The PR is `wait`
  ("reviewer in flight") whatever its comments say; nothing else freezes, since a review neither
  moves main nor conflicts with a merge elsewhere.
- Exit codes: `0` success (prs may be empty), `1` runtime error, `2` usage error.

## Prompt templates

Substitute `<n>` (issue), `<pr>` (PR number), `<default>` (origin's default branch), `<branch>` (the
PR's head branch from `pr_state.py`), and `<work-issue dir>` (the installed work-issue skill
directory — the one holding its `SKILL.md`; it ships in the hew plugin). The implementer and
reviewer load their skills by name; the reviewer's fix step and the repairer need `<work-issue dir>`
for the quality-gate table.

### Worker

```text
Use the work-issue skill. Work issue #<n> exactly as it specifies, with flags
--non-interactive --json '.work-epic/we-<n>.json'. When it finishes, create `.work-epic/`
if needed and write that file; do not commit it. Then send the worker_done message the
orchestration preamble specifies, with --outcome succeeded only if the file's status is
delivered, otherwise failed, and --report-path '.work-epic/we-<n>.json'. Do not ask
questions and do not interact with the user.
```

### Reviewer (reviews, then fixes, in one session)

```text
Review PR #<pr> and fix what you find, in this worktree. Issue #<n> is the change the PR carries;
read it with `hew show <n>` when its intent is not clear from the diff.

This worktree is already on the PR's issue branch. Bring it to the PR head first:
1. `git fetch origin`
2. `git merge --ff-only origin/<branch>`
If the fast-forward fails, stop and write status "error" with the reason; do not reset, rebase,
or force anything.

Then:
3. Use the review-code skill with flags --non-interactive --json '.work-epic/wr-<pr>.json'. Its
   default branch-vs-default scope is exactly this PR's diff.
4. For each finding at P0, P1, or P2, in order, try to fix it:
   - make the smallest change that resolves it, inside the files this PR already changes or
     their direct tests;
   - run the quality gate the changed files select (the table in <work-issue dir>/REFERENCE.md);
   - if the gate passes, commit it as `fix: <finding title>` and set "fixed": true and
     "fixedIn": "<short sha>" on that finding in the file;
   - otherwise undo the change entirely (`git restore --staged --worktree .`) and set
     "fixed": false and "unfixedReason": "<why>" on that finding.
   Leave a finding unfixed, with the reason, when the fix needs a design decision, reaches outside
   this PR's files, would be large, or conflicts with another finding. Never weaken or delete a
   test to make a gate pass. Leave P3 findings alone.
5. If you committed anything: `git push origin HEAD:<branch>`. Never --force, never rebase,
   never push to a ref other than this PR's <branch>.
6. Add to the file's top level "head": "<sha after the push>" and "gate": "<command and result>".
   Create `.work-epic/` if needed; do not commit the file.
7. Send the worker_done message the orchestration preamble specifies, with --outcome succeeded
   only if the file's status is reviewed, otherwise failed, and --report-path
   '.work-epic/wr-<pr>.json'. Ask nothing and do not interact with the user.
```

The file is review-code's findings file with four additions the converter and the pump read:
`fixed` and `fixedIn` per finding (and `unfixedReason` when not fixed), and `head` and `gate` at
the top. Everything else is untouched, so a file with no fixes is exactly review-code's output.

### Repairer (conflict or red CI)

There is no repair skill to load: the prompt carries the whole contract.

```text
Repair PR #<pr>. Issue #<n> is the change the PR carries; read it with `hew show <n>` when its
intent is not clear from the diff. The PR is either in conflict with origin/<default> or has a
failing check; find out which.

This worktree is already on the PR's issue branch. Bring it to the PR head first:
1. `git fetch origin`
2. `git merge --ff-only origin/<branch>`
If the fast-forward fails, stop and write status "error" with the reason; do not reset, rebase,
or force anything.

Then:
3. If the PR conflicts: `git merge origin/<default>`. For each conflicted file, reconcile both
   sides' intent: the PR side is issue #<n>'s change, the incoming side is already-merged work.
   Combine both when they are compatible; when they contradict each other in behaviour — not just
   in text — stop and write status "blocked" with the clashing files and why. Never drop one side
   wholesale, never guess.
4. If a check is failing: read it with `gh pr checks <pr>` and the failing run's log. Fix the
   cause when this PR caused it. When it did not — a flaky test, an outage, a failure that is
   already on origin/<default> — stop and write status "blocked" and say so; do not paper over it,
   and never skip, weaken, or delete a test or a check.
5. Run the quality gate the changed files select (the table in <work-issue dir>/REFERENCE.md) over
   the union of files you touched. A failing gate is "blocked"; do not push.
6. Commit and `git push origin HEAD:<branch>`. Never --force, never rebase, never push to a ref
   other than this PR's <branch>.
7. Write '.work-epic/wc-<pr>.json' as JSON:
   { "status": "resolved" | "blocked" | "error", "head": "<sha after the push>",
     "reason": "<why, when not resolved>", "gate": "<command and result>" }
   Do not commit it.
8. Send the worker_done message the orchestration preamble specifies, with --outcome succeeded
   only if status is "resolved", otherwise failed, and --report-path '.work-epic/wc-<pr>.json'.
   Ask nothing and do not interact with the user.
```

The prompt trusts only the outcome file: the head is verified before the pump acts on `resolved`.

## Review-round comment

Every `reviewed` findings file — clean or not — becomes exactly one comment. Post it **after** the
findings are filed and the fixed ones closed (see below): it quotes the issues' numbers, and a round
comment with no blocker filed behind it reads to the planner as a clean review:

```bash
gh pr comment <pr> --body "$(cat <<'EOF'
review-code findings (work-epic reviewer agent):

### P1 — <finding title>
<location> — <consequence>. Fixed in <sha>. Filed as #<issue> and closed.

### P2 — <finding title>
<location> — <consequence>. Not fixed: <unfixedReason>. Filed as #<issue>.

### P3 — <finding title>
<location> — <consequence>. Fix: <prescription>. Not filed.

gate: <the file's `gate`>
EOF
)"
```

A clean review says so in one line in place of the finding blocks. Keep each finding's own
title/location text; the comment is a relay, not a rewrite. The first line is identity, like
`review-key:` — `pr_state.py` reads it as "reviewed", so it must survive verbatim. A missing round
comment reads as "never reviewed" and the PR is never merged.

## Repair comments

The pump posts exactly one comment per repairer run — never the agent — from its outcome file,
before acting on it:

```bash
# resolved — the success record; the planner doesn't count it
gh pr comment <pr> --body "$(cat <<'EOF'
work-epic repair (repair agent):

<what was repaired: conflict with origin/<default>, failing check <name>> — gate: <command and result>.
repaired-head: <head from the outcome file>
EOF
)"

# anything but a verified resolved push — blocked, error, no outcome file, a spent budget, a
# head mismatch; the planner counts these toward the two-attempt cap
gh pr comment <pr> --body "$(cat <<'EOF'
work-epic repair failed (repair agent):

<reason>

attempt-head: <head at the attempt>
EOF
)"
```

The failure comment's first line is identity, like the review round's: `pr_state.py` counts these
and parks the PR on `conflict` or `ci_failed` after two. The success comment is the timeline's
record. Nothing about a successful repair puts the PR back into review.

## Findings filing

The reviewer's findings file (critique's FINDINGS.md shape, plus the `fixed` fields) becomes
issues, filed with no parent: they are the paper trail of this review. This runs before the
review-round comment is posted, so a failure here leaves the PR unreviewed rather than mergeable
with its blocker missing:

```bash
uv run --no-project <raise-issues skill dir>/scripts/findings_to_plan.py \
  "$OUTDIR/outcomes/wr-<pr>.json" --reviewed-issue <n> --reviewed-pr <pr> \
  --at-or-above P2 --out "$OUTDIR/wr-<pr>.plan.jsonl"
hew list --json --bodies --state all > "$OUTDIR/issues.ndjson"
uv run --no-project <raise-issues skill dir>/scripts/dedup_candidates.py \
  "$OUTDIR/wr-<pr>.plan.jsonl" "$OUTDIR/issues.ndjson" --reviewed-issue <n>
hew apply "$OUTDIR/wr-<pr>.plan.jsonl" --dry-run
hew apply "$OUTDIR/wr-<pr>.plan.jsonl"
```

The converter derives each line's `review-key: <skill>/<pattern>/<scope>` mechanically, stamps
`review-of: #<n> (PR #<pr>)` into `where`, adds `fixed-in: <sha>` when the finding carries
`fixedIn`, and — with `--at-or-above P2` — leaves P3s to the round comment. Exit 3 means the file's
status is not `reviewed`; Step 5 has already escalated that case, so it should never reach here.
`dedup_candidates.py` lists, per plan line, the issues that already carry the same key and were
raised against this reviewed issue; a hit on the reviewed issue itself, or on a finding raised
against another issue, comes back under `other_generation` and is never a reason to skip. For each
candidate, apply raise-issues' Step 3 table: read the body, and skip the line only if it describes
the same finding. The scan spans open and closed, so a finding whose fix merged before is re-filed
as a regression (`--discovered-from`), and one a human declined stays suppressed. Drop suppressed
lines from the plan before `hew apply`.

Then close what the reviewer fixed. Every open issue that names this PR and carries a `fixed-in:`
line is closed as completed, with that commit as the reason. Unfixed findings carry no `fixed-in:`
line, so they stay open:

```bash
hew list --json --bodies \
  | jq -r --arg of "review-of: #<n> (PR #<pr>)" \
      'select(.body | contains($of) and test("(^|\n)fixed-in: [0-9a-f]+"))
       | "\(.number) \(.body | capture("(^|\n)fixed-in: (?<sha>[0-9a-f]+)").sha)"' \
  | while read -r issue sha; do
      hew close "$issue" --completed --reason "Fixed in $sha on PR #<pr> before merge"
    done
```

The command is safe to repeat — a closed issue no longer lists — which is why Step 7 runs it again
for every reviewed PR: a crash between filing and closing leaves a fixed finding open, which holds
a P1's PR until the sweep closes it. The hold is safe in that direction.

Each findings issue is filed `blocked-by` the reviewed issue, so an unfixed finding's own fix waits
until the PR merges and the defect exists on main. An open finding at P1 or above holds its PR until
the human closes it — after fixing the branch, or accepting the finding as is. Once it closes, the
next pass readies and merges the PR; nothing re-reviews it.

## Timeout budgets

`check --wait` is the pump's clock. Size the loop like this:

- **Single `check --wait` timeout:** ~10 minutes. On timeout, enumerate `worker-list`, handle any
  `agentWait`/attention row, then run the merge pass. Do not treat the timeout as failure.
- **Hard per-implementer budget:** ~2 hours of continuous `working`. Beyond it, `worker-read` the
  worker, mark its worktree `--unread` with the budget in the comment, and escalate. Keep it
  un-released rather than killing a run that may be legitimately long.
- **Hard per-reviewer budget:** ~90 minutes of continuous `working`, handled the same way. It is
  bounded by one PR's diff plus the fixes and their gates; one running this long is stuck.
- **Hard per-repairer budget:** ~1 hour of continuous `working`, handled the same way, and its
  failure comment posted then — an uncounted hang is respawned by every later run. A repair is
  bounded by one PR's conflict or failure plus the gate. Left un-released, it stays `--repairing`
  and keeps the queue held until the human closes it.
- **`exited` liveness with no `worker_done`:** positive proof the agent stopped. Read the outcome
  file (with the grace period); if it exists, treat it as a settled report. If it is missing,
  follow the orchestration recovery reference — `worker-stop` only on proven exit,
  `worker-abandon` for `outcome_unknown` when the guide says so; never invent a kill from a
  timeout.
- **CI wait (merge pass):** poll `pr_state.py` on a ~2-minute cadence; a PR with no state change for
  ~60 minutes of continuous `wait` is escalated, its worktree marked unread, and set aside — the
  pump moves on and the next pass reaps it if CI recovers. `queued` is not a `wait`: it has no
  budget of its own and moves or parks with the queue head.

## Orca commands used

- `ORCA worktree current --json` — the coordinator worktree, repo id, and path
- `ORCA status --json` — runtime readiness
- `ORCA repo list --json` — confirm the target repo is registered; map `--repo owner/name`
- `ORCA repo add --path <mainCheckout> --json` — register a repo the human wants Orca to own (a
  human action, not a pump mutation)
- `ORCA orchestration run-create|run-use|run-current|run-list` — bind and resume the Run
- `ORCA orchestration worker-start` — create an issue worktree and its supervised worker, or start
  a reviewer or repairer in an existing one
- `ORCA orchestration task-list --run <id> --json` — live writers, reviewers, repairers
- `ORCA orchestration worker-list --run <id> --json` — liveness, attention, reclaimable terminals
- `ORCA orchestration worker-show --dispatch <id> --json` — `observation.agentWait` and details
- `ORCA orchestration worker-read --dispatch <id> --source auto --json` — bounded output
- `ORCA orchestration worker-release --dispatch <id> --json` — archive and close a settled agent
- `ORCA orchestration worker-retain --dispatch <id> --json` — explicitly keep a settled terminal
  live for debugging, only on the human's instruction
- `ORCA orchestration check --wait --types "worker_done,escalation,question"` — the pump's inbox
- `ORCA orchestration check --ack <delivery-id> --json` — acknowledge a processed batch
- `ORCA orchestration check --unread` / `--all` — drain a resumed Run
- `ORCA orchestration worker-stop|worker-abandon` — recovery only, per the orchestration guide
- `ORCA worktree set` — issue/PR links, status, comment, unread
- `ORCA worktree show --worktree "issue:<n>"` — the durable issue selector
- `ORCA worktree list --json` — the run-marker sweep
- `ORCA worktree rm` — remove a completed or workless worktree
- `ORCA worktree ps --json` — optional cross-check of live worktree terminals

## Merge-pass commands

Per `pr_state.py` action. None of them checks out a PR branch in `$MAIN`:

```bash
# mark_ready — flips the draft so the next pass sees the real mergeState
gh pr ready <pr>

# merge — the planner already verified checks, mergeState, and holds. No --delete-branch:
# the worktree still has the branch checked out. A failure touches nothing else.
gh pr merge <pr> --squash

# after a successful merge only — finish the issue, then the branches
ORCA worktree set --worktree "id:<child-id>" --workspace-status completed \
  --comment "work-epic · <run> · we-<n> · opencode · merged" --json
ORCA worktree rm --worktree "id:<child-id>" --json          # only when clean
gh api -X DELETE "repos/{owner}/{repo}/git/refs/heads/<branch>"   # 422 = already gone
git -C "$MAIN" branch -D "<branch>"                         # skip if the worktree was kept
git -C "$MAIN" branch -d "<orca-branch>"                    # Orca's own branch; -d refuses unmerged work
# worktree rm deletes the local branch only when it can prove it merged, which a squash merge
# defeats — hence the explicit branch -D (the PR is merged; nothing unique is lost).
# branch -d (lowercase) on Orca's own branch is deliberate: it refuses a branch holding commits
# the default branch lacks, which is the safety check.

# update_branch — GitHub merges the base into the PR branch server-side
gh pr update-branch <pr>

# post-merge main fast-forward, only while $MAIN is on the default branch
test "$(git -C "$MAIN" symbolic-ref --short HEAD)" = "$DEFAULT" &&
  git -C "$MAIN" fetch origin &&
  git -C "$MAIN" merge --ff-only "origin/$DEFAULT"
```

If the worktree is dirty or removal fails, do not discard anything: keep it, mark it unread, report
the path, and run only the remote delete (the local branch is still checked out). Branch cleanup
failing after a successful merge is reported, never an escalation.

The merge method is squash, and the repairer's merge commit is squashed away with the rest of the
branch. A failed `update-branch` is re-planned, not filed blind: the next pass reads the PR `DIRTY`
and the `repair` row owns it. A failed `gh pr merge` (a required check appeared, the base moved
between read and merge) is not retried blind — re-run the planner, which classifies the PR's new
state; a second merge failure on the same head is an escalation. `gh pr merge --auto` would
delegate the final trigger to GitHub, but it requires repo-level auto-merge and forfeits the merge
queue and the repair budget; keep the explicit loop. GitHub's own merge queue does the same job
where the plan allows it, but it is not available on every repository, and the pump must work on
all of them.

## Report format

One block per issue, one per PR review, one per repair, one per merge-pass action, then the
stopped/drained distinction, retained worktrees, and the decisions needed:

```
Run run_abc123 over #12 (opencode implements, claude reviews and fixes, 2 workers, squash):
  coordinator: <worktree-id> · in-review
  #21 we-21 (large): delivered → PR #34; reviewed by claude: 2 fixed (#41, #42 closed), 1 P2
    filed open (#43); merged, main ff'd; worktree removed
  #22 we-22: delivered → PR #35; clean review; worktree <id> in-review
  #23 skipped: blocked (blocked by #35)
  #24 we-24: delivered → PR #36; P1 finding #44 not fixed (needs a schema decision) — PR held,
    worktree <id> unread
  #26 skipped: stalled (branch fix/26-retry-budget pushed, no open PR)
  PR #36 wc-36 (opencode): conflict with origin/main repaired in the issue's worktree (gate:
    go test ./... — passed), no re-review
  PR #38 wc-38 (opencode): blocked (pkg/api rename vs #33's call sites) — coupling filed #46,
    PR parked, worktree <id> retained
  PR #39: checks failing, 2 repair attempts spent — parked as ci_failed
  merge pass: 2 merged, 1 update_branch, 1 conflict (PR #37, filed #45), 1 held, 1 ci_failed
  skipped totals: blocked 1, untriaged 0, claimed 0, in_review 0, stalled 1
  progress: 5/8 issues closed — 0 eligible remain, spawn budget 2; pump stopped, not drained
  retained worktrees: #24 <id> (held); #38 <id> (conflict); 0 reclaimable terminals
  decisions needed:
    #24 / PR #36 — finding #44 (P1): <one line>; close #44 to release the PR
    PR #38 — conflicts with #33's change; resolve by hand or re-scope
    PR #39 — CI red on <check> after two repairs: <reason>
```

"0 eligible remain" without "stopped, not drained" reads as a finished scope; the resolver's
`counts` is what keeps the two apart, which is the same distinction work-issue's `no_ready_work` vs
`not_eligible` protects. Likewise "N eligible remain, spawn budget 0" is a full backlog, not an
empty queue. PRs set aside on a spent CI budget when the pump stops are listed so the next run — or
the human — knows what is still in flight. A retained worktree with no reason is an omission: every
one is either held, conflicted, failed, blocked, or kept for a human's inspection, and each one
appears under the decisions needed.

## Script tests

The decision logic of the scripts — `pr_state.plan_pr`, `pr_state.schedule`,
`resolve_ready.classify`, and `repo_state`'s scope parser — is pure over hew and gh JSON and covered
by stdlib `unittest` files beside them:

```bash
python3 -m unittest discover <this skill's directory>/scripts
```

A change to a decision table, a skip reason, or a parser lands with the test case that pins it,
before the pump that depends on it is trusted. The review-once rule is pinned in
`test_pr_state.py`: a moved head is not re-reviewed, and an unfixed P1 holds without any second
round to escalate to.

## Worktree reliability notes

- **The issue worktree's branch is work-issue's.** Orca creates the worktree with a base branch;
  work-issue may create its conventional `fix|feat|chore/<n>-…` branch inside it. That is the
  checkout the reviewer and the repairer reuse; the unused Orca branch is cleaned up per
  [Lifecycle and cleanup](#lifecycle-and-cleanup).
- **A server-side `update_branch` moves the PR branch, not the issue's checkout.** A later reviewer
  or repairer must fast-forward the checkout to `origin/<branch>` first; a fast-forward failure is
  an `error`, not a reset.
