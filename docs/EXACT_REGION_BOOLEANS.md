# R1o — Source-exact Boolean boundaries for proven non-crossing regions

This is an **incremental native Rust CAD** capability on top of the
persistent R1n compound-region model. It is NOT general polygon clipping,
curve-flattening, pocket geometry, tool radius compensation or CNC output.

## Use it in the native Drawing workspace

1. Make two independently saved compound CAD regions, each built
   from closed source-analytic line / genuine circular-arc loops.
2. Open **Edit Vector Topology → BOOLEAN CAD · EXACT NON-CROSSING REGIONS**.
3. Choose the **A** and **B** saved region names, give the result a
   descriptive name, and click **Union**, **Intersection** or **A minus B**.
4. The result appears as editable *new* native source paths; the
   original source paths and saved operand regions remain unchanged.
   Select a generated member to inspect the derived saved compound
   region, if the result has multiple loops. Each operation is one Undo.

The operands may have nested holes, nested material islands and
multiple separate regions, as long as **ALL boundaries from both
operands are simple and mutually disjoint** (no shared points,
tangencies, crossing, coincident circular sweeps or touching lines).

## Why the source-curve result is exact

A Boolean of two regions with **non-intersecting boundaries** can only
change its inside/outside state across complete original source loops.
For each loop of A, the B material state is constant along the loop's
entire boundary (because the full inter-loop contact test passed).
The operation's Boolean truth values on either side of A determine
whether the whole original loop remains in the result. The same
proof applies to each loop of B using A's material state.

For example, for a boundary of A, retain the original complete
true line/arc loop precisely when:

`operation(false, b_material) != operation(true, b_material)`

No new crossing points, sampled polygons, spline approximations,
extrapolated arc centers, arbitrary reorientation or repair of
unresolved boundaries are introduced. These are *exactly selected
existing source curves* with new stable vector IDs.

The result's boundary set is independently revalidated by the same
R1m nesting analysis. If it contains multiple loops, the editor
creates a new durable R1n compound CAD region, preserving its
verified parent-vector hierarchy. If it has one loop, the result
is a single native closed editable vector. Empty results return
an explicit error rather than creating a fake or invisible vector.

## Deliberately unsupported (fail closed)

- Intersecting, touching or coincident boundaries, including the
  very common partially overlapping pair of rectangles. These
  cases require a future **exact edge-splitting** and topology
  reconstruction milestone; silently assuming either boundary
  would be incorrect.
- Arbitrary cubic Bézier curve Boolean reconstruction or polyline
  flattening to pretend it is source-accurate.
- More than 32 combined input source loops (or the R1m analytical
  scan budget); same-region operands, absent saved sources,
  ambiguity or empty result.
- Machine pocketing, cutter offsets, holder/fixture checking,
  NC/G-code exports and real CNC job previews. R6 safety remains
  a separate future gate.

## Integration goldens and owner acceptance

`crates/core/tests/exact_region_booleans.rs` checks:

- Nested rectangular **Union**, **Intersection** and **A minus B**:
  expected complete edge source identities, exact Boolean
  material parity, parent-child links and saved .cfd reload.
- Reversed difference with its own unique retained boundary set.
- Disconnected material union and explicit empty intersection.
- Partially intersecting and edge-tangent saved shapes fail
  atomically without modifying either original region.
- Missing/repeated operands and invalid result names fail.
- Concentric true-circle arc loops preserve all original true
  centers, sweeps and segments in generated results.
- Independently hand-authored SVG/DXF capsule fixtures preserve
  their original true arcs when involved in nested Union.

Manual owner Arch Linux / KDE Plasma / Wayland acceptance:

- [ ] Create/save two separate compound CAD regions and select the
      two named operands in the topology inspector.
- [ ] Verify each Boolean button, A/B order (especially **A minus B**),
      editable node/arc source output, and a single Undo/Redo.
- [ ] Move a newly generated loop only when its own saved parent
      remains valid; ensure atomic refusal of invalid drags.
- [ ] Try overlapping rectangles, tangent circles, exact duplicate
      boundaries, empty intersection and cubic input. Verify
      understandable refusal, no partial output or crash.
- [ ] Export results to SVG and DXF, open independently in external
      CAD software and inspect actual arc directions and dimensions.
- [ ] Test desktop display scale and inspector layout at 100%,
      125%, 150%. CI is not a substitute for these UI checks.

**Initial implementation branch:** `feature/rust-r1o-exact-region-booleans`.
CI, merging and external desktop acceptance are separate gates.
