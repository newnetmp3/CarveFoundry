# CNC safety and current limitations

## Machine-output status

**NO TOOLPATH OR NC OUTPUT IS IMPLEMENTED.** The new Rust application is a
design preview. Its `.cfd` files do not contain GRBL commands or callable
machine paths. No preflight checker, tool length compensation, stock removal
simulation, CNC connection, work-offset checks or safe rapid motion planner
exists in this reboot yet.

A green CI result is **not** proof of physical safety.

## Coordinate contract

- World XY0 is the lower-left corner of the stock (millimetres).
- Z0 is the top face of material, not the spoilboard.
- A fence physically 23 mm above the bed with 19 mm material has a
  **stock-relative fence top Z of +4 mm**; this is only an example, not a
  hardcoded universal machine setting.
- Side fences are allowed to have negative stock-relative X/Y extents.
- Fixture margins are additional physical margins, not replacements for
  cutter/holder radius.
- NC rapid moves must avoid fences, clamps and tool holders through the
  complete travel, including machine origin transitions and parking.
- Distinct cutter stages require separately verifiable NC files and a
  manual tool change with fresh Z probing.

## Required conditions before NC generation is enabled

1. Native tool/cutter models, bounded CAM inputs and verified geometry.
2. Complete working coordinate and stock/fixture models including cutter
   radius and holder envelope.
3. Conservative rapid/toolpath/preflight checks on **posted** G-code with
   stock, spindle/cutter, machine travel and safe retract Z.
4. Explicit stale-stage gating, dependency invalidation and failure refusal.
5. Tests with known positive and negative motion fixtures, golden simulation,
   multiple cutters, source mutation, project recovery and CLI export.
6. Physical scrap tests and KDE/Wayland interaction QA on target machine.

These are blocking release criteria. They cannot be disabled with a UI toggle.
