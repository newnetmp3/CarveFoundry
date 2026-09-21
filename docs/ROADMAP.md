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
4. **Persistent multi-tool planning and dependencies:** A session-owned
   multi-cutter job planner now supports appending operations, reordering/removing
   generated paths, cutout/rough-before-finish checks, stage estimates, full
   preview and preflighted per-cutter export. Native CF3D still does NOT retain
   calculated paths or tool-stage setup records; full automatic operation
   dependency generation and stock-aware sequencing remain future work.
5. **V-carve inlays:** matched plug/pocket geometry, taper, gap, insertion depth,
   and fit/tolerance validation.
6. **Beyond sampled stock-aware rest:** 3D Rest now simulates all previously
   generated cutter stages and retains only selected-cutter cleanup passes at
   sample centres with residual material above an operator-set threshold.
   It appends to the existing ordered job, refuses no-op rest, and requires
   actual preceding operations for each model. Exact volumetric stock-aware
   clearing, variable cutter-engagement feeds and collision/holder simulation
   remain future work.
7. **Extended vector editing, group cutouts and text-on-path:** Direct
   Selection now edits newly drawn Pen/Line XY control points, with viewport
   handles, exact coordinate controls, midpoint insertion/deletion, real mesh
   rebuild, Undo/Redo and CF3D persistence. Imported STL/legacy pen meshes,
   ellipse/polygon shape primitives, traced meshes and baked Boolean/Offset
   results do NOT yet have editable source knots or Bézier handles. Group
   cutouts and text-on-path remain unimplemented. Planar silhouette
   Union/Subtract/Intersect and signed Offset separately produce Z0-topped
   2.5D watertight extrusions, not true 3D mesh Booleans.
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
