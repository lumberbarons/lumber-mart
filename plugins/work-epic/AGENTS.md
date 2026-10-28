Skills for orchestrating a [hew](https://github.com/lumberbarons/hew) epic across
[Orca](https://github.com/stablyai/orca)-managed worktrees and supervised agents.

| Directory | What | When to read |
|-----------|------|--------------|
| `skills/work-epic/` | Pumps an epic: implementers, reviewers, reconcilers, findings filing, merge pass | Changing how the pump resolves, spawns, reaps, files, merges, or reports |
| `skills/work-epic/REFERENCE.md` | The scripts' schemas, the Run/Task/worktree lifecycle, agent roles and adapters, prompt templates, review-round and reconciliation comments, filing flow, budgets, report format | Changing what the pump tells its agents or how it reads them back |
| `skills/work-epic/scripts/resolve_ready.py` | The deterministic spawn planner | Changing which children get worked or in what order |
| `skills/work-epic/scripts/pr_state.py` | The deterministic merge-pass planner | Changing which PRs merge, reconcile, update, hold, or escalate |
| `skills/work-epic/scripts/repo_state.py` | Read-only git/gh probes both planners share | Changing how PRs, branches, or the default branch are read |
| `skills/work-epic/scripts/test_*.py` | stdlib `unittest` over both decision tables | Changing any decision, skip reason, or parser — add the pinning case |
| `skills/work-epic/evals/` | Why there is no behavioral eval set, and the measured cost of skill-creator's trigger loop | Writing or running evals |
| `README.md` | Plugin overview, modes, and the multi-agent role matrix | Understanding what work-epic does |

Requires Orca 1.4+ with the `orca-cli` and `orchestration` skills, the target repo registered in
Orca, `hew` on PATH (authenticated), and the skills this pump drives: `work-issue` (hew plugin)
for implementers and `review-code` (critique plugin) for reviewers. Findings are filed through
raise-issues' `findings_to_plan.py` converter. Install `work-issue` for every implementer and
`review-code` for every reviewer; the prompt adapters cover `opencode` and `claude` by skill name
and `codex` by file path. Reconcilers read the work-issue quality-gate table from the skill
directory.

Never run skill-creator's description optimizer against this skill. Its loop boots one full
`claude -p` agent per prompt-run — 60 per iteration, five iterations by default — and two runs
on 2026-10-26 spent a five-hour allowance in minutes while scoring a harness that cannot trigger
the skill. `skills/work-epic/evals/README.md` has the numbers, why the score is meaningless, and
the one-session bounded check.

The scripts are the policy layer. Anything that sorts, filters, or sizes hew's output — or
classifies a PR's mergeability — in the agent's head instead of running `resolve_ready.py` or
`pr_state.py` makes the pump un-reasonable-about from its logs: two runs on the same epic
must produce the same plan, and the scripts are what make that true. Changes to spawn or
merge policy belong in the scripts, where they are testable, not in the skill prose.

Orca is the execution layer, not a second planner. A **Run** scopes the pump; each child (or a
review's finding batch) is a **Task** and a durable **worktree**; each attempt is a
**Dispatch**. Orca Tasks record execution and do not replace hew's dependency graph. The child
worktree is the unit: issue link, PR link, workspace status, comment marker, checkout, and the
place review and reconciliation happen. A
reviewer gets its own transient worktree on a named `review/<pr>-r<round>` branch so it never
fights the child over its issue branch; a reconciler reuses the child's checkout when this Run
still holds it, and otherwise gets a transient checkout.

The pump is explicitly multi-agent. Implementers, reviewers, and reconcilers are chosen from
`--implementers`, `--reviewers`, and `--reconciler`; the default reviewer is a different agent
from the implementer whenever the implementer pool has one, and a re-review moves to the next
candidate when more than one remains.
Assignment is deterministic by issue/PR/round number, not spawn order. The role's agent is
recorded in the Task title, the worktree marker, the state file, and the report — never inferred
from a terminal title. Orca's CLI
does not expose an installed/available agent list (`agent-context` and `account list` are not
one), so the pool is the operator's declaration; a failed `worker-start` names the agent that
could not launch, and the pump reports it rather than silently substituting another agent.

The pump keeps the human gates by design: it never closes an issue or epic, never `--force`s
a claim, never answers a worker's permission dialog or question, and never reconciles a merge
conflict itself. Without `--resolve-conflicts` a conflict is filed and escalated like any
other gate; with it, the edit is delegated to a reconciler agent whose new head is un-readied
and re-reviewed before any merge, and two failed attempts park the PR for the human anyway.
Autonomous mode moves the *merge* off the human's list — bounded to this epic's PRs, CI green
on a head current with main, a current review, and no finding at or above `--block-on` — not
the judgement: P1 holds, conflicts, and ping-pong escalations all land on the human. Removing
any of those bounds turns an accelerator into an unsupervised committer.

Ownership is Run-scoped. Never act on a Task, Dispatch, terminal, or worktree whose
`work-epic #<epic> · <run>` marker names another Run; the `we-`/`wr-`/`wc-` task-title prefixes
are reporting conventions, not the lock. The issue link is the durable child selector
(`worktree show --worktree issue:<n>`), and the comment is the only custom metadata Orca gives
the pump — keep both. Run scoping is not an epic lock: hew's claim lock tells users apart, not
orchestrators, so two pumps on one `gh` login over the same epic are still forbidden.

The pump never runs git inside a PR branch in the human's main checkout: branch updates are
`gh pr update-branch`, reviewers get a named review branch in their own worktree, reconcilers
reuse the child or get a transient checkout, and the post-merge fast-forward happens only while
the main checkout sits on the default branch. Because child worktrees are based on
`origin/<default>` explicitly, a main checkout on a human branch does not block the fan-out; the
pump skips the ff and says so.

Implementer, reviewer, and reconciler outcomes are read from `--json` files written inside their
own worktrees, never inferred from terminal output: the Dispatch's settlement (`worker_done`,
`exited` liveness, or a transcript that ended without one) proves the agent stopped, the file
says what happened. `worker-release` archives the terminal before closing it; never release
before reading the outcome, and never drive a worker with `agent launch`, `worktree create
--agent`, `orchestration dispatch`, or direct terminal commands — those bypass Task/Dispatch
ownership and settlement.
