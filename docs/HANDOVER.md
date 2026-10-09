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

## Verified baseline R0 — merged on main

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

**Validated source state:**
- [PR #99](https://github.com/newnetmp3/CarveFoundry/pull/99) clean Rust
  reboot merged to `main` as `909ae2a4eef989515cb93d66cf9de41f4709f0f3`.
- Exact feature head `916cffe80dd8f1860aa7f4c3552f529eab3db310`
  passed [Rust Reboot CI `37862945581`](https://github.com/newnetmp3/CarveFoundry/actions/runs/37862945581):
  10 Rust core tests, strict Clippy and Linux native release build passed.
  Failed earlier CI runs were lint-only and repaired before this green run.
- `main` now contains only 15 Rust workspace, docs, GitHub CI and launcher
  files. No Python, PySide6, old CF3D conversion, old UI or old CI remains
  in its working tree.
- Superseded PR #98 and old Python-only PRs #32/#33 were closed with
  explanatory comments. All remain in Git history; no features were
  merged from them into the reboot.
- **CNC and physical QA are NOT validated.** Design-only `.cfd`
  projects do not interoperate with legacy `.cf3d`; no safe NC export,
  preflight or CAM engine is installed.

**Next engineering batch:** R1 first-class *analytic* vector data
(line, circular arc, cubic Bézier), persistent IDs and exact/finite
curve tessellation. Integrate selection/editing in a dedicated mode,
with new-file schema roundtrip and Undo/Redo. Separate object drags
from individual node handles. Keep R0 workflows intact and gate merges
on Rust tests, strict Clippy and native Linux release CI.
Avoid translating the old Python UI or importing unverified G-code.

**Physical test gate:** launch on KDE Plasma Wayland and exercise
select/drag, Undo/Redo and file roundtrip. Perform actual Onefinity
scrap testing only after CNC stages, posted preflight, fixture
verification and tool-change probing are implemented.

## Safety-critical invariant summary

Stock lower-left XY0, top-of-stock Z0. Fixture top Z stored relative to
stock top; fence bed height minus material thickness for external hardware.
Manual tool changes require separate NC programs and fresh Z probe.
No CNC export exists; physical Wayland/Onefinity tests remain outstanding.

## Append-only checkpoints

| Date | Work | Verification | Next |
|---|---|---|---|
| 2026-10-08 | Preserve old application; create clean pure Rust workspace with R0 geometry, design editor, file schema and UI | CI pending | Validate full Linux build, record commit, proceed R1 |

| 2026-10-08 | Pure Rust reboot merged to main via PR #99; Python GUI archived, incompatible legacy PRs closed | Rust `37862945581` green: 10 tests/Clippy/Linux release; main `909ae2a4` | R1 analytic vectors; KDE Wayland UI QA; no CNC until R6 |
