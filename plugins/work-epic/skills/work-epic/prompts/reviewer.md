Review PR #${pr} and fix what you find, in this worktree. Issue #${n} is the change the PR carries;
read it with `hew show ${n}` when its intent is not clear from the diff.

This worktree is already on the PR's issue branch. Bring it to the PR head first:
1. `git fetch origin`
2. `git merge --ff-only origin/${branch}`
If the fast-forward fails, stop and write status "error" with the reason; do not reset, rebase,
or force anything.

Then:
3. Use the review-code skill with flags --non-interactive --json '.work-epic/wr-${pr}.json'. Its
   default branch-vs-default scope is exactly this PR's diff.
4. For each finding at P0, P1, or P2, in order, try to fix it:
   - make the smallest change that resolves it, inside the files this PR already changes or
     their direct tests;
   - run every check the project gates on — tests, linters, type checks, builds — as step 6 of
     ${work_issue_dir}/SKILL.md describes; its REFERENCE.md table is only the floor;
   - if the gate passes, commit it as `fix: <finding title>` and set "fixed": true and
     "fixedIn": "<short sha>" on that finding in the file;
   - otherwise undo the change entirely (`git restore --staged --worktree .`) and set
     "fixed": false and "unfixedReason": "<why>" on that finding.
   Leave a finding unfixed, with the reason, when the fix needs a design decision, reaches outside
   this PR's files, would be large, or conflicts with another finding. Never weaken or delete a
   test to make a gate pass. Leave P3 findings alone.
5. If you committed anything: `git push origin HEAD:${branch}`. Never --force, never rebase,
   never push to a ref other than this PR's ${branch}.
6. Add to the file's top level "head": "<sha after the push>" and "gate": "<command and result>".
   Create `.work-epic/` if needed; do not commit the file.
7. Send the worker_done message the orchestration preamble specifies, with --outcome succeeded
   only if the file's status is reviewed, otherwise failed, and --report-path
   '.work-epic/wr-${pr}.json'. Ask nothing and do not interact with the user.
