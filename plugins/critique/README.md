# critique

A plugin providing review skills for code, tests, and documentation. Produces structured findings reports that surface design, correctness, coverage, and doc-structure issues that linters and static analysis miss.

## Overview

Focused review skills, each operating on a path you specify:

- **review-code** — one reviewer makes two passes: correctness (defects it can trace to a failing input or state, including retry and existing-data hazards), then design (single responsibility, abstraction levels, testability, meaningful naming, API design, error handling strategy). `--lens design|correctness` runs one lens
- **review-tests** — whether tests would actually catch a regression: falsifiability, isolation hazards, dead expectations, tautologies, coverage gaps. Deliberately short for the same reason as review-docs (see `evals/critique/review-tests/` in the marketplace repo for the benchmark that settled this)
- **review-docs** — README and agent-instructions file (CLAUDE.md, AGENTS.md, AGENTS.override.md, and configured instruction sources) accuracy, drift against the codebase, and context cost. Deliberately short: it states severity discipline and local policy, and leaves the review itself to the model's judgement (see `evals/critique/review-docs/` in the marketplace repo for the benchmark that settled this)

Each skill produces a structured findings report with P1/P2/P3 (and P4 for docs) severities, specific file:line locations, explanations, and concrete fixes.

Code and test reviews automatically make one repair pass when reviewing the current branch's
changes on a clean `feat/`, `fix/` or `chore/` branch with a known default branch and a nonempty
diff. A shared script checks eligibility; uncertain cases stay report-only. A supplied PR
target or a general path/repository audit reports findings without edits. `--fix` (or "and
fix") requests repair explicitly; `--report-only` (or "don't fix") disables it. Existing callers
that specify their own repair phase retain control of it. The review stays read-only; the
calling agent repairs confirmed findings within scope and verifies them. No commit or push
is automatic. See [REVIEW-MODE.md](REVIEW-MODE.md) for the decision and repair boundaries.

In repair mode, the standard report and JSON `findings` list contain unresolved work only;
verified repairs have their own summary and JSON `repaired` list. This keeps successful fixes
out of `raise-issues`. Report-only output retains all findings.

Every skill also takes two flags for use outside an interactive session: `--json <path>` writes a machine-readable findings file alongside the report ([FINDINGS.md](FINDINGS.md)), and `--non-interactive` removes every prompt, reporting `no_scope` or `error` instead of asking which path to review. Together they make a review safe to run unattended — including the part that matters most, distinguishing "reviewed and found nothing" from "never ran".

Every skill delegates by default: each review runs in subagent sessions, so its findings are reached without the caller's context. `--inline` reviews in the current session instead. Where the harness cannot run subagents, skills fall back to an inline review rather than skipping the work.

For `review-code` and `review-tests`, one subagent reviews a branch or focused change as a whole,
with the diff and relevant surrounding code. The code reviewer applies both lenses in sequence.
Multiple reviewers are reserved for exploratory audits of independent subsystems. An explicit
path narrows the scope; it does not by itself select an exploratory audit.

## Installation

Install via the lumber-mart marketplace — see the [root README](../../README.md#usage) for the `/plugin marketplace add` and `/plugin install` commands.

## Skills

| Skill | Description | Model-Invocable |
|-------|-------------|-----------------|
| `review-code` | Review code for design issues and correctness bugs | Yes |
| `review-tests` | Review tests for quality and coverage gaps | Yes |
| `review-docs` | Review README, conventional agent-instructions files, and configured instruction sources | Yes |

### Natural Language Triggers

- **review-code**: "review the code in api/", "check this code for design issues", "any bugs in this module?", "audit this module"
- **review-tests**: "review the tests", "check test quality", "audit test coverage"
- **review-docs**: "review the docs for this project", "check the documentation", "validate CLAUDE.md or AGENTS.md files"

### Usage Examples

Skill names are agent-neutral. Agents that resolve skills by name (opencode, codex) call them
directly; Claude Code prefixes the plugin name (`/critique:review-code`).

```
review-code src/auth/
review-tests tests/unit/
review-code --report-only
review-tests --fix tests/unit/
review-docs
review-docs backend/

review-code --json out/code.json internal/payments/
review-tests --json out/tests.json --non-interactive
```

Findings files feed hew's `raise-issues` skill ([README](../hew/README.md)), which turns them into deduplicated GitHub issues:

```
review-code --json out/code.json internal/http
raise-issues --findings out/code.json
```

## Output

Each skill produces a report with:

- Header: `N files reviewed, M issues found (severity breakdown)`
- One finding per issue with H3 header, priority tag, location, explanation, and concrete fix

No tables, no passing rows — only actionable findings.

## Prerequisites

- `python3` (for code/test review-mode selection and `review-docs` structural validation)
- Git metadata for automatic branch repair; missing or uncertain metadata means report-only

No other tooling required. The review skills assume you already run linters, formatters, security scanners, and type checkers separately — critique focuses on issues those tools cannot detect.
