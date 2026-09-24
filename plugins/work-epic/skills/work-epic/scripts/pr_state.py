#!/usr/bin/env python3
"""Plan the merge pass for a hew epic's open PRs — read-only, decide nothing.

Runs `hew list --epic --json --bodies`, `gh pr list`, and one `gh pr view` and
one compare call per matched PR; never writes. Prints one JSON object to
stdout:

  {
    "epic": <n>, "blockOn": "P1", "defaultBranch": "main",
    "mainCheckout": "/abs/path",
    "queueHead": <pr number or null>,
    "reconcileHead": <pr number or null>,
    "prs": [ { "number", "issue", "issueState", "branch", "head", "draft",
               "mergeState", "mergeable", "checks", "behindBy",
               "reviewRounds", "reviewedHead", "reconcileFailures",
               "worstOpenFinding", "action", "note" } ... ],
    "unmatched": [ {"number", "scrapedIssue", "reason",
                    "action": "outside_epic"} ... ],
    "counts": { "<action>": n, ... }
  }

A PR is matched to an epic child by scraping the conventional issue number
from its head branch (`fix|feat|chore/<n>-<slug>`, work-issue's naming rule).
Findings children filed by the pump carry a `review-of: #<issue>` marker in
their body; the worst-severity open one at or above `--block-on` holds the PR.
Every review round leaves one PR comment carrying the reviewer-agent marker
and a `reviewed-head: <sha>` line; those comments are the round count.

Actions, in decision order (first match wins):
  wait            issue closed, or the PR's comments could not be read
  wait            conflicted under --resolve-conflicts with unreadable
                  comments — the failed-attempt count is unknown, not zero
  reconcile       mergeState DIRTY or mergeable CONFLICTING with
                  --resolve-conflicts, no review-enforced blocker open, and
                  fewer than two failed attempts recorded — a reconciler
                  agent merges the default branch in and reconciles the
                  conflict
  conflict        mergeState DIRTY or mergeable CONFLICTING — escalated to the
                  human, never resolved by hand
  escalate        two review rounds and a blocking finding is still open
  hold            a blocking finding is open — human gate
  update_branch   ready PR behind the default branch (behindBy > 0, or
                  mergeState BEHIND) — merge the default branch in. Drafts
                  are never updated: they are not next to merge, and moving
                  a draft's head spends a review round
  re_review       draft PR whose head moved past the last reviewed head
  wait            no review round yet (reviewer in flight or failed)
  wait            checks failing, pending, or absent (absent is green only
                  under --allow-no-checks)
  mark_ready      draft and otherwise green — GitHub reports a draft's merge
                  state as DRAFT, hiding BEHIND/BLOCKED until it is readied
  wait            behindBy unknown — never merge a PR not known to be current
  merge           checks green, mergeState CLEAN or HAS_HOOKS
  protected       mergeState BLOCKED with green checks — branch protection
                  wants something the pump cannot give (an approval)
  wait            anything else (UNKNOWN while GitHub computes, UNSTABLE)
  outside_epic    unmatched PR — listed for visibility, never touched

Under --no-review the review rows (escalate, hold, re_review, no-round wait)
are skipped and CI is the only gate.

Then the merge queue: at most one PR moves toward main per pass. Every merge
puts every other open PR behind again, so updating them side by side spends a
CI run each on a result the next merge throws away, and merging two from one
plan lands the second on CI that never saw the first. The queue head is, in
order: the lowest-numbered `merge`; else the lowest-numbered ready PR that is
current and waiting on its checks (its CI is the one that counts); else the
`update_branch` PR whose checks last passed, lowest number first. Every other
`merge` and `update_branch` becomes

  queued          waiting its turn behind `queueHead` — no action, and no CI
                  budget: it moves when the head merges or parks

Reconciliations are scheduled the same way: at most one `reconcile` survives,
only while `queueHead` is null (a merge landing mid-reconciliation would
re-conflict it), the lowest-numbered candidate; every other candidate becomes
`queued` too.

GitHub cannot say a reconciler is running, so the pump passes one
`--reconciling <pr>` per live `wc-<pr>` agent. While any is live the plan
freezes around it: that PR is `wait`, `reconcileHead` is the lowest live one,
`queueHead` is null, and every other `merge`, `update_branch`, and `reconcile`
is `queued` behind it — main does not move and no second reconciler starts.

Usage: pr_state.py <epic-number> [--repo owner/name] [--block-on P1|P2|none]
                   [--no-review] [--allow-no-checks] [--resolve-conflicts]
                   [--reconciling <pr>]...
Exit: 0 ok (prs may be empty) · 1 runtime error · 2 usage error / not an epic
"""

import json
import re
import sys

from repo_state import (
    CommandError,
    behind_by,
    branch_issue,
    default_branch,
    main_checkout,
    open_prs,
    run,
)

REVIEWED_HEAD_RE = re.compile(r"reviewed-head:\s*([0-9a-f]{7,40})")
REVIEW_MARKER = "review-code findings (work-epic reviewer agent)"
RECONCILE_FAIL_MARKER = "work-epic conflict reconciliation failed (reconciler agent)"
MAX_RECONCILE_ATTEMPTS = 2
FINDING_MARKER_RE = re.compile(r"review-of: #(\d+)\b")
PRIORITY_RE = re.compile(r"^P(\d+)$")

BLOCK_ON = "P1"  # the default; overridable per run
BLOCK_ON_NUM = {"P1": 1, "P2": 2, "none": -1}  # none: no severity blocks
# mergeStateStatus values a ready (non-draft) PR merges from
MERGEABLE_STATES = {"CLEAN", "HAS_HOOKS"}
PR_FIELDS = (
    "number,headRefName,headRefOid,baseRefName,isDraft,mergeStateStatus,"
    "mergeable,statusCheckRollup"
)

CHECK_OK_CONCLUSIONS = {"SUCCESS", "NEUTRAL", "SKIPPED"}
CHECK_BAD_CONCLUSIONS = {
    "FAILURE",
    "TIMED_OUT",
    "CANCELLED",
    "ACTION_REQUIRED",
    "STARTUP_FAILURE",
}
CONTEXT_BAD_STATES = {"FAILURE", "ERROR"}


def fail(msg, code=1):
    print(f"pr_state: {msg}", file=sys.stderr)
    sys.exit(code)


def check_rollup_state(rollup):
    """Collapse gh's statusCheckRollup into pass | fail | pending | none."""
    if not rollup:
        return "none"
    states = []
    for entry in rollup:
        if "state" in entry:  # legacy StatusContext
            state = entry.get("state", "")
            states.append("fail" if state in CONTEXT_BAD_STATES else
                          "pass" if state == "SUCCESS" else "pending")
            continue
        status = entry.get("status", "")
        conclusion = entry.get("conclusion", "")
        if conclusion in CHECK_BAD_CONCLUSIONS or status == "STARTUP_FAILURE":
            states.append("fail")
        elif status == "COMPLETED" and conclusion in CHECK_OK_CONCLUSIONS:
            states.append("pass")
        else:
            states.append("pending")
    if "fail" in states:
        return "fail"
    if all(s == "pass" for s in states):
        return "pass"
    return "pending"


def severity(item):
    m = PRIORITY_RE.match(item.get("priority") or "")
    return int(m.group(1)) if m else 99


def findings_by_issue(children):
    """Open findings children keyed by the issue they were reviewed against.

    The converter stamps each findings child's `### Where` with
    `review-of: #<n>` naming the reviewed issue; that marker is the
    deterministic link — hew's JSON carries no discovered-from field.
    """
    by_issue = {}
    for c in children:
        if c.get("state") != "open":
            continue
        for m in FINDING_MARKER_RE.finditer(c.get("body") or ""):
            by_issue.setdefault(int(m.group(1)), []).append(c)
    return by_issue


def plan_pr(pr, issue, issue_state, findings, block_on_num, review,
            allow_no_checks=False, reconcile=False):
    """Decision table for one matched PR. First match wins.

    `pr["comments"]` is None when the comments could not be read — the review
    state is then unknown, which is never a reason to act. `pr["behindBy"]`
    is the compare API's count of default-branch commits the head lacks, None
    when unknown. `reconcile` enables the reconciler-agent action; without it
    a conflict is always reported for the human.
    """
    comments = pr.get("comments")
    rounds = [
        c for c in comments or [] if REVIEW_MARKER in (c.get("body") or "")
    ]
    review_rounds = len(rounds)
    reviewed_head = None
    if rounds:
        m = REVIEWED_HEAD_RE.search(rounds[-1].get("body") or "")
        reviewed_head = m.group(1) if m else None
    reconcile_failures = sum(
        1 for c in comments or []
        if RECONCILE_FAIL_MARKER in (c.get("body") or "")
    )

    worst = None
    if findings:
        worst = min(findings, key=severity).get("priority")
    blocking = worst is not None and severity({"priority": worst}) <= block_on_num

    merge_state = pr.get("mergeStateStatus") or "UNKNOWN"
    mergeable = pr.get("mergeable") or "UNKNOWN"
    checks = check_rollup_state(pr.get("statusCheckRollup") or [])
    draft = bool(pr.get("isDraft"))
    head = (pr.get("headRefOid") or "")[:40]
    # a relayed sha may be abbreviated; a prefix of the head is the same commit
    stale = draft and reviewed_head is not None and not head.startswith(reviewed_head)
    green = checks == "pass" or (checks == "none" and allow_no_checks)
    behind_count = pr.get("behindBy")
    behind = merge_state == "BEHIND" or (behind_count or 0) > 0

    base = {
        "number": pr["number"],
        "issue": issue,
        "issueState": issue_state,
        "branch": pr.get("headRefName"),
        "head": head,
        "draft": draft,
        "mergeState": merge_state,
        "mergeable": mergeable,
        "checks": checks,
        "behindBy": behind_count,
        "reviewRounds": review_rounds,
        "reviewedHead": reviewed_head,
        "reconcileFailures": reconcile_failures,
        "worstOpenFinding": worst,
    }

    def act(action, note=None):
        base["action"] = action
        if note:
            base["note"] = note
        return base

    if issue_state != "open":
        return act("wait", "issue closed while PR open")
    if review and comments is None:
        return act("wait", "PR comments unreadable — review state unknown")
    if merge_state == "DIRTY" or mergeable == "CONFLICTING":
        if reconcile and not (review and blocking):
            if comments is None:
                return act("wait", "PR comments unreadable — reconcile attempts unknown")
            if reconcile_failures < MAX_RECONCILE_ATTEMPTS:
                return act("reconcile", "reconciler agent merges the base branch in")
        return act("conflict")
    if review and review_rounds >= 2 and blocking:
        return act("escalate", "two review rounds, blocking finding still open")
    if review and blocking:
        return act("hold", f"open {worst} finding at or above --block-on")
    if behind and not draft:
        return act("update_branch", f"{behind_count} commits behind"
                   if behind_count else "mergeState BEHIND")
    if review and stale:
        return act("re_review", "head moved past the last reviewed head")
    if review and review_rounds == 0:
        return act("wait", "no review round yet — reviewer in flight or failed")
    if not green:
        # a current, ready PR whose CI is still running is the one the queue
        # waits on; a failed one is stuck and must not hold the queue
        if not draft and checks != "fail" and behind_count == 0:
            base["inFlight"] = True
        return act("wait", {"fail": "checks failing",
                            "pending": "checks pending",
                            "none": "no checks reported yet"}.get(checks))
    if draft:
        return act("mark_ready")
    if behind_count is None:
        return act("wait", "behind count unknown — not known to be current")
    if merge_state in MERGEABLE_STATES:
        return act("merge")
    if merge_state == "BLOCKED":
        return act("protected", "branch protection blocks the merge despite green checks")
    return act("wait", f"mergeState {merge_state}")


def queue_merges(prs):
    """Let at most one PR move toward main; queue the rest behind it.

    Mutates the planned PRs in place and returns the head's number, or None
    when nothing is moving. Order rules are in the module docstring.
    """
    merges = [p for p in prs if p["action"] == "merge"]
    in_flight = [p for p in prs if p.get("inFlight")]
    updates = [p for p in prs if p["action"] == "update_branch"]
    if merges:
        head = min(merges, key=lambda p: p["number"])
    elif in_flight:
        head = min(in_flight, key=lambda p: p["number"])
    elif updates:
        head = min(updates, key=lambda p: (p["checks"] != "pass", p["number"]))
    else:
        return None
    for p in merges + updates:
        if p is not head:
            p["action"] = "queued"
            p["note"] = f"queued behind PR #{head['number']}"
    return head["number"]


def queue_reconciles(prs, merge_head):
    """Let at most one reconciler run, and only while nothing moves toward main.

    A merge landing mid-reconciliation re-conflicts it, and reconciliations
    done side by side are invalidated by the first merge; so the
    lowest-numbered `reconcile` survives only when `merge_head` is None, and
    every other candidate waits its turn. Mutates in place and returns the
    reconciliation head's number, or None when no reconciler should run.
    """
    candidates = [p for p in prs if p["action"] == "reconcile"]
    if not candidates:
        return None
    if merge_head is not None:
        for p in candidates:
            p["action"] = "queued"
            p["note"] = f"queued behind PR #{merge_head}"
        return None
    head = min(candidates, key=lambda p: p["number"])
    for p in candidates:
        if p is not head:
            p["action"] = "queued"
            p["note"] = f"queued behind reconciliation of PR #{head['number']}"
    return head["number"]


def schedule(prs, reconciling):
    """Order the pass: the merge queue, then reconciliations — or neither.

    `reconciling` is the PR numbers of live `wc-<pr>` agents. While any is
    live, its PR waits on the reconciler whatever GitHub reads, and every
    other `merge`, `update_branch`, and `reconcile` is queued behind the
    lowest live one: a merge would re-conflict the reconciliation, and a
    second reconciler is the one the planner exists to prevent. Mutates in
    place and returns `(queueHead, reconcileHead)`.
    """
    if not reconciling:
        merge_head = queue_merges(prs)
        return merge_head, queue_reconciles(prs, merge_head)
    head = min(reconciling)
    for p in prs:
        if p["number"] in reconciling:
            p["action"] = "wait"
            p["note"] = f"reconciler wc-{p['number']} in flight"
        elif p["action"] in ("merge", "update_branch", "reconcile"):
            p["action"] = "queued"
            p["note"] = f"queued behind reconciliation of PR #{head}"
    return None, head


def parse_args(args):
    """Flags in any position — the skill passes them after the epic number."""
    args = list(args)
    repo, block_on, review, allow_no_checks = None, BLOCK_ON, True, False
    reconcile, reconciling = False, set()
    positional = []
    while args:
        a = args.pop(0)
        if a == "--repo":
            if not args:
                fail("--repo needs owner/name", 2)
            repo = args.pop(0)
        elif a == "--block-on":
            if not args or args[0] not in BLOCK_ON_NUM:
                fail("--block-on needs P1, P2, or none", 2)
            block_on = args.pop(0)
        elif a == "--no-review":
            review = False
        elif a == "--resolve-conflicts":
            reconcile = True
        elif a == "--reconciling":
            if not args or not args[0].isdigit():
                fail("--reconciling needs a PR number", 2)
            reconciling.add(int(args.pop(0)))
        elif a == "--allow-no-checks":
            allow_no_checks = True
        else:
            positional.append(a)
    if len(positional) != 1 or not positional[0].isdigit():
        fail(
            "usage: pr_state.py <epic-number> [--repo owner/name] "
            "[--block-on P1|P2|none] [--no-review] [--allow-no-checks] "
            "[--resolve-conflicts] [--reconciling <pr>]...",
            2,
        )
    return (positional[0], repo, block_on, review, allow_no_checks, reconcile,
            frozenset(reconciling))


def plan(epic_n, repo, block_on, review, allow_no_checks, reconcile,
         reconciling=frozenset()):
    suffix = ["--repo", repo] if repo else []
    gh_suffix = ["-R", repo] if repo else []

    show = json.loads(run(["hew", "show", epic_n, "--json", *suffix]))
    if not show.get("epic"):
        fail(f"#{epic_n} is not an epic — there is no merge pass to plan", 2)

    children = [
        json.loads(line)
        for line in run(
            ["hew", "list", "--epic", epic_n, "--json", "--bodies", *suffix]
        ).splitlines()
        if line.strip()
    ]
    child_by_number = {c["number"]: c for c in children}
    findings = findings_by_issue(children)
    default = default_branch(repo)

    prs_out, unmatched = [], []
    for raw in open_prs(PR_FIELDS, repo):
        issue = branch_issue(raw.get("headRefName"))
        reason = None
        if issue is None:
            reason = "no issue number in the head branch"
        elif issue not in child_by_number:
            reason = f"#{issue} is not a child of this epic"
        elif default and raw.get("baseRefName") != default:
            reason = f"targets {raw.get('baseRefName')}, not {default}"
        if reason:
            unmatched.append({"number": raw["number"], "scrapedIssue": issue,
                              "reason": reason, "action": "outside_epic"})
            continue
        try:
            view = json.loads(
                run(["gh", "pr", "view", str(raw["number"]), "--json", "comments",
                     *gh_suffix])
            )
            raw["comments"] = view.get("comments") or []
        except (CommandError, ValueError):
            raw["comments"] = None
        raw["behindBy"] = behind_by(default, raw.get("headRefOid"), repo)
        prs_out.append(
            plan_pr(
                raw,
                issue,
                child_by_number[issue].get("state", "open"),
                findings.get(issue) or [],
                BLOCK_ON_NUM[block_on],
                review,
                allow_no_checks,
                reconcile,
            )
        )
    queue_head, reconcile_head = schedule(prs_out, reconciling)
    counts = {}
    for p in prs_out:
        counts[p["action"]] = counts.get(p["action"], 0) + 1
    counts["outside_epic"] = len(unmatched)
    prs_out.sort(key=lambda p: (p["issue"], p["number"]))

    return {
        "epic": int(epic_n),
        "blockOn": block_on,
        "defaultBranch": default,
        "mainCheckout": main_checkout(),
        "queueHead": queue_head,
        "reconcileHead": reconcile_head,
        "prs": prs_out,
        "unmatched": sorted(unmatched, key=lambda u: u["number"]),
        "counts": counts,
    }


def main():
    epic_n, repo, block_on, review, allow_no_checks, reconcile, reconciling = (
        parse_args(sys.argv[1:])
    )
    try:
        out = plan(epic_n, repo, block_on, review, allow_no_checks, reconcile,
                   reconciling)
    except CommandError as e:
        fail(str(e))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
