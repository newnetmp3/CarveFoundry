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
- Last verified merged baseline: `c89b5872f9a514d33fab26a505036f7d544c9546` (PR #72).
- [PR #61](https://github.com/newnetmp3/CarveFoundry/pull/61): retained analytic line, circular arc and cubic Bézier path foundation, native persistence, direct planar CAM use, basic vector snapping.
- [PR #62](https://github.com/newnetmp3/CarveFoundry/pull/62): close/open/split/join topology editing, analytic segment preservation, persistent CAM source UUID retargeting, Undo/Redo.
- The previous #62 validation reported Python 3.12 and 3.14 at **475 passed, 27 warnings**, plus green Ruff, Python compile, Rust formatting/Clippy/tests, installation-script syntax, and CarveWork tests. These results belong to #62, **not** to current development.
- Existing retained machining operations, preflight, GRBL-style separated cutter stages, sampled removal preview, and double-sided project preparation are documented in [ROADMAP.md](ROADMAP.md). Do not present them as machine-tested guarantees.
- Approximate historical roadmap assessment: native CAD ~50%, object-aware CAM ~85–90%, core router workflow ~82–85%, entire ten-part vision ~55%. These are subjective estimates, not measured acceptance coverage.

## Active development — interactive adjacent tangent/normal handle constraints

- Verified merged `main`: `c89b5872f9a514d33fab26a505036f7d544c9546` (PR #72). Its final GitHub Actions run `37809124842` passed Python 3.12 and Python 3.14 after resolving executable-shebang lint and benchmark test import issues. The Rust/Python raster benchmark script and numerical parity regression are merged, but representative workstation performance measurements have NOT been collected.
- Active branch: `feature/adjacent-tangent-normal-handle-drag` based on merged #72.
- Added an adjacent-segment reference tangent for each cubic control handle where a real neighboring contour segment exists. Reference direction samples the transformed analytic segment close to the adjoining endpoint; no tangent is fabricated at an open-path boundary.
- During viewport Bézier handle drag: **Ctrl** projects the handle onto the adjacent tangent line; **Ctrl+Shift** projects it onto that line's perpendicular; **Shift** alone retains the configurable angle increment from PR #71. The active constraint has a distinct cyan/green/purple marker.
- Extended native renderer/widget signal and Direct Selection commit interface with an optional constraint kind, avoiding subsequent grid/node snapping from silently overriding a constrained drop. Normal unmodified geometry/grid snapping remains unchanged.
- Added geometric reference and offscreen UI regression tests for Ctrl/normal projection, modified handle persistence and indicator state.
- **Unvalidated branch:** CI, manual KDE/Wayland dragging and real-machine output tests are not yet complete. This is cubic handle editing only, not automatic smoothness enforcement across arbitrary CAD objects.
- Rust migration remains a gradual parallel path; no new Rust CAM engine beyond the existing kernels is claimed.

### Next checkpoints

- [ ] Open PR and validate Python 3.12/3.14, Ruff and Rust CI. Fix any failures before merging.
- [ ] Confirm physical modifier semantics on KDE Plasma/Wayland when available.
- [ ] Add general-purpose live geometric snap indicators beyond modifier-constrained cubic handles.
- [ ] Continue trim/extend, fillet/chamfer, retained editable primitives and SVG/DXF vector import fidelity.
- [ ] Run baseline raster benchmarks on development hardware and expand parity fixtures before replacing more Python code.
- [ ] Update this handover and the live roadmap with actual merged results.

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
