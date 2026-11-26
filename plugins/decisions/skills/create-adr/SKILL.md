---
name: create-adr
description: Creates an Architectural Decision Record (ADR) in MADR format, researching the codebase and prior ADRs to fill in real context, alternatives, and consequences. Use when the user asks to record, log, write, capture, or document an architectural decision, design choice, technology selection, trade-off, or ADR — including phrases like "make an ADR", "write this up as a decision", or "capture why we picked X". Also invoke proactively when the conversation is clearly settling a non-trivial architectural question (framework selection, data model choice, protocol trade-off, sequencing of a migration) and no ADR has been drafted yet — in that case, offer to record it before the thread moves on.
---

# Create ADR

## User Input

The user's request describes the decision being recorded (e.g., "use Postgres for the event store", "adopt trunk-based development", "replace custom retry wrapper with Temporal").

If the request does not state a decision, ask the user what decision they want to record — specifically, what was chosen and what alternatives were considered. Do not proceed without at least a decision statement.

## Orientation

ADRs are **standalone policy**. Each one records a constraint and the reasoning behind it; it does not track the downstream specs, plans, or tasks that inherit that constraint. The citation direction runs the other way: a spec that is shaped by an ADR names that ADR in its own frontmatter. The link lives on the churning side (specs get renamed, split, archived), not the stable side (accepted ADRs are append-only history). Once an ADR is accepted you do not revise it when downstream artifacts move around.

The primary reader of an ADR in this project is another AI agent picking up the codebase weeks or months from now. That agent will decide whether a proposed change respects or violates the decision, and whether a driver has shifted enough that the ADR should be revisited. Write for that reader: state the drivers precisely enough that an agent can evaluate "does this still hold?", and name the rejected options so the agent doesn't re-propose them.

**One decision per ADR.** An ADR answers one question: what was chosen, over what, for which reasons, at what cost, and what future code must therefore keep true. It can be summed up in one sentence — *in the context of X, facing Y, we chose Z over W, to get V, accepting U* — and if yours cannot, it holds more than one decision. Keep it to a page or two. Two things make ADRs grow past that, and both cost more than the words:

- **A second decision.** If a part of the outcome could be reversed on its own while the rest still stands, it is a decision of its own and gets its own ADR. Bundled, it can only be replaced by superseding everything around it.
- **Design detail.** Interfaces, file layouts, command exit codes, sequences, error handling and test plans say *how* to build what the ADR decided. They belong in the spec that cites the ADR. Written into an accepted ADR, each becomes binding policy that `review-policy` holds code to and that only a new ADR can change.

The ADR keeps the invariants: the few rules a reviewer could cite against a diff to say that a change breaks the decision.

Use MADR format with rich frontmatter. Link to other ADRs via `supersedes`, `superseded-by`, `amends`, `amended-by` and `related`, and to the research the decision rests on via `research` — those edges are stable and directionally correct. Do not embed paths to specs, plans, or task files; those are forward-references that rot.

Research (`create-research`) sits upstream of the ADR: it establishes what is true, and the ADR records what was decided given that. An ADR cites the research documents it relies on by id (`RES-0004`), and once the ADR is accepted the cited document gets this ADR's id added to its own `related`, so the link can be followed from either end. Both ends are append-only records with stable ids, which is what makes a link in each direction safe; that does not extend to specs, which is why the spec side still does the citing.

This skill writes a **`proposed`** ADR and stops. A proposed ADR is not policy: `review-policy` ignores it, it is not registered in the agent instructions, and nothing else is edited on its account. Acceptance is a separate act by a person, through `approve-adr`, and it is what applies the supersede, amend and research back-links, updates the index and registers the ADR. `refine-adr` sharpens a proposed ADR before then. Keeping the two apart means an ADR that is never accepted leaves nothing behind.

The format is held by `adr.py`, which sits in this skill's `scripts/` directory: `check` validates an ADR against the template, and it is what `refine-adr` and `approve-adr` gate on. Resolve it once:

```bash
ADR="<this skill's directory>/scripts/adr.py"
```

## Workflow

### Step 1: Determine the ADR directory

Check the target project for an existing ADR directory, in this order:

1. If `docs/adr/` exists, use it
2. If `docs/decisions/` exists, use it
3. If `docs/adrs/` exists, use it
4. If none exist, ask the user where ADRs should live, defaulting to `docs/adr/`

### Step 2: Read existing ADRs

If the directory already contains ADRs, read them before drafting. You need to know:

- **Already-documented decisions** — if an existing ADR already covers the same choice at the same scope, stop and tell the user which ADR it is. Do not create a duplicate. If the user's intent is actually to *change* the prior decision, that's a supersede flow (see below), not a new ADR.
- **Conflict, supersede or amend candidates** — any prior ADR that contradicts or is narrower than the new one. Record the relationship in the new ADR only, and leave the old ADR exactly as it is: it stays `accepted`, and so stays binding, until the new one is accepted, at which point `approve-adr` applies the back-link.
  - **The new decision replaces the old one whole** → `supersedes:`. On acceptance the old ADR becomes `superseded` and stops binding.
  - **It replaces only part of an older ADR**, usually one that bundled several decisions → `amends:`. On acceptance the old ADR stays `accepted` and gains `amended-by`; everything in it still binds except what the amendment replaces. In Decision Outcome, quote the lines of the old ADR this one replaces, so a reader can tell exactly where the old record stops applying.
  - **Never supersede a whole ADR to change one part of it and then adopt the rest back by reference** ("this ADR adopts ADR-0006's decision, with three exceptions"). That leaves binding policy inside a record marked superseded, reachable only through an ADR named for something else, and the next change to it has to carry the chain further. Amend instead.
- **Related decisions** — prior ADRs that the new one depends on or complements. Capture these in `related:`.
- **House style** — deciders convention, tag vocabulary, any project-specific sections.

Then look for research. Find the research directory (`docs/research/` or `research/`) and read the titles and research questions of what is there. A document that investigated this question, or the options on the table, is the strongest source for the Context, Drivers and Consequences you are about to write, so read it before researching the codebase yourself in Step 6.

- **Cite only research whose `status` is `complete`.** A `draft` is unconfirmed; if it is the only research there is, say so in your report rather than resting the decision on it.
- **Do not cite `superseded` research.** Follow its `superseded-by` to the document that replaced it.
- **Weigh the confidence of the findings you lean on.** A driver that rests on a `Low` finding should be written as an assumption, not as fact.
- **Check `Revisit When`.** If a condition in it has been met, the research is stale. Tell the user and suggest `create-research` to refresh it before the ADR leans on it.
- **A decision with no research behind it is fine** when the question is simple or already well understood. Write `research: []`. If the choice hinges on facts nobody has established yet, say that in your report and offer `create-research` first, rather than inventing the evidence.

### Step 3: Scope it to one decision

Write the one-sentence summary — *in the context of X, facing Y, we chose Z over W, to get V, accepting U* — before writing anything else. It is the test of scope, and it becomes the first line of the Decision Outcome.

If the request settles several things, list them and sort each into one of three:

- **The decision** — the one choice this ADR records.
- **Another decision** — something that could be reversed while the first one stands (where state lives, which transport the API uses, which risk to accept). Tell the user these deserve ADRs of their own and ask which to record now. Do not fold them in to save a step.
- **Design detail** — how the decision gets built. Leave it out, and say in your report that it belongs in the spec.

Ask the user only when the split is not obvious from the request.

### Step 4: Generate the slug and title

Derive a kebab-case slug from the decision statement. The slug should name the *choice*, not the problem.

Examples:
- "use Postgres for the event store instead of DynamoDB" → slug `use-postgres-event-store`, title `Use Postgres for the event store`
- "adopt trunk-based development with short-lived feature flags" → slug `adopt-trunk-based-dev`, title `Adopt trunk-based development`
- "replace the custom retry wrapper with Temporal workflows" → slug `replace-retry-wrapper-with-temporal`, title `Replace retry wrapper with Temporal workflows`

Prefer verb-first, imperative. Keep the slug concise; the title can be slightly more descriptive but should still fit in a commit-message line.

### Step 5: Scaffold the ADR

The scaffold script requires `bash` and `jq` on PATH. Check both before running
it; if a dependency is missing, report it before creating the ADR file.

Run the init script to create the file from the template. The script auto-numbers the ADR by scanning the target directory for the highest existing `NNNN-*.md` and incrementing. It sits in `scripts/` beside this file — resolve it once against this skill's own directory rather than hardcoding a path, which breaks the moment the skill is vendored into another repo or installed elsewhere:

```bash
INIT_ADR="<this skill's directory>/scripts/init-adr.sh"
bash "$INIT_ADR" <slug> <adr-dir> "<title>"
```

This outputs JSON with `ADR_FILE`, `ADR_DIR`, `ADR_ID`, and `ADR_NUMBER`. Use `ADR_FILE` for all subsequent edits.

### Step 6: Research the codebase

Before filling in the template, investigate the project to ground the ADR in reality:

- **Code paths the decision affects** — modules, services, or directories that will change
- **Existing specs and plans** — scan `docs/specs/`, `specs/`, spec-kit artifacts, `plan.md`, `tasks.md` for context on how the decision will land in practice, but do **not** record their paths in the ADR; forward-references to specs rot as specs are renamed or archived
- **Configuration and infra** — Dockerfiles, Terraform, CI pipelines, package manifests
- **Prior discussion artifacts** — commit messages, PR descriptions, existing docs on the topic
- **Operational realities** — observability, runbooks, deployment model that constrain viable options

> [!IMPORTANT]
> Decision Drivers must be **specific to this project**, not generic engineering platitudes. "Must be fast" is not a driver. "p99 read latency budget is 30 ms under 10k QPS because of the checkout path in `services/checkout/`" is a driver. If you cannot find specifics from the codebase or user, ask — do not invent numbers.

### Step 7: Fill in the ADR

Edit the scaffolded file, replacing every placeholder with project-specific content:

- **Frontmatter**:
  - `status`: always `proposed`, even if the user says the decision is already made — acceptance goes through `approve-adr`, which is also what registers it
  - `deciders`: names/handles of the people deciding, from the user's input — do not guess. If you do not have them, ask; `check` rejects an empty list
  - `supersedes` / `amends` / `related`: ADR IDs you identified in Step 2. Leave `superseded-by` and `amended-by` empty — they are filled in when a later ADR is accepted
  - `research`: the `RES-NNNN` IDs of the research documents this decision rests on, from Step 2. Ids only, not paths
  - `tags`: short nouns (e.g., `storage`, `observability`, `build`) — reuse vocabulary from prior ADRs
- **Context and Problem Statement**: the forces at play, grounded in the codebase research and any cited research documents, ending on the one question this ADR answers
- **Decision Drivers**: specific, measurable where possible
- **Considered Options**: include the chosen option plus at least one real alternative; "do nothing" is a valid option if relevant
- **Decision Outcome**: the one-sentence decision from Step 3, then *which drivers tipped the balance* and, for each rejected option, the driver it failed — a reader should be able to tell whether changing a driver would invalidate this decision. An amendment also quotes the lines of the amended ADR it replaces
- **Consequences**: honest positives, negatives, and risks; if there are no negatives, you haven't thought hard enough
- **Implementation Notes**: the invariants future changes must respect, each phrased so a reviewer could cite it against a diff, and the conditions that would prompt revisiting. Not how to build it: interfaces, file layouts, sequences and test plans go in the spec
- **References**: links to discussions, PRs, issues, and prior ADRs, plus a markdown link to each cited research document with a few words on what it established. Where a driver or consequence rests on a specific finding, name it in the text (`RES-0004 F2`) so a later reader can check the claim at its source

**Say each thing once.** A rule stated in the Decision Outcome, again as an invariant and again in a consequence will be edited in one place and not the others, and the copies then contradict each other. Put each rule where it belongs and refer to it elsewhere. The template has no per-option Pros and Cons section for this reason: the reasons an option lost go in the Decision Outcome. A project whose earlier ADRs keep that section may keep it as house style.

> [!NOTE]
> If the request or the conversation does not provide enough material for Decision Drivers or Consequences, stop and ask the user. An ADR with hand-wavy drivers and made-up consequences is worse than no ADR.

### Step 8: Check the ADR

```bash
uv run --no-project "$ADR" check <ADR_FILE>
```

Fix whatever it reports — an unfilled placeholder, an empty `deciders` list, a cited research document that does not exist — before showing the ADR to anyone. Do not edit any other file: no back-links, no index entry, no change to the agent instructions. Those belong to acceptance (`approve-adr`).

A `warning:` that the body is long does not fail the check, but take it as a sign that Step 3 let something through. Re-read the Decision Outcome and Implementation Notes for a second decision or for design detail, and move it out before presenting the ADR.

### Step 9: Present for review

Show the user the completed ADR and ask whether the drivers, rejected alternatives, and consequences match their intent. Explicitly flag:

- Any section where you had to make assumptions due to limited information
- Any `supersedes` or `amends` link, and that the older ADR stays binding as written until this one is accepted
- Anything you left out under Step 3: the other decisions that deserve ADRs of their own, and the design detail that belongs in the spec
- Which research documents the decision cites, and any driver that rests on a `Low`-confidence finding or on research still at `draft`

Say that the ADR is `proposed` and what comes next: `refine-adr` to sharpen it with a short interview, `approve-adr` to review and accept it. Do not run either unprompted, and do not change `status` yourself.
