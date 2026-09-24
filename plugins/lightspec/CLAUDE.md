The lightspec spec pipeline: draft, approve, and file a feature spec as trackable work.

| Directory | What | When to read |
|-----------|------|--------------|
| `skills/draft-spec/` | Drafts a spec into `specs/NNN-slug/spec.md`, checker-enforced | Changing the spec format, the checker, or the drafting workflow |
| `skills/approve-spec/` | Reviews a Draft spec on substance, moves it to Accepted | Changing the review questions or the verdict vocabulary |
| `skills/spec-to-epic/` | Files an Accepted spec as a hew epic with one child per story | Changing the mapping to hew's body conventions or the plan schema |
| `README.md` | Pipeline overview | Understanding what lightspec does |

The format lives in `skills/draft-spec/scripts/lightspec.py`, and the format is defined twice —
the skeleton generator and the checker. The tests in `scripts/test_lightspec.py` pin them
together; run them when changing either. That file is the source: `approve-spec` runs its own
copy in `skills/approve-spec/scripts/`, kept identical by `scripts/sync-skill-files.sh` at the
repo root, so edit the draft-spec copy and re-run the sync. `spec-to-epic` reads the `**Status**`
line itself and only uses lightspec when a draft-spec install is there to find.

Statuses are a closed vocabulary (`Draft`, `Accepted`, `Implemented`, `Superseded`) held shut by
the checker; `approve-spec` is the only thing that moves a spec off `Draft`, and it must never
run automatically after drafting — an author who approves their own work has not been reviewed.

`spec-to-epic` gates on `Accepted` before filing: a Draft spec's issues are a quiet way of
building from something nobody signed off on. It also owns the deliberate non-feature of not
inventing dependency chains between stories — hew's priority-then-oldest ordering is the build
sequence, and a guessed `--blocked-by` graph blocks work that was never blocked.
