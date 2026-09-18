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
| [critique](plugins/critique/) | Workflow | Review skills for code, tests, documentation, and observability -- design, coverage, doc-structure, and logging issues that linters miss |
| [decisions](plugins/decisions/) | Workflow | Architectural Decision Record (ADR) authoring in MADR format with relationship tracking and CLAUDE.md registration |

### [runbooks](plugins/runbooks/)

Operational runbook creation with consistent structure and built-in maintenance feedback loops.

| Component | Type | Description |
|-----------|------|-------------|
| `runbooks:create-runbook` | Skill | Create a new operational runbook from a standard template |

### [critique](plugins/critique/)

Review skills that surface design, coverage, doc-structure, and logging issues that linters and static analysis miss. Each skill produces a structured findings report with P1/P2/P3 (and P4 for docs) severities, file:line locations, and concrete fixes.

| Component | Type | Description |
|-----------|------|-------------|
| `critique:review-code` | Skill | Review code for design issues -- single responsibility, abstraction levels, testability, naming |
| `critique:review-tests` | Skill | Review tests for completeness, coverage gaps, output validation, isolation, readability |
| `critique:review-docs` | Skill | Review README and CLAUDE.md files for progressive disclosure, enumeration completeness, index drift |
| `critique:review-o11y` | Skill | Review observability -- log levels, log value, missing logs at I/O boundaries, error-message quality |

### [decisions](plugins/decisions/)

Architectural Decision Record (ADR) authoring, maintenance, and enforcement. Produces MADR-format ADRs as standalone, append-only policy with ADR-to-ADR relationship tracking (`supersedes`, `superseded-by`, `related`). Specs cite the ADRs that constrained them; ADRs do not track their downstream consumers. Includes a review skill that audits a code change against the accepted ADRs and flags violations, erosions, drift, and driver-shift candidates.

| Component | Type | Description |
|-----------|------|-------------|
| `decisions:create-adr` | Skill | Create a new ADR from a MADR template, research context from the codebase, and register it in the project's CLAUDE.md |
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
