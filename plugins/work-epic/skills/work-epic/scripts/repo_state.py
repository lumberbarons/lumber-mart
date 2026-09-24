"""Read-only repository probes shared by resolve_ready.py and pr_state.py.

Both planners need the same facts — where the primary checkout is, which
branch is the default, which open PRs and pushed branches map to which issue —
and must agree on them, so they read them through one module rather than two
copies that drift.
"""

import json
import re
import subprocess
from urllib.parse import quote

# work-issue's naming rule: <prefix>/<n>-<slug>
BRANCH_ISSUE_RE = re.compile(r"^(?:fix|feat|chore)/(\d+)(?:-|$)")

# gh pr list defaults to 30; a busy repo would silently drop epic PRs past it
PR_LIMIT = "1000"


class CommandError(Exception):
    """A probe command exited non-zero; the message is its stderr."""


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise CommandError(p.stderr.strip() or f"{' '.join(cmd)} exited {p.returncode}")
    return p.stdout


def branch_issue(name):
    """The issue number a conventional branch name carries, or None."""
    m = BRANCH_ISSUE_RE.match(name or "")
    return int(m.group(1)) if m else None


def main_checkout():
    """Absolute path of the repository's primary worktree, or None.

    `git worktree list --porcelain` lists the main worktree first; that is
    the checkout every other worktree hangs off, so it is where the pump
    updates the default branch and where herdr sessions inherit cwd from.
    """
    p = subprocess.run(
        ["git", "worktree", "list", "--porcelain"], capture_output=True, text=True
    )
    if p.returncode != 0:
        return None
    for line in p.stdout.splitlines():
        if line.startswith("worktree "):
            return line[len("worktree ") :] or None
    return None


def default_branch(repo=None):
    """The default branch name, or None if undeterminable.

    origin/HEAD first (local, free); it is unset on some clones, so fall back
    to asking GitHub.
    """
    if repo is None:
        p = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "origin/HEAD"],
            capture_output=True,
            text=True,
        )
        name = p.stdout.strip()
        if p.returncode == 0 and name.startswith("origin/") and name != "origin/HEAD":
            return name[len("origin/") :]
    p = subprocess.run(
        ["gh", "repo", "view", *([repo] if repo else []),
         "--json", "defaultBranchRef", "--jq", ".defaultBranchRef.name"],
        capture_output=True,
        text=True,
    )
    return (p.stdout.strip() or None) if p.returncode == 0 else None


def open_prs(fields, repo=None):
    """Every open PR as gh JSON with the given comma-separated fields."""
    return json.loads(
        run(
            ["gh", "pr", "list", "--state", "open", "--limit", PR_LIMIT,
             "--json", fields, *(["-R", repo] if repo else [])]
        )
    )


def remote_branches(repo=None):
    """Names of every branch on the GitHub remote."""
    out = run(
        ["gh", "api", "--paginate",
         f"repos/{repo or '{owner}/{repo}'}/branches?per_page=100",
         "--jq", ".[].name"]
    )
    return [line for line in out.splitlines() if line.strip()]


def behind_by(base, head, repo=None):
    """How many commits on `base` the commit `head` lacks, or None if unknown.

    GitHub's mergeStateStatus says BEHIND only when branch protection requires
    branches to be up to date; without that rule a stale PR reads CLEAN and
    would merge on CI that never saw what landed since. The compare API
    answers regardless of protection.
    """
    if not base or not head:
        return None
    p = subprocess.run(
        ["gh", "api",
         f"repos/{repo or '{owner}/{repo}'}/compare/{quote(base)}...{head}",
         "--jq", ".behind_by"],
        capture_output=True,
        text=True,
    )
    if p.returncode != 0:
        return None
    try:
        return int(p.stdout.strip())
    except ValueError:
        return None
