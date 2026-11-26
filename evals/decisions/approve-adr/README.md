# approve-adr evals

Evals on the reviewer's judgement, which is the part of `approve-adr` that decides whether an
ADR converges. The runner plays the calling agent's dispatch: it gives a fresh agent the ADR
path, the repository root and this skill's path, and asks it to perform the reviewer steps
(3–5) and return a verdict. The gate, acceptance and registration steps are scripted and
covered by `tests/decisions/create-adr/`.

Both evals run against `../create-research/fixtures/jobqueue` with an overlay that adds a
proposed ADR-0002, in a fresh copy with `git init` run in it.

| Eval | What it tests |
|------|---------------|
| `bloated-proposal` | An ADR that bundles a second decision, spec-level detail with a defect in it (a 45 s heartbeat against a 30 s TTL) and a rule stated two ways is sent back with scope as the lead finding, and the fix is to cut, not to correct the detail or add caveats inside the ADR |
| `tight-proposal` | A control: a page-long ADR recording only the decision, with real options, disclosed costs and checkable invariants, is approved, so the scope question does not over-block |

The tight proposal has no Pros and Cons section, which the checker before v2.4.0 required; a
baseline run against that version reviews its substance only, since the runner skips the gate.
