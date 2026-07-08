#!/usr/bin/env bash
set -euo pipefail

git config --global --unset alias.deploy-staging >/dev/null 2>&1 || true
git config --global alias.deploy-prod \
  '!f(){ repo="$(git rev-parse --show-toplevel)" || return 1; bash "$repo/scripts/git-deploy-prod" "$@"; }; f'

cat <<'EOF'
Installed aliases:
  git deploy-prod

Removed aliases:
  git deploy-staging

These aliases require:
- You are inside this repository.
- Bash is available.
EOF
