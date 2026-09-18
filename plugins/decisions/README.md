# decisions

Architectural Decision Record (ADR) creation, maintenance, and enforcement tooling for coding
agents (Claude Code, opencode, codex).

## Overview

ADRs capture the *why* behind significant architectural choices — constraints, trade-offs, rejected alternatives — and act as standalone, append-only policy. A spec describes *what* to build and cites the ADRs that constrained it; the ADR itself does not track downstream specs. When decisions live only in Slack threads or a reviewer's memory, future agents re-litigate settled questions or quietly drift from intent. This plugin produces structured, version-controlled ADRs that agents can read and honor.

The output is MADR-style (Markdown Architecture Decision Records) with rich frontmatter. ADRs link only to other ADRs — via `supersedes`, `superseded-by`, and `related` — keeping the graph stable and directionally correct. Spec-to-ADR citation is the responsibility of the spec side.

## Skills

| Skill | Description | Model-Invocable |
|-------|-------------|-----------------|
| `create-adr` | Create a new ADR from a standard MADR template, researching context from the codebase and registering it in the project's agent instructions (`AGENTS.md`/`CLAUDE.md`) | Yes |
| `review-policy` | Review a code change (working diff, PR, or path) against the accepted ADRs and report violations, invariant erosions, drift toward rejected options, and driver-shift candidates for ADR revisit | Yes |

## Usage

Skill names are agent-neutral. Agents that resolve skills by name (opencode, codex) call them
directly; Claude Code prefixes the plugin name (`/decisions:create-adr`).

```
create-adr use Postgres for the event store instead of DynamoDB
create-adr adopt trunk-based development with short-lived feature flags
create-adr replace the custom retry wrapper with Temporal workflows

review-policy                   # review the current working diff against all accepted ADRs
review-policy main...HEAD       # review a specific ref range
review-policy PR#42             # review a pull request
review-policy --adr ADR-0007    # review the diff against a single ADR
```

If `create-adr` is called without an argument, it asks what decision to record. If `review-policy` is called without an argument, it defaults to the working diff against the repo's base branch.

## Template Structure

Every ADR follows MADR conventions:

- **Frontmatter** — `id`, `title`, `status`, `date`, `deciders`, `supersedes`, `superseded-by`, `related`, `tags`
- **Context and Problem Statement** — forces in play, constraints, the problem
- **Decision Drivers** — the criteria that matter
- **Considered Options** — options under evaluation, with one-line summaries
- **Decision Outcome** — which option won, and why against the drivers
- **Consequences** — positive, negative, and risks accepted
- **Pros and Cons of the Options** — per-option analysis
- **Implementation Notes** — how the decision cascades into code and operational policy
- **References** — links to discussions, PRs, and prior ADRs

## ADR Directory Convention

The skill looks for an existing ADR directory in this order:

1. `docs/adr/` (if it exists)
2. `docs/decisions/` (if it exists)
3. `docs/adrs/` (if it exists)
4. Asks the user, defaulting to `docs/adr/`

## ADR ↔ spec relationship

ADRs do not track the specs that inherit their constraints. Specs cite ADRs from their own frontmatter; ADRs cite only other ADRs. This keeps ADRs stable (accepted decisions are append-only history) and puts the maintenance burden on the churning side, where it belongs. To find which specs a given ADR constrains, grep spec frontmatter for the ADR id.

## Registration in agent instructions

The skill appends (or updates) an `## Architectural Decisions` section in the project's root agent-instructions file — `AGENTS.md`, or `CLAUDE.md` where that is the convention — listing each ADR with a one-line "when this applies" description. This is how future agent sessions discover and honor prior decisions — if an ADR isn't registered, agents won't see it.

## Bundled Resources

### Scripts

| Script | Language | Purpose |
|--------|----------|---------|
| `init-adr.sh` | Bash | Create an ADR file from the MADR template with auto-numbered ID and today's date |

### Assets

| File | Purpose |
|------|---------|
| `adr-template.md` | MADR-format ADR template with all sections and frontmatter |
