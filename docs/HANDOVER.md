# CarveFoundry — rolling Rust reboot handover

## Canonical continuity

At the start of every development chat, read this file, `docs/ROADMAP.md`
and live GitHub branch status. Work from the latest verified source, not from
a prior conversation's assumptions. Update this handover after each meaningful
milestone; CI results must be linked and attributed to the exact commit.

## Reboot decision — October 8, 2026

The owner explicitly requested starting CarveFoundry over from scratch in
**Rust**, instead of continuing the gradual Python-UI replacement.
- Archived previous full Python/PySide6 application:
  `archive/python-ui-2026-10` at historical main commit
  `e5d51de90358e54eea0431841339acb68c71d411`.
- Closed superseded unified-bridge PR #98 without merging.
- New clean Rust source tree in branch `rust-reboot`.
- **No Python dependency** anywhere in the new Cargo workspace.
- This is not a promise of old .cf3d file compatibility, or complete
  CAM parity; it is a fresh application, with new .cfd files.
- Old unrelated open PRs #32 and #33 refer to the archived Python GUI;
  do NOT merge them into the reboot. They were not changed in this reboot.

## Baseline R0 — implemented pending verification

- `crates/core/src/geometry.rs`: finite closed polygons, crossing/touching
  checks, point selection.
- `crates/core/src/project.rs`: typed versioned native .cfd design,
  stock XY and thickness, stock-relative fixtures, stable vector IDs,
  bounded JSON files, same-directory atomic staging on save. Legacy CF3D
  is not interpreted.
- `crates/core/src/editor.rs`: validated typed edit actions, contour
  creation/position/lock/remove, stock and fixture changes, one-action
  Undo/Redo and atomic drag cancel.
- `apps/studio/src/main.rs`: native egui desktop, 2D work canvas, zoom,
  visual fence bounds, create/move/select/lock/delete rectangles, property
  editing, stock and fixture inventory and file open/save. **NO CAM.**
- `.github/workflows/rust.yml`: native Rust tests, Clippy, release compile
  and file-format/geometry safety gates.

**First thing to do next:** inspect live CI, fix compile/Clippy failures,
record successful run and merge/promote the clean reboot only when green.
Then begin R1 first-class analytic vector geometry and editing. Do not
spend time porting Python UI wiring.

## Safety-critical invariant summary

Stock lower-left XY0, top-of-stock Z0. Fixture top Z stored relative to
stock top; fence bed height minus material thickness for external hardware.
Manual tool changes require separate NC programs and fresh Z probe.
No CNC export exists; physical Wayland/Onefinity tests remain outstanding.

## Append-only checkpoints

| Date | Work | Verification | Next |
|---|---|---|---|
| 2026-10-08 | Preserve old application; create clean pure Rust workspace with R0 geometry, design editor, file schema and UI | CI pending | Validate full Linux build, record commit, proceed R1 |
