# runbooks

Operational runbook creation and maintenance tooling for coding agents (Claude Code, opencode, codex).

## Overview

Runbooks are step-by-step operational procedures for tasks like deployments, incident response, and system maintenance. This plugin provides skills to create well-structured runbooks with consistent formatting and built-in maintenance feedback loops that prompt both humans and AI agents to keep runbooks current.

## Skills

| Skill | Description | Model-Invocable |
|-------|-------------|-----------------|
| `create-runbook` | Create a new operational runbook from a standard template | Yes |

## Usage

```
create-runbook deploying the API to production
create-runbook rotating database credentials
create-runbook diagnosing high memory usage on worker nodes
```

## Template Structure

Every runbook follows a consistent structure:

- **Prerequisites** — what must be true before starting
- **Context** — how the system works, so commands make sense
- **Procedure** — numbered steps with commands and explanations
- **Verify** — commands to confirm success
- **Troubleshooting** — symptom/cause/fix table
- **Runbook Maintenance** — instructions for keeping the runbook current

## Runbook Directory Convention

The skill looks for an existing runbook directory in this order:

1. `docs/ops/` (if it exists)
2. `docs/runbooks/` (if it exists)
3. Asks the user, defaulting to `docs/ops/`

## Bundled Resources

### Scripts

| Script | Language | Purpose |
|--------|----------|---------|
| `init-runbook.sh` | Bash | Create a runbook file from the standard template |

### Assets

| File | Purpose |
|------|---------|
| `runbook-template.md` | Standard runbook template with all sections |
