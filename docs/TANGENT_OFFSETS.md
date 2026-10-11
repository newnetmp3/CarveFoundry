# R1j — Source-exact tangent line/arc parallel offsets

CarveFoundry's native **Drawing → Edit Vector Topology → Create offset vector**
supports these retained analytic sources:

- Straight lines and straight-sided contours, including bounded mitered
  line/line corners (existing R1f solver).
- Individual true circular arcs and concentric all-arc closed circles
  (existing R1g solver).
- **New:** mixed lines and true circular arcs joined at tangent (G1)
  corners, including open chains and closed rounded contours made from
  multiple circular centers. Straight/straight corners in these mixed
  chains use bounded analytic miters; any seam containing an arc must
  have matching left normals.

**Open paths:** positive offset is left of the traversal, negative right.
**Closed paths:** positive offset is *outward*, negative *inward*, independent
of clockwise/counterclockwise path winding. Closed mixed-curve winding is
computed from **Green's theorem over exact straight edges and circular
sectors** — not from preview tessellation. Offset arcs keep original
circle center and clockwise flag, changing only their radius/endpoints.
Lines are translated to true parallels. The source remains unchanged:
a new editable vector is added in the original layer and one Undo
restores the design.

## Intentionally rejected

- Generic cubic Bézier offsets: the mathematical parallel of an
  arbitrary cubic **is not itself a cubic Bézier**. Do not relabel
  raster/polygon approximations as exact analytic source curves.
- Sharp line/arc or arc/arc corners: offset support segments no longer
  meet at the same point. These require a separate explicit join
  strategy (round/bevel/trim with validated topology); the current
  tangent-chain solver fails closed with the measured junction gap.
- Radius collapse, infinite/zero offset values, near-reversing line
  corners, excessive line miters, and changed closed winding.
- Arbitrary local self-crossing/offset collapse beyond the current
  analytic winding and source validation: this stage does **not**
  claim complete offset topology validation for complex overlapping
  multi-loop shapes. Use the source-preserving operation only on
  simple profiles until robust global self-intersection handling
  is independently validated.

No raster preview points become design source curves, toolpaths, or
G-code. NC export remains locked behind dedicated R6 safety gates.

## Arch KDE/Wayland manual acceptance

- [ ] Make an open clockwise semicircular arc with its ending tangent
      connected to a straight line. Offset +2 mm and -2 mm. Confirm
      the center remains identical and circular radius differs by 2 mm.
- [ ] Make a closed capsule/racetrack with two straight runs and
      true semicircular ends. Offset outward 3 mm, inward 2 mm.
      Original circle centers and winding must be retained.
- [ ] Add a sharp line/arc corner and press Offset. Verify an explicit
      tangent-junction rejection and **no mutation**.
- [ ] Try a line/line corner before a tangent arc: bounded miter
      behaves correctly.
- [ ] Try a cubic Bézier mixed with a line: an explanatory refusal
      (not approximation) is expected.
- [ ] Undo/Redo, layer lock/unlock, save/reopen the .cfd design and
      inspect DXF/SVG interchange in an independent viewer.

The Rust CI checks geometry and build behavior; actual KDE UI and
third-party interchange acceptance are still outstanding.

## Verified Rust implementation checkpoint

[PR #123](https://github.com/newnetmp3/CarveFoundry/pull/123)
merged to main at `4f8ee59b5d3cabb45ae0ce5ebe24021336c18d5c`.
The exact tested head `0cb5f1e19e3cbc5a88e48f7eaacc1d530e156049`
passed [Rust CI #38104323749](https://github.com/newnetmp3/CarveFoundry/actions/runs/38104323749):
**127 Rust tests, strict Clippy and Linux native release build**.
Real KDE visual/interaction acceptance and independent source
SVG/DXF validation in the checklist above remain pending.


## R1k engineering slice — complete-chain intersection validation

The source-accurate R1j offset solver checks local joint tangency, radius
collapse, excessive miters and closed winding, but these **do not imply a
simple contour**. R1k adds a separate bounded, source-faithful global check
for mixed line/circle chains **before** creating an offset and **after**
its exact offset coordinates are calculated:

- Compare every distinct source edge pair with retained line/true-circle
  intersection mathematics (maximum 256 edges, 32,640 candidate pairs).
- Ignore only the one shared endpoint of neighboring edges; reject remote
  crossings, tangencies, unexpected endpoint contact, collinear overlaps
  and backtracking, including on open shapes.
- Coincident circular supports have no unique isolated crossing in the
  existing solver. They are **conservatively rejected**, including adjacent
  same-center arcs in mixed chains, until interval-overlap proof is added.
  The dedicated concentric full-circle offset operation is unchanged.
- Source and result are checked; an error leaves source geometry intact
  and no derived offset is committed. The source layer/Undo semantics remain
  as before. This is **not** global CNC toolpath clearance or external
  file validation and does not support non-tangent curved joins.

### Additional KDE/Wayland acceptance

- [ ] On a mixed line/arc profile with a distant crossing, use Create
      offset vector. Confirm a self-crossing error and no extra vector.
- [ ] On adjacent collinear backtracking lines in a mixed path, confirm
      overlap is rejected. A clean tangent capsule should still offset.
- [ ] On a mixed chain with same-center neighboring arcs, confirm an
      explicit unresolved/overlap error rather than an incorrect contour.
- [ ] Verify Undo, save/reopen and third-party SVG/DXF behavior separately
      from automated checks; the UI tool remains CAD-only.

**Validation status:** implementation branch
feature/rust-r1k-global-offset-validation; native CI and real owner
KDE/Wayland acceptance need verification before this slice is marked
complete. Later R1k tasks remain: sharp round/bevel circular junctions,
proven closed contour offset topology, cubic approximation with a
stated tolerance if added, and golden file interoperability tests.
