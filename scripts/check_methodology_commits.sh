#!/usr/bin/env bash
# Validates that commits with methodology-relevant scopes include
# required structured fields (Why: and Impact:) in the commit body.
#
# Usage: scripts/check_methodology_commits.sh <base-ref> <head-ref>
#   e.g.: scripts/check_methodology_commits.sh origin/main HEAD

set -euo pipefail

BASE="${1:?Usage: $0 <base-ref> <head-ref>}"
HEAD="${2:?Usage: $0 <base-ref> <head-ref>}"

# Methodology-relevant scope patterns
SCOPE_PATTERN='^\(wfo\|threshold\|stage-\|execution\|data\|reduced-core\)'

FAILED=0

while IFS= read -r sha; do
    subject=$(git log -1 --format='%s' "$sha")
    # Extract scope from conventional commit: type(scope): message
    scope=$(echo "$subject" | sed -n 's/^[a-z]*(\([^)]*\)).*/\1/p')

    if [ -z "$scope" ]; then
        continue
    fi

    # Check if scope matches methodology patterns
    if ! echo "$scope" | grep -q "$SCOPE_PATTERN"; then
        continue
    fi

    body=$(git log -1 --format='%b' "$sha")

    missing=""
    if ! echo "$body" | grep -qi '^Why:'; then
        missing="${missing} Why:"
    fi
    if ! echo "$body" | grep -qi '^Impact:'; then
        missing="${missing} Impact:"
    fi

    if [ -n "$missing" ]; then
        echo "ERROR: Commit $sha has methodology scope ($scope) but missing:$missing"
        echo "  Subject: $subject"
        echo "  Methodology commits must include Why: and Impact: lines in the body."
        echo ""
        FAILED=1
    fi
done < <(git rev-list "$BASE".."$HEAD")

if [ "$FAILED" -eq 1 ]; then
    echo "FAILED: Some methodology commits are missing required fields."
    echo "Required format for methodology scopes (wfo, threshold, stage-*, execution, data, reduced-core):"
    echo ""
    echo "  feat(threshold): short description"
    echo ""
    echo "  Why: explanation of rationale"
    echo "  Impact: what changed in outcomes"
    echo ""
    exit 1
fi

echo "OK: All methodology commits have required fields."
