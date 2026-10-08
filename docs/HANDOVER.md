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
- Last verified merged feature baseline: `8375833b85231309d194a8af48bd6e7c2a5bc1ca` (PR #83).
- [PR #61](https://github.com/newnetmp3/CarveFoundry/pull/61): retained analytic line, circular arc and cubic Bézier path foundation, native persistence, direct planar CAM use, basic vector snapping.
- [PR #62](https://github.com/newnetmp3/CarveFoundry/pull/62): close/open/split/join topology editing, analytic segment preservation, persistent CAM source UUID retargeting, Undo/Redo.
- The previous #62 validation reported Python 3.12 and 3.14 at **475 passed, 27 warnings**, plus green Ruff, Python compile, Rust formatting/Clippy/tests, installation-script syntax, and CarveWork tests. These results belong to #62, **not** to current development.
- Existing retained machining operations, preflight, GRBL-style separated cutter stages, sampled removal preview, and double-sided project preparation are documented in [ROADMAP.md](ROADMAP.md). Do not present them as machine-tested guarantees.
- Approximate historical roadmap assessment: native CAD ~50%, object-aware CAM ~85–90%, core router workflow ~82–85%, entire ten-part vision ~55%. These are subjective estimates, not measured acceptance coverage.

## Active — native Rust UI migration and production capability gaps

- Verified baseline: latest main feature PR #83 merged `8375833b85231309d194a8af48bd6e7c2a5bc1ca`, main docs `63e12fed02f3590aa848c031be5a28748131f6a0`. Python 3.12/3.14 CI green.
- Active branch `feature/rust-native-layout-studio` (initial new UI, not yet merged or tested on KDE/Wayland).
- Introduced a **separate Rust eframe/egui native desktop layout studio** in `rust-ui/`, with pure Rust 2D geometry, rectangle/ellipse/polygon/star shapes, selection/dragging, exact position and quarter-turn rotation, undo/redo, versioned layout JSON, SVG export, polygon-aware first-fit nesting, clearance/margins and array copy.
- New UI has independent Cargo build, strict Clippy, geometry/layout/SVG tests in `.github/workflows/native-rust-studio.yml`; no release or performance claim until CI passes.
- User priority is **tools missing compared with commercial CNC CAD/CAM applications**. See `docs/RUST_UI_GAP_PLAN.md`: sheet nesting, vector textures, reusable templates, automatic plug/cavity inlays, compatible toolpath merging, batch automation.
- This is **not a full UI replacement yet**: native CF3D projects, 3D viewport, cutters, simulation, machine profiles, fixture-aware preflight, toolpath export and physical CNC remain in the existing Python UI/CAM. Its desktop launcher must remain unchanged; the Rust version launches separately via `scripts/run-rust-studio.sh`.
- Never copy trademarked third-party product names into project branding, branch names or UI identifiers. Do not weaken CNC safety while migrating.

### Next implementation block

- [ ] Fix Rust Studio build/clippy/test errors in Github Actions; merge only on green.
- [ ] Introduce versioned read/write engine bridge for native CF3D, stable object UUIDs, CAM invalidation and transactional edits; first real Rust-main-UI takeover when these pass parity.
- [ ] Expand polygon packing to multi-sheet, grain-aware and optimized placement after source-vector import, plus SVG import.
- [ ] Implement native operation/template workspace with existing preflight and verified export, then inlay and texture tools.
- [ ] Validate on real KDE Plasma Wayland and router separately from CI.

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
