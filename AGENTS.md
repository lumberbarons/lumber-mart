A Codex and Claude Code plugin marketplace hosting plugins for hardware and workflow development.

| Directory | What | When to read |
|-----------|------|--------------|
| `plugins/` | Plugin source directories | Adding or modifying a plugin |
| `.claude-plugin/` | Marketplace metadata | Changing marketplace config or plugin listings |
| `.agents/plugins/` | Codex marketplace catalog | Changing plugin listings or install policies |
| `README.md` | Project overview and quick start | Understanding what lumber-mart is |
| `scripts/` | Repo tooling: `sync-skill-files.sh` copies files shared by several skills into each skill directory; `check-marketplace.py` enforces the version rules in CI | Editing a file more than one skill ships, or adding one |
| `.github/` | CI: shared-file sync, official marketplace validation, skill frontmatter, marketplace and version checks, lightspec tests, shellcheck | Changing what CI enforces |
| `LICENSE` | MIT license | Checking license terms |

Changing a plugin means bumping its `version` in `plugins/<name>/plugin.json` and
`plugins/<name>/.claude-plugin/plugin.json`, and setting the same value on its entry in
`.claude-plugin/marketplace.json`, in the same commit as the change. Portable root manifests
are canonical; keep their identity fields equal to the Claude manifests. Both catalogs must
list the same plugins at the same repo-relative paths. Versions must never drift apart:
Claude Code installs from its manifest, while
marketplace browsers such as APM display the entry's `version`, and the version is the only thing
distinguishing a revised plugin from the copy someone already installed. Unbumped, a fix is
indistinguishable from no fix at all, and there is no way to tell from the outside which revision
anyone is running. `scripts/check-marketplace.py` fails CI when the two disagree, and when a
change under `plugins/<name>/` has not advanced the version past the base branch. Carry the new
versions in the PR title as `[vX.Y.Z]`, matching the existing history: minor for behaviour a
caller could notice, major with a `!` when something is removed or renamed.
