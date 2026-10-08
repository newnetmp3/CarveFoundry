# CarveFoundry implementation roadmap

This file separates **working, integrated features** from proposals. A roadmap
entry is not a claim that a control or algorithm is available. Update this file
in the same pull request whenever a roadmap capability is actually delivered.

## Recently completed roadmap milestones

- **Persistent object-aware machining operations — PR #59 / PR #60:** Native
  projects retain machining intent separately from generated motion. The
  Inspector exposes ordered operations with stable IDs, source-object links,
  cutter/settings, READY / RECALCULATE / DISABLED state, edit, reorder,
  duplicate, delete, enable/disable and selective background recalculation.
  Preview/export remain blocked while any enabled stage is stale or missing
  generated motion.
- **Analytic native vector foundation — PR #61:** Retained editable
  paths support line, circular-arc and cubic Bezier segments, deterministic
  curve tessellation, exact segment splitting, CF3D persistence, Direct
  Selection segment editing and node/midpoint/arc-center/intersection snapping.
  Planar retained vectors feed Profile, Pocket, Engrave and V-Carving directly
  at the 2D CAM boundary instead of first reconstructing their contours from
  triangles.
- **Vector topology editing — PR #62 (upon merge):** Direct Selection can
  close an open contour, open a closed contour at a chosen node, split an open
  path at an interior node, and join two selected open vector paths within the
  configured snap tolerance. Arc and cubic-Bezier segments remain analytic.
  Split/join update persistent CAM source-object IDs and participate in normal
  Undo/Redo and stale-operation invalidation.

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

## Further development — do not treat proposals as implemented

1. **Live, managed CNC sender:** GRBL planner/serial response tracking, real
   machine position, feed overrides, pause, stop, recovery and alarm handling;
   design for interrupted transfers and controller disconnection.
2. **Exact volumetric simulation beyond the sampled, verified-NC stock preview:**
   The top-down 2.5D viewer now decodes and preflights exported GRBL motion,
   models actual cutter radial profiles, approximate removed volume and
   top-surface deviation. It does not validate arbitrary unsupported NC.
   Accurate undercuts, continuous CSG, holder collision and live machining
   verification remain unimplemented.
3. **Robust job recovery:** immutable job manifests, machine state/work-zero
   and tool identification, verified safe entry and machine-aware resumption.
4. **Persistent multi-tool planning and dependencies — substantially
   implemented:** Native CF3D retains both calculated toolpaths and ordered
   persistent machining-operation definitions. Operations store stable IDs,
   source-object links, cutter/settings, enabled state and recalculation state.
   The Inspector can edit, reorder, duplicate, delete, disable and selectively
   recalculate operations; geometry/settings changes invalidate the earliest
   affected stage and dependent downstream stages while retaining earlier valid
   motion. Preview/export fail closed while any enabled operation is stale or
   missing motion. Remaining work is richer dependency graphs beyond ordered
   downstream invalidation, exact stock-state dependency reasoning, reusable
   operation/toolpath templates and automatic global multi-tool optimization.
5. **V-carving inlays:** matched plug/pocket geometry, taper, gap, insertion depth,
   and fit/tolerance validation.
6. **Beyond sampled stock-aware rest:** 3D Rest now simulates all previously
   generated cutter stages and retains only selected-cutter cleanup passes at
   sample centres with residual material above an operator-set threshold.
   It appends to the existing ordered job, refuses no-op rest, and requires
   actual preceding operations for each model. Exact volumetric stock-aware
   clearing, variable cutter-engagement feeds and collision/holder simulation
   remain future work.
7. **Extended native vector editing, group cutouts and text-on-path —
   in progress:** Direct Selection edits retained Pen/Line anchors with viewport
   dragging, exact coordinates, insertion/deletion, Undo/Redo and CF3D
   persistence. PR #61 adds analytic line, circular-arc and cubic Bezier
   segments, exact curve splitting, numeric arc/Bezier segment editing, and
   snapping to vector nodes, segment midpoints, arc centers and intersections.
   Planar retained vectors feed the 2D Profile, Pocket, Engrave and V-Carving
   CAM boundary directly, with mesh projection retained as a fallback.
   PR #62 adds close/open-at-node, split-at-node and two-object endpoint join
   operations with CAM source retargeting.
   A follow-on core change introduces immutable cubic handle movement with
   input validation and save/Undo regression coverage; graphical handle
   hit-testing, dragging and snap indicators are not yet wired into the viewport. Remaining vector-CAD work includes
   interactive viewport Bezier-handle dragging, tangent/perpendicular/grid snapping,
   trim/extend, fillet/chamfer, first-class editable circle/ellipse/polygon primitives,
   editable imported SVG/DXF contours, group cutouts and text-on-path.
   Planar Union/Subtract/Intersect and signed Offset currently produce
   Z0-topped 2.5D watertight results rather than retained analytic contours or
   true volumetric 3D mesh Booleans.
8. **Multi-component 3D relief compositing and editable heightmap layers.**
9. **Machine-integrated double-sided workflow:** Stock-registered two-face
   setup now partitions visible front/back models, reflects the chosen physical
   flip axis, validates XY/Z containment, and writes two verified CF3D projects
   and a setup checklist in a new folder without touching source geometry.
   Each face must separately generate, preflight and export G-code. Live fixture
   detection, physical registration testing, machine-aware flip verification,
   and automatic multi-face G-code execution are NOT implemented.
10. **Optimized batch production/nesting:** Editable regular-grid duplication
    now supports selected multi-part templates, cutter-radius stock margins,
    recorded fixture clearance, hidden originals and Undo/Redo. Irregular
    silhouette nesting, optional grain rotation, serial text and automatic
    global multi-tool optimization remain future additions.
11. **Spoilboard mapping and probe-backed height compensation** with verified
    source/units and explicit controller dependencies.
12. **Material presets, first-run machine wizard and packaged Linux releases.**
13. **Extended recovery features:** Complete CF3D idle checkpoints,
    checksum verification, source modification warnings, restore/discard
    choice, user-controlled normal Save, and bounded retention now exist.
    Persistent Undo history, cross-device sync and cloud backups remain
    unimplemented.

For each item, do not add a button or a stub until calculation, UI,
persistence (where needed), export/sender behavior and regression tests can
be delivered together.
