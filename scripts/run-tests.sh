#!/usr/bin/env bash
# Runs every test suite under tests/<plugin>/<skill>/, each in its own interpreter: suites
# import the script under test by bare module name, and several skills ship a module of the
# same name (lightspec.py), so one shared process would let them shadow each other.
#
# A directory under tests/ is picked up automatically; there is no list to keep in step.
#
# Usage:
#   scripts/run-tests.sh                     Run every suite
#   scripts/run-tests.sh tests/hew/raise-issues   Run the named suite(s) only

set -uo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root" || exit 1

if [ "$#" -gt 0 ]; then
  suites=("$@")
else
  suites=()
  for dir in tests/*/*/; do
    suites+=("${dir%/}")
  done
fi

failed=()
for suite in "${suites[@]}"; do
  echo "== $suite"
  # An empty suite exits non-zero ("NO TESTS RAN"), so a directory of misnamed files fails
  # loudly instead of passing.
  if ! python3 -m unittest discover -s "$suite"; then
    failed+=("$suite")
  fi
done

if [ "${#failed[@]}" -gt 0 ]; then
  echo >&2
  echo "failed: ${failed[*]}" >&2
  exit 1
fi
