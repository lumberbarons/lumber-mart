# skill-portability

A plugin providing a review skill for skill portability: harness coupling that breaks or degrades a skill when another coding agent (Claude Code, opencode, codex) runs it.

## Overview

- **review-portability** — slash-command references, `$ARGUMENTS`, plugin-root paths, machine-specific paths, single-harness examples and tool names. File-based rather than diff-based: point it at a skill directory, a plugin's `skills/` directory, or a single file.

It produces a structured findings report with P1/P2/P3 severities, file:line locations, explanations, and concrete fixes. `--json <path>` additionally writes a machine-readable findings file (`skill: "portability"`, following the schema in [critique's FINDINGS.md](../critique/FINDINGS.md)) that feeds hew's `raise-issues` skill ([README](../hew/README.md)). `--non-interactive` removes every prompt, and `--inline` reviews in the current session instead of delegating to subagents.

## Installation

Install via the lumber-mart marketplace — see the [root README](../../README.md#usage) for the `/plugin marketplace add` and `/plugin install` commands.

## Skills

| Skill | Description | Model-Invocable |
|-------|-------------|-----------------|
| `review-portability` | Review skill files for agent-harness coupling | Yes |

### Natural Language Triggers

- **review-portability**: "review this skill", "is this skill agent-agnostic", "check the skill for Claude-only assumptions", "audit skills/ for portability"

### Usage Examples

Skill names are agent-neutral. Agents that resolve skills by name (opencode, codex) call them
directly; Claude Code prefixes the plugin name (`/skill-portability:review-portability`).

```
review-portability plugins/hew
review-portability --json out/portability.json plugins/
raise-issues --findings out/portability.json
```

## Prerequisites

None beyond the agent itself.
