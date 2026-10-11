# R1n — Persistent source-exact compound CAD regions

This milestone upgrades the earlier **read-only compound analysis** to
**saved, editable source-path membership**. It does NOT create a new
merged outline, a pocket toolpath, a Boolean polygon approximation, a
CNC clearance result or machine-executable instructions.

## Drawing workflow

1. In the native **Drawing → Edit Vector Topology** inspector, select
   **2–32 closed, disjoint, source-analytic straight/circular paths**.
2. Use **Analyze selected closed contours** to preview each loop's
   nesting parent, depth and Outline/Hole/Island role.
3. Name the region and click **Save as editable compound region**.
4. Select any member vector to view saved region membership. The
   inspector lists per-source roles and offers **Check cursor material**
   to query the design XY location, or **Remove saved region** to
   unlink members without deleting their original editable vectors.

The hierarchy is a strict, verified **even/odd Boolean material set**:

- Multiple unrelated outer contours combine as a design-level union.
- A nested hole toggles material off (set difference).
- Nested islands toggle material back on.
- Deeper nesting alternates by parity regardless of source winding.

An inside/outside material query does **not** imply pocket milling
clearance, Z depth, tool radius or fixture safety. A query on a
retained line or circular arc boundary rejects as ambiguous rather
than guessing interior/exterior.

## Persistence and atomic safety

The native version-1 `.cfd` schema gains an **optional** JSON
`compound_regions` field, defaulting to an empty list. Existing
saved files require no migration and omit the new field when empty.
A saved region stores `id`, `name`, original source `path_ids`,
and each member's proven `parent_path_ids` to keep original
hole/island relationships stable. All original CAD paths retain their analytic
lines, centers, circular sweeps and stable node/edge identities.

Every project save/open, edit, and pointer drag preview runs
`Project::validate`. That validation rechecks:

- Up to 64 saved regions and 2–32 distinct source paths each.
- Unique globally allocated region IDs with no cross-region
  vector ownership, missing IDs or stale member references.
- The full R1m analytic self-contour, cross-loop touch/cross/
  coincidence and line/circle containment proof for current
  source path positions.

Edits that would make the saved region invalid (e.g. pulling its
hole across the outer wall, opening a closed member, or deleting a
still-linked member) are rejected atomically. Valid node movement,
object movement, Undo, Redo and source geometry preservation
continue to work. To delete a region member freely, first click
**Remove saved region**, which leaves the source vectors untouched.

## Source-true query API

`Project::compound_material_at(region_id, world_xy)` validates
current project state, rejects unbounded input and exact-boundary
queries, then applies exact line and circular-ray containment
across the retained loops with Boolean parity. It returns a
design-only `Result<bool,String>`, not any generated CAM region.
The inspector uses this API on the most recent cursor design point.

## Automated contract and manual acceptance

`crates/core/tests/persistent_compound_regions.rs` includes
save/reload and legacy-file compatibility, region identity and
membership checks, Undo/Redo, Rename/Remove, valid/invalid
single-source moves, refused drag previews, source deletion
while linked, duplicate/missing/source-ID injection, nested
material/hole/island parity, separated union islands and
hand-authored SVG/DXF capsule circle-boundary/rectangle-hole
material queries.

Manual **Arch KDE Plasma Wayland** acceptance still required:

- [ ] Select nested loops and save named region; reopen the
      `.cfd` design and verify membership/roles and original
      node/arc editing.
- [ ] Move a hole within its host outline; verify geometry and
      persistent region. Attempt to drag it through the boundary;
      confirm reject/no partially-applied visual displacement.
- [ ] Test region removal, source deletion after removal and
      compound-region Undo/Redo from the inspector.
- [ ] Test cursor material queries in a hole, solid wall, island,
      out-of-stock area and exactly on an arc boundary.
- [ ] Verify native inspector at 100%, 125%, 150% scale and
      no stale source selection/analysis after document reopen.
- [ ] Open exported SVG/DXF independently in third-party CAD
      software; optional `.cfd` region metadata is not itself
      a generic DXF/SVG construct.
- [ ] Do not attempt machine milling based solely on these CAD
      classifications. NC/G-code remains intentionally gated.

**Branch status at implementation:** `feature/rust-r1n-persistent-compound-regions`.
Exact PR-head CI/merge are separately verified before promotion.
R1 remains unfinished; R6 machine-safety preflight stays locked.


### Strict saved nesting identity

A saved region additionally stores `parent_path_ids` in source order,
representing the parent determined at creation by the same exact
analytic contour proof. Every subsequent Project validation checks
that each current source loop retains its **original immediate parent**.
This prevents a subtle but critical semantic change: a hole dragged
fully OUTSIDE its host outline would leave disjoint simple contours,
yet turn a subtraction into another material island. Such edits
**reject atomically** until the user removes/recreates the region.
The same protects an original disconnected outline from unexpectedly
becoming a nested hole. The format remains schema version 1 and
the new field is present only for the newly optional region objects.


## Verified automation and remaining checks

[PR #130](https://github.com/newnetmp3/CarveFoundry/pull/130) merged as c3c32f3f05f60288bfc5dbb52995fa7cc9f79988.
Exact PR head 2f4681207447f27d148ebcee13a5b46227041f03
passed [CI #38109518506](https://github.com/newnetmp3/CarveFoundry/actions/runs/38109518506): **165 Rust tests**, strict Clippy,
native Linux release. New six-case persistence suite includes
the previously failing hole-escape regression, now blocked by
saved parent identity; the original CI revision was not promoted.
Real KDE desktop and independent third-party SVG/DXF visual
acceptance remain unverified; NC/G-code output stays disabled.
