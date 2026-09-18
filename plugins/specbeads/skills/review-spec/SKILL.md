---
name: review-spec
description: Validate implementation against spec-kit artifacts (spec.md, plan.md, constitution.md). Use when asked to check spec conformance, validate implementation matches specs, or audit code against specifications.
---

# Spec Review

Validate that the implementation conforms to its spec-kit artifacts.

> [!IMPORTANT]
> Consult `REFERENCE.md` in this skill directory for the expected output format and level of detail.

## User Input

You **MUST** consider the user input before proceeding (if any was given).

## Argument Parsing

Parse the input for:
- **Path**: Optional path to focus the review (default: entire repo)
- **Spec folder name**: If provided (e.g., `001-user-auth`), use that spec instead of deriving from branch
- **`--create-beads`**: Create beads for findings (default: report only)

## Outline

### 1. Validate Prerequisites

Run prerequisite checks:

```bash
./.specify/scripts/bash/check-prerequisites.sh --json
```

Parse the JSON response to get `FEATURE_DIR`.

Then verify beads is initialized:

```bash
bd info
```

> [!CAUTION]
> ERROR if beads is not initialized. Instruct user to run `bd onboard` first.
> ERROR if spec.md is missing. Instruct user to run `/speckit.spec` first.

If a spec folder name was provided in arguments, override `FEATURE_DIR` to `specs/<folder-name>`.

### 2. Load Context Documents

Read from `FEATURE_DIR`:
- **Required**: `spec.md`
- **Optional**: `plan.md`, `.specify/memory/constitution.md`

Note which optional documents are present — validation criteria are gated on document availability.

### 3. Read Implementation Code

If a path argument was provided, scope to that path. Otherwise, read the project's source code (excluding vendor, node_modules, build output, and other generated directories).

Build a working understanding of the implementation: files, modules, public APIs, imports, configuration, and test files.

### 4. Validation

Run each applicable validation section below. Skip sections whose required documents are not present.

**Status Definitions** (use consistently throughout):
- ✅ PASS: Fully implemented as specified
- ⚠️ PARTIAL: Implemented but with minor deviations from spec
- ❌ GAP: Missing or significantly divergent

**Evidence Format**: `file:line` only (or `—` if no specific location). Detailed explanations go in Findings section.

**Table Output**: Only show non-passing items (⚠️ PARTIAL and ❌ GAP). End each table with "N passed, not shown."

#### 4.1 Specification Conformance (requires spec.md)

Evaluate ALL functional requirements and acceptance criteria from spec.md.

**Functional Requirements**: Scan spec.md for all FR-xxx identifiers or numbered requirements. For each:
- Compare the implementation against the requirement
- Evaluate: behavior coverage, edge case handling, constraint enforcement, API surface match
- Record status and evidence for non-passing items

**Acceptance Criteria**: Scan spec.md for all user stories (USx-x format) and their scenarios. For each scenario:
- Verify the described behavior is implemented
- Record status and evidence for non-passing items

#### 4.2 Architecture Consistency (requires plan.md)

Extract ALL architectural declarations from plan.md. This includes:
- Module/package structure
- Naming conventions
- Technology choices (frameworks, libraries, databases)
- Configuration patterns
- External integrations

Evaluate each declaration:
- Does the code use the declared frameworks/libraries? (check imports, config files, dependency manifests)
- Is code organized per the declared directory structure?
- Do external service integrations match the plan?
- Does the data layer match (database driver, ORM, migration tool)?

#### 4.3 Constitution Alignment (requires constitution.md)

For EACH numbered principle in constitution.md, create a table row and evaluate whether the code adheres to it. Common principle categories:
- API design standards
- Security requirements
- Infrastructure-as-code requirements
- Testing standards
- Code organization conventions

Only flag cases where code clearly contradicts a stated principle. Do not flag ambiguous or inapplicable cases.

### 5. Deduplication

Before creating beads, check for existing ones:

- Run `bd list --status=open` to see all open issues
- Run `bd list --status=closed` to see previously resolved issues
- Compare findings against existing bead titles and descriptions
- Skip creating beads for issues that already have matching open beads
- **Check closed beads before suppressing.** Use `bd show <id>` on relevant closed beads and verify the fix actually resolved the issue in the current code. Only suppress if the fix is complete — if the problem still exists (in the same or different locations), create a new bead for the remaining instances. The goal is to prevent flip-flopping on intentional resolutions, not to give closed beads permanent immunity.

### 6. Report Format (Mandatory)

You MUST produce a report following the exact structure shown in `REFERENCE.md`. This format is required for every review—do not deviate.

Key rules:
- Only show non-passing items (⚠️ PARTIAL, ❌ GAP) in validation tables—end each with "N passed, not shown."
- Evidence column is just `file:line` (or `—`)—detailed explanations go in Findings
- Use H3 headers for Findings section (see REFERENCE.md for format)
- No Summary table—Findings section already lists issues
- Skip sections (4.2, 4.3) if their required documents are not present
- Include Findings section only if there are non-passing items
- End with "To create beads..." footer unless `--create-beads` was used

### 7. Bead Creation (`--create-beads` mode)

When `--create-beads` is specified, create beads for each finding.

Each bead description MUST include all five fields:

```
**Source**: <spec.md|plan.md|constitution.md §section-heading>
**Violated**: <exact quote or requirement identifier from the source document>
**Code**: <file:line (or — if not yet implemented)>

Fix: <Concrete prescription tied to the spec. Reference the specific section,
requirement ID, or user story. Example: "Implement the rate-limit check from
spec.md §FR-004: reject requests exceeding 100/min with HTTP 429 before
the handler runs." Not: "Implement the missing requirement.">

Done when: <Verifiable criterion. Must name observable code behaviour or a
specific test. Example: "A request at 101/min receives HTTP 429; a test
covers this scenario."
NOT: "The spec requirement is satisfied.">
```

```bash
bd create --type=bug --priority=<1-3> \
  --title="Spec: <issue>" \
  --description="**Source**: <spec.md|plan.md|constitution.md §section>
**Violated**: <quote or requirement ID>
**Code**: <file:line>

Fix: <concrete prescription>

Done when: <verifiable criterion>"
```

**Priority mapping**:
- Missing core behavior from spec: P1
- Architecture divergence from plan: P2
- Constitution violations: P2

After creating beads, append to the report:

```
## Beads Created

- <bead-id>: "<title>"
- ...
```

Omit the "To create beads..." footer when beads have been created.

## Error Handling

- If `bd` commands fail, report the error and continue with remaining findings
- If spec.md cannot be read, abort (it is the only hard requirement)
- Missing optional documents skip their corresponding validation sections silently

## Design Principles

- **Spec-aware**: This command reads and understands spec-kit artifacts, unlike the generic review commands
- **Code-level validation**: Evaluates actual code against specs, not just file existence or build output
- **Gated sections**: Each validation section is gated on its required document being present
- **Non-destructive**: Creates bug beads for findings, never modifies source code or spec artifacts
- **Focused scope**: Validates spec conformance only — use the critique plugin's `review-code`, `review-tests`, `review-docs` skills for generic quality
- **Stable numbering**: When recommending removal of a numbered item (FR-xxx, USx-x, principles), never delete it. Mark it as "Removed" in place to preserve stable identifiers and avoid breaking cross-references
