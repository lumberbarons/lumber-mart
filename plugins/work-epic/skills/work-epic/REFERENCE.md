# Reference

Resolver and merge-pass schemas, prompt templates, the review-round comment, findings filing,
naming, timeout budgets, and the report format for `work-epic`.

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

- `mainCheckout` — the primary worktree (`git worktree list --porcelain`'s first entry). Every
  spawn (`--cwd`) and every post-merge fast-forward happens here; an orchestrator inside a
  worktree must not nest worktrees under itself. `null` when undeterminable — fall back to
  `$PWD` and say so in the report.
- `defaultBranch` — origin's HEAD branch, falling back to GitHub's default branch; `null` when
  neither answers. The ff target and the base every PR must target.
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
[--block-on P1|P2|none] [--no-review] [--allow-no-checks] [--resolve-conflicts]`
(flags in any position):

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
  blocker is open, and fewer than two failed attempts are recorded; otherwise `conflict` · two
  rounds with an open blocker → `escalate` · open
  blocker → `hold` · ready PR behind (`behindBy` > 0 or `BEHIND`) → `update_branch` · stale
  draft → `re_review` · no review round → `wait` · checks not green → `wait` · draft →
  `mark_ready` · `behindBy` unknown → `wait` · `CLEAN | HAS_HOOKS` → `merge` · `BLOCKED` →
  `protected` · otherwise `wait`. A hold comes before `update_branch` on purpose, and drafts are
  never updated: moving a held or draft PR's head spends a review round on nothing but a merge
  from main, for a PR that is not next to merge anyway. Under `--no-review` the review rows are
  skipped and CI is the only gate — findings don't suppress `reconcile` either.
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
- Exit codes: `0` success (prs may be empty), `1` runtime error, `2` usage error or "not an
  epic".

## Prompt templates

Substitute `<n>` (issue), `<pr>` (PR number), `<path>` (outcome/findings file), `<default>`
(origin's default branch), and — for codex, which has no skill loader — `<work-issue dir>` /
`<review-code dir>`: the installed skill directories, resolved the same way as this skill's own
(the directory holding that skill's `SKILL.md`; work-issue ships in the hew plugin, review-code
in critique). Send the literal text; the skills load by name inside opencode, by file path
inside codex.

### Worker — opencode

```text
Use the work-issue skill. Work issue #<n> exactly as it specifies, with flags
--non-interactive --json '<path>'. When it finishes, report the outcome per its own Step 9.
Do not interact with the user.
```

### Worker — codex

```text
Read <work-issue dir>/SKILL.md and its REFERENCE.md. Follow them exactly for issue #<n>
with flags --non-interactive --json '<path>'. Ask nothing; write the outcome file.
```

### Reviewer — opencode

```text
Check out PR #<pr>'s head (use worktree_checkout if you have it, else gh pr checkout <pr>).
Then use the review-code skill with flags --non-interactive --json '<path>' — its default
branch-vs-default scope is exactly this PR's diff. Report findings; do not modify code.
```

### Reviewer — codex

```text
gh pr checkout <pr> first. Then read <review-code dir>/SKILL.md and its REFERENCE.md and
run it with --non-interactive --json '<path>'. Report findings; do not modify code.
```

### Reconciler — both kinds

There is no reconciler skill to load: the prompt carries the whole contract, and opencode and
codex receive the same literal text.

```text
Reconcile PR #<pr>'s conflict with origin/<default>. Issue #<n> is the change the PR carries;
read it with `hew show <n>` when its intent is not clear from the diff.

1. `git fetch origin`, then `gh pr checkout <pr>`.
2. `git merge origin/<default>`.
3. For each conflicted file, reconcile both sides' intent: the PR side is issue #<n>'s change,
   the incoming side is already-merged work. Combine both when they are compatible; when they
   contradict each other in behaviour — not just in text — stop and write status
   "irreconcilable" with the clashing files and why. Never drop one side wholesale, never guess.
4. Run the quality gate the changed files select (work-issue's REFERENCE.md table) over the
   union of files the merge touched. A failing gate is "irreconcilable"; do not push.
5. Commit the merge and `git push`. Never `--force`, never rebase, never touch a branch other
   than this PR's.
6. Write '<path>' as JSON:
   { "status": "resolved" | "irreconcilable" | "error", "head": "<sha after the push>",
     "reason": "<why, when not resolved>", "gate": "<command and result>" }
Ask nothing and do not interact with the user.
```

Both worker prompts deliberately route output through `--json`: herdr's settled states prove the
agent stopped; the file says what happened. Both reviewer prompts deliberately checkout-first:
`review-code`'s default scope is branch vs default, which on the PR head is the PR's diff. The
reviewer runs in its own isolated session (Step 5), so the checkout never touches `$MAIN`. The
reconciler's prompt is its whole contract — nothing loads a skill for it — and the pump trusts
only its outcome file: the head is verified, the PR is un-readied, and the new head re-reviewed.

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

# irreconcilable or failed — the planner counts these toward the two-attempt cap
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
  "$OUTDIR/wr-<pr>.json" --parent <epic> --reviewed-issue <n> --reviewed-pr <pr> \
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

## Naming

Agent names must match `[a-z][a-z0-9_-]{0,31}` and be unique among live agents. Workers are
`we-<issue-number>`, reviewers `wr-<pr-number>`, reconcilers `wc-<pr-number>`. The prefix
doubles as the ownership rule: an orchestrator inspects and closes only names with its own
prefixes.

## Timeout budgets

`herdr agent wait <name>` without `--until` settles on `idle`, `done`, or `blocked`. Size the
reaping loop like this:

- **Single wait timeout:** ~10 minutes. On timeout, `herdr agent get <name>`; if still
  `working`, wait again.
- **Hard per-worker budget:** ~2 hours of continuous `working`. Beyond it, `agent read` the
  worker, escalate via `herdr notification show ... --sound request`, and keep it un-closed
  rather than killing a run that may be legitimately long.
- **Hard per-reviewer budget:** ~1 hour of continuous `working`, handled the same way. A
  review is read-only and bounded by one PR's diff; one running this long is stuck.
- **Hard per-reconciler budget:** ~1 hour of continuous `working`, handled the same way. A
  reconciliation is bounded by one PR's conflict plus the gate; one running this long is stuck.
- **`blocked`:** notify once per agent, not on every pass — re-notifying on each poll turns
  the escalation channel into spam.
- **`unknown`:** never counts as settled. `herdr agent explain <name>` and `agent read` before
  believing anything about it.
- **CI wait (merge pass):** poll `pr_state.py` on a ~2-minute cadence; a PR with no state
  change for ~60 minutes of continuous `wait` is escalated and set aside — the pump moves on
  and the next pass reaps it if CI recovers. `queued` is not a `wait`: it has no budget of its
  own and moves or parks with the queue head.

## Merge-pass commands

Per `pr_state.py` action. None of them checks out a PR branch locally:

```bash
# mark_ready — flips the draft so the next pass sees the real mergeState
gh pr ready <pr>

# merge — the planner already verified checks, mergeState, and holds
gh pr merge <pr> --<method> --delete-branch

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
- `gh pr checkout <pr>` — the reviewer's and reconciler's checkout, inside its own isolated
  session
- `gh pr comment <pr> --body ...` — the review-round and reconciliation comments
- `gh pr ready <pr>` — draft→ready, after a passing review or on `mark_ready`
- `gh pr ready --undo <pr>` — back to draft after a reconciliation, so the new head is re-reviewed
- `gh pr update-branch <pr>` — bring the queue head up to date, server-side
- `gh pr merge <pr> --<method> --delete-branch` — the bounded merge

## Report format

One block per worker, one per reconciler run, one per merge-pass action, then the
stopped/drained distinction and escalations:

```
Epic #12 pumped (2 workers, max 4 open PRs, opencode, block-on P1, squash, resolve-conflicts):
  #21 we-21: delivered → PR #34; clean review, merged (squash), main ff'd
  #22 we-22: delivered → PR #35; P2 finding filed as #41 (blocked by #22), merged
  #23 skipped: blocked (blocked by #35)
  #24 we-24: delivered → PR #36; P1 finding #44 filed — PR held, human notified
  #26 skipped: stalled (branch fix/26-retry-budget pushed, no open PR)
  PR #36 wc-36: reconciled vs origin/main (gate: go test ./... — passed) — re-drafted, reviewer spawned
  PR #38 wc-38: irreconcilable (pkg/api rename vs #33's call sites) — coupling filed #46, PR parked
  merge pass: 2 merged, 1 update_branch, 1 conflict (PR #37, filed #45), 1 held
  skipped totals: blocked 1, untriaged 0, claimed 0, in_review 0, stalled 1
  epic progress: 5/8 children closed — 0 eligible remain, spawn budget 2; pump stopped, not drained
  escalations: we-25 blocked on a permission dialog (notification raised)
               PR #37 conflicts with #23's branch — reconciliation attempts spent, filed #45, parked
```

"0 eligible remain" without "stopped, not drained" reads as a finished epic; the resolver's
`counts` is what keeps the two apart, which is the same distinction work-issue's
`no_ready_work` vs `not_eligible` protects. Likewise "N eligible remain, spawn budget 0" is a
full backlog, not an empty queue. PRs set aside on a spent CI budget when the pump
stops are listed so the next run — or the human — knows what is still in flight.

## Script tests

The decision logic of the scripts — `pr_state.plan_pr`, `pr_state.queue_reconciles`,
`resolve_ready.classify` — is pure over hew and gh JSON and covered by stdlib `unittest` files
beside them:

```bash
python3 -m unittest discover <this skill's directory>/scripts
```

A change to a decision table, a skip reason, or a parser lands with the test case that pins it,
before the pump that depends on it is trusted.
