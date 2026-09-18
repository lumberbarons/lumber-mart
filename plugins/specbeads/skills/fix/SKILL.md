---
name: fix
description: Implement standalone bug and task beads that are not part of a spec-kit phase epic — for example, beads filed by raise-beads from critique review findings, or by review-spec with --create-beads. Executes one bead at a time, committing after each. For feature phase implementation, use the implement skill instead.
---

## User Input

You **MUST** consider the user input before proceeding (if any was given).

## Argument Parsing

Parse the input for:
- **Bead ID** (e.g., `sam-b3i`): Fix that specific bead
- **Type keyword** (`bugs` or `tasks`): Work only beads of that type. `bugs` → `--type bug`, `tasks` → `--type task`. If omitted, work both types.
- **Filter text** (e.g., `auth`, `code review`): Work all matching standalone beads whose title contains the filter (case-insensitive substring). Show the matched list before proceeding.
- **`--dry-run`**: Show the list of beads that would be worked without making any changes
- **Additional instructions**: Any other text is treated as implementation guidance applied throughout

Type keywords and filter text can be combined (e.g., `fix bugs auth` → only bug beads whose title contains "auth").

If no arguments: work all standalone bug and task beads that are open or in-progress.

If an epic bead ID is given, stop and tell the user to run the implement skill with that epic id instead.

## Resolving the Bead List

**Single bead ID given:**
```bash
bd show <bead-id>
```
Confirm it is type `bug` or `task`. If it is an `epic`, stop and redirect to the implement skill.

**Filter or no argument:**

Build the `bd list` command based on parsed arguments:
- If a type keyword was given: `bd list --type <bug|task>`
- If no type keyword: run both `bd list --type bug` and `bd list --type task`

Exclude epics and their child tasks (which belong to a phase). If filter text was provided, further narrow to beads whose title contains it. Show the matched list to the user before proceeding.

> [!CAUTION]
> If no matching beads are found, stop and report: "No standalone beads match. Run `bd list` to check."

Stop here in `--dry-run` mode, after showing the matched list.

## Execution

Process each bead sequentially — one at a time, in the order returned by `bd list`. Do not bundle multiple beads into one commit.

For each bead:

### 1. Claim
```bash
bd update <bead-id> --status=in_progress
bd show <bead-id>
```
Read the full description: files to change, scope, and the "Done when" clause.

### 2. Synthesize "Done when" if absent
If the description does not contain a `Done when:` clause, derive one before writing any code:
- Identify the specific functions, files, or behaviours that must change
- Write a criterion verifiable by reading the diff (e.g., "Both `parseSkillFrontmatter` and `parseAgentFrontmatter` call a shared `parseFrontmatterRaw`; no duplicated delimiter-scanning logic remains in either")
- State the synthesized criterion explicitly so the user can see it

### 3. Implement
Stay within the files and functions named in the description. Do not fix adjacent issues — if you find something else wrong, create a new bead for it.

### 4. Verify
Confirm the "Done when" clause passes — either the one from the description or the synthesized one:
- Run `git diff HEAD` and check that every file or function named in the description was actually changed. If a named file was not touched, stop and explain the gap before closing.
- Run any tests cited in the description or directly relevant to the changed files.

### 5. Commit
```bash
git add <files changed>
git commit -m "fix: <bead title> [<bead-id>]

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

### 6. Close
```bash
bd close <bead-id>
```

Repeat for the next bead.

## Blocking Issues

If you discover something that blocks a bead and is outside its stated scope, create a new bead and move on — do not work around it silently:

```bash
bd create --type bug \
  --title "Blocking: <short description>" \
  --description "<file:line>

Discovered while fixing <bead-id>.
<Detail of the problem.>

Done when: <resolution criterion>"
```

Report the new bead ID to the user before continuing to the next bead.

## Report

After all beads are processed:

```
Fixed N beads:
  ✓ <bead title> [<id>]   — <one-line summary of what changed>
  ...

Skipped: 0
New blocking beads filed: 0

Run `bd list` to check for remaining work.
```

## Design Principles

- **One commit per bead.** Readable history, surgical rollback.
- **Verify before closing.** The "Done when" clause — stated or synthesized — is the acceptance criterion. Never close without confirming it passes.
- **Synthesize, don't skip.** If a bead lacks a "Done when", derive one explicitly rather than guessing when you're done.
- **Scope discipline.** Fix exactly what the bead says. File new beads for anything outside that scope.
- **Fail loudly.** Surface errors and gaps. Do not close a bead with a failing verification.
