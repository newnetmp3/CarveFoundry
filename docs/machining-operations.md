# Machining Operations

The **Machining Operations** section in the Inspector is the persistent CNC job
stack for a CarveFoundry project.

Each operation stores machining intent independently from generated machine
motion:

- operation type,
- selected cutter,
- source object IDs,
- feeds, depths, stepover and strategy settings,
- holding-tab and linking settings where applicable,
- enabled/disabled state,
- recalculation state.

## Status

**READY** means the enabled operation has current generated motion.

**RECALCULATE** means the operation's saved setup is still present but its
machine motion is stale or missing. Preview and G-code export remain blocked
while any enabled operation needs recalculation.

**DISABLED** keeps the operation definition in the project but excludes its
machine motion from the active job.

## Editing the job

Select an operation to edit its cutter and persisted CAM parameters. Saving an
edit invalidates that operation and dependent stages after it.

Moving an operation earlier or later changes the material-removal order, so the
earliest affected position and all dependent enabled stages are marked for
recalculation.

Duplicating an operation creates a new stable operation ID and copies its setup.
The duplicate has no trusted machine motion until recalculated.

Deleting an operation removes its owned motion. Later enabled operations are
invalidated because their expected starting stock may have changed.

Disabling an operation removes its generated motion but preserves the setup.
Later enabled stages are invalidated when necessary. Re-enabling always
requires new motion for that stage and dependent enabled stages.

## Recalculation

**Recalculate** on a selected row marks that operation and dependent enabled
stages stale, then regenerates them through the normal background CAM worker in
job order. Earlier valid stages are retained.

## CNC safety

CarveFoundry uses stock-bottom-left work XY0 and stock-top Z0. Generated output
still passes the normal fixture-aware preflight. Manual cutter changes are
never inserted silently into one GRBL program: cutter stages are exported as
separate files and require a physical stop, cutter swap and Z re-probe.
