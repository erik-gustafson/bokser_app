#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

STAGING_BARE="$HOME/git/bokser_app-staging.git"
PROD_BARE="$HOME/git/bokser_app-production.git"

install_bare_repo() {
  local repo_path="$1"
  if [[ ! -d "$repo_path" ]]; then
    mkdir -p "$repo_path"
    git init --bare "$repo_path"
    echo "Initialized bare repo: $repo_path"
  else
    echo "Bare repo already exists: $repo_path"
  fi
}

install_hook() {
  local source_hook="$1"
  local target_repo="$2"
  local target_hook="$target_repo/hooks/post-receive"
  if [[ ! -f "$source_hook" ]]; then
    echo "Missing hook file: $source_hook" >&2
    exit 1
  fi
  install -m 755 "$source_hook" "$target_hook"
  echo "Installed hook: $target_hook"
}

install_bare_repo "$STAGING_BARE"
install_bare_repo "$PROD_BARE"

install_hook "$ROOT_DIR/nas-hooks/post-receive.staging" "$STAGING_BARE"
install_hook "$ROOT_DIR/nas-hooks/post-receive.production" "$PROD_BARE"

echo "NAS bootstrap complete."
