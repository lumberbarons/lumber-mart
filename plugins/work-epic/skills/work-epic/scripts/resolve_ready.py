#!/usr/bin/env python3
"""Resolve a hew epic's ready children into a deterministic fan-out plan.

Read-only: runs `hew show`, `hew list --epic --json --bodies`, `gh pr list`,
the remote branch list, and two local git reads (primary worktree, default
branch); never writes. Prints one JSON object to stdout:

  {
    "epic": <n>, "title": "...",
    "mainCheckout": "/abs/path",         # primary worktree: spawn/branch-update home
    "defaultBranch": "main",             # origin's default branch, when determinable
    "eligible": [ {"number", "title", "priority", "type", "where", "doneWhen",
                   "large", "resume"} ... ],  # priority-sorted, oldest tie-break
    "skipped":  [ {"number", "title", "reason", "detail", "own"?} ... ],
    "counts":   {"eligible": n, "blocked": n, "untriaged": n, "claimed": n,
                 "in_review": n, "stalled": n, "closed": n},
    "spawnBudget": n | null              # null without --max-open-prs
  }

Skip reasons: in_review (an open PR carries the child's number), blocked
(open blockers), untriaged (no priority/type), claimed (in progress — by
someone else, or by you without --resume), stalled (in progress by you, a
branch pushed, no open PR: a worker failed or its PR was closed). Closed
children are counted, not listed.

Children in progress by you are the pump's own claims: in flight, delivered,
or failed. They are never eligible by default — respawning one duplicates or
repeats work. --resume opts the ones with neither a PR nor a pushed branch
back in (`resume: true`), for deliberately picking up a crashed run. Those
bare claims of yours are marked `own: true` in `skipped`.

--max-open-prs N caps the epic's PR backlog: `spawnBudget` is N minus the
epic's open PRs (in_review) minus your own bare claims (workers in flight —
each is a PR on its way), floored at zero. Worker slots bound how many agents
run at once; this bounds how many PRs wait to merge, which is what goes stale
while main moves. Parked PRs (held, conflicted) count: a backlog that cannot
merge is exactly the one not to grow.

Usage: resolve_ready.py <epic-number> [--repo owner/name] [--resume]
                        [--max-open-prs N]
Exit: 0 ok (eligible may be empty) · 1 runtime error · 2 not an epic/usage
"""

import json
import re
import subprocess
import sys

from repo_state import (
    CommandError,
    branch_issue,
    default_branch,
    main_checkout,
    open_prs,
    remote_branches,
    run,
)

PRIORITY_RE = re.compile(r"^P(\d+)$")
WHERE_MAX = 3  # more than three paths -> large (work-issue's sizing rule)
DONE_WHEN_MAX = 5  # more than five done-when items -> large
SKIP_REASONS = ("blocked", "untriaged", "claimed", "in_review", "stalled")


def fail(msg, code=1):
    print(f"resolve_ready: {msg}", file=sys.stderr)
    sys.exit(code)


def current_user():
    """Login name of the gh-authenticated user, or None if undeterminable."""
    p = subprocess.run(
        ["gh", "api", "user", "--jq", ".login"], capture_output=True, text=True
    )
    return p.stdout.strip() or None


def parse_priority(p):
    m = PRIORITY_RE.match(p or "")
    return int(m.group(1)) if m else 99


def section_items(body, heading):
    """Count bullet items under a `### <heading>` section of a hew body."""
    items = 0
    in_section = False
    for line in (body or "").splitlines():
        if line.startswith("### "):
            in_section = line[4:].strip().lower() == heading
            continue
        if in_section and line.lstrip().startswith("- "):
            items += 1
    return items


def delivery_index(prs, branches):
    """Map issue -> open PR number, and issue -> pushed branch name."""
    pr_by_issue, branch_by_issue = {}, {}
    for pr in prs:
        n = branch_issue(pr.get("headRefName"))
        if n is not None:
            pr_by_issue.setdefault(n, pr["number"])
    for name in branches:
        n = branch_issue(name)
        if n is not None:
            branch_by_issue.setdefault(n, name)
    return pr_by_issue, branch_by_issue


def classify(children, me, pr_by_issue=None, branch_by_issue=None, resume=False):
    pr_by_issue = pr_by_issue or {}
    branch_by_issue = branch_by_issue or {}
    eligible, skipped, closed = [], [], 0

    def skip(c, reason, detail, own=False):
        entry = {"number": c["number"], "title": c.get("title", ""),
                 "reason": reason, "detail": detail}
        if own:
            entry["own"] = True
        skipped.append(entry)

    for c in children:
        if c.get("state") != "open":
            closed += 1
            continue
        n = c["number"]
        # an open PR means delivered and in review, whoever holds the claim
        if n in pr_by_issue:
            skip(c, "in_review", f"PR #{pr_by_issue[n]} open")
            continue
        blockers = c.get("openBlockers") or []
        if blockers:
            skip(c, "blocked", "blocked by " + ", ".join(f"#{b}" for b in blockers))
            continue
        if c.get("untriaged"):
            skip(c, "untriaged", "missing priority or type")
            continue
        is_resume = False
        if c.get("inProgress"):
            assignees = c.get("assignees") or []
            if me is None or me not in assignees:
                skip(c, "claimed",
                     "in progress " + (", ".join("@" + a for a in assignees) or "unassigned"))
                continue
            if n in branch_by_issue:
                skip(c, "stalled",
                     f"in progress @{me}, branch {branch_by_issue[n]} pushed, no open PR")
                continue
            if not resume:
                skip(c, "claimed", f"in progress @{me} — pass --resume to pick it up",
                     own=True)
                continue
            is_resume = True
        body = c.get("body") or ""
        where = section_items(body, "where")
        done_when = section_items(body, "done when")
        eligible.append(
            {
                "number": n,
                "title": c.get("title", ""),
                "priority": c.get("priority"),
                "type": c.get("type"),
                "where": where,
                "doneWhen": done_when,
                "large": where > WHERE_MAX or done_when > DONE_WHEN_MAX,
                "resume": is_resume,
            }
        )
    return eligible, skipped, closed


def spawn_budget(skipped, max_open_prs):
    """How many more workers the PR backlog cap allows, or None uncapped."""
    if max_open_prs is None:
        return None
    pending = sum(
        1 for s in skipped
        if s["reason"] == "in_review" or (s["reason"] == "claimed" and s.get("own"))
    )
    return max(0, max_open_prs - pending)


def sort_eligible(children_eligible, raw_by_number):
    """Priority first (P0 best, missing last); ties toward the oldest child."""
    return sorted(
        children_eligible,
        key=lambda e: (
            parse_priority(e["priority"]),
            raw_by_number[e["number"]].get("createdAt") or "",
            e["number"],
        ),
    )


def parse_args(args):
    args = list(args)
    repo, resume, max_open_prs, positional = None, False, None, []
    while args:
        a = args.pop(0)
        if a == "--repo":
            if not args:
                fail("--repo needs owner/name", 2)
            repo = args.pop(0)
        elif a == "--resume":
            resume = True
        elif a == "--max-open-prs":
            if not args or not args[0].isdigit() or int(args[0]) < 1:
                fail("--max-open-prs needs a positive integer", 2)
            max_open_prs = int(args.pop(0))
        else:
            positional.append(a)
    if len(positional) != 1 or not positional[0].isdigit():
        fail("usage: resolve_ready.py <epic-number> [--repo owner/name] [--resume] "
             "[--max-open-prs N]", 2)
    return positional[0], repo, resume, max_open_prs


def resolve(epic_n, repo, resume, max_open_prs=None):
    suffix = ["--repo", repo] if repo else []

    show = json.loads(run(["hew", "show", epic_n, "--json", *suffix]))
    if not show.get("epic"):
        fail(f"#{epic_n} is not an epic — hand it to work-issue instead", 2)

    children = [
        json.loads(line)
        for line in run(
            ["hew", "list", "--epic", epic_n, "--json", "--bodies", *suffix]
        ).splitlines()
        if line.strip()
    ]
    raw_by_number = {c["number"]: c for c in children}
    # fail closed: without these reads a delivered or failed child looks eligible
    pr_by_issue, branch_by_issue = delivery_index(
        open_prs("number,headRefName", repo), remote_branches(repo)
    )
    me = current_user()
    eligible, skipped, closed = classify(
        children, me, pr_by_issue, branch_by_issue, resume
    )
    counts = {"closed": closed}
    for r in SKIP_REASONS:
        counts[r] = sum(1 for s in skipped if s["reason"] == r)
    counts["eligible"] = len(eligible)

    return {
        "epic": int(epic_n),
        "title": show.get("title", ""),
        "mainCheckout": main_checkout(),
        "defaultBranch": default_branch(repo),
        "eligible": sort_eligible(eligible, raw_by_number),
        "skipped": sorted(skipped, key=lambda s: s["number"]),
        "counts": counts,
        "spawnBudget": spawn_budget(skipped, max_open_prs),
    }


def main():
    epic_n, repo, resume, max_open_prs = parse_args(sys.argv[1:])
    try:
        out = resolve(epic_n, repo, resume, max_open_prs)
    except CommandError as e:
        fail(str(e))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
