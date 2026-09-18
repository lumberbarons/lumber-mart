# Reference

Resolver schema, prompt templates, naming, timeout budgets, and report format for `work-epic`.

## Resolver output

One JSON object from `scripts/resolve_ready.py <epic> [--repo owner/name]`:

```json
{
  "epic": 12,
  "title": "Epic title",
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

- `eligible` — spawn order: priority first (`P0` best, missing last), ties toward the oldest
  `createdAt`. `where`/`doneWhen` are bullet counts under the body's `### Where` /
  `### Done when` sections; `large` is work-issue's sizing rule (>3 paths, >5 done-when) —
  surfaced so the report can say why a large child might be worth a `--workers 1` moment.
- `skipped` — open children left behind, `reason` in `blocked | untriaged | claimed`. `claimed`
  is decided against the current `gh api user` login; when it cannot be determined the script
  treats every in-progress child as claimed by someone else (fail-safe).
- Exit codes: `0` success (eligible may be empty), `1` runtime error, `2` usage error or
  "not an epic".

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

## Reviewer findings handling

Read the findings JSON the reviewer wrote. The decision is on the worst severity present:

- file absent/unparseable → escalate (an unread review is not a clean review)
- no findings, or P3-only → `gh pr ready <pr>` and notify
- any P1/P2 → post a comment and notify; stays draft:

```bash
gh pr comment <pr> --body "$(cat <<'EOF'
review-code findings (work-epic reviewer agent):

### P1 — <finding title>
<location> — <consequence>. Fix: <prescription>.

### P2 — <finding title>
...
EOF
)"
```

Keep the finding's own title/location/fix text; the comment is a relay, not a rewrite.

## gh commands used

- `gh api user --jq .login` — resolver's claim-ownership check (read-only)
- `gh pr view <pr> --json headRefName` — reviewer checkout target
- `gh pr ready <pr>` — the pump's "agent-reviewed, awaiting human" signal
- `gh pr comment <pr> --body ...` — P1/P2 relay

## Report format

One block per worker, then the stopped/drained distinction, then escalations:

```
Epic #12 pumped (2 workers, opencode):
  #21 we-21: delivered → PR #34; reviewer clean, marked ready
  #22 skipped: blocked (blocked by #35)
  skipped totals: blocked 1, untriaged 0, claimed 0
  epic progress: 5/8 children closed — 0 eligible remain; pump stopped, not drained
  escalations: we-25 blocked on a permission dialog (notification raised)
```

"0 eligible remain" without "stopped, not drained" reads as a finished epic; the resolver's
`counts` is what keeps the two apart, which is the same distinction work-issue's
`no_ready_work` vs `not_eligible` protects.
