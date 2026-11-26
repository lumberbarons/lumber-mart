# create-adr evals

Evals on the judgement `adr.py` cannot make: whether an ADR records one decision, leaves how to
build it to the spec, and replaces part of an older ADR by amending it rather than superseding
it whole. The checker pins the format; scope and the choice of relationship are the agent's.

Both evals run against `../create-research/fixtures/jobqueue`, a small Redis-backed job queue
with an accepted ADR-0001. Each run gets its own copy with `git init` run in it, so the scripts
find a repository root, and the overlays listed in an eval's `files` are copied over it in order.

| Eval | What it tests |
|------|---------------|
| `bundled-request` | A request that packs a second decision (dead letters to Postgres) and spec-level detail (heartbeat timings, an attempt limit, CLI exit codes) into one ADR comes back as one decision, with the rest named for its own ADR or the spec |
| `partial-change` | Changing one rule of an accepted ADR that bundles several (`fixtures/worker-pool-adr`: config from `jobqueue.toml`) is recorded with `amends`, quoting the rule replaced, not by superseding the whole ADR and adopting the rest by reference |

Runs are unattended: the runner tells the agent to take the recommended choice wherever the
skill says to ask, and to say what it assumed.
