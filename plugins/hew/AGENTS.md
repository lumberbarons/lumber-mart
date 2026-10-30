Skills for GitHub and local issue trackers through the [hew](https://github.com/lumberbarons/hew) CLI.

| Directory | What | When to read |
|-----------|------|--------------|
| `skills/raise-issues/` | Files review findings as deduplicated hew issues | Changing how findings become issues, or the review-key scheme |
| `skills/work-issue/` | Takes a tracked issue from claimed to draft PR, test-first | Changing how issues get implemented, verified, or shipped |
| `skills/finish-issue/` | Reviews and lands an existing delivery; local squash/close recovery helper and real-git tests | Changing how deliveries are merged, closed, or recovered |
| `skills/raise-issues/evals/` | The dedup-judgement eval: a tracker snapshot and two plans | Changing Step 3's match rules or `dedup_candidates.py` |
| `README.md` | Plugin overview, the review-key contract, and the unattended pipeline | Understanding what hew skills do |

Requires the `hew` binary on PATH, authenticated via `gh auth login`.

The review-key scheme in `skills/raise-issues/REFERENCE.md` is the load-bearing part of that
skill: it is what lets a review re-run without re-filing. Changing the key format orphans every
issue already filed under the old one, so treat it as a migration, not an edit.

The key is a lookup index, not an identity: findings in one package legitimately share it, so
a hit counts as already-filed only when the body describes the same finding and its `review-of:`
names the same review target. That is how a finding about a fix stays distinct from the finding
the fix was for, without growing the key. Keep that distinction out of the key format.

`work-issue` rests on two properties of hew that are easy to undo by accident. Work ends at
`hew pr`, never at `hew close` — close means wontfix or duplicate, so closing a delivered issue
skips review and records the opposite of what happened. A local tracker has no `hew pr`, and its
primer ends work with `hew close --completed`; the skill still stops earlier, at a committed
branch, and leaves the merge and that close to whoever reviews it — a person, finish-issue,
or work-epic. The one carve-out is a review finding the
work-epic reviewer fixed in the session that found it: it is filed for the paper trail and closed
`--completed` with the fixing commit, because no PR of its own will ever carry a `Fixes` line for
it. And `hew start`'s exit 3 on a claimed
issue is the concurrency lock that makes unattended runs safe; anything that routes around it
with `--force` removes the only thing keeping two agents off the same issue.

`--batch`'s integration branch is a check, not a deliverable — never pushed, never a PR. Making
one from it would rebuild the single unreviewable PR that per-issue branching exists to prevent,
and the batch's own PRs already carry the `Fixes #n` lines that close the work. Its failure state,
`integration_failed`, is likewise not a retry: the PRs are sound and re-running reproduces it.

`finish-issue` starts at that delivery boundary. It confirms review and project checks, lands
the verified head against the current default branch, and reports finished only after merge and
issue closure are observed. GitHub closes through the PR; a local tracker closes with
`hew close --completed` after the squash commit. The local helper's receipt lives in git's common
directory so a retry can close an already-landed issue without squashing twice. Never delete a
receipt to bypass a failed landing. Tests use real scratch git repositories and substitute only
hew's transport; run `python3 -m unittest discover -s plugins/hew/skills/finish-issue/scripts`.

The skill owns review, project-check discovery, and scoped repairs. Deterministic merge/closure
and recovery are candidates for a future native `hew finish`; the current hew has no such
command. Do not invent it in instructions. Work-epic already has a tested finish loop and should
eventually consume the same CLI operation, rather than launching this skill as another agent
for every delivery. Changing that orchestration is a separate migration.
