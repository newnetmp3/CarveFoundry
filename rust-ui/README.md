# CarveFoundry Studio — Rust-native design and sheet layout

This is the **first native Rust UI migration slice**, not yet a replacement for
the established Python CNC/CAM workspace. Its purpose is to ship a functional,
independently testable Rust CAD surface while preserving the original
machine-safety checks.

## Run on Arch Linux / KDE Plasma Wayland

```bash
sudo pacman -S --needed rust cargo pkgconf libxkbcommon wayland libglvnd
cd /mnt/moar/Downloads/git/CarveFoundry
bash scripts/run-rust-studio.sh
```

The first build downloads Rust dependencies. To install an **additional KDE
application-menu entry** (without replacing your regular CNC application),
run:

```bash
bash scripts/install-rust-studio.sh
~/.local/bin/carvefoundry-studio
```

Look for **CarveFoundry Studio (Rust Preview)** in the KDE launcher. Your
existing `carvefoundry` launcher remains unchanged. The installer rebuilds
the Rust binary in release mode and configures the matching project's Python
environment solely for read-only CF3D inspection.

The merged CAM-status addition provides **Inspect CAM (read-only)**
from the top toolbar. It reports saved operation identities, cutter types,
stale/missing motion and disabled stages; no CNC output or preflight is exposed.
This is informational only and runs on a worker thread.

The next experimental production tool lets you choose a saved CAM stage and
**export settings as JSON**, then apply those settings to a matching operation
in another existing CF3D. It accepts only the same operation strategy, exact
cutter geometry and parameter names/types. Both actions require a current
source SHA-256. Applying settings creates a **new CF3D**; all previous
toolpaths are deleted and all machining operations marked stale. This is
not compatible with arbitrary cutters, does not create additional machining
operations, and still requires generation and CNC preflight in the established
application.

## Working tools in this slice

- Editable vector shapes: rectangle, ellipse, polygon and star.
- Mouse selection/drag, exact X/Y and 90-degree rotation, duplicate and remove.
- Undo/redo, and versioned **Rust layout JSON** files (not CF3D).
- Deterministic **polygon-aware first-fit sheet placement**, tested with concave
  contours, four right-angle rotations, gap and stock-edge margin.
  This does **not** claim a mathematically optimal true-shape nesting algorithm.
  The step size trades speed for packing density. The packer is synchronous in
  this first slice, so large sheets with fine grid spacing can temporarily
  stall the Rust UI.
- Rectangular array copy with stock and polygon collision validation.
- **Multi-sheet production layout preview:** background-worker polygon-aware
  first-fit packing across up to 32 identical stock sheets, fixed edge margins,
  cutter-outline clearance and optional 90-degree rotation. Inspection provides
  per-sheet part lists, nominal area utilization, versioned plan JSON and
  separate SVG output for each sheet (`<prefix>-sheet-01.svg`, etc.).
  The plan JSON can be reopened in the Rust Studio with **Open saved plan
(read-only)**, after strict version, shape, clearance and count validation.
Invalid files leave the current source and preview unchanged. The plan remains
separate from the original editable CF3D and Rust source layout.
The original editable design stays unchanged. A failure to fit any part
  within the chosen sheet limit returns an error without partial results.
  The planner limits sampling density; it is a heuristic and does not account
  for material thickness, grain vectors beyond rotation locking, physical
  clamps, cutting tabs, real cutter kerf or machine travel. Each SVG must be
  imported and separately preflighted in the original CAM app.
- Export of closed stock-relative SVG contours for import into the established
  CarveFoundry application. The saved Rust layout remains editable separately.
- **Guarded vector XY placement to NEW CF3D:** after importing a source CF3D,
  move eligible retained vectors and use **Save XY placements as NEW CF3D**
  in Job Setup. The Rust UI checks original source SHA-256 and UUIDs and
  refuses if objects, outlines, names, stock dimensions or rotations changed.
  The Python engine revalidates source hash, object locks and requested XY
  translations, and writes a distinct new native CF3D without overwriting
  the original. All generated machine toolpaths are removed and all stored
  CAM operations marked stale. Open the new CF3D in the original CNC
  application, regenerate toolpaths, preview and run fixture-aware preflight
  before exporting anything. Do NOT expect native CF3D topology/3D edits.
- **Read-only existing CF3D import** using the original trusted Python serializer:
  supply the existing project path in the top toolbar and choose **Import
  vectors (read-only)**. The new Rust layout contains only eligible closed
  retained planar vector outlines and stock dimensions; curves are sampled.
  Unsupported imported 3D meshes, open/nonplanar paths and untransferred
  objects are counted, not converted or overwritten. The original project
  never changes when importing or editing this snapshot.

### Existing workflow and critical limits

Open the established CarveFoundry application with **Open verified CAM**.
Import the exported SVG there, review its geometry and orientation, assign
cutters, regenerate toolpaths, preview, run CNC preflight and export separate
NC files as usual. **Never treat SVG or the Rust layout JSON as G-code.**

The Rust UI only creates **new CF3D files for strictly guarded XY placement**.
It still does not write vector topology, display/edit CAM operations,
import arbitrary SVG/STL, drive a controller, calculate actual cut time, perform
inlays, merge toolpaths, store CAM templates, check clamps/fences, or verify CNC
safety. The read-only snapshot service exports no fixtures, cutters, CAM stages
or project history, and must **never** be treated as a full CF3D roundtrip.
Those features require an explicit tested engine bridge rather than silently
rewriting the existing production workflow.

### Why this architecture

The Rust front end uses `eframe`/`egui`, which is a direct native desktop
interface with Linux Wayland support. It lives in `rust-ui/`, separate from
the existing PyO3 numerical crate at `rust/` and the mature PySide6 app.
This enables migration by working end-to-end slices rather than an
all-at-once rewrite that would strand existing CAM functionality.

```bash
cargo test --manifest-path rust-ui/Cargo.toml
cargo clippy --manifest-path rust-ui/Cargo.toml --all-targets -- -D warnings
cargo build --manifest-path rust-ui/Cargo.toml --release
```

The `Native Rust Studio` GitHub Actions workflow runs on changes to this tree.
Tests and compilation on GitHub are not a physical KDE Wayland verification.
