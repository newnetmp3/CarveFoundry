# CarveFoundry — Rust reboot

**New, native Rust CAD/CAM architecture.** This is a fresh implementation, not
a wrapper, translation or UI adapter around the previous Python application.

**Current milestone: 2D design foundation and experimental retained analytic paths.** It has a real Rust project file,
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

**The fresh Rust implementation is now the `main` branch** (PR #99, checked with Rust CI). The old application is archived at
[`archive/python-ui-2026-10`](https://github.com/newnetmp3/CarveFoundry/tree/archive/python-ui-2026-10).
**Legacy `.cf3d` files are NOT yet supported.** The new versioned `.cfd`
file format is JSON and belongs solely to the Rust implementation. Do not
rename .cf3d files to .cfd.

## Run on Arch Linux / KDE Plasma / Wayland

Install the native toolchain and system OpenGL/Wayland libraries:

```bash
sudo pacman -S --needed rust cargo pkgconf libxkbcommon wayland mesa
git clone https://github.com/newnetmp3/CarveFoundry.git
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

Use **Add rectangle** to create a closed contour or create a retained **Line**, **Circular arc** or **Cubic Bézier** path. Choose **Move objects** to drag whole shapes or **Edit nodes** to drag individual analytic anchors and cubic handles. Click to select objects, drag to
position it, or edit X/Y numerically. Locked contours cannot move or delete.
Undo/Redo records each drag as one history action. The Inspector exposes numeric node and cubic-handle coordinates, midpoint insertion into straight edges, lossless line-node deletion, open/close, and path locking. Arc anchors currently refuse individual translation until proper circular constraints are available. Arcs and Béziers are serialized analytically in `.cfd`, not as sampled polylines. `.cfd` v1 from the original Rust reboot still loads; machining remains disabled. Save/Open a project using
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

## Practical Rust CAD editor controls (usability recovery)

The Rust app now offers **editable analytic rectangles, circles, ellipses,
triangles, pentagons, hexagons, octagons and stars**, an interactive
polyline/polygon Pen, straight paths, circular arcs and cubic Bézier paths.
These are all stored as editable vector paths with stable nodes rather than
noneditable legacy contour samples. Circles and ellipses currently use four
cubic Bézier segments (a curve approximation, not mathematically exact
circle primitives).

- **V** selects/moves objects; **N** directly selects and drags any visible
  anchor or Bézier control (no initial click to select the parent needed).
- **P** draws a line/polyline by clicking on the canvas; check **Close outline**
  for polygons; **Enter** or double-click to finish; **Escape** cancels.
- **Mouse wheel** zooms around the pointer, **middle/right drag** pans;
  **F** or **Fit** resets the camera.
- **Ctrl+Z**, **Ctrl+Y** or **Ctrl+Shift+Z**, **Ctrl+D**, **Delete**:
  Undo, Redo, Duplicate, Delete selected. Escape cancels an active drag.
- In the left design toolbar: duplicate, flip horizontally/vertically,
  rotate 90° in either direction, align object to stock center X/Y,
  hide/show. All validated edits are Undo/Redo actions.
- **Grid snapping is OFF by default.** Turning it on snaps *movement
  displacement*, not the existing position, so a node cannot jump on
  mouse-down. Pointer target selection is based on original press position,
  not the position after crossing the drag threshold.
- Arc endpoints now adjust via **exact circular geometry refits** that
  preserve signed sweep, and Bézier anchor movement preserves adjacent
  control-handle offsets.

### Known restrictions

The UI is still design-only. Node insertion/deletion on analytic curved
segments requires topology-preserving algorithms that are not implemented
yet; this version only inserts/deletes nodes on eligible straight segments.
Text, SVG/DXF, tool libraries, 3D, CAM and NC export are not implemented.
See `docs/UX_SMOKE.md` for manual KDE Plasma/Wayland tests. A green CI
does NOT substitute for testing pointer behaviors on your actual display.
