Review skills for code, tests, and documentation quality.

| Directory | What | When to read |
|-----------|------|--------------|
| `skills/` | Skill definitions (SKILL.md files) | Adding or modifying critique skills |
| `FINDINGS.md` | Schema for the `--json` findings file; source for the copy in each skill | Changing machine-readable output, or what a downstream consumer can rely on |
| `scripts/discover-files.sh` | Scope discovery (source for the copy in each skill that scopes); exit codes drive the no_scope/error split | Changing how review scope is determined |
| `scripts/review-mode.py`, `REVIEW-MODE.md` | Shared report/fix decision and repair policy, copied into code and test skills | Changing when reviews repair findings |
| `.claude-plugin/` | Plugin metadata | Changing plugin name, version, or description |
| `README.md` | Plugin overview and skill docs | Understanding what critique does |

The shared files above are the sources; each skill that uses them
carries its own copy, because per-skill installers such as APM copy a skill's directory and
nothing around it. Edit the source, then run `scripts/sync-skill-files.sh` from the repo root.

Run `python3 -m unittest discover -s plugins/critique/scripts` for review-mode Git boundary tests.

Every critique skill must itself be agent-agnostic — a harness-coupled construct in a review
skill is a finding in its own deliverable. When editing a skill here, run the `skill-portability`
plugin's `review-portability` against it.
