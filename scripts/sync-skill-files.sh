#!/usr/bin/env bash
# Copies files shared by several skills into each skill directory that uses them, so every
# skill directory is self-contained. Per-skill installers (APM, anything following the Agent
# Skills spec) copy a skill's directory and nothing around it, and filter symlinks — a skill
# that reaches ../../ for a file finds nothing there once installed.
#
# Edit the source, never a copy, then run this. CI runs --check and fails on any drift.
#
# Usage:
#   scripts/sync-skill-files.sh           Overwrite every copy with its source
#   scripts/sync-skill-files.sh --check   Exit 1 if any copy is missing or differs from its source

set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# source                                          copy
pairs=(
  "plugins/critique/FINDINGS.md                   plugins/critique/skills/review-code/FINDINGS.md"
  "plugins/critique/FINDINGS.md                   plugins/critique/skills/review-docs/FINDINGS.md"
  "plugins/critique/FINDINGS.md                   plugins/critique/skills/review-o11y/FINDINGS.md"
  "plugins/critique/FINDINGS.md                   plugins/critique/skills/review-portability/FINDINGS.md"
  "plugins/critique/FINDINGS.md                   plugins/critique/skills/review-tests/FINDINGS.md"
  "plugins/critique/scripts/discover-files.sh     plugins/critique/skills/review-code/scripts/discover-files.sh"
  "plugins/critique/scripts/discover-files.sh     plugins/critique/skills/review-docs/scripts/discover-files.sh"
  "plugins/critique/scripts/discover-files.sh     plugins/critique/skills/review-o11y/scripts/discover-files.sh"
  "plugins/critique/scripts/discover-files.sh     plugins/critique/skills/review-tests/scripts/discover-files.sh"
  "plugins/lightspec/skills/draft-spec/scripts/lightspec.py  plugins/lightspec/skills/approve-spec/scripts/lightspec.py"
)

check=false
case "${1:-}" in
  --check) check=true ;;
  "") ;;
  *) echo "usage: $0 [--check]" >&2; exit 2 ;;
esac

drift=0
for pair in "${pairs[@]}"; do
  read -r src dst <<<"$pair"
  if $check; then
    if ! cmp -s "$root/$src" "$root/$dst"; then
      echo "out of sync: $dst (source: $src)" >&2
      drift=1
    fi
  else
    mkdir -p "$(dirname "$root/$dst")"
    cp -p "$root/$src" "$root/$dst"
  fi
done

if [ "$drift" -ne 0 ]; then
  echo "Edit the source, then run scripts/sync-skill-files.sh." >&2
  exit 1
fi
