# 🪵🛒 Lumber Mart

A plugin marketplace for Codex and Claude Code, with shared skills for review, architecture, operational docs, specifications, issue delivery, and epic orchestration.

Packages follow the [portable Agent Plugins format recommended by OpenAI](https://developers.openai.com/plugins/build/plugins) and also ship the [Claude Code plugin layout](https://code.claude.com/docs/en/plugins-reference).

## Prerequisites

- Codex with `codex plugin` support, or Claude Code with plugin marketplace support
- `git` for cloning or fetching the marketplace
- Skill-specific tools: Bash for bundled shell scripts; Python 3 for review and spec tooling; authenticated `gh` and `hew` for issue workflows; `herdr` plus the `hew` and `critique` plugins for `work-epic`. See each plugin README for its prerequisites.

## Available Plugins

| Plugin | Category | Description |
|--------|----------|-------------|
| [runbooks](plugins/runbooks/) | Workflow | Operational runbook creation with consistent structure and built-in maintenance feedback loops |
| [critique](plugins/critique/) | Workflow | Review skills for code, tests, documentation, and observability -- design, coverage, doc-structure, and logging issues that linters miss |
| [decisions](plugins/decisions/) | Workflow | Architectural Decision Record (ADR) authoring and policy review, with AGENTS.md/CLAUDE.md registration |
| [lightspec](plugins/lightspec/) | Workflow | Draft and approve feature specs, then convert accepted specs into tracked epics |
| [hew](plugins/hew/) | Workflow | File review findings as issues and take tracked work from claim to draft PR |
| [work-epic](plugins/work-epic/) | Workflow | Coordinate workers, reviews, reconciliation, and merges for a hew epic through herdr |

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
| `critique:review-portability` | Skill | Review skills for assumptions that break across coding agents |

### [decisions](plugins/decisions/)

Architectural Decision Record (ADR) authoring, maintenance, and enforcement. Produces MADR-format ADRs as standalone, append-only policy with ADR-to-ADR relationship tracking (`supersedes`, `superseded-by`, `related`). Specs cite the ADRs that constrained them; ADRs do not track their downstream consumers. Includes a review skill that audits a code change against the accepted ADRs and flags violations, erosions, drift, and driver-shift candidates.

| Component | Type | Description |
|-----------|------|-------------|
| `decisions:create-adr` | Skill | Create a new ADR from a MADR template, research context from the codebase, and register it in the project's agent instructions (AGENTS.md/CLAUDE.md) |
| `decisions:review-policy` | Skill | Review a code change (working diff, PR, or path) against the accepted ADRs, flagging violations, invariant erosions, drift toward rejected options, and driver-shift candidates for ADR revisit |

## Installation

### Codex

Add this GitHub marketplace, browse its plugins, and install one:

```bash
codex plugin marketplace add lumberbarons/lumber-mart
codex plugin list --marketplace lumber-mart
codex plugin add critique@lumber-mart
```

For local testing, add the repository root instead:

```bash
codex plugin marketplace add /absolute/path/to/lumber-mart
```

In Codex in the ChatGPT desktop app, restart the app after adding or changing a local marketplace, then open the Plugins Directory, select **Lumber Mart**, and install the plugins you want. Start a new conversation to test the installed skills. Local installations use a cached copy; after editing a plugin, refresh/reinstall it through your client.

Refresh a Git-backed marketplace with `codex plugin marketplace upgrade lumber-mart`, then update installed plugins through your client's plugin management surface. Marketplace discovery does not install every plugin or its external CLI prerequisites.

### Claude Code

Run these commands inside Claude Code:

```text
/plugin marketplace add lumberbarons/lumber-mart
/plugin install critique@lumber-mart
```

For local testing, use `/plugin marketplace add /absolute/path/to/lumber-mart`. Open `/plugin` to browse and manage installed plugins.

### Calling skills

In Claude Code, use `/critique:review-code`. In Codex, select the installed `review-code` skill or ask the agent to use it by name. Plugin READMEs describe the inputs each skill accepts.

### OpenCode through APM

APM 0.33.0 can install the same skills into OpenCode through this Claude-compatible marketplace:

```bash
apm marketplace add lumberbarons/lumber-mart
apm install critique@lumber-mart --target opencode
```

Add `--global` to the install command for user-wide skills. Existing dependencies such as `lumberbarons/lumber-mart/plugins/critique` remain supported. Project installs deploy skills to `.agents/skills/`; global OpenCode installs deploy to `~/.config/opencode/skills/`. Restart OpenCode or start a new session to discover newly installed skills.

Each plugin includes a generated `apm.yml` and a small `.apm/` marker. Together they select APM's skill-bundle installation route ahead of its portable Agent Plugin route, which currently registers whole plugins only for Copilot. A metadata-only `apm.yml` without `.apm/` does not select this route. The actual skills stay in `skills/`, shared with Codex and Claude Code; no duplicate skill tree is maintained.

## Maintaining the packages

| File | Purpose |
|------|---------|
| `plugins/<name>/plugin.json` | Canonical portable identity and metadata; OpenAI presentation under `extensions.com.openai` |
| `plugins/<name>/.claude-plugin/plugin.json` | Claude Code manifest with matching identity and version |
| `plugins/<name>/apm.yml` and `.apm/README.md` | Generated explicit APM layout for installing the shared skills into OpenCode |
| `plugins/<name>/skills/<skill>/SKILL.md` | Shared skill instructions and bundled resources for both hosts |
| `.agents/plugins/marketplace.json` | Codex catalog with repo-relative local sources and install policies |
| `.claude-plugin/marketplace.json` | Claude Code catalog with matching plugin names, paths, and versions |

All current plugins contain skills, so they do not need MCP configuration or hooks. If a future plugin bundles an MCP server, use root `mcp.json` with the Agent Plugins schema and provide the configuration Claude Code expects separately.

When changing a plugin, bump its version in both manifests and the Claude catalog, then run `python3 scripts/sync-apm-manifests.py`. Keep shared identity fields equal, and add/remove catalog entries in both catalogs together. CI validates the portable schema, catalog parity, generated APM files, skill frontmatter, and version advancement against the base branch. It also installs all six plugins with pinned APM 0.33.0 through both marketplace selectors and direct subpaths in project and global scope, checking every deployed skill file and allowing only equivalent Markdown link rebasing.

```bash
uv run --no-project --with jsonschema python3 scripts/check-marketplace.py
uv run --no-project --with jsonschema python3 -m unittest discover -s scripts -p 'test_*.py'
uv run --no-project --with pyyaml python3 scripts/check-skill-frontmatter.py
claude plugin validate --strict .
bash scripts/sync-skill-files.sh --check
python3 scripts/sync-apm-manifests.py --check
uv run --no-project --with apm-cli==0.33.0 python3 scripts/check-apm-install.py
```

The Agent Plugins 1.0.0 schema is vendored at `scripts/schemas/plugin.schema.json` from [the specification's schema URL](https://agent-plugins.org/schemas/1.0.0/plugin.schema.json), so validation does not depend on a network fetch. Review schema upgrades explicitly.

## License

MIT
