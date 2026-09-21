# KDE Plasma / Wayland interaction acceptance

CI uses `QT_QPA_PLATFORM=offscreen` and **does not** prove that the compositor,
native `QOpenGLWindow`, physical mouse or GPU behave correctly on KDE Plasma.
Run this before declaring a viewport/UI refactor hardware-validated.

## Start on the actual Linux workstation

Launch a KDE Plasma **Wayland** graphical session and run:

```bash
cd /mnt/moar/Downloads/git/CarveFoundry
git pull --ff-only
source .venv/bin/activate
env -u QT_QPA_PLATFORM python scripts/wayland_qa.py
```

The script refuses X11/XWayland/offscreen, creates the *real* main window with
its native GL child and prints the Qt backend, GL-context validity and actual
mouse/keyboard events received from the compositor. It does not inject fake
input or consume events. A real OpenGL context must be valid and the native
window exposed before proceeding. Record your GPU/driver, KDE, Qt, Python and
display scaling in the QA report (use `inxi -G` if available).

## Physical acceptance checklist

Check every row with the real pointer and keyboard, not with QTest or scripted
`QMouseEvent` objects. Use a disposable project and a small test STL first.

| Area | Physical action | Expected result |
| --- | --- | --- |
| Window/GL | Launch, maximize, resize repeatedly, change splitter/Inspector width | No blank first frame, stale backing pixels, ghosting, crash, clipped rulers or detached native child |
| Camera | Camera tool, left-drag on stock, release, then right/middle drag | Orbit follows pointer without selection/moving objects; pan ends at mouse release |
| Zoom | Wheel up/down at edges and center; double-click canvas | Zoom is smooth, full-detail toolpath returns after motion, double-click fits; no unexpected camera shift |
| Navigation inversion | Toggle Reverse Horizontal and Invert Vertical and repeat orbit/pan | Both orbit and pan directions reverse on the requested axis; restore settings afterward |
| Selection | Choose Select; click one STL, empty space, Ctrl-click and Shift-click two STLs | Object selection, empty deselection, additive/toggle selection, Layers and Inspector remain synchronized; camera does not jump |
| Marquee | With Select, drag across two objects from an empty stock region | Multi-select and Inspector count correct; no unintended object movement |
| Gizmo | Drag X then Y translation arrow; enable snapping and local/global modes | Only intended axis changes; origin and work-coordinate labels remain consistent; undo/redo restores geometry |
| Resize | Drag XY corner handle, then modify exact Inspector Size and Position | XY dimensions match inspector; Z preserved for an XY handle; no rotation-plane swap or wrong axis |
| Keyboard | Focus native viewport; Arrow keys, Shift+Arrow, Ctrl+Arrow, PageUp/Down and Escape | Selected object nudges on documented axes/steps; Esc cancels draw/node editing without deleting completed objects |
| Drawing | Rectangle, ellipse, line, pen, polygon, text, fixture and measure tools | Contextual option bar shows only relevant fields; it disappears in Camera/Select; Inspector shows stock/object properties independently |
| AI import recovery | Generate a local AI relief STL and wait for automatic import | All rail buttons including Select re-enable; new STL appears in Layers and Inspector; Select can click and transform it |
| Stress | Import dense STL, generate very long toolpath, orbit/pan/zoom during progress | UI paints without stalls/ghosting; temporary toolpath LOD restores precise geometry after navigation; cancellation keeps project intact |
| Save/restore | Save the disposable project, reopen and inspect mesh, transforms and tool states | Data and physical dimensions persist; no stale selection or disabled tool |
| Toolpath safety | Recalculate after design change, check fixture preflight | Changed model invalidates old CAM, export remains gated by preflight; no milling movement occurs during UI tests |

## Record and report

Save a plain-text acceptance report with date, workstation/GPU/driver, KDE
Plasma, Qt/PySide6, Python, display scaling, any device errors, the script's
input-count summary, and **PASS/FAIL + actual observations for each row**.
Take screen captures of ghosting/clipping, if observed. Do not mark the pass
complete when merely the automated CI tests pass.

To run regression tests independently of physical compositor acceptance:

```bash
ruff check src tests scripts
pytest -q
cargo fmt --manifest-path rust/Cargo.toml --check
cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path rust/Cargo.toml
```
