# decisions

Architectural Decision Record (ADR) creation, maintenance, and enforcement tooling for coding
agents (Claude Code, opencode, codex).

## Overview

Research documents capture what was found out before a decision; ADRs capture the *why* behind significant architectural choices — constraints, trade-offs, rejected alternatives — and act as standalone, append-only policy. A spec describes *what* to build and cites the ADRs that constrained it; the ADR itself does not track downstream specs. When decisions live only in Slack threads or a reviewer's memory, future agents re-litigate settled questions or quietly drift from intent. This plugin produces structured, version-controlled ADRs that agents can read and honor.

The process this belongs to is **research → ADR → spec**. Research establishes what is true, the ADR records what was decided given that, and a spec (`lightspec`) says what to build.

The output is MADR-style (Markdown Architecture Decision Records) with rich frontmatter. ADRs link to other ADRs — via `supersedes`, `superseded-by`, and `related` — and to the research they rest on via `research`, keeping the graph stable and directionally correct. Spec-to-ADR and spec-to-research citation is the responsibility of the spec side.

## Skills

| Skill | Description | Model-Invocable |
|-------|-------------|-----------------|
| `create-adr` | Create a new ADR from a standard MADR template, researching context from the codebase and registering it in the repository's active agent instructions | Yes |
| `create-research` | Investigate a question and record it in `docs/research/NNNN-slug.md` with per-finding confidence and cited sources, in a script-enforced format, ahead of an ADR or a spec | Yes |
| `review-policy` | Review a code change (working diff, PR, or path) against the accepted ADRs and report violations, invariant erosions, drift toward rejected options, and driver-shift candidates for ADR revisit | Yes |

## Usage

Skill names are agent-neutral. Agents that resolve skills by name (opencode, codex) call them
directly; Claude Code prefixes the plugin name (`/decisions:create-adr`).

```
create-adr use Postgres for the event store instead of DynamoDB
create-adr adopt trunk-based development with short-lived feature flags
create-adr replace the custom retry wrapper with Temporal workflows

create-research does the nightly export lose rows when the database fails over
create-research compare SQS and Redis lists against our job-loss requirement

review-policy                   # review the current working diff against all accepted ADRs
review-policy main...HEAD       # review a specific ref range
review-policy PR#42             # review a pull request
review-policy --adr ADR-0007    # review the diff against a single ADR
```

If `create-adr` is called without an argument, it asks what decision to record. `create-research` turns a "which should we pick?" request into research on what is true and leaves the choice to `create-adr`; a bare topic ("research caching") gets a short round of questions before anything is written. If `review-policy` is called without an argument, it defaults to the working diff against the repo's base branch.

## Template Structure

Every ADR follows MADR conventions:

- **Frontmatter** — `id`, `title`, `status`, `date`, `deciders`, `supersedes`, `superseded-by`, `related`, `research`, `tags`
- **Context and Problem Statement** — forces in play, constraints, the problem
- **Decision Drivers** — the criteria that matter
- **Considered Options** — options under evaluation, with one-line summaries
- **Decision Outcome** — which option won, and why against the drivers
- **Consequences** — positive, negative, and risks accepted
- **Pros and Cons of the Options** — per-option analysis
- **Implementation Notes** — how the decision cascades into code and operational policy
- **References** — links to discussions, PRs, prior ADRs, and the research the decision rests on

## ADR Directory Convention

The skill looks for an existing ADR directory in this order:

1. `docs/adr/` (if it exists)
2. `docs/decisions/` (if it exists)
3. `docs/adrs/` (if it exists)
4. Asks the user, defaulting to `docs/adr/`

## ADR ↔ spec relationship

ADRs do not track the specs that inherit their constraints. Specs cite ADRs; ADRs cite other ADRs and research. This keeps ADRs stable (accepted decisions are append-only history) and puts the maintenance burden on the churning side, where it belongs. To find which specs a given ADR constrains, grep the specs for the ADR id.

## Research ↔ ADR relationship

Research is upstream: an ADR cites the research it rests on by `RES-NNNN` id in its `research` frontmatter, and `create-adr` adds the ADR's id to each cited document's `related` so the link can be followed from either end. Both are append-only records with stable ids, so a link in each direction does not rot. Specs are the exception: they cite research from a `## Research` section, and research never links to a spec.

Research is cited only when its status is `complete`; `superseded` research is followed to its replacement, and a `Revisit When` condition that has been met makes the research stale.

## Research directory convention

`create-research` uses `docs/research/` if it exists, else `research/`, else creates `docs/research/`. Documents are numbered `NNNN-slug.md` with ids `RES-NNNN`, and the format is enforced by a checker script.

## Registration in agent instructions

The skill appends (or updates) an `## Architectural Decisions` section in the repository's active agent instructions, listing each ADR with a one-line "when this applies" description. It checks `AGENTS.md`, `AGENTS.override.md`, `CLAUDE.md`, and configured repository instruction paths/globs, preserving existing shared imports or links. Registration follows the files each agent actually loads; an inactive default alone is insufficient. If the repository has no instruction convention, it creates `AGENTS.md`.

Policy reviews use parallel reviewers when delegation is available and review the same ADRs sequentially when it is not.

## Bundled Resources

ADR scaffolding requires `bash` and `jq` on PATH. Policy diff reviews require
`git`, and PR reviews additionally require an authenticated `gh` CLI.

### Scripts

| Script | Language | Purpose |
|--------|----------|---------|
| `init-adr.sh` | Bash | Create an ADR file from the MADR template with auto-numbered ID and today's date |
| `research.py` | Python (stdlib) | `new` writes a numbered research skeleton; `check` validates a filled document |
| `test_research.py` | Python (stdlib) | Pins the research skeleton and checker together |

### Assets

| File | Purpose |
|------|---------|
| `adr-template.md` | MADR-format ADR template with all sections and frontmatter |
| `example-research.md` | A filled research document, written to be imitated; it must pass the checker |

`create-research` also ships `evals/` with the fixture repo they run against.
