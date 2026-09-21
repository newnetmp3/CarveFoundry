#!/usr/bin/env bash
# CarveFoundry user launcher installer. No sudo or global pip modifications.
set -Eeuo pipefail

usage() {
    cat <<'HELP'
Install CarveFoundry as a native Linux desktop application for this user.

Usage: bash scripts/install-linux.sh [--with-ai] [--venv PATH] [--desktop-only]

Default: reuse this checkout's .venv if it exists; otherwise create a venv
under ${XDG_DATA_HOME:-~/.local/share}/carvefoundry/venv. Build/install the
editable Python+Rust app there and register the KDE/GNOME app launcher.
--with-ai       Also install local AI dependencies (large download). This may
                replace existing CPU/CUDA/ROCm torch wheels; choose matching
                wheels first if GPU acceleration is important.
--venv PATH     Use a specific existing/new Python venv.
--desktop-only  Skip pip/build; register an already-installed venv's app.
--help          Show this help.

Re-run after a git pull when Rust, dependencies, or the app have changed.
The source checkout must remain in place for an editable installation.
HELP
}

ROOT="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
APP_ID="io.github.newnetmp3.CarveFoundry"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
BIN_HOME="${HOME}/.local/bin"
DESKTOP_HOME="${DATA_HOME}/applications"
ICON_HOME="${DATA_HOME}/icons/hicolor/scalable/apps"
ICON_SOURCE="${ROOT}/packaging/${APP_ID}.svg"
WITH_AI=0
DESKTOP_ONLY=0
VENV=""

die() { printf 'CarveFoundry install: %s\n' "$*" >&2; exit 1; }

while (( $# )); do
    case "$1" in
        --with-ai) WITH_AI=1; shift ;;
        --desktop-only) DESKTOP_ONLY=1; shift ;;
        --venv)
            (( $# >= 2 )) || die "--venv needs a path"
            VENV="$2"
            shift 2
            ;;
        --help|-h) usage; exit 0 ;;
        *) die "unknown option: $1 (try --help)" ;;
    esac
done

(( ! (WITH_AI && DESKTOP_ONLY) )) || die "--with-ai cannot be combined with --desktop-only"
[[ -f "$ROOT/pyproject.toml" ]] || die "run the installer from a CarveFoundry source checkout"
[[ -f "$ICON_SOURCE" ]] || die "missing desktop icon: $ICON_SOURCE"

if [[ -z "$VENV" ]]; then
    if [[ -x "$ROOT/.venv/bin/python" ]]; then
        VENV="$ROOT/.venv"
    else
        VENV="$DATA_HOME/carvefoundry/venv"
    fi
fi

if (( ! DESKTOP_ONLY )); then
    command -v python3 >/dev/null || die "Python 3.12+ is required"
    command -v cargo >/dev/null || die "Rust/Cargo is required to build the native CAM extension"
    python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' \
        || die "Python 3.12+ is required; install a newer Python and retry"

    if [[ ! -x "$VENV/bin/python" ]]; then
        printf 'Creating Python environment: %s\n' "$VENV"
        python3 -m venv "$VENV" \
            || die "unable to create venv; install your distribution's Python venv/ensurepip package"
    fi
    [[ -x "$VENV/bin/python" ]] || die "venv is missing Python: $VENV"
    "$VENV/bin/python" -m pip --version >/dev/null \
        || die "the venv has no pip; install the distribution Python pip/ensurepip package"

    if (( WITH_AI )); then
        printf 'Installing CarveFoundry and optional local AI models/dependencies...\n'
        "$VENV/bin/python" -m pip install --editable "$ROOT[ai]"
    else
        printf 'Installing CarveFoundry (preserving any AI packages already in this venv)...\n'
        "$VENV/bin/python" -m pip install --editable "$ROOT"
    fi
fi

[[ -x "$VENV/bin/carvefoundry" ]] \
    || die "CarveFoundry is not installed in $VENV (omit --desktop-only to install)"

# Resolve relative --venv paths without assuming that the user's current
# terminal directory is the project's source directory.
VENV="$(CDPATH='' cd -- "$VENV" && pwd -P)"

mkdir -p "$BIN_HOME" "$DESKTOP_HOME" "$ICON_HOME"
LAUNCHER="$BIN_HOME/carvefoundry"
DESKTOP="$DESKTOP_HOME/${APP_ID}.desktop"
ICON="$ICON_HOME/${APP_ID}.svg"

# Do not overwrite an unrelated executable in the user's own bin directory.
if [[ -e "$LAUNCHER" ]] && ! grep -Fq \
    '# Managed by CarveFoundry scripts/install-linux.sh' "$LAUNCHER"; then
    die "$LAUNCHER exists and is not a CarveFoundry-managed launcher"
fi

temp_launcher="$(mktemp "$BIN_HOME/.carvefoundry.XXXXXX")"
{
    printf '%s\n' '#!/usr/bin/env bash'
    printf '%s\n' '# Managed by CarveFoundry scripts/install-linux.sh'
    printf 'cd -- %q || exit 1\n' "$ROOT"
    printf 'exec %q "$@"\n' "$VENV/bin/carvefoundry"
} > "$temp_launcher"
chmod 0755 "$temp_launcher"
mv -f -- "$temp_launcher" "$LAUNCHER"

cp -- "$ICON_SOURCE" "$ICON"

# Freedesktop desktop-file Exec quoting uses double quotes, not shell quoting.
# The standard ~/.local/bin path is used, even when the project itself contains
# whitespace (the executable wrapper cd's to it with safe shell quoting).
desktop_exec="${LAUNCHER//\\/\\\\}"
desktop_exec="${desktop_exec//\"/\\\"}"
temp_desktop="$(mktemp "$DESKTOP_HOME/.${APP_ID}.XXXXXX")"
cat > "$temp_desktop" <<ENTRY
[Desktop Entry]
Version=1.0
Type=Application
Name=CarveFoundry
GenericName=CNC CAD and CAM
Comment=Design and machine CNC projects locally
Exec="${desktop_exec}"
TryExec=${LAUNCHER}
Icon=${APP_ID}
Terminal=false
Categories=Graphics;Engineering;
Keywords=CNC;CAM;CAD;STL;Onefinity;
StartupNotify=true
ENTRY
chmod 0644 "$temp_desktop"
mv -f -- "$temp_desktop" "$DESKTOP"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DESKTOP_HOME" >/dev/null 2>&1 || :
fi

printf '\nCarveFoundry desktop installation is ready.\n'
printf '  KDE menu: CarveFoundry\n'
printf '  Terminal: %s\n' "$LAUNCHER"
printf '  Environment: %s\n' "$VENV"
printf '  Source checkout: %s\n' "$ROOT"
printf '  Update: git pull --ff-only, then rerun this installer\n'
if (( ! WITH_AI )); then
    printf '  AI: preinstalled AI packages are retained; --with-ai installs them if needed\n'
fi
