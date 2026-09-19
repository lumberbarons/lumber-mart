#!/usr/bin/env python3
"""Plan the merge pass for a hew epic's open PRs — read-only, decide nothing.

Runs `hew list --epic --json --bodies`, `gh pr list`, and one `gh pr view` per
matched PR; never writes. Prints one JSON object to stdout:

  {
    "epic": <n>, "blockOn": "P1", "defaultBranch": "main",
    "mainCheckout": "/abs/path",
    "prs": [ { "number", "issue", "issueState", "branch", "head", "draft",
               "mergeState", "checks", "reviewRounds", "reviewedHead",
               "worstOpenFinding", "action", "note" } ... ],
    "unmatched": [ {"number", "scrapedIssue", "action": "outside_epic"} ... ],
    "counts": { "ready_and_merge": n, "re_review": n, "hold_p1": n,
                "escalate": n, "update_branch": n, "conflict": n,
                "wait": n, "outside_epic": n }
  }

A PR is matched to an epic child by scraping the conventional issue number
from its head branch (`fix|feat|chore/<n>-<slug>`, work-issue's naming rule).
Findings children filed by the pump carry a `review-of: #<issue>` marker in
their body; the worst-severity open one at or above `--block-on` holds the PR.

Actions, in decision order (first match wins):
  wait            issue closed, or the PR is not mergeable yet
  conflict        mergeState DIRTY — a real conflict; file it, never auto-resolve
  update_branch   mergeState BEHIND — merge origin/<default> in, push
  re_review       draft PR whose head moved past the last reviewed head
  escalate        two review rounds and a blocking finding is still open
  hold_p1         a blocking finding is open — human gate
  ready_and_merge checks green, mergeable, review current — flip draft and merge
  outside_epic    unmatched PR — listed for visibility, never touched

Usage: pr_state.py <epic-number> [--repo owner/name] [--block-on P1|P2|none]
                   [--no-review]
Exit: 0 ok (prs may be empty) · 1 runtime error · 2 usage error / not an epic
"""

import json
import re
import subprocess
import sys

BRANCH_ISSUE_RE = re.compile(r"^(?:fix|feat|chore)/(\d+)(?:-|$)")
REVIEWED_HEAD_RE = re.compile(r"reviewed-head:\s*([0-9a-f]{7,40})")
REVIEW_MARKER = "review-code findings (work-epic reviewer agent)"
FINDING_MARKER_RE = re.compile(r"review-of: #(\d+)\b")
PRIORITY_RE = re.compile(r"^P(\d+)$")

BLOCK_ON = "P1"  # the default; overridable per run
# mergeStateStatus values the pump treats as mergeable
MERGEABLE_STATES = {"CLEAN", "HAS_HOOKS", "DRAFT"}

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


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        fail(p.stderr.strip() or f"{' '.join(cmd)} exited {p.returncode}")
    return p.stdout


def try_run(cmd):
    """Run a command, returning (stdout, stderr, returncode) — for probes."""
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.stdout, p.stderr, p.returncode


def main_checkout():
    """Absolute path of the repository's primary worktree, or None."""
    p = subprocess.run(
        ["git", "worktree", "list", "--porcelain"], capture_output=True, text=True
    )
    if p.returncode != 0:
        return None
    for line in p.stdout.splitlines():
        if line.startswith("worktree "):
            return line[len("worktree ") :] or None
    return None


def default_branch():
    """Origin's HEAD branch name, or None if undeterminable."""
    p = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "origin/HEAD"],
        capture_output=True,
        text=True,
    )
    if p.returncode != 0:
        return None
    name = p.stdout.strip()
    if not name.startswith("origin/"):
        return None
    return name[len("origin/") :]


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


def plan_pr(pr, issue, issue_state, findings, block_on_num, review):
    """Decision table for one matched PR. First match wins."""
    pr_number = pr["number"]
    comments = pr.get("comments") or []
    rounds = [
        c
        for c in comments
        if REVIEW_MARKER in (c.get("body") or "")
    ]
    review_rounds = len(rounds)
    reviewed_head = None
    if rounds:
        m = REVIEWED_HEAD_RE.search(rounds[-1].get("body") or "")
        reviewed_head = m.group(1) if m else None

    worst = None
    if findings:
        worst = min(findings, key=severity).get("priority")
    worst_num = severity({"priority": worst}) if worst else 99
    blocking = worst is not None and worst_num <= block_on_num

    merge_state = pr.get("mergeStateStatus") or "UNKNOWN"
    checks = check_rollup_state(pr.get("statusCheckRollup") or [])
    draft = bool(pr.get("isDraft"))
    head = (pr.get("headRefOid") or "")[:40]

    base = {
        "number": pr_number,
        "issue": issue,
        "issueState": issue_state,
        "branch": pr.get("headRefName"),
        "head": head,
        "draft": draft,
        "mergeState": merge_state,
        "checks": checks,
        "reviewRounds": review_rounds,
        "reviewedHead": reviewed_head,
        "worstOpenFinding": worst,
    }
    if issue_state != "open":
        base["action"], base["note"] = "wait", "issue closed while PR open"
    elif merge_state == "DIRTY":
        base["action"] = "conflict"
    elif merge_state == "BEHIND":
        base["action"] = "update_branch"
    elif review:
        stale = draft and reviewed_head is not None and head != reviewed_head
        if review_rounds >= 2 and blocking:
            base["action"] = "escalate"
        elif stale:
            base["action"] = "re_review"
        elif blocking:
            base["action"] = "hold_p1"
        elif draft and review_rounds == 0:
            base["action"] = "wait"  # reviewer in flight or failed
        elif checks in ("pass", "none") and merge_state in MERGEABLE_STATES:
            base["action"] = "ready_and_merge"
        else:
            base["action"] = "wait"
    else:  # --no-review: CI is the only gate
        if checks in ("pass", "none") and merge_state in MERGEABLE_STATES:
            base["action"] = "ready_and_merge"
        else:
            base["action"] = "wait"
    return base


def main():
    args = sys.argv[1:]
    repo = None
    block_on = BLOCK_ON
    review = True
    while args:
        if args[0] == "--repo":
            if len(args) < 2:
                fail("--repo needs owner/name", 2)
            repo, args = args[1], args[2:]
        elif args[0] == "--block-on":
            if len(args) < 2 or args[1] not in ("P1", "P2", "none"):
                fail("--block-on needs P1, P2, or none", 2)
            block_on, args = args[1], args[2:]
        elif args[0] == "--no-review":
            review, args = False, args[1:]
        else:
            break
    if len(args) != 1 or not args[0].isdigit():
        fail(
            "usage: pr_state.py <epic-number> [--repo owner/name] "
            "[--block-on P1|P2|none] [--no-review]",
            2,
        )
    epic_n = args[0]
    block_on_num = 99 if block_on == "none" else int(block_on[1])
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
    child_numbers = {c["number"] for c in children}
    child_by_number = {c["number"]: c for c in children}
    findings = findings_by_issue(children)

    prs_out, unmatched = [], []
    listed, list_err, list_code = try_run(
        [
            "gh",
            "pr",
            "list",
            "--state",
            "open",
            "--json",
            "number,headRefName,headRefOid,isDraft,mergeStateStatus,statusCheckRollup",
            *gh_suffix,
        ]
    )
    if list_code != 0:
        fail(list_err.strip() or f"gh pr list exited {list_code}")
    for raw in json.loads(listed):
        m = BRANCH_ISSUE_RE.match(raw.get("headRefName") or "")
        issue = int(m.group(1)) if m else None
        if issue is None or issue not in child_numbers:
            unmatched.append(
                {"number": raw["number"], "scrapedIssue": issue, "action": "outside_epic"}
            )
            continue
        comments_raw, _, ccode = try_run(
            ["gh", "pr", "view", str(raw["number"]), "--json", "comments", *gh_suffix]
        )
        comments = json.loads(comments_raw).get("comments", []) if ccode == 0 else []
        prs_out.append(
            plan_pr(
                raw,
                issue,
                child_by_number[issue].get("state", "open"),
                findings.get(issue) or [],
                block_on_num,
                review,
            )
        )
    counts = {}
    for p in prs_out:
        counts[p["action"]] = counts.get(p["action"], 0) + 1
    counts["outside_epic"] = len(unmatched)
    prs_out.sort(key=lambda p: (p["issue"], p["number"]))

    print(
        json.dumps(
            {
                "epic": int(epic_n),
                "blockOn": block_on,
                "defaultBranch": default_branch(),
                "mainCheckout": main_checkout(),
                "prs": prs_out,
                "unmatched": sorted(unmatched, key=lambda u: u["number"]),
                "counts": counts,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
