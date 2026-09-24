A Claude Code plugin marketplace hosting plugins for hardware and workflow development.

| Directory | What | When to read |
|-----------|------|--------------|
| `plugins/` | Plugin source directories | Adding or modifying a plugin |
| `.claude-plugin/` | Marketplace metadata | Changing marketplace config or plugin listings |
| `README.md` | Project overview and quick start | Understanding what lumber-mart is |
| `scripts/` | Repo tooling: `sync-skill-files.sh` copies files shared by several skills into each skill directory | Editing a file more than one skill ships, or adding one |
| `.github/` | CI: checks shared skill files match their sources | Changing what CI enforces |
| `LICENSE` | MIT license | Checking license terms |

Changing a plugin means bumping its `version` in `plugins/<name>/.claude-plugin/plugin.json`, in
the same commit as the change. That field is the only thing distinguishing a revised plugin from
the copy someone already installed — unbumped, a fix is indistinguishable from no fix at all, and
there is no way to tell from the outside which revision anyone is running. Carry the new version
in the PR title as `[vX.Y.Z]`, matching the existing history: minor for behaviour a caller could
notice, major with a `!` when something is removed or renamed. Only `plugin.json` carries a
version; `marketplace.json` has no per-plugin version to keep in step.
