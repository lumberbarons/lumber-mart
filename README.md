# 🪵🛒 Lumber Mart

A plugin marketplace for Claude Code that lets you discover and install plugins for enhanced development workflows.

Learn more about Claude Code marketplaces in the [official documentation](https://code.claude.com/docs/en/plugin-marketplaces).

## Prerequisites

- [Claude Code](https://docs.claude.com/en/docs/claude-code) with plugin marketplace support
- `git` (only required to add a local marketplace from a clone)

## Available Plugins

| Plugin | Category | Description |
|--------|----------|-------------|
| [runbooks](plugins/runbooks/) | Workflow | Operational runbook creation with consistent structure and built-in maintenance feedback loops |
| [critique](plugins/critique/) | Workflow | Review skills for code, tests, and documentation -- design, correctness, coverage, and doc-structure issues that linters miss |
| [skill-portability](plugins/skill-portability/) | Workflow | Review skill files for agent-harness coupling that breaks or degrades them on another coding agent |
| [decisions](plugins/decisions/) | Workflow | Research documents and Architectural Decision Records (ADRs) in script- and template-enforced formats, with research cited by the ADRs that rest on it, and policy review of changes against accepted ADRs |

### [runbooks](plugins/runbooks/)

Operational runbook creation with consistent structure and built-in maintenance feedback loops.

| Component | Type | Description |
|-----------|------|-------------|
| `runbooks:create-runbook` | Skill | Create a new operational runbook from a standard template |

### [critique](plugins/critique/)

Review skills that surface design, correctness, coverage, and doc-structure issues that linters and static analysis miss. Each skill produces a structured findings report with P1/P2/P3 (and P4 for docs) severities, file:line locations, and concrete fixes.

| Component | Type | Description |
|-----------|------|-------------|
| `critique:review-code` | Skill | Review code for design issues -- single responsibility, abstraction levels, testability, naming |
| `critique:review-tests` | Skill | Review tests for completeness, coverage gaps, output validation, isolation, readability |
| `critique:review-docs` | Skill | Review README and CLAUDE.md files for progressive disclosure, enumeration completeness, index drift |

### [skill-portability](plugins/skill-portability/)

Review skill files for coupling to one coding agent -- constructs that break, degrade, or teach the wrong thing when Claude Code, opencode, or codex runs the skill.

| Component | Type | Description |
|-----------|------|-------------|
| `skill-portability:review-portability` | Skill | Review skills for slash-command references, `$ARGUMENTS`, plugin-root paths, machine-specific paths, single-harness tool names and examples |

### [decisions](plugins/decisions/)

Research and Architectural Decision Record (ADR) authoring, maintenance, and enforcement. Research documents record what was found out, with a confidence on each finding and the sources it rests on, in a checker-enforced format. ADRs are MADR-format, standalone, append-only policy with ADR-to-ADR relationship tracking (`supersedes`, `superseded-by`, `related`) and a `research` field citing the research they rest on. Specs cite the ADRs and research that constrained them; ADRs do not track their downstream consumers. Includes a review skill that audits a code change against the accepted ADRs and flags violations, erosions, drift, and driver-shift candidates.

| Component | Type | Description |
|-----------|------|-------------|
| `decisions:create-adr` | Skill | Create a new ADR from a MADR template, research context from the codebase, and register it in the project's active agent instructions |
| `decisions:create-research` | Skill | Investigate a question and record it in `docs/research/NNNN-slug.md` with per-finding confidence and cited sources, checker-enforced, ahead of an ADR or a spec |
| `decisions:review-policy` | Skill | Review a code change (working diff, PR, or path) against the accepted ADRs, flagging violations, invariant erosions, drift toward rejected options, and driver-shift candidates for ADR revisit |

## Usage

### Adding This Marketplace

```bash
# If hosted on GitHub
/plugin marketplace add lumberbarons/lumber-mart

# For local testing
/plugin marketplace add /path/to/lumber-mart
```

### Installing Plugins

```bash
# List available plugins
/plugin list

# Install a plugin
/plugin install critique@lumber-mart
```

## License

MIT
