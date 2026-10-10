# R1i — Extend open curved endpoints to another vector

**Feature:** Drawing → Edit Vector Topology → select exactly two analytic
vectors → **Extend end to reference**. Choose **Source** (the open path),
**Start** or **End**, and a maximum reach in millimetres. The other selected
vector is the reference and is never modified. The command is one Undo step.

## Which source shapes can extend?

| Source terminal segment | Behavior |
| --- | --- |
| Straight line | Continue the existing line to the nearest forward intersection |
| True circular arc | Continue the same exact circle, preserving radius, center and winding, and stop at the nearest forward intersection |
| Cubic Bézier | Continue the **original cubic polynomial outside its original parameter domain**, find the first source-accurate intersection, and append the restricted polynomial as a new cubic Bézier segment; this preserves position, tangent and curvature continuity across the seam (C²) |

The code uses the source-geometry intersection engine for references composed
of lines, true circular arcs or cubic Béziers. It does not infer editing
geometry from screen pixels, tessellated preview polylines, or stock pixels.
The original source path's existing nodes/segments and their IDs are retained;
the continuation is a **new** editable segment with new unique IDs.

**Bézier caveat:** a cubic polynomial extension does not necessarily follow
the direction you visually expect from its last short handle; it is the
mathematically exact continuation of the original cubic, not a new
interpolating spline aimed at the boundary. If the continuation never crosses
the selected reference, the command gives an error rather than bending the
original curve to manufacture an intersection.

To avoid unstable extrapolation, the cubic solver only evaluates at most
**two additional normalized Bézier parameter lengths** beyond the endpoint
and within the chosen arc-length reach in millimetres. Circular arcs are
limited to just under one revolution in one appended segment. Both limits
are intentional.

## Why can the button still be disabled?

The chosen **source** must be OPEN, visible/unlocked, and analytic. A
closed pentagon or closed ellipse can be used as a **reference**, but cannot
have its own start/end extended. Choose the open Bézier from the Source
dropdown. If it has a zero tangent (collapsed control handles), a unique
direction is unavailable and the operation fails with a useful message.

The code rejects missing intersections, overlapping/ambiguous references,
non-finite geometry, a collapsed arc radius, zero derivative at a Bézier
endpoint, exceeding max reach or the safe polynomial horizon, and exceeding
the 256-node path limit. No partial CAD edit is saved on failure.

## Arch KDE/Wayland manual QA

- [ ] Select an open Bézier and a CLOSED five-edge polygon. Select the Bézier
      as Source, End, and reach 100–200 mm. Confirm the Extend button is
      enabled. If the mathematical continuation does not meet the polygon,
      the status must report this instead of greying the button.
- [ ] Construct an open cubic that extends into a vertical line. Confirm
      the new segment is a true cubic, and original handles/shape remain
      unchanged; Undo returns to original.
- [ ] Select a true circular arc and line boundary. Verify continued
      radius/center and winding, then Undo.
- [ ] Try Start instead of End; verify reverse source direction is correct.
- [ ] Select a closed polygon as Source: show an explicit "closed" reason
      for the disabled command.
- [ ] Hide or lock Source, hide Reference, choose a far reference beyond
      reach; no partial changes or Undo entry.
- [ ] Save/reopen .cfd, export/import SVG/DXF and inspect source segment
      identities/types against the original.

**Safety:** this is CAD-only vector authoring. No postprocessors,
machining toolpaths, or machine NC export are enabled. CI cannot replace
desktop pointer/geometry acceptance.
