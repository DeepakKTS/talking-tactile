#!/bin/sh
# Point git at the hooks kept in scripts/hooks, so the pre-commit test gate runs on every commit.
set -e
cd "$(git rev-parse --show-toplevel)"
chmod +x scripts/hooks/pre-commit
git config core.hooksPath scripts/hooks
echo "Installed: git core.hooksPath is now scripts/hooks"
