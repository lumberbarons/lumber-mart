---
name: work-issue
description: Take a hew-tracked GitHub issue from claimed to draft PR, test-first — select from `hew ready`, claim it, branch, drive the issue's own "Done when" checklist as tests, verify, push, and open the PR with `hew pr`. Use whenever the user wants a tracked issue worked, fixed, implemented, or delivered: "work the next issue", "fix #42", "implement that bug", "pick up the next ready item", "what's ready — go do it", "fix a few bugs", "drain the backlog". Use it after the raise-issues skill files findings, and inside any scheduled or looping agent that works a hew backlog unattended. Handles bug, task, and enhancement issues; `--batch` works several in one run and verifies them together; given an epic it descends to the next ready child rather than working the epic directly.
argument-hint: "Optional issue number, or flags: --batch [n], --non-interactive, --json <path>, --dry-run"
---

# Work Issue

One issue, from `hew ready` to a draft PR, with the issue's acceptance criteria driving the
tests rather than trailing them.

> [!IMPORTANT]
> [REFERENCE.md](REFERENCE.md) carries the outcome-file schema, the quality-gate table, branch
> and commit conventions, and a worked example. Read it before the verify step.

The `hew prime` primer — injected at session start — already carries the workflow, the
conventions, and the command surface. This skill assumes it and does not restate it. If it is
not in context, the injection is per-repo and optional: run `hew prime` first.

Two of its rules do the most work here, and both are easy to undo by accident:

**Closing is not delivering.** What closes a delivered issue is the merge, through the `Fixes #n`
that `hew pr` composes. Reaching for `hew close` on work you actually did skips review entirely
and records the opposite of what happened — which is what the primer's restriction on it is
protecting.

**Exit 3 is a feature.** `start` refusing a claimed issue is what makes this safe to run on a
schedule beside another agent: two runs cannot take the same issue, and the loser just moves
down the queue. `--force` is there for a human clearing a stuck claim; using it here would
delete the only coordination the loop has.

## Arguments

Your input may carry flags alongside an issue number. Strip the flags; what remains is the
target.

- **`<n>`** — work issue `n`. If it is an epic, descend to its next ready child.
- **`--batch [n]`** — work up to `n` issues in one run, then verify them together. `n` defaults
  to 3; the size rule in Step 1 can lower it but never raises it.
- **`--non-interactive`** — ask nothing. Where this skill would prompt, report the outcome and
  stop.
- **`--json <path>`** — additionally write the outcome file described in
  [REFERENCE.md](REFERENCE.md). Off by default; the report is unchanged either way.
- **`--dry-run`** — resolve the target and show the plan, then stop without claiming anything.
- **anything else** — implementation guidance that applies throughout ("keep it to the handler",
  "no new dependencies").

## Prerequisites

`hew` on PATH and authenticated — exit code 4 from any `hew` command means run `gh auth login`,
and unattended that is an `error` outcome, not an empty queue.

The working tree must be clean before claiming anything. Uncommitted changes would land in this
issue's commit and silently widen its diff. Stop and say so rather than stashing on the user's
behalf.

## Step 1 — Resolve the target

Selection has to be deterministic, because a loop that picks differently on each tick cannot be
reasoned about from its logs.

**No issue number:** take the first eligible entry from `hew ready`. That list is
priority-sorted, so the first entry is the highest-priority ready item and ties break toward the
oldest — walking down it *is* the selection rule. Do not re-rank by what looks quick, tractable,
or interesting. An agent that picks its favourites leaves P1s rotting behind a comfortable run of
P3s, and once that happens the priority label has stopped meaning anything to anyone who sets it.

Skipping an ineligible entry (below) continues down the same order, so what you end up with is
always the highest-priority item actually available to you.

`hew ready` lists non-epic issues only, so this path never selects an epic — descending into one
requires being asked for it by number. An epic's own ready children are ordinary issues and
appear in the queue on their own merits, so nothing is missed by leaving the wrapper out.

Empty output means the backlog is genuinely drained — that is `no_ready_work`, a real result, and
worth distinguishing from every other way of finishing with nothing. Report it and stop; do not
go looking for an epic to descend into because the queue looked disappointing. Choosing to open
up an epic is a decision about what to work on next, and an empty queue is exactly the moment a
human would want to make it rather than discover it was made for them.

**An issue number:** `hew show <n> --json`. If `epic` is true, descend (below). If it is closed,
say so and stop — reopening is a human decision.

**Epic descent — only when an epic was named explicitly.** This path is reachable when you are
invoked with an explicit issue number `n` that is an epic, never from the no-argument path above. The primer's
rule against working an epic directly leaves the question of what to do instead.
`hew list --epic <n> --json` returns the children with `state`, `inProgress` and
`openBlockers`. Filter to `state: "open"` — unlike a bare `hew list`, the `--epic` form returns
closed children too — drop any with open blockers, then **sort what remains by priority
yourself** and take the top one. Prefer this over `hew epic status`, which renders progress but
not blockers.

Sorting explicitly matters here in a way it does not above: `hew ready` is documented as
priority-sorted so taking its first entry is enough, while `--epic` carries no such guarantee.
Trusting its order would let an epic whose children were filed out of priority order get worked
out of priority order, and nothing downstream would ever flag it.

Report the epic's progress, work exactly one child, and leave the epic open; the next invocation
walks to the next child. If every child is closed, the epic is finished and a human should close
it — say so rather than closing it yourself.

`--batch` does not change that, and the reason is worth stating so nobody expects otherwise: a
child's blockers clear when its PR *merges*, not when this run pushes it. In a dependency chain
the second child is therefore still blocked for the entire run, and a batch aimed at an epic would
work one child and then correctly find nothing eligible. Children with no dependency between them
are ordinary ready issues and reach a batch through `hew ready` on their own merits.

**Eligibility.** Skip and move to the next candidate when:

| Condition | Why, and what to report |
|---|---|
| `inProgress` and assigned to someone else | Another agent or human holds it. Cheap to skip here, though the claim in Step 2 is the authority — this listing can be stale by the time you act on it. |
| `untriaged` (no priority or no type) | The `--priority` the primer says `start` needs is a triage judgement, not a default. Interactively, ask. Unattended, skip and count it — a loop that assigns priorities to get past the prompt is inventing the very signal the queue sorts on. |
| Open blockers | `hew ready` already excludes these; if one arrived via an explicit number, name the blockers and stop. |

If ready work exists but none of it is eligible, that is **not** an empty backlog. Report
`not_eligible` and name the reason — a run that reports "nothing to do" while three issues sit
claimed by a crashed agent reads as a drained queue and hides the stall indefinitely.

**Sizing the batch.** Under `--batch`, decide the whole batch here, before claiming anything.
Take the first `n` eligible candidates in queue order, `hew show` each, and size it from the
body:

> An issue whose `### Where` names more than three paths, or whose `### Done when` carries more
> than five items, is large. Work it alone and stop — it is the batch.

The bound has to be set in advance because the skill cannot measure its own remaining context.
There is no readout it can consult, and an agent compacts its context rather than failing, so a
run that takes on too much does not error — it quietly loses detail. What it loses first is the end of
the run, which is exactly where the integration pass lives. A combined verification performed
against a compacted context is worse than none, because it reports a check nobody actually made.

So size from what the tracker already carries. `### Where` counts the files that will be read
and `### Done when` counts the tests that will be written and run; those are the two things that
actually spend the run. Counting them is deterministic, which estimating is not.

Queue order decides the batch — resist grouping by area to cluster likely conflicts, or spreading
across areas to avoid them. Determinism is worth more here than either, and Step 8 finds what it
finds.

**Sizing fixes how many, not which.** The ceiling is set once, here, because context is spent by
the run as a whole. The issues themselves are still resolved one at a time — each iteration
returns to this step — so the run stays on the highest-priority remaining work and picks up
anything filed or re-prioritised while the previous issue was in flight. A batch pinned to a list
captured at the start would lose that, and it is the more valuable of the two properties.

So the size rule applies twice: once over the first `n` candidates to set the ceiling, and again
to whatever each iteration actually resolves. An issue that comes back large is worked and then
ends the batch, however much of the ceiling is left.

Stop here under `--dry-run`, after showing the resolved target — under `--batch`, the whole
planned batch and the size that justified it.

## Step 2 — Claim it

```bash
hew start <n>
```

The exit code is the whole answer, and it is authoritative in a way that reading `assignees`
first is not — between a read and a claim there is a window for another agent to slip in, and
the claim itself has no such gap:

- **0** — yours. Proceed.
- **3** — someone else took it. The lock working, not an error: re-resolve from Step 1 rather
  than reporting a failed run.
- **5** — the claim was already yours, from an earlier run that did not finish. Resume rather
  than restart: check for a branch and commits from that attempt before redoing the work.

## Step 3 — Read the contract

```bash
hew show <n> --json
```

`body` is markdown in the sections the primer lists. How to read them is the part worth saying:

- **`### Where`** is a boundary, not a hint. Every path it names should appear in your final
  diff, and paths it does not name should not.
- **`### Fix`** / **`### Approach`** is a prescription. Follow it unless it is demonstrably
  wrong, in which case say why before diverging rather than quietly doing something else.
- **`### Done when`** is the acceptance checklist, and everything below is built on it.

**If `### Done when` is missing or empty, write one before touching any code**, and show it to
the user. Derive it from the Fix and the Where: each item must be verifiable by reading the
diff or running a command, never a restatement of intent. "Both parsers call a shared
`parseFrontmatterRaw`, and no delimiter-scanning remains in either" is a criterion. "Frontmatter
parsing is cleaned up" is a wish. An issue you cannot write acceptance criteria for is one you
do not understand well enough to implement — surface that instead of guessing.

## Step 4 — Branch

The name is the part that matters, because two things downstream read it: `hew pr` infers which
claimed issue the PR is for from the number in it, and warns when the prefix disagrees with the
issue type. Use `<prefix>/<n>-<slug>` — `bug` → `fix/`, `enhancement` → `feat/`, `task` →
`chore/`.

Where the branch comes from depends on how the session started:

- **Already isolated** — an agent worktree puts you on a branch the harness named itself
  (e.g. `worktree-feat+some-task` under Claude Code, `opencode/<slug>` under opencode): no issue
  number, no conventional prefix, so it satisfies neither reader above. Do not rename it; the
  harness tracks that branch for its own cleanup.
  Push to a well-named upstream instead, and let the names differ:

  ```bash
  git push -u origin HEAD:fix/42-write-commands-guard-closed
  ```

  `hew pr` resolves the PR head from the upstream ref, so the well-named branch is what reaches
  GitHub, the prefix check, and the reviewer.

- **Not isolated** — branch from the default branch yourself, so the PR carries this issue only.

Under `--batch`, reset to the default branch between issues and push each to its own remote
branch, so every PR carries one issue's diff:

```bash
git checkout -B <next> origin/<default>
```

Working the next issue on top of the last one instead would pile the batch into a single PR that
no one can review a piece of — which is the failure this reset exists to prevent, and it is worth
the cost below.

That cost lands in a worktree, where the two rules above genuinely collide: one worktree has one
checked-out branch, and a batch needs several. From the second issue onward the run is no longer
on the branch the harness named, and the harness tracks the branch it created rather than the run
that moved off it. Nothing is lost — each branch is pushed before the next is created, and the
PRs are already open — but the worktree ends on the last issue's branch and carries a local
branch per issue. Name them in the report so whoever cleans up knows what is there. Do not try to
satisfy both rules; only one of them can hold, and one unreviewable PR is the worse outcome.

Give those branches their conventional `<prefix>/<n>-<slug>` names locally. Past the first issue
there is no harness-named branch left to preserve, the local and upstream names may as well
agree, and Step 8 merges them by name.

## Step 5 — Implement, test-first

The reason TDD earns its keep here rather than being ceremony: **the `### Done when` checklist
is already the test list.** You are not inventing acceptance criteria, you are transcribing ones
a reviewer wrote and a human will check the PR against. Writing them as tests first means the
verify step at the end is re-running the same contract rather than forming a fresh opinion about
whether you are finished.

**Sort each checklist item into one of two kinds first** — treating both alike produces either
untestable tests or unverified claims:

- **Behavioural** — a claim about what the code *does*: a return value, a state change, an error
  surfaced, a flag honoured. These become tests. *"`set` on a closed issue fails without
  mutating"* is a test.
- **Structural** — a claim about what the code *is*: a call site removed, a helper shared, a
  pattern absent. These become checks you run against the diff — a grep, a build, a file read.
  *"No `fmt.Errorf` call in `internal/http` formats an error with `%s`"* is a grep, and writing a
  unit test for it would be theatre.

For the behavioural items, Red → Green → Refactor:

1. **Red.** Write tests that express those items, and run them to watch them fail *for the right
   reason* — the behaviour is absent, not the import is broken. A test that fails on a typo has
   told you nothing about the feature. Fix scaffolding until the failure is the real one.

   Good tests here look like the ones the issue implies: they assert on actual values and state
   rather than "no error thrown", they name the scenario (`TestSet_RefusesClosedIssue`, not
   `TestSet2`), they cover the happy path and at least one failure or edge case, and they hold
   after an internal refactor that does not change behaviour. If a test would pass against an
   empty implementation, it is not testing the issue.

2. **Green.** The minimal implementation that makes them pass. Stay inside `### Where`.

3. **Refactor.** Clean up with the tests green. Do not gold-plate — the checklist bounds what
   "done" means, and work beyond it is unreviewed scope in someone else's PR.

**TDD does not apply to everything, and forcing it is worse than skipping it.** Pure
configuration, migrations, documentation, static assets, CI manifests, and wiring with no
branching logic have nothing to assert about. Say which applied and why in the report; silently
skipping the tests and silently having nothing to test look identical from outside.

**Work discovered along the way goes in the tracker, not in this diff.** The primer gives the
sequence — search for duplicates, then create with `--discovered-from <n>`. Report the new number
and carry on. Fixing it inline instead buries an unrelated change in a PR nobody will think to
look for it in.

## Step 6 — Verify

Three checks, in this order, before anything is pushed:

1. **Every `### Done when` item.** Run the tests for the behavioural ones and the commands for
   the structural ones. Walk the list explicitly — an unchecked box is not done.
2. **The diff covers `### Where`.** `git diff <default-branch>...HEAD --name-only`. A file the
   issue named that you never touched means you solved a different problem than the one filed,
   or the issue's scope was wrong. Either way, stop and explain the gap rather than shipping
   past it.
3. **The repo's quality gate.** Detect it from the changed files — the language-to-command table
   is in [REFERENCE.md](REFERENCE.md). Run every gate that applies; a change touching Go and
   Terraform runs both.

A failure here is not something to work around. Fix it inside the issue's scope and re-run. If
it cannot be fixed inside that scope, that is a `failed` outcome: commit and push the branch so
the work is not lost and is inspectable, do **not** open the PR, and leave the issue claimed.
Leaving it claimed is deliberate — the next loop tick will hit exit 3, skip past it, and work
something else instead of retrying a broken change forever while a human wonders why the queue
stopped moving.

## Step 7 — Ship

```bash
git push -u origin HEAD:<prefix>/<n>-<slug>
hew pr --testing 'Added `TestSet_RefusesClosedIssue` and two siblings in `internal/cli/write_test.go`; `go test ./...` passes'
```

The primer covers what `hew pr` composes and that the branch has to be pushed first. `--testing`
is the one thing it cannot infer from the tracker, so supply it: a reviewer opening a draft PR
wants to know what was actually verified, not to reconstruct it from the diff.

Write the commands, test names, and paths in it as code spans. hew warns about unmarked code
text in composed bodies, but the reason to bother is that the PR body is the one thing here
written for a human in a browser rather than an agent in a terminal — and `go test -race ./...`
set in proportional prose loses exactly the characters that carry its meaning. The same applies
to any issue you file for discovered work.

Commit conventions are in [REFERENCE.md](REFERENCE.md). The short version: conventional subject
matching the branch prefix, and `Refs #<n>` rather than a second `Fixes #<n>` — the PR body
already carries the one closing reference, and a duplicate in a commit closes the issue on merge
by a path the reviewer did not see.

Do not run `hew close`.

Under `--batch`, go back to Step 1 and resolve the next issue, until the ceiling is reached or
the queue runs dry. When the batch is done, Step 8 verifies it as a whole.

## Step 8 — Integrate the batch

Skip this when the run delivered fewer than two issues; there is nothing to combine.

Every issue in the batch was branched from `origin/<default>` and gated against it alone, so at
this point **no tree has ever held two of these fixes at once**. Git catches the overlapping case
on its own — two changes to the same lines become a merge conflict. The case that survives is the
one it waves through: two changes in different files whose behaviours disagree, each branch green,
each merging cleanly, and the default branch broken once both land.

Merge them onto a throwaway branch and run the gate once:

```bash
git checkout -B integration/batch-<first>-<last> origin/<default>
git merge --no-ff <branch-1>
git merge --no-ff <branch-2>
git merge --no-ff <branch-3>
```

One merge at a time, in the order the issues were worked — not `git merge <b1> <b2> <b3>`, which
octopus-merges them and simply refuses the whole thing on any conflict. Sequential merges name
the branch that clashed, which is the difference between reporting a pair and reporting "the
batch broke".

Then the same quality gate Step 6 selected, over the union of the changed files.

**Nothing is pushed and no PR comes off this branch.** It is a check, not a deliverable — the
issues are already delivered through their own PRs, and a fourth PR containing all three diffs
would be exactly the unreviewable artifact Step 4 resets to avoid.

A conflict or a gate failure here does **not** invalidate the PRs. Each one verified against the
contract it was filed under, and each is still individually reviewable. What it means is that a
dependency exists that the tracker never recorded — so record it now:

- Name the specific pair, not the batch. "#47 and #51 both pass alone; together `TestRouteAuth`
  fails" is actionable; "the batch failed" sends someone to bisect it again.
- File it with `--discovered-from` naming both issues, and `--blocked-by` if the ordering is
  clear. The primer's dedup-before-filing sequence applies.
- Do **not** fix it inside either PR. The fix is bounded by neither issue's `### Where`, which
  makes it unreviewed scope in a PR someone has already started reading.

The run's status becomes `integration_failed` — every issue delivered, and the combination did
not hold. That is a different fact from `failed`, where an issue never reached a PR at all, and
collapsing the two would report a fixable coupling as a broken change.

A green pass is worth stating plainly too: it is the evidence that these fixes were genuinely
independent, which is the assumption every separate PR in the batch is resting on.

## Step 9 — Report

Say what happened in terms the next run — or a human reading a job log — can act on:

```
#42 fix: Write commands guard against closed targets
  Branch:   fix/42-write-commands-guard-closed
  Tests:    3 added (behavioural), 1 structural check (grep)
  Gate:     go build ./... + go test ./... — passed
  Done when: 3/3 verified
  PR:       #57 (draft)

Discovered: #58 (filed, --discovered-from 42)
```

Under `--batch`, one block per issue, then the integration result and a summary:

```
Batch: 3 of 3 delivered — 7 ready issues remain
Integration: integration/batch-42-51, gate passed — the three fixes hold together
Worktree left on fix/51-...; local branches fix/42-..., fix/47-..., fix/51-...
```

Say how many ready issues are left. Stopping at the run's own ceiling is success, not a drained
queue, and a caller reading `delivered` without a remaining count cannot tell the two apart —
the next tick is precisely the thing that needs to know.

Between issues, re-resolve from Step 1 rather than working down the list the ceiling was sized
from — re-reading `hew ready` each time is what keeps the run on the highest-priority remaining
work, including anything filed or re-prioritised while the previous issue was in flight. Stop on
the first `failed` outcome rather than continuing into work that may depend on it, and still run
Step 8 over whatever was delivered before it.

When `--json <path>` was given, also write the outcome file from [REFERENCE.md](REFERENCE.md).

## Running unattended

Under `--non-interactive` the skill asks nothing, which means every branch that would have ended
in a question has to end in a reported outcome instead. The `status` field carries which:

| status | Means |
|---|---|
| `delivered` | Every issue the run took was worked and a PR opened. Under `--batch`, `batch.remaining` says whether the queue is drained or the ceiling simply ran out. |
| `integration_failed` | Every issue reached a PR, but Step 8 could not merge or gate them together. The PRs stay open; the coupling is filed as its own issue. |
| `failed` | An issue was claimed and worked, but verification did not pass. Branch pushed, no PR, issue still claimed. |
| `no_ready_work` | `hew ready` was empty. The backlog is drained — a real result. |
| `not_eligible` | Ready work exists, but none of it could be taken: all claimed, or all untriaged. |
| `error` | The run could not start: not authenticated, not a git repository, dirty working tree. |

Four of these end with zero PRs and mean entirely different things — a drained backlog is
success, an unauthenticated CLI is an outage, and a queue of issues claimed by a dead agent is a
stall that will never clear itself. A caller that collapses them reports a broken pipeline as a
finished one, silently, until someone notices the PRs stopped arriving. Which is why `reason` is
required whenever `status` is not `delivered`.

`integration_failed` is the one that breaks that pattern, and deliberately: the PRs exist and are
individually sound, so it is not a stalled run to be retried. It is a signal that two issues were
filed as independent and are not. Retrying changes nothing; reviewing the pair does.

One issue per invocation is still the default, for the same reason the claim is a lock: each tick
takes exactly one item, a bad change costs one reviewable PR rather than ten, and the queue drains
at a rate a human can keep up with. `--batch` trades some of that for a combined verification the
single-issue path cannot offer, and its ceiling is what keeps the trade bounded — which is why
there is no flag for an unbounded run. A queue drained without one degrades exactly where it can
least afford to, and reports a green integration pass it never really made.
