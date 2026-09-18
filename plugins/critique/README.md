# critique

A plugin providing review skills for code, tests, documentation, observability, and skill portability. Produces structured findings reports that surface design, coverage, doc-structure, logging/error-message, and agent-harness-coupling issues that linters and static analysis miss.

## Overview

Five focused review skills, each operating on a path you specify:

- **review-code** — design issues (single responsibility, abstraction levels, testability, meaningful naming, API design, error handling strategy)
- **review-tests** — whether tests would actually catch a regression: falsifiability, isolation hazards, dead expectations, tautologies, coverage gaps. Deliberately short for the same reason as review-docs (see `skills/review-tests/evals/` for the benchmark that settled this)
- **review-docs** — README and agent-instructions file (CLAUDE.md, AGENTS.md) accuracy, drift against the codebase, and context cost. Deliberately short: it states severity discipline and local policy, and leaves the review itself to the model's judgement (see `skills/review-docs/evals/` for the benchmark that settled this)
- **review-o11y** — observability: logging consistency, log level appropriateness, log value, missing logs at I/O boundaries, and error-message quality and consistency. Deliberately short for the same reason as the others, and capped at ten findings (see `skills/review-o11y/evals/` for the benchmark that settled this)
- **review-portability** — skill portability: harness coupling that breaks or degrades a skill when another agent (Claude Code, opencode, codex) runs it — slash-command references, `$ARGUMENTS`, plugin-root paths, single-harness examples and tool names

Each skill produces a structured findings report with P1/P2/P3 (and P4 for docs) severities, specific file:line locations, explanations, and concrete fixes.

Every skill also takes two flags for use outside an interactive session: `--json <path>` writes a machine-readable findings file alongside the report ([FINDINGS.md](FINDINGS.md)), and `--non-interactive` removes every prompt, reporting `no_scope` or `error` instead of asking which path to review. Together they make a review safe to run unattended — including the part that matters most, distinguishing "reviewed and found nothing" from "never ran".

## Installation

Install via the lumber-mart marketplace — see the [root README](../../README.md#usage) for the `/plugin marketplace add` and `/plugin install` commands.

## Skills

| Skill | Description | Model-Invocable |
|-------|-------------|-----------------|
| `review-code` | Review code for design issues | Yes |
| `review-tests` | Review tests for quality and coverage gaps | Yes |
| `review-docs` | Review README and agent-instructions files (CLAUDE.md, AGENTS.md) | Yes |
| `review-o11y` | Review logging, log levels, and error messages | Yes |
| `review-portability` | Review skill files for agent-harness coupling | Yes |

### Natural Language Triggers

- **review-code**: "review the code in api/", "check this code for design issues", "audit this module"
- **review-tests**: "review the tests", "check test quality", "audit test coverage"
- **review-docs**: "review the docs for this project", "check the documentation", "validate CLAUDE.md or AGENTS.md files"
- **review-o11y**: "review the logging", "are our logs any good", "check observability", "audit error messages", "do we log the right things"
- **review-portability**: "review this skill", "is this skill agent-agnostic", "check the skill for Claude-only assumptions", "audit skills/ for portability"

### Usage Examples

Skill names are agent-neutral. Agents that resolve skills by name (opencode, codex) call them
directly; Claude Code prefixes the plugin name (`/critique:review-code`).

```
review-code src/auth/
review-tests tests/unit/
review-docs
review-docs backend/
review-o11y internal/payments/
review-portability plugins/hew

review-o11y --json out/o11y.json internal/payments/
review-tests --json out/tests.json --non-interactive
review-portability --json out/skills.json plugins/
```

Findings files feed hew's `raise-issues` skill ([README](../hew/README.md)), which turns them into deduplicated GitHub issues:

```
review-o11y --json out/o11y.json internal/http
raise-issues --findings out/o11y.json
```

## Output

Each skill produces a report with:

- Header: `N files reviewed, M issues found (severity breakdown)`
- One finding per issue with H3 header, priority tag, location, explanation, and concrete fix

No tables, no passing rows — only actionable findings.

## Prerequisites

- `python3` (for `review-docs` structural validation script)

No other tooling required. The review skills assume you already run linters, formatters, security scanners, and type checkers separately — critique focuses on issues those tools cannot detect.
