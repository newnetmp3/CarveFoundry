#!/usr/bin/env bash
# Launch the Git-tracked CarveWork companion without moving private chat data.
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
APP_ROOT="$REPO_ROOT/tools/carve-work"

# If the user originally installed the separate archive, retain its SQLite
# history and PROJECT_CONTEXT.md even if tests or an early launch created\n# an empty in-repo database. Respect an explicit CARVE_WORK_DATA override.
if [[ -z "${CARVE_WORK_DATA:-}" && -f "$HOME/git/carve-work/data/carve_work.sqlite3" ]]; then
    export CARVE_WORK_DATA="$HOME/git/carve-work/data"
    printf 'CarveWork: using existing private data at %s\n' "$CARVE_WORK_DATA"
fi

export CARVEFOUNDRY_REPO="${CARVEFOUNDRY_REPO:-$REPO_ROOT}"
exec bash "$APP_ROOT/run.sh" "$@"
