#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
SYNC_DIR="${REPO_ROOT}/final_paper"
SYNC_PATHSPEC="final_paper"

DEFAULT_REMOTE_URL="https://git@git.overleaf.com/69d7f5837aeb48de51af6f12"
REMOTE_URL="${OVERLEAF_FINAL_PAPER_URL:-${2:-$DEFAULT_REMOTE_URL}}"
REMOTE_BRANCH="${OVERLEAF_FINAL_PAPER_BRANCH:-master}"
REMOTE_WORKDIR=""

usage() {
  cat <<'EOF'
Usage: scripts/final_paper_overleaf_sync.sh <command> [overleaf-url]

Commands:
  status       Show the configured Overleaf target and local Git status
  diff-remote  Show a diff between final_paper/ and the Overleaf project
  pull         Copy the Overleaf project into final_paper/
  push         Copy committed final_paper/ changes back to Overleaf

Environment:
  OVERLEAF_FINAL_PAPER_URL      Override the Overleaf Git URL
  OVERLEAF_FINAL_PAPER_BRANCH   Override the Overleaf branch (default: master)

Notes:
  - pull and push both clone the remote into a temporary directory.
  - push requires final_paper/ to be clean in Git before it runs.
EOF
}

cleanup() {
  if [[ -n "${REMOTE_WORKDIR}" && -d "${REMOTE_WORKDIR}" ]]; then
    rm -rf "${REMOTE_WORKDIR}"
  fi
}

trap cleanup EXIT

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

ensure_repo_root() {
  git -C "${REPO_ROOT}" rev-parse --show-toplevel >/dev/null
}

ensure_sync_dir() {
  if [[ ! -d "${SYNC_DIR}" ]]; then
    echo "Missing sync directory: ${SYNC_DIR}" >&2
    exit 1
  fi
}

ensure_clean_final_paper() {
  if [[ -n "$(git -C "${REPO_ROOT}" status --porcelain=v1 --untracked-files=all -- "${SYNC_PATHSPEC}")" ]]; then
    echo "final_paper/ has uncommitted changes. Commit, stash, or clean them first." >&2
    exit 1
  fi
}

clone_remote() {
  REMOTE_WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/overleaf-final-paper.XXXXXX")"
  git clone --quiet --branch "${REMOTE_BRANCH}" --single-branch "${REMOTE_URL}" "${REMOTE_WORKDIR}"
}

sync_remote_to_local() {
  rsync -a --checksum --delete --exclude '.git/' "${REMOTE_WORKDIR}/" "${SYNC_DIR}/"
}

sync_local_to_remote() {
  rsync -a --checksum --delete --exclude '.git/' "${SYNC_DIR}/" "${REMOTE_WORKDIR}/"
}

remote_author_name() {
  local configured_name
  configured_name="$(git -C "${REPO_ROOT}" config user.name || true)"
  printf '%s\n' "${OVERLEAF_GIT_AUTHOR_NAME:-${configured_name:-GitHub final_paper sync}}"
}

remote_author_email() {
  local configured_email
  configured_email="$(git -C "${REPO_ROOT}" config user.email || true)"
  printf '%s\n' "${OVERLEAF_GIT_AUTHOR_EMAIL:-${configured_email:-noreply@example.com}}"
}

show_status() {
  echo "Overleaf URL: ${REMOTE_URL}"
  echo "Overleaf branch: ${REMOTE_BRANCH}"
  echo "Sync directory: ${SYNC_PATHSPEC}/"
  echo
  git -C "${REPO_ROOT}" --no-pager status --short --branch -- "${SYNC_PATHSPEC}"
}

show_diff_remote() {
  clone_remote
  set +e
  diff -ruN --exclude '.git' "${REMOTE_WORKDIR}" "${SYNC_DIR}"
  local diff_status=$?
  set -e
  if [[ ${diff_status} -gt 1 ]]; then
    exit "${diff_status}"
  fi
}

pull_remote() {
  ensure_clean_final_paper
  clone_remote
  sync_remote_to_local
  echo "Pulled Overleaf into final_paper/. Review the diff, then commit it to GitHub."
}

push_remote() {
  ensure_clean_final_paper
  clone_remote
  sync_local_to_remote

  if [[ -z "$(git -C "${REMOTE_WORKDIR}" status --porcelain=v1)" ]]; then
    echo "Overleaf already matches final_paper/."
    return 0
  fi

  git -C "${REMOTE_WORKDIR}" add -A
  git -C "${REMOTE_WORKDIR}" \
    -c user.name="$(remote_author_name)" \
    -c user.email="$(remote_author_email)" \
    commit -m "${OVERLEAF_FINAL_PAPER_COMMIT_MESSAGE:-Sync final_paper from GitHub $(git -C "${REPO_ROOT}" rev-parse --short HEAD)}"
  git -C "${REMOTE_WORKDIR}" push origin "HEAD:${REMOTE_BRANCH}"
  echo "Pushed final_paper/ to Overleaf."
}

main() {
  local command="${1:-status}"

  require_command git
  require_command mktemp
  require_command rsync
  ensure_repo_root
  ensure_sync_dir

  case "${command}" in
    status)
      show_status
      ;;
    diff-remote)
      show_diff_remote
      ;;
    pull)
      pull_remote
      ;;
    push)
      push_remote
      ;;
    help|-h|--help)
      usage
      ;;
    *)
      usage >&2
      exit 1
      ;;
  esac
}

main "$@"
