# Beta2 desktop redesign — development handover

**Scope:** PySide6 Linux desktop UI only, on GitHub branch `Beta2`.
**Base:** `main` at `0a7a281b5b622fae9d5fda014cbb532dceadd7da`.
**Original Beta2 handoff:** `f1beae378298bc244214c0f4cdc91ffd2f31e843`.
**Do not merge to main until physical KDE/Wayland acceptance.**
**Do not modify `web/` or desktop CAM/Rust algorithms for UI-only work.**

## Milestone A — focused CAD workspace (earlier Beta2)

- Persistent Design / Machine workspace and Beginner / Advanced experience selection.
- Compact viewport controls, independent Design Inspector and Machine dock.
- Theme-independent painted icons and restorable machining panel.
- Ctrl+K quick command search invokes existing canonical Qt actions, respecting
  disabled action states. Ctrl+K/Restore Panels are available in the header.

**Handover:** Focus UI changes on `src/carvefoundry/ui/beta_workspace.py`,
`workspace_icons.py`, `workspace_palette.py`, and `theme.py`.
The existing native viewport remains the authoritative Qt/OpenGL renderer.

## Milestone B — integrated, guarded machining workflow

- One dock with **Setup / Operations / Review / Export** tabs, saving tab selection.
- Operations embeds the **existing** CAM form, with unchanged Python/Rust
  background CAM generation, settings, cut types, cutter profiles and Z heights.
- Dedicated operations picker includes specialty CAM (Rest, Waterline, etc.).
  It automatically switches to Advanced where Simple cannot express the cut.
- Live cutter-stage sequence and order manipulation share the same job list.
  Inline stage review avoids opening the planner; Advanced can still invoke
  the detailed legacy planner.
- The docked nonmodal generation form captures a cheap immutable project
  context key (project, stock, geometry identities/transforms, cutter, machine,
  fixtures, ordered toolpaths) and refuses submission if the input changes.
  Reopening the editor refreshes its settings.
- Review offers toolpath/rapid overlays, full backplot access, native
  async **posted-NC stock-removal simulation**, 2.5D preview and deviation
  coloring. Failed/cancelled simulations invalidate their results.
- Background CNC preflight produces the existing raw verifier report
  **inline** in Review; reports are invalidated on job/machine/stock changes.
- Export is gated by the existing verified job fingerprint and the
  **existing independent post-processed NC verifier** (not UI-only gating).
  G-code remains split at cutter changes. Always change bit, re-probe
  stock-top Z0, and inspect actual fixtures between files.

**Handover:** `BetaWorkspaceMixin` is a presentation layer. Never introduce
a duplicate CAM job engine, a separate preflight implementation, or mutable
toolpaths directly in UI callbacks. Keep the old dialog entry points available
for other action/menu routes while validating the embedded interface.

## Milestone C — testing and real desktop acceptance

- `tests/test_beta_workspace.py` exercises workspace persistence, basic
  and advanced CAM modes, input-stale generation blocking, job ordering,
  verified preflight invalidation, inline reports, simulation image/output,
  failure/cancellation states, command palette, and dock recovery.
- Linux hosted GitHub Actions runs offscreen Qt; **it does not exercise
  KDE Plasma/Wayland native OpenGL or physical CNC hardware**.
- Test with Python 3.12 and 3.14, Ruff, Cargo and full pytest.

### Local commands (Arch Linux)

```bash
cd /mnt/moar/Downloads/git/CarveFoundry
git status --short    # preserve any unrelated local edits before switching!
git fetch origin
git switch Beta2
git pull --ff-only

# Existing editable install should use the changed Python modules.
carvefoundry

# Hosted/headless-style checks (requires dev dependencies)
QT_QPA_PLATFORM=offscreen LIBGL_ALWAYS_SOFTWARE=1 pytest -q tests/test_beta_workspace.py
ruff check src tests scripts
cargo test --manifest-path rust/Cargo.toml
```

### Physical KDE/Wayland acceptance checklist

1. Open a scratch project, import STL/SVG and verify stock bottom-left
   XY0 and stock-top Z0. Confirm usual camera orbit/pan/zoom on Wayland.
2. Design workspace: select multiple objects, transform, inspect layers,
   use drawing/text, Ctrl+K actions, hide/reopen Inspector.
3. Machine workspace: resize and float the dock, close and Restore Panels.
   Check full CAM form scrolls inside Operations without clipping.
4. Choose V-Carve, 3D Rest, Waterline and generic operations in Beginner /
   Advanced; ensure the selected *actual* operation matches the displayed
   operation, cutter and settings.
5. Begin an operation, then attempt editing while background CAM runs;
   ensure editing is blocked, cancellation works and the UI stays responsive.
6. Modify stock/fixtures after opening inline CAM form; generation must
   refuse stale input until editor is reopened.
7. Generate multi-tool rough→finish→detail jobs. Preview operations and
   test stage ordering and cutout-last validation.
8. Simulate posted NC at more than one stock sampling density. Verify report,
   visible stock image, residual material highlights and full-size viewer.
   Trigger a deliberately invalid fixture/stock profile and verify error
   handling and inability to export.
9. Run preflight and check report and export gating. Change fixture and
   verify it invalidates the previous PASS and blocks export.
10. Check separate per-cutter files, manual tool changes, re-probing Z0 and
    job sheet with NO physical machine connected.
11. Bed-height fence conversion: fixture top relative stock Z0 =
    physical fence height above bed minus stock thickness. **A 23 mm fence
    above a 19 mm stock has a top at +4 mm, not +23 mm.**
12. Verify no regression in the native KDE/Wayland viewport on different
    window sizes and multi-monitor scaling.

### Remaining limitations

- Native fullscreen backplot and the high-resolution stock viewer remain
  standalone windows intentionally; the small sample image appears inline.
- Machine profile and fixture editors are still their canonical dialogs.
- CNC preflight is software validation, NOT proof that physical clamps,
  work offset, tool length or machine setup is safe.
- GUI CI cannot substitute for actual physical desktop/GPU/machine QA.
- Browser `web/` is a separate early prototype and is unchanged by Beta2.

## Recommended follow-up

After green hosted CI: run the physical checklist, record precise
Wayland layout/interaction bugs, and fix them **on Beta2 only**.
Once usable, create a PR from Beta2 into main for review; do not merge
before the user approves. Continue cloud/browser work in separately
scoped branches.
