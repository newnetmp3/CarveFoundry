# CarveFoundry native Rust design-workspace specification

This milestone prioritizes daily CAD usability over additional CAM algorithms.
It follows established professional CNC drawing patterns without copying
other applications' identities, artwork, branding or source code.

## Screen regions

1. Menu bar: File / Edit / View / Drawing / Help, including native KDE Open
   and Save As through XDG Desktop Portal; unsaved design confirmation.
2. Tool ribbon: Drawing vs read-only Toolpaths workspace, Select / Node Edit
   / Pen, quick shapes, Undo/Redo and Fit.
3. Left palette: grouped vector creation, path drawing, dimensions, transform,
   view/grid. Primary tools visible without scrolling; secondary groups collapse.
4. Central design canvas: light stock on dark background, visible XY0 and
   bounded coordinate rulers/grid, highlighted vectors/nodes, cursor-centric
   wheel zoom and middle/right drag pan. Mouse pan/zoom never edits geometry.
5. Right inspector: object list with visibility and lock, precise properties
   for selected object/nodes/handles, independent Material setup and fixtures.
6. Bottom bar: selected tool, material size, pointer XY, snap and operation
   status; clearly identifies the CAD-only safety boundary.

The Toolpaths workspace is informational. It has no executable CNC export
until native geometry, holder/cutter, fixture and posted-code safeguards exist.

## Interaction guarantees

- Node mode displays handles for all visible paths; first-press hit-testing
  selects and drags in one gesture, even past the drag threshold.
- Grid snap is OFF by default and never changes pre-drag coordinates.
- Numeric editing is retained in the Properties panel, separate from the
  primary object browser. Renames are explicit and one Undo step each.
- New designs get a fresh unsaved identity; first Save invokes Save As.
  Destructive New/Open actions require confirmation if design data is dirty.
- Sidebars resize and scroll vertically, without forcing horizontal scrolling.
- Every common drawing tool is immediately discoverable in the left palette
  or in the ribbon; advanced controls may collapse.
- All original analytic arcs and cubic Bezier data remain in native Rust
  source model. UI appearance does not mutate stored design geometry.

## KDE Plasma / Wayland manual acceptance (NOT automatically passed)

- [ ] On 1920x1080 and 1280x800, controls and labels remain visible at
  100%, 125% and 150% display scale.
- [ ] Creating rectangle, circle, star, line, arc and Bezier path is clear
  from the left palette, with the object selected in the inspector.
- [ ] Press N and immediately drag an unselected anchor. Test fast drag,
  selected handle, lock and Escape cancellation. No camera movement.
- [ ] Undo/Redo, duplication, mirroring, rotation and centering behave
  predictably and do not change file state without a real design edit.
- [ ] Wheel zoom remains pointer-centered, middle/right drag pans and
  Fit returns the drawing to the stock, without altering geometry.
- [ ] Native KDE Open and Save As dialogs work; cancel does not replace the
  current design. First Save requests a filename.
- [ ] Dirty New/Open requires confirmation; cancel preserves every object.
- [ ] Object names, node coordinates and Material settings remain editable.
- [ ] No NC output or CAM simulation tools are shown as usable.

Run the existing complementary test list in UX_SMOKE.md. Physical KDE/Wayland
interaction is NOT verified by a GitHub compile or an automated geometry test.


## Tool-placement usability contract

- Clicking Rectangle/Circle/Ellipse/Polygon/Star in the palette,
  ribbon or Drawing menu selects a tool; **does not create anything**.
- Press-drag-release on the paper-toned stock defines shape dimensions.
  Reverse corners work; all coordinates are mm relative to stock XY0.
- While dragging, show a temporary outline plus live width × height.
  No draft vector enters Project or Undo until successful release.
- Shift locks equal width/height; Circle is always square.
  The snap option quantizes only pointer displacement, never the
  original off-grid start coordinate.
- Escape cancels; choosing Select, Nodes or Pen leaves shape mode.
  Small/out-of-range placements reject with a status, no history.
- New objects are selected automatically, displayed in Properties
  with editable numeric coordinates, and can be undone in one action.
- Precise numeric size entry remains accessible in Vector Dimensions
  with an explicit create-at-offset button.
- **Manual KDE Wayland QA required:** test pointer capture, fast dragging,
  modifier behavior, circle radius, reverse direction and no-commit
  cancellation on 100–150% display scales.
