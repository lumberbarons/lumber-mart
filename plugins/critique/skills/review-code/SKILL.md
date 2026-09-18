---
name: review-code
description: Reviews code for design issues that static analysis misses — single responsibility, abstraction levels, testability, meaningful naming, API design, and error-handling strategy. Use when asked to review code, audit a module, check architecture or design, find design problems, improve code quality, or look at testability/coupling/SRP. Also invoke when a user says things like "review this code", "is this well-structured", "audit src/X for design problems", "what's wrong with this module", "check the architecture here", "look for SRP violations", "is this testable", or asks for a design-level (not lint-level) read of a file or directory.
---

# Code Review

Review the code in scope for design and architecture problems.

> [!IMPORTANT]
> Consult [REFERENCE.md](REFERENCE.md) for the expected output format and level of detail.

You already know what bad design looks like — a function with two unrelated reasons to change, business rules interleaved with transport parsing, a constructor that reaches out and builds its own dependency, an API that must be called in an order nothing enforces, a name that describes a category instead of an action, an error path that collapses three different failures into one. Apply that judgement directly and thoroughly; reading the code closely is the bulk of the value here.

What follows is only the local policy you could not infer. Prescribing the review itself made reviews worse, not better: a 249-line version of this skill scored 78.4% across four fixtures against 94.5% for this one, with five times the variance, because attention went to restating design criteria instead of reading the code.

## Arguments

Your input may carry flags alongside a path. Strip the flags first; whatever remains is the path.

- **`--json <path>`** — additionally write a findings file at that path, per [FINDINGS.md](../../FINDINGS.md). Off by default; the markdown report is unchanged either way.
- **`--non-interactive`** — ask no questions. Where this skill would otherwise prompt, report the outcome and stop.

## Scope

Determine the review scope before discovering files. The discovery script sits at the plugin root, two levels above this skill's directory — resolve it against that location rather than hardcoding an install path, which only holds for one harness's layout:

```bash
DISCOVER="<this skill's directory>/../../scripts/discover-files.sh"
```

- If a path was given, treat it as a path (file or directory) and run:
  ```bash
  bash "$DISCOVER" <path>
  ```
- If no path was given, scope to files added or modified on the current branch relative to the default branch:
  ```bash
  bash "$DISCOVER"
  ```

Handle the script's exit codes:
- **0 with output** — review the listed paths.
- **0 with empty output** — nothing is in scope. Interactively, say so and ask which path to review; under `--non-interactive`, report `no_scope` and stop.
- **non-zero** — the script explains itself on stderr (path not found, not a git repo, on the default branch with no path, detached HEAD, or default branch indeterminate). Relay that message, then ask which path to review, or under `--non-interactive` report `error` with the message and stop.

A review that ran and found nothing, and a review that never ran, both end with zero findings and mean opposite things — so say which happened, in the report and in the findings file's `status`. A caller that cannot tell them apart reports a broken pipeline as a clean codebase.

The script returns paths language-blind. Filter to source files, dropping tests, vendored and generated code, and pure configuration.

For five or more source files — or fewer large ones — fan out: give each subagent a couple of files, the severity rules below, and the named-consequence requirement, and tell it not to use Bash, since this is static reading and shell access only adds latency and risk. Merge what comes back before collapsing patterns.

## Severity, anchored on a named consequence

These findings feed a work-tracking pipeline, so an inflated severity becomes false urgency in someone's backlog and teaches people to ignore the reviewer. The driving question for every finding: **name a specific change someone is likely to make that this design would predictably break.** State it concretely — *"adding a CLI entry point would force re-implementing the discount tiers currently inlined in the HTTP handler."* A finding you cannot put in that form is below the bar; drop it, and do not demote it to P3 because it sounds mild. P1 is the exception: its consequence is implicit.

- **P1** — a security flaw in the design, or code with no test seam at all. Authorization decided from caller-controlled input, a privileged operation with no check, a secret or credential that escapes into a response or a log. Or: no way to substitute a dependency, even with the language's standard mocking tools.
- **P2** — a change someone is likely to make goes wrong. An SRP violation where you can name the ripple ("a pricing rule change lands in the same function as a validation rule change"). Mixed abstractions where you can name the entry point the mixing blocks. Temporal coupling that nothing enforces, with the misuse named. Divergent shapes across sibling APIs, where you name the consumer that cannot share code. Testability friction whose cost you can state as a test that cannot be written cleanly.
- **P3** — the same shape, but the named consequence is narrower: it misleads a reader, or costs readability rather than future change. Naming and small API asymmetries usually live here.

P1 is narrower than it looks, and it is the severity that drifts. Where the language has monkeypatching — Python, TypeScript — a module-scope singleton is almost never a testability P1: `monkeypatch.setattr` or `vi.mock` is the seam, so it is friction, not a wall. Reserve it for the design where you can name no seam at all, and for security flaws you can trace from an attacker-controlled input to the privilege it buys. If a report carries more than one P1, be suspicious of the second.

The P2/P3 line: does the named consequence hit a change someone is **likely to make**, or only a **reader's first impression**? A design that forces a future refactor to land in many places is P2; one that merely reads awkwardly is P3.

## What not to flag

Each of these spends the reader's attention on something they cannot act on, or on a decision they already made:

- **Anything the toolchain already prints.** Linters, formatters, type checkers and security scanners run alongside this review, and they own function length, nesting depth, cyclomatic complexity, dead code, formatting, type errors, injection and hardcoded secrets. If a linter would flag it, it is not a design finding. Where those tools appear to be missing, say so once in the report rather than filing their findings by hand.
- **A test defect rather than a code defect.** A weak assertion or a missing case is a real observation and the wrong review; it belongs to a test review.
- **Anything under `fixtures/`, `testdata/`, `__fixtures__/`, or `golden/`.** Those files are deliberately shaped input, and their defects are usually the point.
- **A missing abstraction nothing yet needs.** An interface with one implementation, a config value not yet configurable, a layer someone might want later — speculative generality costs more than it saves, and asking for it lands on code that is currently right.
- **An alternative idiom the codebase has already chosen.** Raising versus returning an error, constructor injection versus a factory, a protocol with a single implementation: a defensible convention consistently applied is not a defect. Flag inconsistency, not preference.

## Do not drop a correctness defect because this is a design review

The framing here pulls attention toward structure, and the cost shows up in one particular
blind spot: an operation that is not idempotent in a world that will retry it. A refund
`UPDATE` with no already-refunded guard, a retry loop that mints a fresh idempotency key on
every attempt, a batch job that recharges on re-run. These sit in the seam between structure
and behaviour, so a reviewer looking for responsibilities and abstraction levels reads past
them — in testing, unskilled reviews caught these and design-focused ones did not.

When you notice a defect like that, file it with the same named-consequence discipline as
everything else. The reader does not care which review was supposed to catch it. This is not
licence to file every bug you can find: it applies to what you noticed while reading for
design, not to a hunt for logic errors, which is a different review.

## Collapse patterns, then cap at ten

N findings for N instances of one anti-pattern is noise. When several findings share a root cause — three route modules each constructing their own connection pool at import scope, business rules inlined at every transport boundary, every repository leaking its driver's row type — collapse them into **one** finding that names the pattern, lists the affected locations, and prescribes the codebase-wide fix, at the highest severity among them. Keep findings separate when they merely share a category.

Then cap the report at ten. It is a ceiling, not a target: four real findings means a four-finding report, and landing on exactly ten more than once is a sign of padding rather than a coincidence. Include every P1 — they never belong in a truncated tail — then fill with P2s and P3s by impact, favouring the ones whose consequence reaches more callers. If you cut any, end with `Note: N additional findings omitted (X P2, Y P3) — re-run after addressing these to surface what remains.`

When the cap binds, keep the finding that names the largest structural problem even if several smaller ones are easier to write up. A unit doing four unrelated jobs is worth more to the reader than three separate notes about its consequences, and it is the finding most easily crowded out — symptoms are more concrete than their cause, so they win the budget unless you watch for it.

Design changes have wider blast radius than test fixes, so churn matters more here, not less. A thirty-finding review is unmergeable as one PR; it ages out or gets half-applied. Batches of ten are what people actually do, and re-running after fixes surfaces what only became visible once the pressing things were gone — often one cross-cutting refactor dissolves several adjacent findings. The cap also works against the "asked to find things, so finds things" reflex.

## When the code is sound, say so

A review that finds little should read as a verdict, not as a shrug. Reporting only issues is the right default, but on well-designed code a bare count line leaves the reader unable to tell a careful review from a cursory one, and the next thing they do is ask whether you actually looked. Say plainly that the design holds up and name what carries it — the injected dependencies, the single-purpose modules, the error type that gives callers something to branch on. Two sentences is enough. Then file the one or two real findings if there are any, and stop; do not reach for filler to make the report look substantial.

## Output

Produce a report following the structure in [REFERENCE.md](REFERENCE.md). Each finding must include:

- **Priority** (P1/P2/P3) in the H3 header
- **Location** (file:line)
- **Explanation** of the problem and why it matters
- **Fix** — concrete prescription. For an API design issue, give the exact shape: parameter names, types, signatures, not just the general approach.
- **Done when** — a criterion verifiable by reading the diff, referencing specific functions, files or observable behaviour. "Both parseSkillFrontmatter and parseAgentFrontmatter delegate to a shared parseFrontmatterRaw; no duplicated delimiter-scanning code remains." NOT: "the duplication is removed."

When `--json <path>` was given, write the findings file described in [FINDINGS.md](../../FINDINGS.md) as well. Two fields need care because nothing downstream can recover them if they are wrong: `files` must list every path a finding touches, and `pattern` must be the slug that names its root cause, taken from the vocabulary in [REFERENCE.md](REFERENCE.md). Findings you collapsed together share a root cause, so they share a slug — that pairing is what lets a later run recognise this finding as one it has already reported.
