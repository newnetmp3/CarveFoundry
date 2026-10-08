#!/usr/bin/env bash
# Install a SECONDARY Rust Studio KDE menu entry. The trusted Python CAM
# application/launcher and its existing venv are never overwritten.
set -Eeuo pipefail

ROOT="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
BIN="$ROOT/rust-ui/target/release/carvefoundry-studio"
APP_ID="io.github.newnetmp3.CarveFoundryStudio"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
LAUNCHER="$BIN_DIR/carvefoundry-studio"

command -v cargo >/dev/null || { echo "Missing cargo; install rust on Arch." >&2; exit 1; }
cargo build --manifest-path "$ROOT/rust-ui/Cargo.toml" --release
[[ -x "$BIN" ]] || { echo "Rust Studio executable missing after build" >&2; exit 1; }

if [[ -x "$ROOT/.venv/bin/python" ]]; then
    PYTHON_EXEC="$ROOT/.venv/bin/python"
elif [[ -x "${XDG_DATA_HOME:-$HOME/.local/share}/carvefoundry/venv/bin/python" ]]; then
    PYTHON_EXEC="${XDG_DATA_HOME:-$HOME/.local/share}/carvefoundry/venv/bin/python"
else
    PYTHON_EXEC="$(command -v python3)"
fi

mkdir -p "$BIN_DIR" "$DESKTOP_DIR"
if [[ -e "$LAUNCHER" ]] && ! grep -Fq '# CarveFoundry Studio managed launcher' "$LAUNCHER"; then
    echo "Refusing to replace an unrelated launcher: $LAUNCHER" >&2
    exit 1
fi

tmp_launcher="$(mktemp "$BIN_DIR/.studio-launch.XXXXXX")"
{
    printf '%s\n' '#!/usr/bin/env bash' '# CarveFoundry Studio managed launcher' 'set -Eeuo pipefail'
    printf 'cd -- %q\n' "$ROOT"
    printf 'export CARVEFOUNDRY_PYTHON=%q\n' "$PYTHON_EXEC"
    printf 'export PYTHONPATH=%q${PYTHONPATH:+:$PYTHONPATH}\n' "$ROOT/src"
    printf 'exec %q "$@"\n' "$BIN"
} > "$tmp_launcher"
chmod 0755 "$tmp_launcher"
mv -f -- "$tmp_launcher" "$LAUNCHER"

tmp_desktop="$(mktemp "$DESKTOP_DIR/.studio-desktop.XXXXXX")"
# The desktop Exec value is a user-owned absolute path, quoted per Desktop Entry spec.
escaped_exec="${LAUNCHER//\\/\\\\}"
escaped_exec="${escaped_exec//\"/\\\"}"
cat > "$tmp_desktop" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=CarveFoundry Studio (Rust Preview)
GenericName=Native CNC vector layout
Comment=Experimental Rust-native design and polygon-aware sheet arrangement
Exec="$escaped_exec"
TryExec=$LAUNCHER
Icon=io.github.newnetmp3.CarveFoundry
Terminal=false
Categories=Graphics;Engineering;
Keywords=Rust;CAD;CNC;Nesting;Sheet;
StartupNotify=true
EOF
chmod 0644 "$tmp_desktop"
mv -f -- "$tmp_desktop" "$DESKTOP_DIR/$APP_ID.desktop"
if command -v update-desktop-database >/dev/null; then
    update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || :
fi
echo "Rust Studio installed in KDE menu. Existing CarveFoundry CAM launcher unchanged."
echo "Terminal launcher: $LAUNCHER"
echo "Rust binary: $BIN"
