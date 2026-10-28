#!/usr/bin/env python3
"""Convert a critique findings file into a `hew apply` JSONL plan.

Pure translation — reads one findings file (the FINDINGS.md shape), writes
one plan line per fileable finding. Deduplication against the tracker stays
with the raise-issues agent (Step 3); this script never queries hew.

  findings_to_plan.py <findings.json> [--parent <epic>] [--reviewed-issue <n>]
                      [--reviewed-pr <n>] [--reviewed-key <key>]
                      [--at-or-above P1..P4] [--type bug|task] [--out FILE]

Per finding, the emitted plan line carries:

  title         the finding's title, unchanged
  type          --type, default bug
  priority      P1..P4; a P0 finding is filed P1 (P0 is a human's declaration)
  parent        --parent, when given (attach findings as epic children)
  blocked-by    --reviewed-issue, when given (fixes wait for the PR to merge)
  discovered-from  --reviewed-issue, when given
  where         backticked locations, then blank, then the identity lines:
                `review-key: <skill>/<pattern>/<scope>[#family:<reviewed-key>]`
                and, when the finding was raised against a PR review,
                `review-of: #<n>` — both bare, both grep targets (pr_state.py
                greps the latter)
  problem       the explanation
  fix           the fix
  done-when     [done_when] as a one-item checklist

Scope is derived mechanically from the finding's own file set: the file itself
when there is one, otherwise the deepest common directory plus the sorted
relative paths in braces, e.g. `internal/store/{index.go,store.go}`. Two
findings in one package that touch different files therefore get different
keys, while a pattern-collapsed finding still names every file.

`--reviewed-key` is the `review-key:` value of the issue being reviewed, when
that issue is itself a finding. It appends `#family:<key>` to every emitted
key, so generation 2 of a seam is distinguishable from the finding it reviews
instead of deduplicating onto it.

A finding is skipped (and counted on stderr) when it lacks priority, files,
fix, or pattern — the pump files from critique findings files, which always
carry a pattern; hand-written lists go through the raise-issues agent instead.
`--at-or-above P2` also skips findings less severe than P2 (P3, P4), for
callers that relay those elsewhere rather than track them.
`skill` is required for every finding — the file is rejected without it.

Exit: 0 plan written (may be empty — reviewed, nothing found) · 3 findings
file status is not `reviewed` (no_scope/error — nothing was reviewed) ·
1 runtime error · 2 usage error.
"""

import json
import os
import sys

USAGE = (
    "usage: findings_to_plan.py <findings.json> [--parent <epic>] "
    "[--reviewed-issue <n>] [--reviewed-pr <n>] [--reviewed-key <key>] "
    "[--at-or-above P1..P4] [--type bug|task] [--out FILE]"
)


def fail(msg, code=1):
    print(f"findings_to_plan: {msg}", file=sys.stderr)
    sys.exit(code)


def derive_scope(files):
    """Stable identity of the finding's own file set.

    One file keeps its path, which is what the first key scheme used. Several
    files become the deepest common directory plus the sorted relative paths
    in braces, so a pattern-collapsed finding still names every affected file
    and two findings in one package with different files get different keys.
    """
    files = sorted({f for f in files if f})
    if len(files) == 1:
        return files[0]
    if not files:
        return "."
    try:
        common = os.path.commonpath(files)
    except ValueError:
        common = "."
    if common in ("", ".", "/"):
        common = "."
    common = common.replace(os.sep, "/")
    rel = [os.path.relpath(f, common).replace(os.sep, "/") for f in files]
    return f"{common}/{{{','.join(rel)}}}"


def derive_scope_legacy(files):
    """The scope the original key scheme used, for dedup against old issues.

    Deepest directory containing every file, or the single file itself. This
    is what an issue filed before file-set scopes carries in its body.
    """
    files = sorted({f for f in files if f})
    if len(files) == 1:
        return files[0]
    try:
        scope = os.path.commonpath(files) if files else ""
    except ValueError:
        scope = "."
    if scope in ("", ".", "/"):
        return "."
    return scope.replace(os.sep, "/")


def review_key(skill, pattern, scope, reviewed_key=None):
    key = f"{skill}/{pattern}/{scope}"
    if reviewed_key:
        key += f"#family:{reviewed_key}"
    return key


def backtick(paths):
    return ", ".join(f"`{p}`" for p in paths)


def priority_number(priority):
    digits = "".join(c for c in priority or "" if c.isdigit())
    return int(digits) if digits else None


def convert(finding, parent, reviewed_issue, reviewed_pr, forced_type,
            at_or_above=None, reviewed_key=None):
    """One finding -> one plan line, or (None, reason) when not fileable."""
    priority = finding.get("priority")
    files = finding.get("files")
    fix = finding.get("fix")
    pattern = finding.get("pattern")
    if not priority or not files or not fix:
        return None, "missing priority, files, or fix"
    if not pattern:
        return None, "missing pattern"
    pnum = priority_number(priority)
    if pnum is None:
        return None, f"unreadable priority {priority!r}"
    if at_or_above is not None and pnum > at_or_above:
        return None, f"below --at-or-above P{at_or_above}"
    priority = f"P{max(1, min(4, pnum))}"  # never P0, never below P4

    scope = derive_scope(files)
    # Older portability reports used the schema's `skills` spelling. New plans
    # share one identity; tracker dedup must still search existing legacy keys.
    skill = finding.get('skill')
    if skill == 'skills':
        skill = 'portability'
    key = review_key(skill, pattern, scope, reviewed_key)
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


def parse_args(args):
    opts = {"parent": None, "reviewed_issue": None, "reviewed_pr": None,
            "reviewed_key": None, "type": "bug", "out": None,
            "at_or_above": None}
    positional = []

    def value(flag):
        if not args:
            fail(f"{flag} needs a value\n{USAGE}", 2)
        return args.pop(0)

    def number(flag):
        v = value(flag)
        if not v.isdigit():
            fail(f"{flag} needs an issue number, got {v!r}", 2)
        return int(v)

    while args:
        a = args.pop(0)
        if a == "--parent":
            opts["parent"] = number(a)
        elif a == "--reviewed-issue":
            opts["reviewed_issue"] = number(a)
        elif a == "--reviewed-pr":
            opts["reviewed_pr"] = number(a)
        elif a == "--reviewed-key":
            v = value(a).strip()
            if not v or any(c.isspace() for c in v):
                fail("--reviewed-key needs one review-key value", 2)
            opts["reviewed_key"] = v
        elif a == "--at-or-above":
            v = value(a)
            if v not in ("P1", "P2", "P3", "P4"):
                fail("--at-or-above must be P1, P2, P3, or P4", 2)
            opts["at_or_above"] = int(v[1])
        elif a == "--type":
            opts["type"] = value(a)
            if opts["type"] not in ("bug", "task"):
                fail("--type must be bug or task", 2)
        elif a == "--out":
            opts["out"] = value(a)
        elif a.startswith("-"):
            fail(f"unknown flag {a}\n{USAGE}", 2)
        else:
            positional.append(a)
    if len(positional) != 1:
        fail(USAGE, 2)
    return positional[0], opts


def main():
    path, opts = parse_args(sys.argv[1:])
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        fail(f"cannot read findings file {path}: {e}")

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
            converted, opts["parent"], opts["reviewed_issue"], opts["reviewed_pr"],
            opts["type"], opts["at_or_above"], opts["reviewed_key"],
        )
        if line is None:
            skipped += 1
            title = finding.get("title") or "<untitled>"
            print(f"findings_to_plan: skipped finding — {reason} ({title!r})",
                  file=sys.stderr)
            continue
        lines.append(line)

    text = "".join(json.dumps(l, separators=(",", ":")) + "\n" for l in lines)
    if opts["out"]:
        with open(opts["out"], "w") as f:
            f.write(text)
    else:
        sys.stdout.write(text)
    print(
        f"findings_to_plan: {len(lines)} planned, {skipped} skipped",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
