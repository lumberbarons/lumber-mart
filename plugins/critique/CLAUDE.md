Review skills for code, tests, documentation quality, and skill portability.

| Directory | What | When to read |
|-----------|------|--------------|
| `skills/` | Skill definitions (SKILL.md files) | Adding or modifying critique skills |
| `FINDINGS.md` | Schema for the `--json` findings file, shared by all five skills | Changing machine-readable output, or what a downstream consumer can rely on |
| `scripts/discover-files.sh` | Scope discovery; exit codes drive the no_scope/error split | Changing how review scope is determined |
| `.claude-plugin/` | Plugin metadata | Changing plugin name, version, or description |
| `README.md` | Plugin overview and skill docs | Understanding what critique does |

Every critique skill must itself be agent-agnostic — these files are the ones
`review-portability` exists to police, so a harness-coupled construct in a review skill is a
finding in its own deliverable. When editing a skill here, run `review-portability` against it.
