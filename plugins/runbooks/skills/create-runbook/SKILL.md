---
name: create-runbook
description: Creates an operational runbook from a standard template with sections for prerequisites, procedure, verification, and troubleshooting, researching the codebase to fill in project-specific procedures. Use when asked to create a runbook, write operational docs, document a deployment process, or create step-by-step procedures for ops tasks.
---

# Create Runbook

## User Input

The input describes what the runbook covers (e.g., "deploying the API to production", "rotating database credentials", "diagnosing high memory usage").

If no input was given, ask the user what operational procedure they want to document.

## Workflow

### Step 1: Determine the runbook directory

Check the target project for an existing runbook directory:

1. If `docs/ops/` exists, use it
2. If `docs/runbooks/` exists, use it
3. If neither exists, ask the user where runbooks should live, defaulting to `docs/ops/`

### Step 2: Generate a runbook name

Convert the user's description into a kebab-case filename.

Examples:
- "deploying the API to production" → `deploy-api-production`
- "rotating database credentials" → `rotate-db-credentials`
- "diagnosing high memory usage on worker nodes" → `diagnose-high-memory-workers`

Use imperative verb form. Keep it concise but descriptive.

### Step 3: Scaffold the runbook

Run the init script to create the file from the template. The script sits in `scripts/` beside this file — resolve it against this skill's own directory rather than hardcoding an install path, which only holds for one harness's layout:

```bash
INIT_RUNBOOK="<this skill's directory>/scripts/init-runbook.sh"
bash "$INIT_RUNBOOK" <runbook-name> <target-directory>
```

This outputs JSON with `RUNBOOK_FILE` and `RUNBOOK_DIR` paths. Use `RUNBOOK_FILE` for all subsequent edits.

### Step 4: Research the codebase

Before filling in the template, investigate the project to understand the relevant system:

- **Makefiles, scripts, CI configs** — look for existing automation around the procedure
- **Deployment configs** — Dockerfiles, Kubernetes manifests, Terraform, etc.
- **README and docs** — existing documentation that covers related processes
- **Configuration files** — environment variables, settings, service definitions
- **Infrastructure code** — how services are deployed, connected, monitored

> [!IMPORTANT]
> The goal is to write a runbook with real commands and real paths, not generic placeholders. Every command in the Procedure section should be something the reader can actually run.

### Step 5: Fill in the runbook

Edit the scaffolded file, replacing all template placeholders with project-specific content:

- **Title**: Clear, imperative description (e.g., "Deploy API to Production")
- **Prerequisites**: Actual tools, access, permissions needed
- **Context**: How the system works — deployment model, architecture, relevant services
- **Procedure**: Numbered steps with real bash commands, real paths, and explanations
- **Verify**: Actual commands to confirm success with expected output
- **Troubleshooting**: Real failure modes you discovered during research

> [!NOTE]
> Keep the Runbook Maintenance section as-is from the template. It contains instructions for both humans and AI agents to suggest updates when the runbook is used.

### Step 6: Update the runbook index (if one exists)

Check if the runbook directory has an index file (e.g., `CLAUDE.md`, `README.md`, or `INDEX.md` in the runbook directory). If so, add an entry for the new runbook following the existing format.

### Step 7: Register the runbook in the project CLAUDE.md

> [!IMPORTANT]
> This step is critical. Runbooks only get used if agents and developers know they exist. The project's root `CLAUDE.md` is the single source of truth that Claude Code always reads — if a runbook isn't listed there, it effectively doesn't exist.

Read the project's root `CLAUDE.md`. Look for an existing `## Operational Runbooks` section.

**If the section already exists**, add a new row to the table for the runbook you just created, following the existing format.

**If the section does not exist**, append it to the end of `CLAUDE.md` using this format (substitute the actual runbook directory, filename, and a concise "when to use" description):

```markdown
## Operational Runbooks

Runbooks live in `<runbook-dir>/`. Consult these before ad-hoc debugging — they have tested commands and troubleshooting steps.

| Runbook | When to use |
|---|---|
| `<runbook-dir>/<runbook-name>.md` | <1-line description of when to reach for this runbook> |
```

The "When to use" column should describe the symptoms or situations that should trigger using the runbook — not just restate the title. Good example: "Debugging API errors, slow responses, auth failures, or investigating request patterns in CloudWatch". Bad example: "When you need to access API logs".

### Step 8: Present for review

Show the user the completed runbook and ask if any steps need adjustment. Highlight any areas where you had to make assumptions due to limited information.
