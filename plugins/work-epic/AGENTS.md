Skills for burning down a [hew](https://github.com/lumberbarons/hew) epic or set of issues across
[Orca](https://github.com/stablyai/orca)-managed worktrees and supervised agents.

| Directory | What | When to read |
|-----------|------|--------------|
| `skills/work-epic/` | The skill: settles the scope, launches the driver, relays the report | Changing what the skill tells an agent to do around the driver |
| `skills/work-epic/scripts/work_epic.py` | The driver's CLI: preflight, skill-directory discovery, `--dry-run`, report, exit codes | Changing arguments, startup checks, or the exit-code contract |
| `skills/work-epic/scripts/pump.py` | The coordinator as code: the loop, reaping, review and repair lifecycles, merge pass, parking, the agents block | Changing how the pump behaves, spawns, reaps, merges, or stops |
| `skills/work-epic/scripts/orca_api.py` | The Orca CLI as typed calls, with the shapes captured from a live Orca | Changing which Orca commands the pump uses or how it reads them |
| `skills/work-epic/scripts/findings.py` | Filing findings, the dedup rule, closing the fixed, the round comment | Changing how a review becomes issues and a PR comment |
| `skills/work-epic/prompts/` | What the implementer, reviewer, and repairer are told | Changing an agent's contract |
| `skills/work-epic/REFERENCE.md` | The scripts' schemas, the Run/Task/worktree lifecycle, the agents and their prompts, review-round and repair comments, filing flow, budgets, report format | Changing what the pump tells its agents or how it reads them back |
| `skills/work-epic/scripts/resolve_ready.py` | The deterministic spawn planner | Changing which issues get worked or in what order |
| `skills/work-epic/scripts/pr_state.py` | The deterministic merge-pass planner | Changing which PRs merge, repair, update, or hold |
| `skills/work-epic/scripts/repo_state.py` | Read-only git/gh/hew probes both planners share, including scope resolution | Changing how PRs, branches, the default branch, or the scope are read |
| `skills/work-epic/scripts/test_*.py` | stdlib `unittest`: both decision tables, the scope parser, the Orca shapes, filing, and the whole pump against a simulated world (`test_pump.py`) | Changing any decision, skip reason, parser, or the loop — add the pinning case |
| `skills/work-epic/evals/` | Why there is no behavioral eval set, and the measured cost of skill-creator's trigger loop | Writing or running evals |
| `README.md` | Plugin overview, the agents, and how a run works | Understanding what work-epic does |

Requires Orca 1.4+ with the `orca-cli` and `orchestration` skills, the target repo registered in
Orca, `hew` on PATH (authenticated), and the skills this pump drives: `work-issue` (hew plugin)
for the implementer and `review-code` (critique plugin) for the reviewer. Findings are filed
through raise-issues' `findings_to_plan.py` converter. The reviewer's fix step and the repairer read
the work-issue quality-gate table from the skill directory.

Never run skill-creator's description optimizer against this skill. Its loop boots one full
`claude -p` agent per prompt-run — 60 per iteration, five iterations by default — and two runs
on 2026-10-26 spent a five-hour allowance in minutes while scoring a harness that cannot trigger
the skill. `skills/work-epic/evals/README.md` has the numbers, why the score is meaningless, and
the one-session bounded check.

This is a lean software factory with one golden path. The skill takes few flags on purpose: the
agents are a single block in `pump.py`, the merge method is squash, conflicts and red CI are
repaired, and a P1 the reviewer could not fix holds its PR. Resist adding a flag for a policy; a
flag is a mode the next editor has to keep working, and the modes that were removed (human-review,
agent pools, block-on, finding-depth, no-review) each carried their own prose, tests, and bugs.

The scripts are the policy layer. Anything that sorts, filters, or sizes hew's output — or
classifies a PR's mergeability — in the agent's head instead of running `resolve_ready.py` or
`pr_state.py` makes the pump un-reasonable-about from its logs: two runs on the same scope must
produce the same plan, and the scripts are what make that true. Changes to spawn or merge policy
belong in the scripts, where they are testable, not in the skill prose.

**The coordinator is code, not prose.** The loop used to be instructions an agent re-interpreted on
every run; it is now `pump.py`, and `test_pump.py` runs the real loop against a simulated Orca, GitHub,
and tracker (`World`), so a change to how it spawns, reaps, reviews, repairs, merges, parks, stops, or
recovers lands with a scenario. Every effect goes through an injected collaborator (`sh`, `orca`, the
two planners, the filer, the clock), which is what makes that possible; keep new effects behind one.
The prompts live in `prompts/`, not in the docs, because they are the contract the pump sends; the
docs describe the contract, the files are it. When Orca's behavior is in question, run the read-only
commands (`worker-list`, `worktree list`, `agent-context`) and pin the captured shape in
`test_orca_api.py`; do not guess a field.

The pump waits with `check --wait` and acknowledges each Delivery on its next wait, but it reads what
settled from `worker-list` and the outcome files, not from the messages: a message is a wake-up and a
place a worker's question can arrive, never the proof of completion. Mutations do not yet use
`--retry-request`; crash safety comes from `state.json`, `recover()`, and re-reading Orca. Adding
request ids is the next hardening step, once their format is confirmed on a live run.

**A PR is reviewed once, and the reviewer fixes in the session that found the problem.** This is
the load-bearing simplification. Findings used to be filed as children and worked by a later
session, which meant a review of the fix, a round counter, a stale-head check, an escalation at two
rounds, a generation bound to stop a finding about a finding, and rotation of reviewers across
rounds. Fixing in the same session removes all of it: the reviewer has the whole diff in context, a
PR is small enough to fix in one go, and the quality gate and CI are the check on what it pushes.
The same reasoning covers a repair and a human's edit — nothing that lands after the review round is
reviewed again. If a fix is too large or needs a decision, it is not a fix: the reviewer leaves it
unfixed, it is filed open, and at P1 it holds the PR for the human. Do not reintroduce a re-review
to catch a bad fix; tighten what the reviewer may fix instead.

Findings are still filed, because the issue is the paper trail: fixed ones are closed with the
fixing commit (`fixed-in:`), unfixed ones stay open. They are filed with no parent, so they are
never part of the scope, and the pump never works one — a finding is either fixed by the reviewer or
handed to the human. That is the whole stopping rule for a review chain.

Orca is the execution layer, not a second planner. A **Run** scopes the pump; each issue is a
**Task** and a durable **worktree**; each attempt is a **Dispatch**. Orca Tasks record execution
and do not replace hew's dependency graph. The issue's worktree is the unit: issue link, PR link,
workspace status, comment marker, checkout, and the place review and repair happen. The reviewer and
the repairer run in the implementer's own checkout once it is released — there is no transient
review worktree or review branch — and they fast-forward it to the PR head first.

The implementer and the reviewer are different agents by construction, and the roles are recorded
in the Task title, the worktree marker, and the report. Orca's CLI does not expose an
installed/available agent list (`agent-context` and `account list` are not one), so the agents are
the operator's declaration; a failed `worker-start` names the agent that could not launch, and the
pump reports it rather than silently substituting another agent.

The pump keeps the human gates by design: it never closes an issue or epic (the one exception is a
finding it filed and the reviewer fixed), never `--force`s a claim, never answers a worker's
permission dialog or question, and never edits code itself. Autonomous merging is bounded to the
scope's PRs, CI green on a head current with main, a review round, and no open finding at P1 or
above: P1 holds, repairs that fail twice, and outages all land on the human. Removing any of those
bounds turns an accelerator into an unsupervised committer.

Ownership is Run-scoped. Never act on a Task, Dispatch, terminal, or worktree whose
`work-epic · <run>` marker names another Run; the `we-`/`wr-`/`wc-` task-title prefixes are
reporting conventions, not the lock. The issue link is the durable selector
(`worktree show --worktree issue:<n>`), and the comment is the only custom metadata Orca gives the
pump — keep both. Run scoping is not a lock on the issues: hew's claim lock tells users apart, not
orchestrators, so two pumps on one `gh` login over the same issues are still forbidden.

The pump never runs git inside a PR branch in the human's main checkout: branch updates are
`gh pr update-branch`, reviewers and repairers work in the issue's own worktree, and the post-merge
fast-forward happens only while the main checkout sits on the default branch. Because worktrees are
based on `origin/<default>` explicitly, a main checkout on a human branch does not block the
fan-out; the pump skips the ff and says so.

Implementer, reviewer, and repairer outcomes are read from `--json` files written inside their own
worktrees, never inferred from terminal output: the Dispatch's settlement (`worker_done`, `exited`
liveness, or a transcript that ended without one) proves the agent stopped, the file says what
happened. `worker-release` archives the terminal before closing it; never release before reading
the outcome, and never drive a worker with `agent launch`, `worktree create --agent`,
`orchestration dispatch`, or direct terminal commands — those bypass Task/Dispatch ownership and
settlement.
