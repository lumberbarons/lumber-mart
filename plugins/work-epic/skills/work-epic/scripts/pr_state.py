#!/usr/bin/env python3
"""Plan the merge pass for a hew epic's open PRs — read-only, decide nothing.

Runs `hew list --epic --json --bodies`, `gh pr list`, and one `gh pr view` per
matched PR; never writes. Prints one JSON object to stdout:

  {
    "epic": <n>, "blockOn": "P1", "defaultBranch": "main",
    "mainCheckout": "/abs/path",
    "prs": [ { "number", "issue", "issueState", "branch", "head", "draft",
               "mergeState", "mergeable", "checks", "reviewRounds",
               "reviewedHead", "worstOpenFinding", "action", "note" } ... ],
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
  conflict        mergeState DIRTY or mergeable CONFLICTING — never auto-resolve
  escalate        two review rounds and a blocking finding is still open
  hold            a blocking finding is open — human gate
  update_branch   mergeState BEHIND — merge the default branch in
  re_review       draft PR whose head moved past the last reviewed head
  wait            no review round yet (reviewer in flight or failed)
  wait            checks failing, pending, or absent (absent is green only
                  under --allow-no-checks)
  mark_ready      draft and otherwise green — GitHub reports a draft's merge
                  state as DRAFT, hiding BEHIND/BLOCKED until it is readied
  merge           checks green, mergeState CLEAN or HAS_HOOKS
  protected       mergeState BLOCKED with green checks — branch protection
                  wants something the pump cannot give (an approval)
  wait            anything else (UNKNOWN while GitHub computes, UNSTABLE)
  outside_epic    unmatched PR — listed for visibility, never touched

Under --no-review the review rows (escalate, hold, re_review, no-round wait)
are skipped and CI is the only gate.

Usage: pr_state.py <epic-number> [--repo owner/name] [--block-on P1|P2|none]
                   [--no-review] [--allow-no-checks]
Exit: 0 ok (prs may be empty) · 1 runtime error · 2 usage error / not an epic
"""

import json
import re
import sys

from repo_state import (
    CommandError,
    branch_issue,
    default_branch,
    main_checkout,
    open_prs,
    run,
)

REVIEWED_HEAD_RE = re.compile(r"reviewed-head:\s*([0-9a-f]{7,40})")
REVIEW_MARKER = "review-code findings (work-epic reviewer agent)"
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
            allow_no_checks=False):
    """Decision table for one matched PR. First match wins.

    `pr["comments"]` is None when the comments could not be read — the review
    state is then unknown, which is never a reason to act.
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
        "reviewRounds": review_rounds,
        "reviewedHead": reviewed_head,
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
        return act("conflict")
    if review and review_rounds >= 2 and blocking:
        return act("escalate", "two review rounds, blocking finding still open")
    if review and blocking:
        return act("hold", f"open {worst} finding at or above --block-on")
    if merge_state == "BEHIND":
        return act("update_branch")
    if review and stale:
        return act("re_review", "head moved past the last reviewed head")
    if review and review_rounds == 0:
        return act("wait", "no review round yet — reviewer in flight or failed")
    if not green:
        return act("wait", {"fail": "checks failing",
                            "pending": "checks pending",
                            "none": "no checks reported yet"}.get(checks))
    if draft:
        return act("mark_ready")
    if merge_state in MERGEABLE_STATES:
        return act("merge")
    if merge_state == "BLOCKED":
        return act("protected", "branch protection blocks the merge despite green checks")
    return act("wait", f"mergeState {merge_state}")


def parse_args(args):
    """Flags in any position — the skill passes them after the epic number."""
    args = list(args)
    repo, block_on, review, allow_no_checks = None, BLOCK_ON, True, False
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
        elif a == "--allow-no-checks":
            allow_no_checks = True
        else:
            positional.append(a)
    if len(positional) != 1 or not positional[0].isdigit():
        fail(
            "usage: pr_state.py <epic-number> [--repo owner/name] "
            "[--block-on P1|P2|none] [--no-review] [--allow-no-checks]",
            2,
        )
    return positional[0], repo, block_on, review, allow_no_checks


def plan(epic_n, repo, block_on, review, allow_no_checks):
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
        prs_out.append(
            plan_pr(
                raw,
                issue,
                child_by_number[issue].get("state", "open"),
                findings.get(issue) or [],
                BLOCK_ON_NUM[block_on],
                review,
                allow_no_checks,
            )
        )
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
        "prs": prs_out,
        "unmatched": sorted(unmatched, key=lambda u: u["number"]),
        "counts": counts,
    }


def main():
    epic_n, repo, block_on, review, allow_no_checks = parse_args(sys.argv[1:])
    try:
        out = plan(epic_n, repo, block_on, review, allow_no_checks)
    except CommandError as e:
        fail(str(e))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
