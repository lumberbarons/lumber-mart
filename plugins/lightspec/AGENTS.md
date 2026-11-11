The lightspec spec pipeline: draft, approve, and file a feature spec as trackable work.

| Directory | What | When to read |
|-----------|------|--------------|
| `skills/draft-spec/` | Drafts a spec into `specs/NNN-slug/spec.md`, checker-enforced | Changing the spec format, the checker, or the drafting workflow |
| `skills/refine-spec/` | Interviews the author about a Draft spec's rough edges and writes the answers back, staying at Draft | Changing the question limit, the ambiguity lenses, or how answers are folded into the spec |
| `skills/approve-spec/` | Reviews a Draft spec on substance, moves it to Accepted | Changing the review questions or the verdict vocabulary |
| `skills/spec-to-epic/` | Files an Accepted spec as a hew epic with one child per story | Changing the mapping to hew's body conventions or the plan schema |
| `README.md` | Pipeline overview | Understanding what lightspec does |

The format lives in `skills/draft-spec/scripts/lightspec.py`, and the format is defined twice —
the skeleton generator and the checker. The tests in `tests/lightspec/draft-spec/test_lightspec.py` pin them
together; run them when changing either. That file is the source: `refine-spec`, `approve-spec` and
`spec-to-epic` run their own copies in their `scripts/` directories, kept identical by
`scripts/sync-skill-files.sh` at the repo root, so edit the draft-spec copy and re-run the sync.
`spec-to-epic` checks shape and status locally before filing, independently of other installed
skills. Its bundled `reference/example-spec.md` is also synced from draft-spec for parser tests.

Statuses are a closed vocabulary (`Draft`, `Accepted`, `Implemented`, `Superseded`) held shut by
the checker; `approve-spec` is the only thing that moves a spec off `Draft`, and it must never
run automatically after drafting — an author who approves their own work has not been reviewed.

`refine-spec` edits a spec but never moves its status: it works only on `Draft`, keeps `check` green
after every write, and has no log of questions to keep because the checker holds the section list
shut — answers are folded into the body and history lives in version control. It is the one skill
that edits a spec on the user's answers; `approve-spec` still never edits what it reviews.

`spec-to-epic` gates on `Accepted` before filing: a Draft spec's issues are a quiet way of
building from something nobody signed off on. It also owns the deliberate non-feature of not
inventing dependency chains between stories — hew's priority-then-oldest ordering is the build
sequence, and a guessed `--blocked-by` graph blocks work that was never blocked.
