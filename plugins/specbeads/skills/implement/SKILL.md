---
name: implement
description: Implement a spec-kit feature phase. Executes tasks one at a time, committing after each, with diff verification before closing. Use --all to continue through subsequent phases. For standalone bug/task beads outside a feature plan, use the fix skill instead.
---

## User Input

You **MUST** consider the user input before proceeding (if any was given).

## Argument Parsing

Parse the input for:
- **Epic bead ID** (e.g., `sam-cp7l`): Implement that specific phase epic
- **Feature slug** (e.g., `002-realtime-gateway`): Find and implement the next ready phase for that feature
- **`--all`**: Implement all currently unblocked phases sequentially, continuing after each completes
- **`--dry-run`**: Show the execution plan without making any changes
- **Additional instructions**: Any other text is treated as implementation guidance (constraints, approach hints, scope limits) applied throughout

If no arguments: find the next ready phase — the first unblocked phase epic with open tasks — and implement it. If multiple feature slugs are present in the project, confirm with the user which feature to work on.

If a standalone bead ID (bug or task not part of a phase epic) is given, stop and tell the user to run the fix skill with that bead id instead.

## Outline

### 1. Resolve the Target Phase

#### If an epic bead ID was given
```bash
bd show <epic-id>
```
Use that epic directly.

#### If a feature slug was given
```bash
bd list --type epic --status=open
```
Filter to epics whose description contains `Feature: <slug>`. Select the lowest-numbered phase with open tasks and no blocking dependencies.

#### If no argument
```bash
bd ready --type epic
```
Select the first result (lowest-priority-numbered ready epic with open tasks).

> [!CAUTION]
> If no ready epic is found (all blocked or all closed), stop and report: "No phases are ready to implement. Run `bd ready` to check dependencies."

#### If `--all`
Resolve the first target phase as above. After completing it, re-resolve to find the next unblocked phase and continue. Stop when no more ready phases exist.

### 2. Load Phase Context

```bash
bd show <epic-id>
```

Parse the epic description's **feature header block** (written by the beadify skill):
```
Feature: {FEATURE_SLUG}
Plan: {FEATURE_DIR}/plan.md §<phase section>
Covers: {FEATURE_DIR}/spec.md §<user story>
```

Extract:
- `FEATURE_SLUG` — the feature identifier (e.g., `002-realtime-gateway`)
- `FEATURE_DIR` — the spec folder path (e.g., `specs/002-realtime-gateway`)
- `PLAN_SECTION` — the exact plan.md section heading for this phase
- Covered user stories from spec.md

Read the referenced plan section for architecture context and implementation notes. This is background — the tasks themselves are the primary work queue.

> [!NOTE]
> If the feature header block is missing (older bead format), fall back to reading `specs/` for any plan.md and ask the user to confirm the feature.

### 3. Load and Sequence Tasks

```bash
bd show <epic-id>
```

Collect all child tasks. For each, note status, bead ID, title, and `blockedBy` list. Skip closed tasks. Treat `in_progress` tasks as open (resume from the beginning of that task).

**Build a dependency-ordered execution plan** by topological sort:
- Group tasks into **waves** — tasks in the same wave have no dependencies between them and can run in parallel
- Tasks with `blockedBy` wait for their blockers to complete before starting

Output the execution plan to the user before starting:
```
Phase N: <Title> [<epic-id>]
Feature: {FEATURE_SLUG}

Execution plan:
  Wave 1 (parallel): <task titles>
  Wave 2 (sequential): <task title>  ← blocked by Wave 1
  ...

Tasks remaining: X of Y
```

Stop here in `--dry-run` mode.

### 4. Execute Tasks

Work through waves in order.

#### Single task in wave → implement directly

1. `bd update <task-id> --status=in_progress`
2. `bd show <task-id>` — read the full description: feature anchor, full spec paths, exact files to touch, scope boundaries, cross-task handoff notes, and the "Done when" clause
3. Read any spec sections explicitly cited that have detail beyond what the description captures
4. **Implement the task using TDD when applicable.** Stay strictly within the stated file scope — if the description says "this task writes the migration; task .2 wires it in," do not wire it in

   **TDD applies** when the task produces code that can be meaningfully unit- or integration-tested (application logic, library functions, API handlers, data transforms, etc.).

   **TDD does not apply** to pure configuration, migrations, documentation, static assets, CI/CD manifests, or boilerplate wiring with no branching logic.

   When TDD applies, follow Red-Green-Refactor:
   1. **Red** — Write a failing test (or tests) that express the "Done when" clause and the task's expected behavior. Tests must:
      - Assert on actual return values and state, not just "no error thrown"
      - Test behavior, not implementation details — if you refactored internals without changing behavior, the test should still pass
      - Use meaningful expected values, not arbitrary placeholders
      - Cover at least the happy path and one error/edge case
      - Have clear, descriptive names that communicate the scenario being verified (e.g., `TestCheckout_AppliesVolumeDiscount`, not `TestCheckout2`)
      - Follow arrange-act-assert structure with no shared mutable state between test cases

      Run the test suite to confirm the new tests fail for the right reason (missing implementation, not import errors or syntax mistakes). Fix any scaffolding issues until the tests fail because the feature is absent
   2. **Green** — Write the minimal implementation to make all tests pass
   3. **Refactor** — Clean up the implementation while keeping tests green. Do not gold-plate — stay within scope
5. **Verify the "Done when" clause.** Run whatever checks it specifies (tests, `terraform validate`, file existence, etc.). Additionally, run `git diff HEAD` and confirm that every file or function explicitly named in the description was actually changed. If any named file was not touched, stop and explain the gap before closing the task. Fix failures before proceeding
6. **Commit:**
   ```bash
   git add <files changed>
   git commit -m "feat({FEATURE_SLUG}): <task title> [{task-id}]

   Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
   ```
7. `bd close <task-id>`

#### Multiple tasks in wave → spawn parallel subagents

Subagents keep implementation details out of the main context, which protects against compaction on large phases. Cap at **4 concurrent subagents** per batch — if a wave has more than 4 tasks, split into batches of 4 and run batches sequentially.

**Before spawning**, extract the explicit file paths from each task's bead description (paths are always present per the beadify quality gate — look for tokens containing `/`). Build a path set per task and check for overlap. Any two tasks sharing a path must run sequentially: move the later task into a new wave after the earlier one completes. Do not rely on the `[P]` marker alone; verify by path inspection.

Each subagent receives:
- Full task description (verbatim from `bd show <task-id>`)
- Feature slug and spec dir
- Instruction to: mark in_progress → write failing tests (when TDD applies) → implement to make tests pass → refactor → verify done-when → commit → mark complete
- TDD guidance: use TDD (Red-Green-Refactor) for testable code; skip TDD for config, migrations, docs, static assets, or pure wiring with no logic
- Commit message format: `feat({FEATURE_SLUG}): <task title> [{task-id}]`
- Any user-provided additional instructions from the input

Wait for all subagents in the batch to complete. If any subagent reports failure:
1. Mark that bead back to `open`
2. Stop immediately — do not start the next batch or wave
3. Surface the failure and the subagent's output
4. Do not close the epic

### 5. Phase Quality Gate

After all tasks in the phase are complete, detect which gates apply by inspecting changed files (`git diff --name-only HEAD~<N>` across the commits made in this phase), then run every applicable gate:

| Signal | Gate command |
|--------|-------------|
| `*.py` changed | `uv run pytest` (scoped to the relevant test module if possible) |
| `*.go` changed | `go build ./...` and `go test ./...` |
| `*.ts` / `*.tsx` / `*.js` / `*.jsx` changed | `npm test` (or `pnpm test` / `yarn test` — match the lockfile present) |
| `*.java` / `*.kt` changed | `./mvnw test` or `./gradlew test` — whichever build file is present |
| `*.rs` changed | `cargo test` |
| `*.rb` changed | `bundle exec rspec` (or `bundle exec rake test` if no spec/ dir) |
| `*.tf` / `*.tfvars` changed | `terraform validate` in the module directory |
| `*.cs` changed | `dotnet test` |
| `*.swift` changed | `swift test` |
| `*.php` changed | `./vendor/bin/phpunit` |
| Shell / config / docs only | No automated gate — done-when clauses are the verification |
| Integration / hardening phase | Done-when clauses define their own verification |

Run all applicable gates. If multiple apply (e.g., Go + Terraform), run both.

If the quality gate fails:
1. Report which check failed and the output
2. Fix the issue (staying within the scope of this phase)
3. Re-run until it passes
4. Do NOT close the epic until the gate passes

### 6. Close the Phase and Sync

```bash
bd close <epic-id>
bd sync
git add .beads/
git commit -m "chore({FEATURE_SLUG}): complete Phase N [{epic-id}]

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git push
```

Verify push succeeded. If it fails (remote diverged), `git pull --rebase` and push again.

### 7. Report and Hand Off

```
Phase N complete: <Title> [{epic-id}]
Feature: {FEATURE_SLUG}

Tasks completed: X
  ✓ <task title> [<id>]   — <one-line summary of what was done>
  ...

Quality gate: passed (<gate>: <summary>, <gate>: <summary>)

Committed and pushed.

Next:
  Unblocked by this phase: <next phase title> [<id>]
  Run the implement skill to continue, or `bd show <next-epic-id>` to review.
```

If `--all` was specified and another phase is now ready, proceed automatically.

## Handling Interruptions and Partial Progress

If invoked on a phase that is partially complete (some tasks closed, some open):
1. Report: "Phase N is X% complete — Y tasks done, Z remaining."
2. Skip all closed tasks.
3. Resume from the first open/in_progress task in dependency order.
4. Run the full quality gate at the end regardless of how many tasks were skipped.

## Scope Discipline

- Do not implement tasks from other phases even if they seem related
- Do not refactor outside the task's stated file scope
- Do not add features beyond the "Done when" clause
- If a task references a spec decision as background only, do not act on it unless the task explicitly says to

If you discover a blocking issue outside your scope, create a bead:
```bash
bd create --type bug \
  --title "Blocking: <description>" \
  --description "Feature: {FEATURE_SLUG}
Discovered while implementing {task-id}. <detail>

Done when: <resolution criterion>"
```
Then surface it to the user rather than working around it silently.

## Design Principles

- **Bead-driven**: Task descriptions (written by beadify) are the source of truth — feature anchor, spec paths, file scope, done-when. Trust and follow them.
- **Commit granularity**: One commit per task. Readable history, surgical rollback.
- **Verify before closing**: The "Done when" clause is not a suggestion. Never close a task without confirming it passes.
- **Parallel when safe**: Independent tasks run concurrently via subagents. Dependency order is always respected.
- **Fail loudly**: Surface errors rather than working around them. Do not continue to dependent tasks after a failure.
- **Scope discipline**: Implement exactly what the task says — no more, no less.
