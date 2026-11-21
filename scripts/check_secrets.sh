#!/usr/bin/env bash
# Fails if a Google API key appears in any file git would commit, or in git history.
# Run before pushing:  bash scripts/check_secrets.sh
# Install as a pre-commit hook:  ln -sf ../../scripts/check_secrets.sh .git/hooks/pre-commit
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

pattern='AIza[0-9A-Za-z_-]{35}|AQ\.[0-9A-Za-z_-]{40,}'
found=0

# Staged and tracked files, plus untracked files that aren't ignored.
if git grep -nE "$pattern" -- . >/dev/null 2>&1 || \
   git diff --cached -U0 | grep -qE "$pattern" || \
   { git ls-files --others --exclude-standard -z | xargs -0 grep -lE "$pattern" 2>/dev/null | grep -q .; }; then
  echo "Possible Google API key in files git would commit:"
  git grep -nE "$pattern" -- . 2>/dev/null | sed -E "s/$pattern/<REDACTED KEY>/g" || true
  git ls-files --others --exclude-standard -z | xargs -0 grep -lE "$pattern" 2>/dev/null || true
  found=1
fi

if git rev-parse --verify HEAD >/dev/null 2>&1 && git log -p --all | grep -qE "$pattern"; then
  echo "A Google API key is in git history. Delete it at aistudio.google.com/api-keys and make a new one."
  found=1
fi

if git ls-files --error-unmatch .env >/dev/null 2>&1; then
  echo ".env is tracked by git. Run: git rm --cached .env"
  found=1
fi

if [ "$found" -eq 0 ]; then
  echo "No API keys found."
fi
exit "$found"
