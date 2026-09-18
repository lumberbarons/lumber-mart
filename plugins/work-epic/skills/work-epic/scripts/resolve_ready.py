#!/usr/bin/env python3
"""Resolve a hew epic's ready children into a deterministic fan-out plan.

Read-only: runs `hew show` and `hew list --epic --json --bodies`, never writes.
Prints one JSON object to stdout:

  {
    "epic": <n>, "title": "...",
    "eligible": [ {"number", "title", "priority", "type", "where", "doneWhen",
                   "large"} ... ],        # priority-sorted, oldest tie-break
    "skipped":  [ {"number", "title", "reason", "detail"} ... ],
    "counts":   {"eligible": n, "blocked": n, "untriaged": n, "claimed": n,
                 "closed": n}
  }

Skip reasons: blocked (open blockers), untriaged (no priority/type),
claimed (in progress by someone else). Closed children are counted, not listed.

Usage: resolve_ready.py <epic-number> [--repo owner/name]
Exit: 0 ok (eligible may be empty) · 1 runtime error · 2 not an epic/usage
"""

import json
import re
import subprocess
import sys

PRIORITY_RE = re.compile(r"^P(\d+)$")
WHERE_MAX = 3  # more than three paths -> large (work-issue's sizing rule)
DONE_WHEN_MAX = 5  # more than five done-when items -> large


def fail(msg, code=1):
    print(f"resolve_ready: {msg}", file=sys.stderr)
    sys.exit(code)


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        fail(p.stderr.strip() or f"{' '.join(cmd)} exited {p.returncode}")
    return p.stdout


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


def classify(children, me):
    eligible, skipped, closed = [], [], 0
    for c in children:
        if c.get("state") != "open":
            closed += 1
            continue
        body = c.get("body") or ""
        blockers = c.get("openBlockers") or []
        if blockers:
            skipped.append(
                {
                    "number": c["number"],
                    "title": c.get("title", ""),
                    "reason": "blocked",
                    "detail": "blocked by " + ", ".join(f"#{b}" for b in blockers),
                }
            )
            continue
        if c.get("untriaged"):
            skipped.append(
                {
                    "number": c["number"],
                    "title": c.get("title", ""),
                    "reason": "untriaged",
                    "detail": "missing priority or type",
                }
            )
            continue
        if c.get("inProgress"):
            assignees = c.get("assignees") or []
            if me is None or me not in assignees:
                skipped.append(
                    {
                        "number": c["number"],
                        "title": c.get("title", ""),
                        "reason": "claimed",
                        "detail": "in progress "
                        + (", ".join("@" + a for a in assignees) or "unassigned"),
                    }
                )
                continue
        where = section_items(body, "where")
        done_when = section_items(body, "done when")
        eligible.append(
            {
                "number": c["number"],
                "title": c.get("title", ""),
                "priority": c.get("priority"),
                "type": c.get("type"),
                "where": where,
                "doneWhen": done_when,
                "large": where > WHERE_MAX or done_when > DONE_WHEN_MAX,
            }
        )
    return eligible, skipped, closed


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


def main():
    args = sys.argv[1:]
    repo = None
    if "--repo" in args:
        i = args.index("--repo")
        if i + 1 >= len(args):
            fail("--repo needs owner/name", 2)
        repo = args[i + 1]
        del args[i : i + 2]
    if len(args) != 1 or not args[0].isdigit():
        fail("usage: resolve_ready.py <epic-number> [--repo owner/name]", 2)
    epic_n = args[0]
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
    me = current_user()
    eligible, skipped, closed = classify(children, me)
    counts = {"closed": closed}
    for r in ("blocked", "untriaged", "claimed"):
        counts[r] = sum(1 for s in skipped if s["reason"] == r)
    counts["eligible"] = len(eligible)

    print(
        json.dumps(
            {
                "epic": int(epic_n),
                "title": show.get("title", ""),
                "eligible": sort_eligible(eligible, raw_by_number),
                "skipped": sorted(skipped, key=lambda s: s["number"]),
                "counts": counts,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
