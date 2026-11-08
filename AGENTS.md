A Claude Code plugin marketplace hosting plugins for hardware and workflow development.

| Directory | What | When to read |
|-----------|------|--------------|
| `plugins/` | Plugin source directories | Adding or modifying a plugin |
| `evals/` | Skill evals and their fixtures, as `evals/<plugin>/<skill>/`; kept outside `plugins/` so installing a plugin does not copy them | Writing, running, or moving a skill's evals |
| `tests/` | Script tests, as `tests/<plugin>/<skill>/` (`tests/critique/shared/` for the scripts several critique skills ship); kept outside `plugins/` so installing a plugin does not copy them. `scripts/run-tests.sh` runs every suite, one interpreter each, and CI calls it | Writing or running a script's tests |
| `.claude-plugin/` | Marketplace metadata | Changing marketplace config or plugin listings |
| `README.md` | Project overview and quick start | Understanding what lumber-mart is |
| `scripts/` | Repo tooling: `sync-skill-files.sh` copies files shared by several skills into each skill directory; `check-marketplace.py` enforces the version rules in CI | Editing a file more than one skill ships, or adding one |
| `.github/` | CI: shared-file sync, official marketplace validation, skill frontmatter, marketplace and version checks, script tests, shellcheck | Changing what CI enforces |
| `LICENSE` | MIT license | Checking license terms |

Changing a plugin means bumping its `version` in `plugins/<name>/.claude-plugin/plugin.json` and
setting the same value on its entry in `.claude-plugin/marketplace.json`, in the same commit as
the change. The two must never drift apart: Claude Code installs from `plugin.json`, while
marketplace browsers such as APM display the entry's `version`, and the version is the only thing
distinguishing a revised plugin from the copy someone already installed. Unbumped, a fix is
indistinguishable from no fix at all, and there is no way to tell from the outside which revision
anyone is running. `scripts/check-marketplace.py` fails CI when the two disagree, and when a
change under `plugins/<name>/` has not advanced the version past the base branch. Carry the new
versions in the PR title as `[vX.Y.Z]`, matching the existing history: minor for behaviour a
caller could notice, major with a `!` when something is removed or renamed.
