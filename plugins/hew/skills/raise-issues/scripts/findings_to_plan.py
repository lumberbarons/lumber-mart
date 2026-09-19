#!/usr/bin/env python3
"""Convert a critique findings file into a `hew apply` JSONL plan.

Pure translation — reads one findings file (the FINDINGS.md shape), writes
one plan line per fileable finding. Deduplication against the tracker stays
with the raise-issues agent (Step 3); this script never queries hew.

  findings_to_plan.py <findings.json> [--parent <epic>] [--reviewed-issue <n>]
                      [--reviewed-pr <n>] [--type bug|task] [--out FILE]

Per finding, the emitted plan line carries:

  title         the finding's title, unchanged
  type          --type, default bug
  priority      P1..P4; a P0 finding is filed P1 (P0 is a human's declaration)
  parent        --parent, when given (attach findings as epic children)
  blocked-by    --reviewed-issue, when given (fixes wait for the PR to merge)
  discovered-from  --reviewed-issue, when given
  where         backticked locations, then blank, then the identity lines:
                `review-key: <skill>/<pattern>/<scope>` and, when the finding
                was raised against a PR review, `review-of: #<n>` — both bare,
                both grep targets (pr_state.py greps the latter)
  problem       the explanation
  fix           the fix
  done-when     [done_when] as a one-item checklist

Scope is derived mechanically per raise-issues: the deepest directory
containing every file in `files`, or the single file itself.

A finding is skipped (and counted on stderr) when it lacks priority, files,
fix, or pattern — the pump files from critique findings files, which always
carry a pattern; hand-written lists go through the raise-issues agent instead.
`skill` is required for every finding — the file is rejected without it.

Exit: 0 plan written (may be empty — reviewed, nothing found) · 3 findings
file status is not `reviewed` (no_scope/error — nothing was reviewed) ·
1 runtime error · 2 usage error.
"""

import json
import os
import sys


def fail(msg, code=1):
    print(f"findings_to_plan: {msg}", file=sys.stderr)
    sys.exit(code)


def derive_scope(files):
    """Deepest directory containing every file, or the single file itself."""
    if len(files) == 1:
        return files[0]
    scope = os.path.commonpath(files) if files else ""
    if scope in ("", ".", "/"):
        return "."
    return scope


def backtick(paths):
    return ", ".join(f"`{p}`" for p in paths)


def convert(finding, parent, reviewed_issue, reviewed_pr, forced_type):
    """One finding -> one plan line, or (None, reason) when not fileable."""
    priority = finding.get("priority")
    files = finding.get("files")
    fix = finding.get("fix")
    pattern = finding.get("pattern")
    if not priority or not files or not fix:
        return None, "missing priority, files, or fix"
    if not pattern:
        return None, "missing pattern"
    pnum = "".join(c for c in priority if c.isdigit())
    if not pnum:
        return None, f"unreadable priority {priority!r}"
    priority = f"P{max(1, min(4, int(pnum)))}"  # never P0, never below P4

    scope = derive_scope(files)
    key = f"{finding.get('skill')}/{pattern}/{scope}"
    where_lines = [
        backtick(finding.get("locations") or files),
        "",
        f"review-key: {key}",
    ]
    if reviewed_issue is not None:
        marker = f"review-of: #{reviewed_issue}"
        if reviewed_pr is not None:
            marker += f" (PR #{reviewed_pr})"
        where_lines.append(marker)

    line = {
        "title": finding.get("title") or f"{pattern} in {scope}",
        "type": forced_type,
        "priority": priority,
        "where": "\n".join(where_lines),
        "problem": finding.get("explanation") or "",
        "fix": fix,
        "done-when": [finding["done_when"]] if finding.get("done_when") else [],
    }
    if parent is not None:
        line["parent"] = parent
    if reviewed_issue is not None:
        line["blocked-by"] = [reviewed_issue]
        line["discovered-from"] = reviewed_issue
    return line, None


def main():
    args = sys.argv[1:]
    parent = None
    reviewed_issue = None
    reviewed_pr = None
    forced_type = "bug"
    out = None
    positional = []
    while args:
        a = args.pop(0)
        if a == "--parent":
            parent = int(args.pop(0))
        elif a == "--reviewed-issue":
            reviewed_issue = int(args.pop(0))
        elif a == "--reviewed-pr":
            reviewed_pr = int(args.pop(0))
        elif a == "--type":
            forced_type = args.pop(0)
            if forced_type not in ("bug", "task"):
                fail("--type must be bug or task", 2)
        elif a == "--out":
            out = args.pop(0)
        elif a.startswith("-"):
            fail(f"unknown flag {a}", 2)
        else:
            positional.append(a)
    if len(positional) != 1:
        fail(
            "usage: findings_to_plan.py <findings.json> [--parent <epic>] "
            "[--reviewed-issue <n>] [--reviewed-pr <n>] [--type bug|task] "
            "[--out FILE]",
            2,
        )

    with open(positional[0]) as f:
        data = json.load(f)

    status = data.get("status", "reviewed")
    if status != "reviewed":
        print(
            f"findings_to_plan: findings status is {status!r} — "
            f"nothing was reviewed, nothing to file ({data.get('reason', '')})",
            file=sys.stderr,
        )
        sys.exit(3)
    if not data.get("skill"):
        fail("findings file carries no `skill` — cannot derive review keys", 1)

    lines, skipped = [], 0
    for finding in data.get("findings") or []:
        converted = dict(finding, skill=data["skill"])
        line, reason = convert(
            converted, parent, reviewed_issue, reviewed_pr, forced_type
        )
        if line is None:
            skipped += 1
            print(f"findings_to_plan: skipped finding — {reason_skip(reason, finding)}", file=sys.stderr)
            continue
        lines.append(line)

    text = "".join(json.dumps(l, separators=(",", ":")) + "\n" for l in lines)
    if out:
        with open(out, "w") as f:
            f.write(text)
    else:
        sys.stdout.write(text)
    print(
        f"findings_to_plan: {len(lines)} planned, {skipped} skipped",
        file=sys.stderr,
    )


def reason_skip(reason, finding):
    title = finding.get("title") or "<untitled>"
    return f"{reason} ({title!r})"


if __name__ == "__main__":
    main()
