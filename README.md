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
sudo pacman -S --needed rust cargo pkgconf libxkbcommon wayland mesa xdg-desktop-portal xdg-desktop-portal-kde
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
  src/main.rs                    Compact desktop application state and shortcuts
  src/ui/shell.rs                Menu/ribbon, workspaces, status and file dialogs
  src/ui/palette.rs              Drawing, dimension, transform and snap tools
  src/ui/inspector.rs            Object tree, precise properties and material
  src/ui/canvas.rs               Main 2D stock sheet, bounded grid, rulers and drag
  src/ui/theme.rs                Contrast, spacing and CAD UI colors
docs/ROADMAP.md                  New implementation phases and acceptance gates
docs/SAFETY.md                   Known machine-side requirements, blocked exports
docs/HANDOVER.md                 Rolling development checkpoint
.github/workflows/rust.yml       Rust CI, Clippy, Linux release compilation
```

Modules are split by ownership. Geometry and project validation have **no UI
dependency**, and the UI cannot invoke a machine exporter that does not exist.

## Native vector design workspace

The interface is organized for a drawing-first CAD workflow. The menu bar
provides File, Edit, View, Drawing and Help; the mode ribbon exposes Select
(V), Node Edit (N) and Pen (P), shape shortcuts, Undo/Redo and Fit. The left
palette groups vector creation, dimensions, transform and snap controls,
with a wide stock drawing area in the center. The right inspector separates
Objects, Properties and Material settings; the bottom line displays current
mode, pointer XY, stock dimensions and snap status.

**Files:** Use File > Open design or Save As to invoke the KDE/Wayland-native
XDG Portal chooser. Ctrl+O and Ctrl+S work in normal canvas focus. A newly
created design opens Save As on its first save and unsaved changes are
confirmed before New/Open. Old native Rust CFD files remain readable.
Historic CF3D conversion is not supported.

**Drawing:** New editable shapes include Rectangle, Circle, Ellipse,
Triangle, Pentagon, Hexagon, Octagon and Star, plus Line, Arc and cubic
Bézier paths. Click to draw points with Pen; Enter/double-click finishes
an open polyline or closed polygon. Use the object tree to select, hide
or lock individual vectors, and Properties for numeric node/handle edits.
Exact circular arc endpoints can refit without flattening geometry. Circles
and ellipses use four cubic Bézier segments as visual approximations.

**Navigation:** Mouse wheel zooms under the pointer, middle/right mouse
drag pans, F fits material. V moves whole objects, N edits anchors, P starts
a polyline. Ctrl+Z Undo, Ctrl+Y or Ctrl+Shift+Z Redo, Ctrl+D Duplicate,
Delete Remove. Snap movement is OFF by default; turning it on quantizes
movement, not the existing anchor position.

**Machining:** The Toolpaths workspace is deliberately informational, not
an NC export interface. This application does not yet generate CNC output.

Detailed UI acceptance targets and an *uncompleted* physical KDE Plasma
Wayland checklist are in [docs/UI_DESIGN.md](docs/UI_DESIGN.md).

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


### Direct shape placement

In the **Drawing** workspace select Rectangle, Circle, Ellipse, Star or
Polygon from the tool palette, top ribbon or Drawing menu. Drag a
diagonal across the stock to draw; the temporary outline and live
width/height preview appear until mouse release. **No object is added
until you release the button.** Hold Shift for equal width and height;
circles constrain to a square automatically. Press Esc or select
V/N/P to leave the shape tool. The tool remains active to draw more.

For precise predefined sizes open **Vector Dimensions** in the left
palette, set width/height and choose **Use exact size**, then click the intended lower-left
location on the stock. A ghost outline previews the shape until placed. Existing
Rust-native .cfd projects continue to open unchanged; machine toolpaths
and G-code export are still intentionally unavailable.

### Precision positioning and arranging vectors

The Drawing toolbox now includes **Precision Align & Position**.
Shift/Ctrl-click multiple vectors, then align their left/right/top/bottom
edges or horizontal/vertical centers, distribute three or more by even
center spacing, or move their shared bounding rectangle to the material
edges/center. Curves retain their exact analytic definitions.

For exact work, set **Left X** and **Bottom Y** in millimeters and click
**Set X/Y**; these are coordinates of the selected shape(s)' combined
bounding rectangle relative to the lower-left stock origin. Nothing
moves while you type. Use **Read position** to reset draft coordinates.
Arrow keys nudge by the adjustable **Step**; Shift+arrow moves ten steps.
Each accepted transform is a single Undo/Redo action. Geometry locked
against edits is never moved as part of a group.

This is still a design-only CNC CAD application. Native G-code output,
toolpath simulation and machining preflight are not implemented.


## Native SVG vector import/export (R1b)

**File -> Import SVG vectors…** adds supported SVG path outlines to the
current design in one Undo operation. **File -> Export vectors as SVG…**
writes editable line/arc/Bézier sources as SVG artwork, not G-code.
Unsupported transforms, elliptical arcs and text are rejected explicitly.
See [SVG interoperability and acceptance](docs/SVG_INTERCHANGE.md).

## Native DXF vector interchange (R1c)

In the native Rust File menu, **Import DXF vectors…** and
**Export vectors as DXF…** exchange editable 2D outlines in millimetres.
Supported types include LINE, ARC/CIRCLE, LWPOLYLINE with exact bulges,
and simple non-rational cubic SPLINE. Unsupported entity types reject
the entire import. DXF is artwork, not CNC instructions.
See [DXF compatibility and verification](docs/DXF_INTERCHANGE.md).

## Native system-font text (R1d)

Drawing -> Vector text… opens the installed font family and variant picker.
Choose Unicode text, em size, tracking and an XY baseline to create **true
editable vector outlines**, not raster or font preview geometry. Select a
glyph outline and choose Properties -> Edit text source… to regenerate all
outlines from the saved text settings in one undoable transaction. The .cfd
keeps text metadata and curves; missing system fonts prevent reflow but
not viewing existing paths. Individual node edits are allowed, but a later
text reflow replaces those glyph contours. See docs/TEXT_AUTHORING.md.
