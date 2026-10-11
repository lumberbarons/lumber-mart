Operational runbook creation and maintenance tooling.

| Directory | What | When to read |
|-----------|------|--------------|
| `skills/` | Skill definitions (SKILL.md files) | Adding or modifying runbook skills |
| `apm.yml` and `.apm/` | Generated APM compatibility metadata and layout marker | Run the root sync script after changing portable metadata; keep skills in `skills/` |
| `plugin.json` | Canonical portable manifest; identity matches the Claude manifest | Changing plugin metadata or versions |
| `.claude-plugin/` | Plugin metadata | Changing plugin name, version, or description |
| `README.md` | Plugin overview and skill docs | Understanding what runbooks does |
