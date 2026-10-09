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

## Verified R1a — retained Rust analytic geometry and direct editing

- [PR #101](https://github.com/newnetmp3/CarveFoundry/pull/101)
  merged to main as **`49a58bf3b0270af52ac526ec05f65e3e2ad50010`**.
  Exact merged-feature head `6511f900bf5b6aadfe67290c4fe059e601aaa9d1`
  passed [Rust Reboot CI `37867505729`](https://github.com/newnetmp3/CarveFoundry/actions/runs/37867505729):
  **26 Rust tests, strict Clippy, native Linux release compilation**.
- New `crates/core/src/path.rs` retains native Line / center-radius Arc /
  Cubic Bézier source data with permanent node and segment identities,
  finite coordinate/radius validation and bounded preview-only sampling.
  No analytic arc/cubic is silently replaced with a sampled polygon.
- `Project.paths` is an optional property in Rust-native `.cfd` schema v1.
  Old reboot projects deserialize unchanged. Global object IDs are validated
  across legacy polygon contours and analytic paths.
- Typed `Editor` commands: create line/arc/cubic, translate path, exact node
  / Bézier handle movements, split straight edges, remove line-only junctions,
  open/close paths, lock/remove, 64-step Undo/Redo and one-Undo drag sessions.
- Native egui has separate Object and Node modes with analytic path stroke,
  visible node/control handles, numeric editing and topology actions.
  Invalid operations roll back. Arc anchor mutations reject until circular
  constraints preserve true radius and center.
- **Not complete R1**: automatic node snapping, handle constraint tools,
  analytic trim/join/chamfer/fillet, SVG/DXF, fonts/text, grouping and layers
  remain. No 3D, CAM, toolpaths, fixture-aware preflight or NC export.
  Physical KDE Plasma/Wayland and Onefinity tests remain unverified.

**Next engineering batch — R1b:** implement source-preserving SVG vector
interchange, robust nearest-feature snapping, smooth-curve controls and
dedicated analytic path selection. Keep zero Python dependencies and validate
backwards `.cfd` compatibility. Deliver in meaningful, green-CI PRs,
update this rolling handover after each merge, then run real KDE Wayland
interaction QA. DO NOT migrate or reintroduce PySide6.

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

| 2026-10-08 | Implemented Rust R1a retained lines/arcs/cubics and direct node/handle editing, schema-compatible CFD persistence, strict undoable operations | `feature/rust-r1-analytic-vectors`, native CI pending | Verify green Rust CI, merge then update verified handover; next curve constraints and SVG/DXF |

| 2026-10-08 | PR #101 R1a retained analytic curves and native direct node/handle editing merged to main | [Rust CI `37867505729`](https://github.com/newnetmp3/CarveFoundry/actions/runs/37867505729): 26 tests, strict Clippy, native Linux release; main `49a58bf3` | R1b analytic SVG interchange/snapping/curves and physical KDE Wayland QA |
