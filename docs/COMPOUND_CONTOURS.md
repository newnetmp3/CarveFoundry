# R1m — Analytic compound boundaries, holes and nested islands

This is a **pure Rust, source-preserving CAD analysis**, not a CAM pocket
region creator and not a machining clearance sign-off.

## Native workflow

In **Drawing → Edit Vector Topology**, select **2–32 closed analytic
vectors** and click **Analyze selected closed contours**. The inspector
reports a read-only hierarchy with:

- Outer boundaries and independent separate material regions:
  `Outline / island` at even nesting depth (0, 2, 4…).
- Holes/empty regions inside material:
  `Hole / empty region` at odd nesting depth (1, 3, 5…).
- Immediate parent vector ID and depth for each selected loop.

Roles derive from **even/odd nesting parity**, independent of source
clockwise direction. The action does not reverse, join, reidentify,
merge, delete or mutate original curves, project serialization,
layers, Undo history or vector identity. It does not generate a
machining or engraving operation.

The button reports rejections through the usual status line. Successful
results are displayed as individual per-vector descriptions below it.
They are invalidated on design edits and rechecked against the exact
selected source vector snapshots so pointer drags, switching selections
or loading a different design cannot leave stale results displayed.

## Accepted geometry and analytical proof

The initial R1m subset accepts **closed, simple paths made exclusively
of straight edges and true circular arcs**, with at most 32 loops and
150,000 pairwise edge comparisons. The source closed paths themselves
are checked with the R1k full-chain analytic validator.

Every edge pair between every two different loops is then checked
using exact supporting line/line, line/circle or circle/circle
intersections, with true circular sweep restrictions. The analysis
refuses **any** boundary intersection, tangent contact, common
endpoint, coincident circular overlap or collinear line touch/overlap.

Only AFTER all boundaries are proved mutually disjoint does it
classify each loop's starting **source node** against other loop
boundaries with an analytic horizontal-ray even/odd test. It uses
line equations and true circular radii/angles, not a display
tessellation, polygonized approximation or the polygon centroid.
Circular-ray endpoint contacts use half-open parity rules to avoid
counting shared adjacent nodes twice. The classifier additionally
checks for contradictory or non-nested parent relationships.

The resulting hierarchy is independent of selected vector order and
original source winding. A hole containing an island containing
another hole alternates Hole / Outline / Hole at depths 1/2/3.

## Deliberate refusal and remaining scope

- Open paths, even if visually close to a closed loop.
- Cubic Bézier outlines: exact general cubic ray-segment intersection
  and contact classification are **not** implemented in this slice.
- Touching, crossing or overlapping loops, including touching circles
  and coincident tangent straight edges. Zero-clearance boundary
  contact does not prove a valid pocket.
- Near-coincident uncertain circle supports or unproven numerical
  corner cases. No guessed containment.
- Oversized selections or excessive geometry comparisons.
- Complex region Boolean/offset/union/subtraction, durable compound
  grouping, true island fill rendering, raster-safe region operations,
  cutter compensation, holder/fixture clearance, physical machine
  validation and NC/G-code export.

This is a **read-only analysis of selected independent vectors**;
SVG/DXF source import/export still treats them as independent paths.
No change to native `.cfd` file schema is required.

## Source regressions and manual Wayland checklist

`crates/core/tests/compound_topology.rs` includes fixed-order and
reverse-winding golden hierarchies, disjoint multiple outlines,
three nested true concentric circles, circle-in-square and
square-in-circle, hand-authored SVG/DXF capsule with a rectangular
hole, crossing/touch/overlap refusal, true circular tangency refusal,
open/cubic rejection, duplicates and too many selected loops.
Tests also assert that classification does not mutate the Project.

Owner acceptance still to perform on **Arch Linux + KDE Plasma +
Wayland**:

- [ ] Shift-select two closed native vectors; find the compound
      analysis button and check separate outline/hole labels.
- [ ] Add a nested island and a second independent outline; confirm
      depth and immediate parent are correct regardless of winding.
- [ ] Move a node after a successful analysis. The previous cached
      results must disappear until manually reanalyzed.
- [ ] Undo/Redo an edit, load/open a different design and change
      selection; check that no stale compound role remains.
- [ ] Try touching arcs, an open Bézier, a cubic circle, and two
      identical closed paths. Confirm an explicit refusal with no
      project mutation or crash.
- [ ] Test inspector layout at 100%, 125% and 150% desktop scaling.
- [ ] Independently check actual SVG/DXF imports and viewing in a
      third-party CAD application; CI does not certify its rendering.

**Development status:** branch
`feature/rust-r1m-compound-loop-analysis`. Exact CI and PR merge
verification pending. R1 remains incomplete and R6 NC safety is locked.
