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

The first build downloads Rust dependencies. This is an experimental native
desktop window and **does not change the existing `carvefoundry` KDE launcher**.

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
- Export of closed stock-relative SVG contours for import into the established
  CarveFoundry application. The saved Rust layout remains editable separately.

### Existing workflow and critical limits

Open the established CarveFoundry application with **Open verified CAM**.
Import the exported SVG there, review its geometry and orientation, assign
cutters, regenerate toolpaths, preview, run CNC preflight and export separate
NC files as usual. **Never treat SVG or the Rust layout JSON as G-code.**

This initial Rust UI **does not** read/write CF3D, display/edit CAM operations,
import arbitrary SVG/STL, drive a controller, calculate actual cut time, perform
inlays, merge toolpaths, store CAM templates, check clamps/fences, or verify CNC
safety. Those features require an explicit tested engine bridge rather than
silently rewriting the existing production workflow.

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
