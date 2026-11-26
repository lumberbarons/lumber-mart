Architectural Decision Record (ADR) and research creation and maintenance tooling.

| Directory | What | When to read |
|-----------|------|--------------|
| `skills/` | Skill definitions (SKILL.md files) | Adding or modifying ADR or research skills |
| `skills/create-adr/` | Scaffolds an ADR from the MADR template, with `adr.py` to check it, move it to accepted and apply its back-links | Changing the ADR format, the checker, or the drafting workflow |
| `skills/refine-adr/` | Interviews the decider about a proposed ADR's weak points and writes the answers back, staying at proposed | Changing the question limit, the weakness lenses, or how answers are folded into the ADR |
| `skills/approve-adr/` | Reviews a proposed ADR on substance, accepts it, and registers it where agents will read it | Changing the review questions, the verdict vocabulary, or what acceptance does |
| `skills/create-research/` | Scaffolds `docs/research/NNNN-slug.md` and checks it, checker-enforced | Changing the research format, the checker, or the investigation workflow |
| `.claude-plugin/` | Plugin metadata | Changing plugin name, version, or description |
| `README.md` | Plugin overview and skill docs | Understanding what decisions does |

The research format lives in `skills/create-research/scripts/research.py`, defined twice — the
skeleton generator and the checker. The tests in `tests/decisions/create-research/test_research.py` pin them together (a
fresh skeleton must fail the check for its `<FILL: ...>` markers and nothing else, and
`reference/example-research.md` must pass); run them when changing either.

Statuses (`draft`, `complete`, `superseded`), finding confidences and source types are closed
vocabularies held shut by the checker. The skill leaves a document at `draft`; only the user moves
it to `complete`.

Research is upstream of ADRs. `create-adr` cites it by id in the ADR's `research` frontmatter;
`approve-adr` adds the ADR's id to the research document's `related` when it accepts the ADR; specs
cite research from their own side and research never links to a spec.

The ADR format lives in `skills/create-adr/assets/adr-template.md` and is enforced by
`skills/create-adr/scripts/adr.py` (`check`, `status`, `backlinks`). `refine-adr` and `approve-adr`
run their own copies in their `scripts/` directories, kept identical by `scripts/sync-skill-files.sh`
at the repo root, so edit the create-adr copy and re-run the sync. The tests in
`tests/decisions/create-adr/test_adr.py` pin the template to the checker (a fresh scaffold must
fail the check for its placeholders and the empty `deciders` list and nothing else); run them when
changing either. Statuses (`proposed`, `accepted`, `superseded`) are a closed vocabulary.
Replacing part of an ADR is `amends`/`amended-by`, not a status: the amended ADR stays
`accepted`. Those two keys are optional in the checker, because ADRs written before they
existed lack them, and `backlinks` inserts `amended-by` into such an ADR when it is amended.
`Pros and Cons of the Options` is likewise optional and held in order only when present.
The size warning in `check` goes to stderr and never fails the check, so gates that look for
`ok` are unaffected.

`create-adr` writes a `proposed` ADR and edits nothing else. Acceptance is what makes an ADR
bind, so everything that makes it bind happens in `approve-adr`, and only there: moving the status,
marking the ADRs it supersedes or amends, linking cited research back, the index entry and the registration in
the agent instructions. `approve-adr` must never run automatically after `create-adr`, and its
substance review runs in a fresh, read-only subagent with no inherited conversation. `refine-adr`
edits a proposed ADR on the user's answers but never moves its status.
