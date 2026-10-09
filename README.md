# CarveFoundry — Rust reboot

**New, native Rust CAD/CAM architecture.** This is a fresh implementation, not
a wrapper, translation or UI adapter around the previous Python application.

**Current milestone: 2D design foundation.** It has a real Rust project file,
finite polygon geometry and validation, drag-and-drop layout, undoable changes,
stock setup, visual fixture inventory, and a dark native desktop workspace.

**No CAM, simulation, machine preflight, G-code or CNC controller output yet.**
The current GUI is intentionally not suitable for cutting real material.

## Why a clean reboot?

The former Python UI and Python/Rust bridge became two partially overlapping
applications. This branch discards that app architecture and keeps only the
engineering lessons: explicit source identity, stock-bottom-left XY0, stock-top
Z0, fixture/fence height relative to stock, one tool per NC stage, careful
manual re-probing, stable projects, undo/redo, and fail-closed export gating.

The old application is archived at
[`archive/python-ui-2026-10`](https://github.com/newnetmp3/CarveFoundry/tree/archive/python-ui-2026-10).
**Legacy `.cf3d` files are NOT yet supported.** The new versioned `.cfd`
file format is JSON and belongs solely to the Rust implementation. Do not
rename .cf3d files to .cfd.

## Run on Arch Linux / KDE Plasma / Wayland

Install the native toolchain and system OpenGL/Wayland libraries:

```bash
sudo pacman -S --needed rust cargo pkgconf libxkbcommon wayland mesa
git clone --branch rust-reboot https://github.com/newnetmp3/CarveFoundry.git
cd CarveFoundry
cargo run -p carvefoundry-studio --release
```

Or run `bash scripts/run-linux.sh`. No Python interpreter, PySide6, maturin
or Python CAM installation is required. Window/display behavior still needs
human testing on the target KDE Plasma/Wayland system.

## Architecture

```text
Cargo.toml                       Rust workspace
crates/core/                     Pure Rust versioned project + geometry + editor
  src/project.rs                 Stock, contours, fixtures, .cfd persistence
  src/geometry.rs                Finite closed-polygon validation and hit testing
  src/editor.rs                  Validated commands, drag transaction, Undo/Redo
apps/studio/                     Native eframe/egui UI
  src/main.rs                    Canvas, panels, stock/fixture/contour editing
docs/ROADMAP.md                  New implementation phases and acceptance gates
docs/SAFETY.md                   Known machine-side requirements, blocked exports
docs/HANDOVER.md                 Rolling development checkpoint
.github/workflows/rust.yml       Rust CI, Clippy, Linux release compilation
```

Modules are split by ownership. Geometry and project validation have **no UI
dependency**, and the UI cannot invoke a machine exporter that does not exist.

## Design controls

Use **Add rectangle** to create a closed contour, click to select it, drag to
position it, or edit X/Y numerically. Locked contours cannot move or delete.
Undo/Redo records each drag as one history action. Save/Open a project using
a typed `.cfd` path in the toolbar. Stock dimensions and basic fixture
inventory live in the Inspector. Sample left-fence dimensions are an example
only and require measurement before any machining capability is added.

## Core testing

```bash
cargo fmt --all
cargo test --workspace
cargo clippy --workspace --all-targets -- -D warnings
cargo build --release -p carvefoundry-studio
```

The work is only considered a production CNC replacement after the new engine
passes all acceptance gates in `docs/ROADMAP.md`, especially verified
toolpath decoding, collision/preflight gating, physical test cuts and KDE
Wayland acceptance.
