Skills for orchestrating a [hew](https://github.com/lumberbarons/hew) epic across
[herdr](https://github.com/lumberbarons/herdr)-managed agents.

| Directory | What | When to read |
|-----------|------|--------------|
| `skills/work-epic/` | Fans an epic out to worker agents and reviews their PRs | Changing how the pump resolves, spawns, reaps, or reports |
| `skills/work-epic/REFERENCE.md` | Resolver schema, prompt templates, naming, timeout budgets, report format | Changing what the pump tells its agents or how it reads them back |
| `skills/work-epic/scripts/resolve_ready.py` | The deterministic spawn planner | Changing which children get worked or in what order |
| `README.md` | Plugin overview and pipeline | Understanding what work-epic does |

Requires `hew` on PATH (authenticated), the `herdr` CLI, and the skills this pump drives:
`work-issue` (hew plugin) for workers and `review-code` (critique plugin) for reviewers.

The resolver script is the spawn authority. Anything that sorts, filters, or sizes hew's output
in the agent's head instead of running `resolve_ready.py` makes the pump un-reasonable-about from
its logs — two runs on the same epic must produce the same plan, and the script is what makes
that true. Changes to spawn policy belong in the script, where they are testable, not in the
skill prose.

The pump keeps the human gates by design: it never merges a PR, never closes an issue or epic,
never `--force`s a claim, and never clicks through a worker's permission dialog. Removing any of
those turns an accelerator into an unsupervised committer. The `we-`/`wr-` name prefixes are the
ownership rule that lets several orchestrators share a repo safely — closing or reassigning an
agent outside your own prefix breaks that.

Worker and reviewer outcomes are read from `--json` files, never inferred from terminal output:
herdr's settled states prove an agent stopped, the file says what happened. Pointing outcome
paths anywhere but `${TMPDIR:-/tmp}/opencode` costs every spawned agent a permission dialog.
