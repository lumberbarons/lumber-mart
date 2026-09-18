# specbeads

A plugin that integrates [spec-kit](https://github.com/spec-kit/specify) with [beads](https://github.com/beads-project/beads) for streamlined specification-driven development, usable from any coding agent that loads skills (Claude Code, opencode, codex).

## Overview

This plugin bridges two tools:
- **spec-kit**: Manages feature specifications, plans, and design artifacts
- **beads**: Tracks work items (epics, tasks, bugs) with dependencies

The plugin converts spec-kit task lists into beads for implementation tracking, validates implementation against spec-kit artifacts, and files review findings as beads for follow-up work.

### Companion plugin

Code, test, and documentation review skills now live in the **critique** plugin. Install critique alongside specbeads and pipe its findings into `/raise-beads` to turn them into trackable beads.

## Prerequisites

- [spec-kit CLI](https://github.com/spec-kit/specify) (`specify` command)
- [beads CLI](https://github.com/beads-project/beads) (`bd` command)
- Git repository

## Installation

Install via the lumber-mart marketplace — see the [root README](../../README.md#usage) for the `/plugin marketplace add` and `/plugin install` commands.

## Skills

| Skill | Description | Model-Invocable |
|-------|-------------|-----------------|
| `init` | Initialize a repository with both spec-kit and beads | No (user-only) |
| `beadify` | Convert tasks.md into beads (epics for phases, tasks as children) | Yes |
| `implement` | Implement a spec-kit feature phase, one task at a time with per-task commits | Yes |
| `fix` | Implement standalone bug/task beads (e.g. from review findings), one at a time | Yes |
| `raise-beads` | File review findings from conversation context as beads, with deduplication | Yes |
| `review-spec` | Validate implementation against spec-kit artifacts (spec.md, plan.md, constitution.md) | Yes |

### Workflow

1. **Initialize**: Run `init` to set up spec-kit and beads in your repo
2. **Create specs**: Use spec-kit to create feature specs (spec.md, plan.md, data-model.md, contracts/)
3. **Generate tasks**: Run `/speckit.tasks` to decompose specs into tasks.md
4. **Convert to beads**: Run `beadify` to create phase epics and task beads from tasks.md
5. **Implement**: Run `implement` to work through phase tasks, or `implement --all` to continue through all phases
6. **Review quality**: Run the critique plugin's review skills (review-code, review-tests, review-docs), then `raise-beads` to file findings as beads
7. **Fix findings**: Run `fix` to work through standalone beads created by `raise-beads`

### Natural Language Triggers

Model-invocable skills can be triggered by natural language:

- **beadify**: "generate beads for this feature", "convert this feature into beads", "create tasks from the spec", "decompose this into work items"
- **implement**: "implement the next phase", "implement phase 2", "implement 002-realtime-gateway --all"
- **fix**: "fix the review beads", "work through the code review findings", "fix sam-b3i"
- **raise-beads**: "file these findings as beads", "raise beads for the review", "turn the findings into beads"
- **review-spec**: "check if code matches the spec", "validate implementation", "review spec conformance"

### Usage Examples

```
init
beadify 001-user-auth
beadify --dry-run
implement
implement 002-realtime-gateway --all
fix
fix sam-b3i
fix auth
raise-beads
raise-beads --dry-run
raise-beads only P1 and P2
review-spec 001-user-auth
```

## Skill Options

### beadify

- `[spec-folder]` - Specific spec folder (e.g., `001-user-auth`)
- `--dry-run` - Preview implementation plan without creating beads
- `--force` - Create beads even if duplicates detected

### implement

- `[epic-bead-id]` - Specific phase epic to implement
- `[feature-slug]` - Implement the next ready phase for that feature (e.g., `002-realtime-gateway`)
- `--all` - Continue through all unblocked phases sequentially
- `--dry-run` - Show the execution plan without making changes
- `<additional instructions>` - Guidance applied to all tasks (constraints, approach hints)

### fix

- `[bead-id]` - Specific standalone bead to fix
- `[filter]` - Work all ready standalone beads whose title contains the filter text
- `--dry-run` - Show the matched bead list without making changes
- `<additional instructions>` - Guidance applied throughout

### raise-beads

- `--dry-run` - Show the bead list that would be created without running `bd create`
- `<additional instructions>` - Filtering or scope guidance (e.g., "only P1 and P2", "skip the naming findings")

Reads review findings from the most recent review output in conversation context. Works with output from the critique plugin (review-code, review-tests, review-docs) or any hand-written findings list that uses P1/P2/P3/P4 priority tags, file locations, and fix prescriptions.

### review-spec

- `[path]` - Path to focus the review (default: entire repo)
- `[spec-folder]` - Specific spec folder (e.g., `001-user-auth`)
- `--create-beads` - Create beads for findings (default: report only)

## Version Compatibility

- spec-kit: >= 1.0.0
- beads: >= 1.0.0
