Architectural Decision Record (ADR) and research creation and maintenance tooling.

| Directory | What | When to read |
|-----------|------|--------------|
| `skills/` | Skill definitions (SKILL.md files) | Adding or modifying ADR or research skills |
| `skills/create-research/` | Scaffolds `docs/research/NNNN-slug.md` and checks it, checker-enforced | Changing the research format, the checker, or the investigation workflow |
| `.claude-plugin/` | Plugin metadata | Changing plugin name, version, or description |
| `README.md` | Plugin overview and skill docs | Understanding what decisions does |

The research format lives in `skills/create-research/scripts/research.py`, defined twice — the
skeleton generator and the checker. The tests in `scripts/test_research.py` pin them together (a
fresh skeleton must fail the check for its `<FILL: ...>` markers and nothing else, and
`reference/example-research.md` must pass); run them when changing either.

Statuses (`draft`, `complete`, `superseded`), finding confidences and source types are closed
vocabularies held shut by the checker. The skill leaves a document at `draft`; only the user moves
it to `complete`.

Research is upstream of ADRs. `create-adr` cites it by id in the ADR's `research` frontmatter and
adds the ADR's id to the research document's `related`; specs cite research from their own side
and research never links to a spec.
