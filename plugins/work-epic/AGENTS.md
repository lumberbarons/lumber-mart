Skills for orchestrating a [hew](https://github.com/lumberbarons/hew) epic across
[herdr](https://github.com/lumberbarons/herdr)-managed agents.

| Directory | What | When to read |
|-----------|------|--------------|
| `skills/work-epic/` | Pumps an epic: workers, reviewers, reconcilers, findings filing, merge pass | Changing how the pump resolves, spawns, reaps, files, merges, or reports |
| `skills/work-epic/REFERENCE.md` | The scripts' schemas, prompt templates, review-round and reconciliation comments, filing flow, naming, budgets, report format | Changing what the pump tells its agents or how it reads them back |
| `skills/work-epic/scripts/resolve_ready.py` | The deterministic spawn planner | Changing which children get worked or in what order |
| `skills/work-epic/scripts/pr_state.py` | The deterministic merge-pass planner | Changing which PRs merge, reconcile, update, hold, or escalate |
| `skills/work-epic/scripts/repo_state.py` | Read-only git/gh probes both planners share | Changing how PRs, branches, or the default branch are read |
| `skills/work-epic/scripts/test_*.py` | stdlib `unittest` over both decision tables | Changing any decision, skip reason, or parser — add the pinning case |
| `README.md` | Plugin overview and the modes | Understanding what work-epic does |

Requires `hew` on PATH (authenticated), the `herdr` CLI, and the skills this pump drives:
`work-issue` (hew plugin) for workers and `review-code` (critique plugin) for reviewers;
findings are filed through raise-issues' `findings_to_plan.py` converter.

The scripts are the policy layer. Anything that sorts, filters, or sizes hew's output — or
classifies a PR's mergeability — in the agent's head instead of running `resolve_ready.py` or
`pr_state.py` makes the pump un-reasonable-about from its logs: two runs on the same epic
must produce the same plan, and the scripts are what make that true. Changes to spawn or
merge policy belong in the scripts, where they are testable, not in the skill prose.

The pump keeps the human gates by design: it never closes an issue or epic, never `--force`s
a claim, never clicks through a worker's permission dialog, and never reconciles a merge
conflict itself. Without `--resolve-conflicts` a conflict is filed and escalated like any
other gate; with it, the edit is delegated to a reconciler agent whose new head is un-readied
and re-reviewed before any merge, and two failed attempts park the PR for the human anyway.
Autonomous mode moves the *merge* off the human's list — bounded to this epic's PRs, CI green
on a head current with main, a current review, and no finding at or above `--block-on` — not
the judgement: P1 holds, conflicts, and ping-pong escalations all land on the human. Removing
any of those bounds turns an accelerator into an unsupervised committer. The `we-`/`wr-`/`wc-`
name prefixes are the ownership rule that lets several orchestrators share a herdr server
safely — closing or reassigning an agent outside your own prefix breaks that. hew's claim lock
tells users apart, not orchestrators: two orchestrators on one gh login are only kept apart by
sharing a herdr server, where agent names are unique.

The pump never runs git inside a PR branch in the human's main checkout: branch updates are
`gh pr update-branch`, reviewers, reconcilers, and the integration pass get their own
worktree, and the post-merge fast-forward happens only while the main checkout sits on the
default branch.

Worker, reviewer, and reconciler outcomes are read from `--json` files, never inferred from
terminal output: herdr's settled states prove an agent stopped, the file says what happened.
Pointing outcome paths anywhere but `${TMPDIR:-/tmp}/opencode` costs every spawned agent a
permission dialog.
