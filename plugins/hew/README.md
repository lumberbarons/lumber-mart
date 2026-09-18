# hew

Agent skills for tracking work in GitHub Issues through the
[hew](https://github.com/lumberbarons/hew) CLI, usable from any coding agent that loads skills
(Claude Code, opencode, codex).

## Overview

- **raise-issues** — turns structured review findings into hew issues, deduplicated against
  what is already tracked so a review can run repeatedly without re-filing the same work.
- **work-issue** — takes a tracked issue from `hew ready` to a draft PR, test-first, with the
  issue's own "Done when" checklist driving the tests.

Together they close the loop: a review files what is wrong, and the next run picks it up and
fixes it.

## Prerequisites

- [`hew`](https://github.com/lumberbarons/hew) on PATH, authenticated via `gh auth login`
- Run from a checkout of the target repository (`--repo owner/name` overrides detection)
- `hew init` once per repo, to create the convention labels

## Session hooks

`hew` can inject its primer (conventions, ready work, live state) at session start, so every
agent begins with tracker context without a manual `hew prime`:

```
hew hooks install opencode    # or claude, codex, cursor
hew hooks remove opencode     # undo
```

The installer writes a managed artifact and tags it `@hew-managed` — for opencode that is
`.opencode/plugins/hew-prime.js` (runs `hew prime` once per session and injects the output as
system context). Only the artifact's own header comment is documentation; edit the hook through
`hew hooks`, not by hand.

## Skills

| Skill | Description | Model-Invocable |
|-------|-------------|-----------------|
| `raise-issues` | File review findings as deduplicated GitHub issues | Yes |
| `work-issue` | Take a tracked issue from claimed to draft PR, test-first | Yes |

Skill names are agent-neutral. Agents that resolve skills by name (opencode, codex) call them
directly; Claude Code prefixes the plugin name (`/hew:work-issue`).

### Usage

```
raise-issues                       # file them
raise-issues --findings out/o11y.json --dry-run
raise-issues only P1 and P2

work-issue 42                      # a specific issue, or an epic to descend into
work-issue --batch                 # up to 3 issues, then verify them together
work-issue --batch 5               # a higher ceiling; sizing may still stop sooner
work-issue --dry-run
```

## Working an issue

`work-issue` follows the workflow hew prescribes rather than inventing one: `hew ready` →
`hew start` → branch → tests → push → `hew pr`. Two properties of that workflow do the heavy
lifting.

**Work ends at a PR.** `hew pr` composes the PR from tracker state with exactly one `Fixes #n`,
so the merge closes the issue and the change goes through review. `hew close` stays what it is
in hew — a human deciding no work was needed.

**`hew start` is a lock.** It refuses a claimed issue with exit 3, so two agents cannot take the
same issue and the loser simply moves down the queue. That is what makes an unattended run safe
to point at a shared backlog.

The `### Done when` checklist is what makes the test-first part more than ceremony: the
acceptance criteria already exist, written by whoever filed the issue and checked by whoever
reviews the PR. Behavioural items become failing tests before any implementation; structural
ones ("no call site still passes the raw header") become checks run against the diff, because a
unit test asserting the absence of a pattern is theatre.

Epics are trees, not work — given one, the skill descends to the next ready child, works exactly
that, and leaves the epic open for the next run.

## Working several at once

`--batch` works up to three issues in one run — each on its own branch, each its own PR — and
then merges them onto a throwaway branch and runs the quality gate over the combination.

That last step is the reason the mode exists. Every issue is branched from the default branch and
gated against it alone, so until the batch is assembled no tree has held two of the fixes at once.
Git catches the overlapping case by itself; what it waves through is two changes in different
files whose behaviours disagree — both branches green, both merging cleanly, the default branch
broken once they land. The integration branch is never pushed and never becomes a PR: it is a
check, and a failing one means two issues filed as independent are coupled, which gets filed as
its own issue rather than patched into either PR.

The ceiling is set before anything is claimed, sized from what the tracker already carries — the
paths in `### Where` and the items in `### Done when`, which are what the run actually spends
context on. An unbounded drain has no equivalent, on purpose: context fills silently, and the
first casualty is the combined verification at the end of the run.

## The review key

Every issue this skill files carries a key in its `### Where` section:

```
review-key: <skill>/<pattern>/<scope>
```

The key is the identity of a *finding*, not of a line of code, which is what makes it survive
the two things that change constantly — line numbers and the model's phrasing of a title.

- `skill` — which review produced it (`o11y`, `tests`, `docs`, `code`)
- `pattern` — the root-cause slug the review emitted, from the vocabulary each critique skill
  owns in its own `REFERENCE.md`, passed through unchanged
- `scope` — the deepest directory containing every affected file, derived mechanically from the
  file list rather than chosen, so two runs cannot anchor the same finding differently

Severity is deliberately excluded: it moves between runs, and identity must not.

Dedup then follows hew's own read order — `hew search` first, `hew list --json --bodies --state
all` when exhaustiveness matters, `hew show` only for a specific candidate — across open *and*
closed issues. A closed-as-completed match means the pattern regressed and is filed fresh with
`--discovered-from`; a closed-as-declined match is suppressed for good.

## Running unattended

Both skills are built to survive a scheduled loop.

`raise-issues`:

- `--findings <path>` takes a findings file instead of scraping conversation context
- `--non-interactive` removes every question and reports the outcome instead
- writes go through `hew apply`, which checkpoints each creation, so an interrupted run resumes
  without duplicating what already landed
- the final report distinguishes "found nothing" from "received nothing", so a broken pipeline
  cannot masquerade as a clean codebase

`work-issue`:

- `--non-interactive` removes every question; `--json <path>` writes a machine-readable outcome
- one issue per invocation by default, so each tick costs one reviewable PR rather than ten
- `--batch` raises that to a bounded few, sized before anything is claimed — there is no
  unbounded mode, because the combined verification is what an overlong run loses first
- `hew start`'s exit 3 keeps parallel runs off each other's work without any coordination
- a run that cannot verify its change pushes the branch, opens no PR, and leaves the issue
  claimed — so the next tick moves on instead of retrying a broken change forever
- `status` separates the four ways to finish with zero PRs: `no_ready_work` (drained),
  `not_eligible` (something else holds the queue), `failed`, and `error` — plus
  `integration_failed`, the one failure that leaves sound PRs behind and must not be retried

The whole pipeline runs unattended end to end:

```
review-tests --json out/tests.json --non-interactive   # critique plugin
raise-issues --findings out/tests.json --non-interactive
work-issue --non-interactive --json out/work.json
```
