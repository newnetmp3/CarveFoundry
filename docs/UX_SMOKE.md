# Rust Editor — KDE Plasma/Wayland usability QA

These tests require a real desktop. GitHub CI cannot prove that mouse
capture, Wayland compositor, scaling and editor focus work correctly.
**Do not mark tests passed without testing the built Rust app.**

## Priority-0: pointer and node editing

- [ ] Add Rectangle, press N and mouse-down-drag an anchor without
  preselecting the rectangle; first gesture must work.
- [ ] Press on a tiny anchor and move quickly beyond the drag threshold:
  target selection stays on the original press point.
- [ ] With grid snapping OFF (the default), dragging an off-grid anchor
  does not snap it to an integer before actual pointer displacement.
- [ ] With snapping ON, movement quantizes relative to the original
  anchor without shifting its baseline coordinates.
- [ ] Directly drag Bézier handles and circular-arc endpoints; each
  follows the pointer. Undo should restore true curves and controls.
- [ ] Drag through several frames and press Ctrl+Z once to restore the
  starting position. Ctrl+Y restores the final position.
- [ ] Press Escape during a drag: cancel restores the original geometry.
- [ ] Lock the shape, attempt drag, verify refusal. Unlock and repeat.
- [ ] Open an old Rust CFD rectangle; choose Convert to editable nodes;
  verify its corners can be moved and Undo restores the original contour.

## Tools, camera and project integrity

- [ ] Try Rectangle, Circle, Ellipse, Triangle, Pentagon, Hexagon,
  Octagon and Star; use N to access their editable path nodes.
- [ ] Use P for Pen, click 2+ points to make an open polyline;
  click 3+ points and Close Outline for a polygon; Enter/double-click
  finishes, Escape cancels without modifying the project.
- [ ] V selects/moves whole shapes; Ctrl+D duplicates; Flip X/Y,
  Rotate 90 degrees, Center X/Y, Hide/Show and Delete work with Undo.
- [ ] Wheel zoom stays anchored under mouse; middle/right drag pans;
  F resets zoom/pan without modifying the design.
- [ ] Typing inside text fields does not trigger V, N, P or F shortcuts.
- [ ] Save as a new .cfd file and reopen; geometry and Bézier handle
  coordinates stay identical.
- [ ] No G-code output, machine preflight, CAM or CNC controls are
  exposed. This is design-only and must not be used for machine motion.

Report screenshots, steps, Wayland scale and whether mouse/trackpad.
Keep all checkboxes unchecked until verified on the target KDE desktop.
