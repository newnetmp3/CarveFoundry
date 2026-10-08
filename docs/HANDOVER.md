# CarveFoundry — rolling development handover

> **Canonical continuity record.** Read this document and [ROADMAP.md](ROADMAP.md) at the start of every new development chat. This file records verified state, active work, and next actions; it is not a claim that unmerged code is released.

## How to resume

1. Fetch `main`, this file, `docs/ROADMAP.md`, and the latest open pull requests from GitHub. Never assume a previous chat's head SHA is current.
2. Verify whether the active PR below is still open, merged, or superseded; read its latest CI jobs and logs.
3. Resume the earliest unfinished checkpoint. Make changes on a feature branch; preserve working CNC safety behavior.
4. **Update this file in the same branch/PR whenever a meaningful step is completed.** Record exact PR/commit, tests actually run and outcomes, blockers, remaining items, and next action. Once CI passes and the PR merges, update the merged baseline and remove stale active-PR statements in the next PR.
5. Update `ROADMAP.md` in that same PR when a capability transitions from proposed to implemented. Do not mark UI controls, algorithms, or machine output as working until integrated and validated.
6. Before ending a development chat, write a concise checkpoint below including the exact GitHub links and the first action for the next chat.

**Terminology:** The project is CarveFoundry, an open-source CNC CAD/CAM application. Use vendor-neutral feature names, including generic *V-Carving* for the machining operation. Do not use third-party product branding in project identifiers, features, or UI labels.

## Verified merged baseline

- Repository: [newnetmp3/CarveFoundry](https://github.com/newnetmp3/CarveFoundry)
- Primary branch: `main`
- Last verified merged feature baseline: `8dda2b6bd12e2513496e9726a44903df20f34337` (PR #86).
- [PR #61](https://github.com/newnetmp3/CarveFoundry/pull/61): retained analytic line, circular arc and cubic Bézier path foundation, native persistence, direct planar CAM use, basic vector snapping.
- [PR #62](https://github.com/newnetmp3/CarveFoundry/pull/62): close/open/split/join topology editing, analytic segment preservation, persistent CAM source UUID retargeting, Undo/Redo.
- The previous #62 validation reported Python 3.12 and 3.14 at **475 passed, 27 warnings**, plus green Ruff, Python compile, Rust formatting/Clippy/tests, installation-script syntax, and CarveWork tests. These results belong to #62, **not** to current development.
- Existing retained machining operations, preflight, GRBL-style separated cutter stages, sampled removal preview, and double-sided project preparation are documented in [ROADMAP.md](ROADMAP.md). Do not present them as machine-tested guarantees.
- Approximate historical roadmap assessment: native CAD ~50%, object-aware CAM ~85–90%, core router workflow ~82–85%, entire ten-part vision ~55%. These are subjective estimates, not measured acceptance coverage.

## Verified Rust-native UI replacement foundation (PR #84–#86)

- [PR #84](https://github.com/newnetmp3/CarveFoundry/pull/84) merged `a6913e454dd3166a2d06fdea735ee762d4828ca7`: separate Rust `eframe/egui` native Linux 2D design window; editable shape primitives, selection/drag, 90° rotation, undo/redo, polygon-aware heuristic first-fit nesting, array copies, JSON layout and SVG vector exchange. GitHub Actions native Rust run `37826501535` (unit tests, strict Clippy and release build) and Python run `37826501458` passed.
- [PR #85](https://github.com/newnetmp3/CarveFoundry/pull/85) merged `8e0ebbe833fc22bbdad523f3648f44200b46a498`: source-preserving Python CF3D snapshot bridge for eligible closed planar retained vectors + stock size. Curves are sampled and unsupported objects counted, all CAM/fixture state excluded. Python CI `37826657668` passed on 3.12 and 3.14.
- [PR #86](https://github.com/newnetmp3/CarveFoundry/pull/86) merged `8dda2b6bd12e2513496e9726a44903df20f34337`: Rust window reads snapshot via **Import vectors (read-only)** and matching Python environment; an independent `scripts/install-rust-studio.sh` release-build/KDE launcher installs `~/.local/bin/carvefoundry-studio` without touching original `~/.local/bin/carvefoundry`. Read-only JSON schema test and both shell script syntax checks. Native Rust CI run `37827491088` passed tests, strict Clippy, release build and shell; Python CI run `37827491149` passed both lanes.
- The experimental Rust Studio currently **does not** save CF3D, preserve CAM operations/toolpaths/fixtures through snapshot import, perform 3D mesh edits, offer inlay/toolpath templates/vector textures, export CNC programs or replace trusted preflight. It is a separate *layout editor*, not a safety-equivalent replacement for the original PySide6 CAM program. Original CF3D is not modified by snapshot import. Source files remain at `rust-ui/`, `docs/RUST_UI_GAP_PLAN.md`.
- Real KDE Plasma Wayland interactions and actual CNC machine operations remain unverified, despite automated Linux release builds passing. No measured native Rust UI performance or production stock-saving claim.

### Next checkpoints — functional replacement, not cosmetic

- [ ] Build and validate a typed, transactional read/write CF3D engine bridge with source UUIDs, project save/reload, Undo/Redo, active CAM invalidation and fixture/preflight roundtrip. Do not change default launcher until safe.
- [ ] Ship more missing production tools on the Rust side: multi-sheet/grain-aware nesting, saved cutter-compatible toolpath templates, inlay cavity/plug pairing, texture-generation editor and batch workflows, each with real engine integration and tests.
- [ ] Integrate existing 3D scene and preview, cutters, machine profile, simulation and verified G-code/preflight workflow in the Rust desktop shell.
- [ ] Test both `~/.local/bin/carvefoundry` and `~/.local/bin/carvefoundry-studio` on physical KDE Wayland workstation; inspect source CF3D bytes before/after read-only import.
- [ ] Keep project branding vendor-neutral; preserve bottom-left XY0/top Z0, fixture collision safety, tool radius keep-outs, separate cutter NC files/Z re-probe, stale-export fail closed.

### Known boundaries and safety invariants

- Stock bottom-left is the default work XY0; Z0 is the top of stock unless the project explicitly changes it.
- Fixture/fence keep-outs and tool-radius clearance must remain in preflight.
- Keep distinct NC files for physical cutter stages; manual cutter swaps require Z re-probing.
- Preview/export must fail closed if enabled machining intent is stale or missing motion.
- Offline preflight cannot confirm actual machine work offsets, unknown clamps, holder collisions or controller state.

## Append-only checkpoint log

Use entries in this format; keep older material for continuity but correct stale status summaries above.

| Date (UTC) | Change | Evidence / CI | Next action |
| --- | --- | --- | --- |
| 2026-10-08 | #62 merged; vector topology editing baseline | `main` `2360d2e`; previously 475 tests in both Python lanes | Interactive CAD editing |
| 2026-10-08 | #63 control-edit core and regression tests | Commits `fbe8055`, `d750717`, `01dd829` | Check CI |
| 2026-10-08 | Found CI lint failure and corrected test import order | Failed run `37793498674`; fix `709d56b`; new CI not yet verified | Verify latest CI, continue viewport handles |
| 2026-10-08 | Established rolling handover document | This file on PR #63 branch | Keep updating this document with each delivered step |
| 2026-10-08 | PR #63 passed both CI lanes and merged to main | Run `37798718397`; merge `4964e3a` | Viewport interaction |
| 2026-10-08 | Added Bézier viewport control drawing, picking and drag wiring | Branch `feature/bezier-viewport-handles`; tests and CI pending | Add UI regressions and validate |
| 2026-10-08 | Opened PR #64 and added initial offscreen UI regression | CI run `37800820946` queued; no pass claimed | Inspect CI, fix failures and expand tests |
| 2026-10-08 | PR #64 CI passed both Python lanes; roadmap synchronized | Run `37800878113` success; final docs head CI pending | Verify final CI and merge |
| 2026-10-08 | PR #64 merged; grid snapping started | Merge `b4edac44`; branch `feature/vector-grid-snapping` | Validate grid snap PR |
| 2026-10-08 | Added parallel gradual Rust conversion plan while continuing feature milestones | `docs/gradual-rust-migration-roadmap`; roadmap only, no runtime conversion | Validate docs PR and resume #66 |
| 2026-10-08 | Reconciled green PR #66 implementation with merged PR #67 Rust-roadmap docs | Original #66 merge conflict; new branch based on `fb6ea1e` | Validate replacement PR CI |
| 2026-10-08 | Merged PR #68 after green CI; added tangent/normal direction snap primitive and tests | Main `583d853`; new branch `feature/vector-orthogonal-snap-core` | Open PR and validate CI |
| 2026-10-08 | Merged PR #69 and started Shift-constrained Bézier drag | Main `a799d32`; branch `feature/bezier-angle-constraint`; CI pending | Validate interaction PR |
| 2026-10-08 | PR #70 merged with green CI; implemented configurable angular handle constraint and visual indicator | Merge `66450ec`; branch `feature/angle-constraint-ui-feedback` | Validate UI PR and integrate derivative snapping |
| 2026-10-08 | PR #71 merged after green CI; added Python/Rust raster benchmark infrastructure and regression tests | Main `5fc460f`; branch `feature/native-raster-parity-baseline`; CI pending | Validate benchmark PR and collect representative measurements |
| 2026-10-08 | PR #72 benchmark/parity infrastructure merged after both CI lanes passed; adjacent tangent/normal handle constraints implemented on fresh branch | Merge `c89b587`; branch `feature/adjacent-tangent-normal-handle-drag` | Open PR, validate CI, review GUI interaction |
| 2026-10-08 | PR #73 modifier-driven cubic tangent/normal alignment merged; rolling batch handover finalized | Run `37809732554` green both Python lanes; feature merge `d842c072` | Live snap indicators and trim/extend; expand Rust parity benchmarking |
| 2026-10-08 | Began exact line/arc/Bézier open endpoint trim with Direct Selection UI and tests | Branch `feature/analytic-endpoint-trim`; CI pending | Open PR, validate, merge only when green |
| 2026-10-08 | PR #74 opened; added CF3D/history trim regression and verified latest CI run queued | Commit `d631bb4`; run `37812647174` pending | Review results and merge only when green |
| 2026-10-08 | PR #74 merged after green CI; added strictly validated straight endpoint extension and Direct Selection integration | Main `8885f24`; branch `feature/analytic-line-endpoint-extension`; CI unverified | Validate follow-on PR |
| 2026-10-08 | Opened PR #75 and added UI extension regression | Latest UI test commit `a907676`; final CI pending | Verify final CI; merge only when green |
| 2026-10-08 | PR #75 merged after green CI, finite target line-segment fitting core started | Merge `e1aa01c`; new `feature/vector-line-intersection-geometry` | Validate geometry PR and design world-space editor integration |
| 2026-10-08 | PR #76 merged green; interactive finite-line trim/extend UI added on new branch | Merge `e99e328`; CI pending on `feature/interactive-line-fit` | Validate UI and merge only if green |
| 2026-10-08 | PR #77 merged after green CI; bounded open-line chamfer implemented with UI/tests | Main `f0319ed`; feature `feature/analytic-line-chamfer`, CI pending | Validate and merge chamfer PR |
| 2026-10-08 | PR #78 chamfer merged green, analytic line fillet with UI and tests implemented | Main `1874f49`; branch `feature/analytic-line-fillet` | Validate PR CI before merge |
| 2026-10-08 | Merged PR #79 after both Python CI lanes passed; interactive line-corner fillet completes three-PR CAD batch | Run `37819700239` success; merge `9930cef` | Live geometric indicators, safe closed-contour corners, Rust parity expansion |
| 2026-10-08 | Implemented closed-contour chamfer/fillet for wrapped seam and interior nodes | Branch `feature/closed-vector-corner-editing`; CI pending | Validate and merge if green |
| 2026-10-08 | PR #80 merged green and expanded native raster parity to sparse/overlap fixtures | Main `158c3d2`, branch `feature/native-raster-scene-parity` pending CI | Validate and merge fixture benchmark PR |
| 2026-10-08 | PR #81 native raster parity scene expansion passed both CI lanes and merged | Run `37821725814` green, merge `85aa914` | Inspector organization, live snap feedback and cutter-contact parity |
| 2026-10-08 | Grouped Direct Selection controls into five persistent scrollable tabs, with regression tests | Branch `feature/direct-selection-tabbed-inspector`, CI unverified | Validate PR, merge if green, then live snap indicators |
| 2026-10-08 | PR #82 merged green; new cutter-contact Python/Rust parity benchmark and tests staged on fresh main base | Merge `d0d2390`; branch `feature/native-contact-parity-rebased` pending CI | Validate and merge parity diagnostic |
| 2026-10-08 | PR #83 cutter-contact parity diagnostic merged with both Python lanes green after PR #82 tabbed inspector merge | Run `37823171975` success; feature merge `8375833` | Native live snap feedback and stock-sweep parity |
| 2026-10-08 | Began Rust-native egui desktop workspace replacing UI in verified slices; polygon-aware first-fit layout and arrays, JSON/SVG interchange | Branch `feature/rust-native-layout-studio`; CI unverified | Verify native Cargo CI, then bridge CF3D engine |
| 2026-10-08 | PR #84 Rust Studio and #85 read-only CF3D snapshot merged green; native Rust preview CF3D import and secondary KDE launcher implemented | Branch `feature/rust-ui-cf3d-import-and-kde`; CI unverified | Open PR, validate Cargo + Python CI, merge green only |
| 2026-10-08 | Rust GUI CF3D read-only import and independent KDE installer merged in #86 after native Rust and Python CI green | Run `37827491088` Rust, `37827491149` Python; merge `8dda2b6` | Full CF3D transactional editor bridge and missing production tools |
