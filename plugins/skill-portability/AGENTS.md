Skill portability review: finds agent-harness coupling in skill files.

| Directory | What | When to read |
|-----------|------|--------------|
| `skills/review-portability/` | The review skill: `SKILL.md`, the pattern vocabulary in `REFERENCE.md`, and a copy of the findings schema | Adding or modifying the portability review |
| `.claude-plugin/` | Plugin metadata | Changing plugin name, version, or description |
| `README.md` | Plugin overview and skill docs | Understanding what skill-portability does |

`skills/review-portability/FINDINGS.md` is a copy: its source is `plugins/critique/FINDINGS.md`,
the schema shared by every review skill and read by hew's `raise-issues`. Edit the source, then run
`scripts/sync-skill-files.sh` from the repo root.

The skill must itself be agent-agnostic — a harness-coupled construct in it is a finding in its own
deliverable. When editing it, run `review-portability` against it.
