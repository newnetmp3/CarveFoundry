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
- Last verified `main` commit at handover creation: `2360d2e7873e9f6e87e067613546d29adbe4ca4c`
- [PR #61](https://github.com/newnetmp3/CarveFoundry/pull/61): retained analytic line, circular arc and cubic Bézier path foundation, native persistence, direct planar CAM use, basic vector snapping.
- [PR #62](https://github.com/newnetmp3/CarveFoundry/pull/62): close/open/split/join topology editing, analytic segment preservation, persistent CAM source UUID retargeting, Undo/Redo.
- The previous #62 validation reported Python 3.12 and 3.14 at **475 passed, 27 warnings**, plus green Ruff, Python compile, Rust formatting/Clippy/tests, installation-script syntax, and CarveWork tests. These results belong to #62, **not** to current development.
- Existing retained machining operations, preflight, GRBL-style separated cutter stages, sampled removal preview, and double-sided project preparation are documented in [ROADMAP.md](ROADMAP.md). Do not present them as machine-tested guarantees.
- Approximate historical roadmap assessment: native CAD ~50%, object-aware CAM ~85–90%, core router workflow ~82–85%, entire ten-part vision ~55%. These are subjective estimates, not measured acceptance coverage.

## Active development — PR #63

- Pull request: [#63 — Add retained cubic Bézier handle editing core](https://github.com/newnetmp3/CarveFoundry/pull/63)
- Branch: `feature/bezier-control-editing-core`
- Starting `main`: `2360d2e7873e9f6e87e067613546d29adbe4ca4c`
- Most recently created code-fix commit before this document: `709d56b5456e93ad3fe805a3aaa42f1fe409aeb5`
- Goal: complete interactive retained cubic Bézier handle dragging and precision snapping as the next native-CAD slice, without altering safety/preflight semantics.

### Completed checkpoints, in sequence

1. **GitHub baseline checked:** verified live `main` and `docs/ROADMAP.md` match the previous handover.
2. **Branch and PR opened:** created `feature/bezier-control-editing-core`, PR #63.
3. **Core API added:** `move_cubic_control(path, segment_index, control_index, xy)` edits one control of an existing cubic segment with local-mm coordinates, preserving anchors/other control and retaining an analytic cubic.
4. **Regression tests added:** cover first/second handle movement, input errors, changed curve geometry, CF3D roundtrip and history restoration.
5. **Roadmap updated:** explicitly distinguishes the finished core control editor from **not-yet-integrated viewport mouse handles**.
6. **First CI inspected:** GitHub Actions run `37793498674` failed on Python 3.12 and 3.14 at Ruff import sorting in `tests/test_vector_path_editing.py`; pytest was **skipped** in both lanes. Rust checks and earlier job steps passed on Python 3.12.
7. **Lint fix committed:** `709d56b5456e93ad3fe805a3aaa42f1fe409aeb5` reorders `move_cubic_control` and `move_node` in test imports. **CI revalidation still needed** at this checkpoint.
8. **Rolling handover instituted:** this file becomes a required per-step status record on the active development branch. It must reach `main` through the normal reviewed/validated merge.

### Remaining checkpoints

- [ ] Confirm latest PR #63 CI after the import-order fix; inspect failing logs and fix regressions.
- [ ] Locate native viewport node drawing and mouse-hit/drag event handlers; ensure Wayland-safe mouse interaction.
- [ ] Draw visible Bézier control handles and anchor-to-control guide lines for selected editable cubic segments.
- [ ] Hit-test and drag individual handles, converting world XY to retained local XY and committing via existing undo/invalidation workflow. Address transform-pivot changes.
- [ ] Add tests for handle picking, drag conversion, selection, persistence, Undo/Redo and stale CAM invalidation.
- [ ] Implement tangent/perpendicular/grid snapping and optional angle constraints with truthful visual snap indicators; separate follow-on PRs if needed.
- [ ] Run both Python CI lanes and relevant Rust/QA checks, inspect results, then merge only when green.
- [ ] After merging, update merged-baseline SHA, close the active-PR entry, and record the next milestone: trim/extend, fillet/chamfer, retained primitives, editable SVG/DXF.

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
