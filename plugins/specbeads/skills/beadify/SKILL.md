---
name: beadify
description: Convert spec-kit tasks (tasks.md) into beads for tracking implementation. Use when asked to generate beads, create tasks from specs, decompose a feature into work items, or convert specifications into trackable work.
---

## User Input

You **MUST** consider the user input before proceeding (if any was given).

## Argument Parsing

Parse the input for:
- **Spec folder name**: If provided (e.g., `001-user-auth`), use that spec instead of deriving from branch
- **`--dry-run`**: Preview what would be created without actually creating beads
- **`--force`**: Create beads even if duplicates are detected (skip duplicate check)

## Outline

### 1. Validate Prerequisites

Run prerequisite checks:

```bash
./.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks
```

Parse the JSON response to get `FEATURE_DIR` and `TASKS_PATH` (the path to tasks.md).

Then verify beads is initialized:

```bash
bd info
```

> [!CAUTION]
> ERROR if beads is not initialized. Instruct user to run `bd onboard` first.
> ERROR if tasks.md is missing. Instruct user to run `/speckit.tasks` first to generate it.

If a spec folder name was provided in arguments, override `FEATURE_DIR` to `specs/<folder-name>`.

**Derive `FEATURE_SLUG`** from the last path component of `FEATURE_DIR`:
- `specs/002-realtime-gateway` → `FEATURE_SLUG = 002-realtime-gateway`

### 2. Parse tasks.md

Read `TASKS_PATH` and extract the full structure.

#### Phase headers

Each `## Phase N: Title (Priority: PN)` line becomes an epic bead. Extract:
- Phase number
- Phase title (e.g., `Setup`, `Foundational`, `User Story 1 — Search Products`)
- Priority from the header tag (`P1`, `P2`, `P3`). If absent, infer: Setup/Foundational → P1, Polish → P3, user story phases → match story priority.

#### Task lines

Each `- [ ] TXXX ...` line becomes a task bead. Extract:
- Task ID (e.g., `T012`) — used for deduplication
- `[P]` marker — task is parallelisable (no intra-phase dependency needed)
- `[USN]` label — which user story this task belongs to
- Description — the remainder of the line, including any file paths

Skip `- [x]` / `- [X]` lines (already completed).

#### Dependencies section

Parse `## Dependencies & Execution Order` for inter-phase ordering. Standard ordering (applied if the section is absent):
- Setup blocks Foundational
- Foundational blocks all user story phases
- All user story phases block Polish

### 3. Check for Existing Beads (skip if `--force`)

```bash
bd list --type epic --status=all
```

Filter to epics whose description contains `Feature: {FEATURE_SLUG}`. If any are found, warn the user and ask whether to:
1. Show the current bead plan (read-only)
2. Recreate from scratch (equivalent to `--force`)

### 4. Output Implementation Plan

Always output the plan before creating anything (also the only output in `--dry-run` mode):

```
Implementation Plan: {FEATURE_SLUG}
Tasks: {TASKS_PATH}
=====================================

Phase 1: Setup (P1)
  T001  Create project structure per implementation plan
  T002  Initialize Go module with gqlgen, pgx dependencies   [api/go.mod]
  T003  [P] Configure linting and formatting tools

Phase 2: Foundational (P1) — blocks all user stories
  T004  Setup database migrations framework
  T005  [P] Implement authentication middleware             [src/middleware/auth.py]
  ...

Phase 3: US1 — Search Products (P1)
  T012  [P] [US1] Create Product model                     [src/models/product.py]
  T013  [P] [US1] Create Store model                       [src/models/store.py]
  T014  [US1] Implement search service                     [src/services/search.py]
  ...

Phase N: Polish (P3) — after all stories complete
  ...

Dependencies: Setup → Foundational → [US1, US2, US3 in parallel] → Polish
Epics: N | Tasks: M | Ready to start: K
```

Stop here in `--dry-run` mode.

### 5. Create Phase Epics

For each phase, create an epic bead:

```bash
bd create --type epic \
  --title "Phase N: <Title>" \
  --description "<description>" \
  --priority <1-3>
```

**Epic description format:**

```
Feature: {FEATURE_SLUG}
Plan: {FEATURE_DIR}/plan.md
Covers: {FEATURE_DIR}/spec.md §<user story title>

<2–4 sentences: what this phase achieves, why it exists in this order, and what is
observable/true when the phase is complete. Derive from the phase title and task list.>
```

For Setup and Foundational phases with no direct user story, write `Covers: all stories (prerequisite)`.

### 6. Create Task Beads

For each task line under a phase, create a task bead with the phase epic as parent:

```bash
bd create --type task \
  --parent <phase-epic-id> \
  --title "<task description>" \
  --description "<full description>" \
  --priority <priority>
```

**Task description format:**

```
Feature: {FEATURE_SLUG}
Source: {TASKS_PATH} #{task-id}

<task description from tasks.md, preserving file paths verbatim>

Done when: <specific verifiable outcome derived from the task description and file paths>
```

**"Done when" synthesis rules:**
- If the task names a specific file and operation (e.g., "Create Product model in src/models/product.py"), write: *"Done when: `src/models/product.py` exists and contains a Product model."*
- If the task names an endpoint or service, write: *"Done when: the endpoint/service responds correctly per the task description."*
- Always make it checkable by reading the diff or running the relevant test.

**Priority:** Inherit from the parent phase epic.

### 7. Set Dependencies

**Inter-phase (epic) dependencies:**

```bash
bd dep add <foundational-id> <setup-id>
bd dep add <story-phase-id> <foundational-id>
bd dep add <polish-id> <story-phase-id>
```

**Intra-phase (task) dependencies:**

Within each phase, apply ordering from the Dependencies section of tasks.md. Typical ordering:
- Tests before implementation (if tests are present)
- Models before services
- Services before endpoints

Tasks without `[P]` that depend on earlier tasks in the same phase should have explicit deps:

```bash
bd dep add <downstream-task-id> <upstream-task-id>
```

### 8. Bead Quality Gate

After all beads are created, read back every created bead and validate mechanically:

```bash
bd show <bead-id>
```

**Task bead checks:**
1. Description opens with `Feature: ` on the first line
2. Description contains `Done when:` followed by non-trivial content
3. Description contains at least one full path (a string with `/` that is not a bare filename)

**Epic bead checks:**
1. Description opens with `Feature: ` on the first line
2. Description contains a `Plan: ` line
3. Description contains a `Covers: ` line
4. Description contains at least 2 sentences of narrative after the header block

**Report results:**
```
Bead Quality Gate:
  ✓ 14 beads passed
  ✗ 2 beads flagged:
    <bead-id>  [Phase 2 / task title]  Missing "Done when:" clause
```

Auto-fix straightforward failures (missing `Done when:`, bare path reconstructable from `FEATURE_DIR`). Ask the user only if the failure requires judgment.

### 9. Report Summary

```
Created beads from {TASKS_PATH}:

Epics: N (Phase 1–N)
  - Phase 1: Setup → <bead-id>
  - Phase 2: Foundational → <bead-id>
  ...

Tasks: M total
  - Created: X
  - Skipped (duplicates): Y

Dependencies established:
  - Setup → Foundational → User story phases → Polish

Next steps:
  - Run `bd ready` to see available work
  - Run `bd show <epic-id>` to see tasks in a phase
  - Tasks source: {TASKS_PATH}
```

In `--dry-run` mode, prefix with:
```
DRY RUN — No beads were created. The following would be created:
```

## Duplicate Detection (skip if `--force`)

Before creating each task bead, check for an existing bead with the same task ID:

```bash
bd search "<T-ID>" 2>/dev/null || true
```

If a match is found, skip and count as a duplicate. For phase epics, check by title match against existing epics.

## Error Handling

- If `bd create` fails, report the error and continue with remaining items
- Track failures and include in summary: `Failed: N (see errors above)`
- If all phase epic creations fail, abort (cannot create child tasks without parents)

## Design Principles

- **Tasks-first**: tasks.md (generated by `speckit.tasks`) is the source of truth for decomposition. Beadify converts — it does not re-decompose.
- **Beads-native**: Uses bead IDs, dependencies, and epic hierarchy natively.
- **Context-complete**: Every bead is self-contained — a fresh agent reading it has everything needed to find the feature and understand scope.
- **One conversion**: tasks.md is the input artifact. Once beads are created, bead state is the live tracker. tasks.md is not updated.
- **Readable output**: Always produces a formatted implementation plan for human review.
- **Idempotent**: Duplicate detection by task ID prevents accidental double-creation.
