#!/usr/bin/env bash
# Launch the experimental Rust-native 2D layout interface without modifying
# the installed, safety-validated Python CAM launcher.
set -Eeuo pipefail
ROOT="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
command -v cargo >/dev/null || { echo "Install Rust/Cargo with pacman first." >&2; exit 1; }
exec cargo run --manifest-path "$ROOT/rust-ui/Cargo.toml" --release -- "$@"
