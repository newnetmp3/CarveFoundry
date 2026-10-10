# R1f — Exact 2D vector topology (first source-preserving slice)

This stage adds **design geometry editing only**. It does not generate cutter
paths, machining operations or NC/G-code. Curves remain true circles and cubic
Béziers in the native .cfd file, SVG and DXF interchange.

## Where to find the tools

Drawing workspace → left tool palette → **6 EDIT VECTOR TOPOLOGY**.

- **Split selected edge** — choose an edge from the dropdown and a fraction
  between 0 and 1. Exact line interpolation, circular-angle subdivision
  or de Casteljau cubic subdivision creates a new node. It keeps the original
  first-segment identity and is one undoable CAD edit.
- **Trim end** — choose Start or End of a selected open path, and fraction.
  Removes a fraction of its *terminal segment* analytically while preserving
  that segment's source type. This is not yet a click-to-intersection cutter.
- **Extend straight end** — extends only a terminal straight segment by
  millimetres along its existing axis. Curve extrapolation is not guessed.
- **Join selected** — select exactly two visible, editable *open analytic
  paths*. It automatically chooses the closest endpoints, reverses source
  direction as needed (including Bézier handle order/arc sweep), and retains
  exact curves. If endpoints touch, they share a node. If gap is nonzero
  but within chosen tolerance (max 5 mm), a **real straight bridge edge**
  is added without bending original curves. Result retains the first
  selected ID in deterministic ascending order; second vector is removed.
  Requires matching layer/group membership; text-linked glyphs are refused.
- **Create offset vector** — source-preserving parallel offset for
  straight-only open or closed contours, including miter intersection.
  Positive distance offsets an open path left of its direction, and a
  closed shape OUTWARD regardless of winding. Negative offsets the reverse
  side. Offset adds a new independent editable vector and carries layer,
  while leaving the original unchanged. Sharp, collapsing/self-intersecting
  results are rejected, never approximated from preview sampling.
- **Fillet selected node / Chamfer selected node** — in Nodes mode select
  an *interior* line-line corner of an open vector, choose radius or bevel
  length in mm. A fillet inserts a tangent **true circular arc** with exact
  radius/center. Chamfer inserts a straight connecting edge. Both preserve
  adjacent straight edges and refuse oversize/degenerate corners.

All actions pass through native Rust project validation and one Undo
transaction; invalid edits leave the design as-is. Geometry remains fully
editable as line, arc and cubic source segments.

## Intentionally unsupported

- Offsets of arbitrary cubic curves and general elliptical/variable-radius
  contours. They must use an independently validated native offset solver
  in a later R1f slice—not a polygonized preview approximation.
- Automatic intersection-aware trim, multi-curve extend and closed-loop
  fillets/chamfers. This initial numeric subset performs exact endpoint
  edits and interior line-line corners only.
- Geometry rewriting for text-linked outlines may invalidate editable
  source-text intent; treat node modifications as individual contour edits
  and regenerate from font if needed.

## KDE Plasma Wayland acceptance

- [ ] Create one circular arc and one Bézier. Split each at fraction 0.3;
      original sweep/shape must not change.
- [ ] Trim a cubic end and Undo. Source handles remain editable.
- [ ] Select two touching open paths and Join; Undo restores both.
- [ ] Join near endpoints with 0.2 mm tolerance; visible straight bridge
      must connect without distorting the source arcs.
- [ ] Offset a closed rectangle outward by 2 mm; original stays untouched.
- [ ] In Nodes mode, fillet and chamfer a 90° open polyline corner and Undo.
- [ ] Lock a layer/group; every topology edit must fail without mutations.
- [ ] Export/reimport SVG/DXF; verify arcs/cubics are still source curves.
- [ ] Confirm no CNC NC export or posted G-code becomes available.

**CI does not replace visual geometry or machine QA.** CNC output is
blocked pending the independent R6 machine-safety release gate.

## Verified automated checkpoint

[PR #116](https://github.com/newnetmp3/CarveFoundry/pull/116)
merged after [Rust CI #38011306582](https://github.com/newnetmp3/CarveFoundry/actions/runs/38011306582)
passed 95 Rust tests, strict Clippy and native Linux release build.
Physical KDE/Wayland editing and independent SVG/DXF curve QA are
still outstanding.

**Offset clarification:** closed line-only contours have explicit
self-intersection/degeneracy checks. Open path offsets are bounded and
validated as analytic lines, but overlapping distant segments in a
pathological open polyline are not yet exhaustively checked. Visually
review complex offsets until a robust general contour solver ships.

## R1h — Extend a straight endpoint to another vector (implemented)

Use **Drawing → Edit Vector Topology**, select **exactly two** analytic
vectors, and choose **Extend one open straight end to reference**.
Choose which selected vector is the **source**, select its Start or End
terminal, and enter a **maximum forward reach** in millimetres. The other
selected vector becomes the reference boundary.

The source must be an open path whose chosen terminal edge is straight.
Only its existing terminal node is moved, in the edge's forward direction.
The reference may be a straight path, a true circular arc, or a cubic
Bézier (including a closed multi-edge contour). Intersection coordinates
come from the previously verified exact-source line/arc/Bézier
intersection engine; the nearest forward crossing inside the maximum
reach is chosen. Reference paths are NEVER modified.

Operations validate current source/reference state and remain one-step
Undo/Redo. Hidden reference, locked source, no forward crossing,
overlapping collinear reference, unsupported degenerate curve, exceeding
maximum reach or closed source fail explicitly without changing geometry.
There is no line/cubic/circle preview sampling or machine NC output.

### KDE/Wayland manual acceptance

- [ ] Create horizontal open line ending at X 20, reference vertical
      line at X 35. Select both, choose source and End, reach 20 mm.
      Extend to X 35; Undo restores X 20.
- [ ] Repeat with a reference Bézier crossing at X 35 and a true arc
      with two possible crossings. Nearest *forward* crossing wins.
- [ ] Choose Start to extend backwards toward a different vector.
- [ ] Reach shorter than the gap rejects, as does a collinear
      overlapping reference or a hidden/locked source.
- [ ] Save/reopen .cfd, export/reimport SVG/DXF, verify original
      source line and reference curve identities remain analytic.
- [ ] Repeat with layer/group selection and observe status messages.

This is one source-exact R1h tranche, NOT a general curve extrapolation,
mixed/cubic offset or machining capability.

## Verified R1h checkpoint

[PR #120](https://github.com/newnetmp3/CarveFoundry/pull/120)
merged into main at `51ab853abb19922f9e589fad0766613a4f5dc863`.
Its exact tested revision `809f716595cda32a5ce565672fabe602941c8c8f`
passed [CI 38014783760](https://github.com/newnetmp3/CarveFoundry/actions/runs/38014783760):
**117 Rust tests, strict Clippy and native Linux release build**.

The contrast improvement to crossing numbers was independently
merged in PR #119, with 112 tests and Linux release checks passing.
Live KDE/Wayland mouse/zoom and independent external CAD geometry
inspection are still required; this milestone does not unlock CAM/NC.
