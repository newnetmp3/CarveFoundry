# Native DXF 2D interoperability

DXF import and export transfer editable vector drawing geometry only.
The native .cfd project retains material, fixtures and project metadata.
**DXF export is not CNC G-code or machine instructions.**

## File menu workflow

Import DXF vectors… merges all imported vectors as one undoable operation.
Export vectors as DXF… writes all native and legacy vector outlines as a
2D ASCII R2000 DXF file in millimetres.

## Supported DXF entities

- LINE: exact editable straight segment.
- LWPOLYLINE: open/closed paths with exact signed circular bulges.
- ARC and CIRCLE: exact circular arcs; circles become four editable arcs.
- SPLINE: a non-rational, clamped cubic with exactly four XY control
  points and eight knots, retained as a cubic Bézier.
- Source units $INSUNITS: mm (4), inches (1), cm (5), metres (6).
  Other and missing unit declarations are rejected to protect scale.
- XY is bottom-left origin with positive Y up (same as CarveFoundry).
- Native XDATA metadata is written so CarveFoundry-to-CarveFoundry exports
  can reconstruct multi-span geometry, names, locks and visibility.
  Other CAD software may discard this XDATA; if so the ordinary DXF
  individual entities remain geometrically analytic but grouping is lost.

## Deliberate limits

No binary DXF, 3D Z or non-default extrusion, classic POLYLINE + VERTEX,
INSERT/BLOCK references in the drawing, TEXT/MTEXT, dimensions, HATCH,
unrepresentable general/rational/periodic splines, variable-width
polylines or non-vector entities. An unsupported entity rejects the
**entire import**; there are no silently skipped drawing entities.

Limits: at most 16 MiB input, 512 drawable entities, 256 nodes/path.
An invalid imported vector never alters the design or its undo history.
Material dimensions remain unchanged by DXF import.

## KDE Plasma / Wayland manual checks

- [ ] Export a rectangle, arc, cubic Bézier and circle to DXF.
- [ ] Reimport to a fresh design: verify node positions and curve handles.
- [ ] Use Ctrl+Z once to undo an entire multi-object import.
- [ ] Verify 1 inch scales to 25.4 mm for a source with $INSUNITS = 1.
- [ ] Invalid dimensions/unsupported entities reject without partial data.
- [ ] Use the native file dialogs, and confirm cancel leaves project alone.
- [ ] Inspect a saved DXF using a separate viewer/CAD application.
- [ ] Confirm that no G-code, postprocessor, or CNC motion is exposed.

Passing GitHub CI is not a substitute for desktop CAD interoperability QA.
