# CarveFoundry implementation roadmap

This file separates **working, integrated features** from proposals. A roadmap
entry is not a claim that a control or algorithm is available.

## Workshop-safe output — implemented in PR #16 (upon merge)

- Project-owned rectangular fixture keep-outs with editable XY extents, top Z,
  clearance, visible viewport outlines, native CF3D persistence, and Undo/Redo.
- Cutter-radius-aware segment/fixture preflight, stock depth, configured machine
  travel and parking movement checks. Normal, resume and tiled exports are
  blocked when preflight detects an error. Preflight is also available as a
  separate report-only command.
- Dedicated G-code file per consecutive cutter stage rather than silently
  switching cutters inside one GRBL file. Manual cutter change and Z re-probe
  between files are required.
- Project-window open/save moved to workers; Save-before-New/Open/Close defers
  the requested action until the save succeeds.

Preflight is deliberately conservative and offline. It cannot know the actual
work offset, controller travel origin, hold-downs omitted from the project,
cutter holder envelope, spindle state, or where the machine is currently parked.
It must not be described as a guarantee of physical safety.

## Not yet implemented — only ship as complete end-to-end features

1. **Live, managed CNC sender:** GRBL planner/serial response tracking, real
   machine position, feed overrides, pause, stop, recovery and alarm handling;
   design for interrupted transfers and controller disconnection.
2. **True material-removal simulation:** model the cutter swept volume and
   remaining stock and account for tool profile; report uncut material and
   potential gouges, not merely a path-tracing playback.
3. **Robust job recovery:** immutable job manifests, machine state/work-zero
   and tool identification, verified safe entry and machine-aware resumption.
4. **Multi-tool machining plan UI:** group/order operations by cutter, explicit
   rough/finish/detail/cutout dependencies and per-cutter setup records.
5. **V-carve inlays:** matched plug/pocket geometry, taper, gap, insertion depth,
   and fit/tolerance validation.
6. **Stock-aware rest machining/adaptive clearing/feed optimization:** use
   actual remaining material and cutter engagement, with validated limits.
7. **Direct Selection / editable vector nodes, group cutouts, text-on-path.**
   Planar silhouette Union/Subtract/Intersect and signed Offset are implemented
   separately: results are Z0-topped watertight extrusions, not 3D mesh
   Booleans or editable source vector paths. Original shapes are hidden, not
   destroyed; Undo/Redo and CF3D save/load preserve the outcome.
8. **Multi-component 3D relief compositing and editable heightmap layers.**
9. **Double-sided machining wizard:** choose actual physical flip axis, compute
   stock-relative registration, and validate front/back alignment across
   origin modes, fixtures and tool changes.
10. **Batch production and nesting:** generate multiple positioned copies with
    registration margin, clamp area and machine travel checks.
11. **Spoilboard mapping and probe-backed height compensation** with verified
    source/units and explicit controller dependencies.
12. **Material presets, first-run machine wizard and packaged Linux releases.**
13. **Autosave/crash recovery:** atomic backups, resume/restore choice and
    safeguards against corrupted or obsolete checkpoints.

For each item, do not add a button or a stub until calculation, UI,
persistence (where needed), export/sender behavior and regression tests can
be delivered together.
