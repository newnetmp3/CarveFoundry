#!/usr/bin/env bash
# Launch the experimental Rust-native 2D layout interface without modifying
# the installed, safety-validated Python CAM launcher.
set -Eeuo pipefail
ROOT="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
command -v cargo >/dev/null || { echo "Install Rust/Cargo with pacman first." >&2; exit 1; }
if [[ -z "${CARVEFOUNDRY_PYTHON:-}" ]]; then
    if [[ -x "$ROOT/.venv/bin/python" ]]; then
        CARVEFOUNDRY_PYTHON="$ROOT/.venv/bin/python"
    elif [[ -x "${XDG_DATA_HOME:-$HOME/.local/share}/carvefoundry/venv/bin/python" ]]; then
        CARVEFOUNDRY_PYTHON="${XDG_DATA_HOME:-$HOME/.local/share}/carvefoundry/venv/bin/python"
    else
        CARVEFOUNDRY_PYTHON="$(command -v python3)"
    fi
fi
export CARVEFOUNDRY_PYTHON
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
exec cargo run --manifest-path "$ROOT/rust-ui/Cargo.toml" --release -- "$@"
