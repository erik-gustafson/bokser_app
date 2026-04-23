#!/usr/bin/env bash
set -euo pipefail

git config --global alias.deploy-staging \
  '!f(){ repo="$(git rev-parse --show-toplevel)" || return 1; bash "$repo/scripts/git-deploy-staging" "$@"; }; f'
git config --global alias.deploy-prod \
  '!f(){ repo="$(git rev-parse --show-toplevel)" || return 1; bash "$repo/scripts/git-deploy-prod" "$@"; }; f'

cat <<'EOF'
Installed aliases:
  git deploy-staging
  git deploy-prod

These aliases require:
- You are inside this repository.
- Bash is available.
EOF

