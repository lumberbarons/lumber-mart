Review the branch `${branch}` and fix what you find, in this worktree. Issue #${n} is the change the
branch carries; read it with `hew show ${n}` when its intent is not clear from the diff. This
repository tracks issues locally: there is no remote and no pull request, so nothing is fetched or
pushed.

This worktree is where the work was done. Confirm that first:
1. `git branch --show-current` must print `${branch}`. If it does not, stop and write status
   "error" with the reason; do not switch, reset, or rebase anything.

Then:
2. Use the review-code skill with flags --non-interactive --json '.work-epic/wr-${n}.json'. Its
   default branch-vs-default scope is exactly this branch's diff.
3. For each finding at P0, P1, or P2, in order, try to fix it:
   - make the smallest change that resolves it, inside the files this branch already changes or
     their direct tests;
   - run every check the project gates on — tests, linters, type checks, builds — as step 6 of
     ${work_issue_dir}/SKILL.md describes; its REFERENCE.md table is only the floor;
   - if the gate passes, commit it as `fix: <finding title>` and set "fixed": true and
     "fixedIn": "<short sha>" on that finding in the file;
   - otherwise undo the change entirely (`git restore --staged --worktree .`) and set
     "fixed": false and "unfixedReason": "<why>" on that finding.
   Leave a finding unfixed, with the reason, when the fix needs a design decision, reaches outside
   this branch's files, would be large, or conflicts with another finding. Never weaken or delete a
   test to make a gate pass. Leave P3 findings alone.
4. Leave what you committed on the branch. Never push, never rebase, never force anything.
5. Add to the file's top level "head": "<`git rev-parse HEAD`>" and "gate": "<command and result>".
   Create `.work-epic/` if needed; do not commit the file.
6. Send the worker_done message the orchestration preamble specifies, with --outcome succeeded
   only if the file's status is reviewed, otherwise failed, and --report-path
   '.work-epic/wr-${n}.json'. Ask nothing and do not interact with the user.
