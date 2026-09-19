# Reference

Resolver and merge-pass schemas, prompt templates, findings filing, naming, timeout budgets,
and the report format for `work-epic`.

## Resolver output

One JSON object from `scripts/resolve_ready.py <epic> [--repo owner/name]`:

```json
{
  "epic": 12,
  "title": "Epic title",
  "mainCheckout": "/abs/path/to/repo",
  "defaultBranch": "main",
  "eligible": [
    { "number": 21, "title": "child b", "priority": "P1", "type": "task",
      "where": 2, "doneWhen": 3, "large": false }
  ],
  "skipped": [
    { "number": 22, "title": "child c", "reason": "blocked", "detail": "blocked by #35" }
  ],
  "counts": { "eligible": 1, "blocked": 1, "untriaged": 0, "claimed": 0, "closed": 4 }
}
```

- `mainCheckout` — the primary worktree (`git worktree list --porcelain`'s first entry). Every
  spawn (`--cwd`), every branch update, and every post-merge fast-forward happens here; an
  orchestrator inside a worktree must not nest worktrees under itself. `null` when
  undeterminable — fall back to `$PWD` and say so in the report.
- `defaultBranch` — origin's HEAD branch, or `null`; the branch-update and ff targets.
- `eligible` — spawn order: priority first (`P0` best, missing last), ties toward the oldest
  `createdAt`. `where`/`doneWhen` are bullet counts under the body's `### Where` /
  `### Done when` sections; `large` is work-issue's sizing rule (>3 paths, >5 done-when) —
  surfaced so the report can say why a large child might be worth a `--workers 1` moment.
- `skipped` — open children left behind, `reason` in `blocked | untriaged | claimed`. `claimed`
  is decided against the current `gh api user` login; when it cannot be determined the script
  treats every in-progress child as claimed by someone else (fail-safe).
- Exit codes: `0` success (eligible may be empty), `1` runtime error, `2` usage error or
  "not an epic".

## Merge-pass output

One JSON object from `scripts/pr_state.py <epic> [--repo owner/name]
[--block-on P1|P2|none] [--no-review]`:

```json
{
  "epic": 12,
  "blockOn": "P1",
  "defaultBranch": "main",
  "mainCheckout": "/abs/path/to/repo",
  "prs": [
    { "number": 34, "issue": 21, "issueState": "open", "branch": "fix/21-child-b",
      "head": "9f2c…", "draft": true, "mergeState": "BEHIND", "checks": "pass",
      "reviewRounds": 1, "reviewedHead": "40ba…", "worstOpenFinding": "P2",
      "action": "update_branch" }
  ],
  "unmatched": [ { "number": 99, "scrapedIssue": null, "action": "outside_epic" } ],
  "counts": { "ready_and_merge": 0, "update_branch": 1, "re_review": 0, "hold_p1": 0,
              "escalate": 0, "conflict": 0, "wait": 0, "outside_epic": 1 }
}
```

- PRs are matched to children by scraping the conventional issue number off the head branch
  (`fix|feat|chore/<n>-…`, work-issue's naming rule). A PR that scrapes to nothing, or to an
  issue that is not this epic's child, lands in `unmatched` — listed for visibility, never
  touched.
- `checks` collapses `statusCheckRollup`: `pass`, `fail`, `pending`, or `none` (no checks
  configured — vacuously green; branch protection remains the enforcement layer).
- `reviewRounds` counts this pump's findings comments on the PR (bodies containing the
  reviewer-agent marker); `reviewedHead` is the head SHA recorded in the latest one. A draft
  PR whose head no longer matches is stale — `re_review`.
- `worstOpenFinding` is the worst severity among open findings children carrying
  `review-of: #<issue>` in their body (see the filing flow below). At or above `--block-on`
  it blocks; below, it just becomes tracked work.
- Decision order: issue closed → `wait` · `DIRTY` → `conflict` · `BEHIND` → `update_branch` ·
  two rounds with an open blocker → `escalate` · stale review → `re_review` · open blocker →
  `hold_p1` · draft with no review comment yet → `wait` · checks green and
  `mergeState` in `CLEAN | HAS_HOOKS | DRAFT` → `ready_and_merge` · otherwise `wait`.
  Under `--no-review` the review steps collapse and CI is the only gate.
- Exit codes: `0` success (prs may be empty), `1` runtime error, `2` usage error or "not an
  epic".

## Prompt templates

Substitute `<n>` (issue), `<path>` (outcome/findings file), `<branch>` (PR head), `<pr>`
(PR number). Send the literal text; the skills load by name inside opencode, by file path inside
codex.

### Worker — opencode

```text
Use the work-issue skill. Work issue #<n> exactly as it specifies, with flags
--non-interactive --json '<path>'. When it finishes, report the outcome per its own Step 9.
Do not interact with the user.
```

### Worker — codex

```text
Read ~/.config/opencode/skills/work-issue/SKILL.md and its REFERENCE.md. Follow them
exactly for issue #<n> with flags --non-interactive --json '<path>'. Ask nothing; write
the outcome file.
```

### Reviewer — opencode

```text
Check out PR #<pr>'s head branch <branch> (use worktree_checkout if you have it, else
git fetch + git checkout <branch>). Then use the review-code skill with flags
--non-interactive --json '<path>' — its default branch-vs-default scope is exactly this
PR's diff. Report findings; do not modify code.
```

### Reviewer — codex

```text
git fetch && git checkout <branch> first. Then read
~/.config/opencode/skills/review-code/SKILL.md and its REFERENCE.md and run it with
--non-interactive --json '<path>'. Report findings; do not modify code.
```

Both worker prompts deliberately route output through `--json`: herdr's settled states prove the
agent stopped; the file says what happened. Both reviewer prompts deliberately checkout-first:
`review-code`'s default scope is branch vs default, which on the PR head is the PR's diff.

## Findings filing (autonomous mode)

The reviewer's findings file (critique's FINDINGS.md shape) becomes epic children:

```bash
uv run --no-project <raise-issues skill dir>/scripts/findings_to_plan.py \
  "$OUTDIR/wr-<pr>.json" --parent <epic> --reviewed-issue <n> --reviewed-pr <pr> \
  --out "$OUTDIR/wr-<pr>.plan.jsonl"
hew apply "$OUTDIR/wr-<pr>.plan.jsonl" --dry-run
hew apply "$OUTDIR/wr-<pr>.plan.jsonl"
```

The converter derives each line's `review-key: <skill>/<pattern>/<scope>` mechanically and
stamps `review-of: #<n> (PR #<pr>)` into `where`. Before applying, apply raise-issues' Step 3
dedup table against those keys — `hew search "review-key: <key>"` spans open and closed, so a
finding whose fix merged before is re-filed as a regression (`--discovered-from`), and one a
human declined stays suppressed. Drop suppressed lines from the plan before `hew apply`.

Each findings child is filed `blocked-by` the reviewed issue, so a below-`--block-on` finding's
fix unblocks exactly when the PR merges and the defect exists on main. An at-or-above
`--block-on` finding additionally holds its PR: the pump never un-holds — the human closes the
finding child (finding accepted) or fixes the branch, and the next pass re-reviews the new head.

P1 findings are also relayed to the PR itself — the hold's public reason and the marker the
merge pass reads back:

```bash
gh pr comment <pr> --body "$(cat <<'EOF'
review-code findings (work-epic reviewer agent):

### P1 — <finding title>
<location> — <consequence>. Fix: <prescription>.

reviewed-head: <head sha>
EOF
)"
```

Keep the finding's own title/location/fix text; the comment is a relay, not a rewrite. The
`reviewed-head:` line is identity, like `review-key:` — `pr_state.py` parses it to detect a
stale review, so it must survive verbatim. `reviewRounds` counts these comments; at two rounds
with a still-open blocker the planner says `escalate` and the pump stops automating.

## Naming

Agent names must match `[a-z][a-z0-9_-]{0,31}` and be unique among live agents. Workers are
`we-<issue-number>`, reviewers `wr-<pr-number>`. The prefix doubles as the ownership rule:
an orchestrator inspects and closes only names with its own prefixes.

## Timeout budgets

`herdr agent wait <name>` without `--until` settles on `idle`, `done`, or `blocked`. Size the
reaping loop like this:

- **Single wait timeout:** ~10 minutes. On timeout, `herdr agent get <name>`; if still
  `working`, wait again.
- **Hard per-worker budget:** ~2 hours of continuous `working`. Beyond it, `agent read` the
  worker, escalate via `herdr notification show ... --sound request`, and keep it un-closed
  rather than killing a run that may be legitimately long.
- **`blocked`:** notify once per worker, not on every pass — re-notifying on each poll turns
  the escalation channel into spam.
- **`unknown`:** never counts as settled. `herdr agent explain <name>` and `agent read` before
  believing anything about it.
- **CI wait (merge pass):** poll `pr_state.py` on a ~2-minute cadence; a PR with no state
  change for ~60 minutes of continuous `wait` is escalated and set aside — the pump moves on
  and the next pass reaps it if CI recovers.

## Merge-pass commands

Per `pr_state.py` action, executed on `$MAIN` (the resolver's `mainCheckout`) unless the
action says otherwise:

```bash
# ready_and_merge — the planner already verified checks, mergeState, and holds
gh pr ready <pr>                     # only when still draft
gh pr merge <pr> --<method> --delete-branch

# update_branch — on the PR branch (its own checkout/worktree)
git fetch origin
git merge --no-edit "origin/$DEFAULT"
git push

# post-merge main fast-forward
git -C "$MAIN" merge --ff-only "origin/$DEFAULT"
```

`--method` is `--merge-method`'s value (default `squash`). Merge-time conflicts surface as
`conflict` on the next pass — never resolved into the PR by hand. `gh pr merge --auto` would
delegate the final trigger to GitHub, but it requires repo-level auto-merge and forfeits the
`update_branch` step and the escalation budgets; keep the explicit loop.

## gh commands used

- `gh api user --jq .login` — resolver's claim-ownership check (read-only)
- `gh pr list --state open --json …` / `gh pr view <pr> --json comments` — the planner's reads
- `gh pr ready <pr>` — draft→ready before an automated merge
- `gh pr merge <pr> --<method> --delete-branch` — the bounded merge
- `gh pr comment <pr> --body ...` — P1 relay with the `reviewed-head:` marker

## Report format

One block per worker, one per merge-pass action, then the stopped/drained distinction and
escalations:

```
Epic #12 pumped (2 workers, opencode, block-on P1, squash):
  #21 we-21: delivered → PR #34; clean review, merged (squash), main ff'd
  #22 we-22: delivered → PR #35; P2 finding filed as #41 (blocked by #22), merged
  #23 skipped: blocked (blocked by #35)
  #24 we-24: delivered → PR #36; P1 finding #44 filed — PR held, human notified
  merge pass: 2 merged, 1 update_branch, 1 conflict (PR #37, filed #45), 1 held
  skipped totals: blocked 1, untriaged 0, claimed 0
  epic progress: 5/8 children closed — 0 eligible remain; pump stopped, not drained
  escalations: we-25 blocked on a permission dialog (notification raised)
               PR #37 conflicts with #23's branch — filed #45, never auto-resolved
```

"0 eligible remain" without "stopped, not drained" reads as a finished epic; the resolver's
`counts` is what keeps the two apart, which is the same distinction work-issue's
`no_ready_work` vs `not_eligible` protects. PRs parked on `wait` when the pump stops are
listed with their counts so the next run — or the human — knows what is still in flight.

## Script tests

Both scripts' decision logic is importable and side-effect free; a change to the decision
table or the parsers is verified with `uv run --no-project python -` importing the module and
asserting on its functions before the pump that depends on it is trusted.
