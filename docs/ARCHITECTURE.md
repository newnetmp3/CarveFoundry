# CarveFoundry architecture and module ownership

CarveFoundry is a PySide6 desktop application, a Python project/CAM layer and a
small Rust/PyO3 geometry acceleration library. The UI is Linux/Wayland first.

## UI composition

`ui/project_window.py` is the application window used at startup. It extends
`ui/main_window.py` with project dirty-state management, background save/open,
Undo/Redo and guarded New/Open/Close flows. Keep history ownership here.

`ui/main_window.py` owns application construction, selection/Inspector state,
mesh transform interactions, import/export orchestration and the reusable
background-job lifecycle. It **composes** the following functional mixins:

| Module | Owner / purpose |
| --- | --- |
| `ui/workspace_commands.py` | Shared QAction registry, visible top menus, compact left tool rail and the hidden legacy ribbon host. |
| `ui/text_editor.py` | Editable text Inspector, installed-font grouping, font-face validation, typography-to-mesh updates. |
| `ui/interface_settings.py` | Load/save/migrate persistent layout and viewport preferences, display toggles, navigation defaults. |
| `ui/planar_operations_actions.py` | Background task orchestration and commit of selected vector-outline Boolean/Offset results. |
| `ui/ribbon_actions.py` | Drawing, CAM control state, cutter/machine commands, Smart Values, fixtures and export actions; it inherits `CamGenerationDialogMixin`. |
| `ui/cam_generation_dialog.py` | Full CAM requirements/strategy dialog and its validation/readiness controls. |
| `ui/native_viewport.py` / `ui/viewport_gpu.py` | Native OpenGL interaction, scene overlays and GPU data/cache operations. |

All mixin methods operate on the **same MainWindow instance** and existing Qt
widgets. UI actions are created only once in WorkspaceCommandsMixin and are
bound to their real owning handlers; avoid duplicate buttons or parallel state.
Put new behavior in the narrowest relevant module, not automatically in
`main_window.py` or `ribbon_actions.py`.

## Model, motion and file formats

- `core/project.py`, `core/history.py`, `core/project_file.py`: design
  state, snapshots and self-contained .cf3d assets. Mesh assets are shared in
  snapshots rather than deep-copied on every Undo.
- `core/planar_operations.py`: XY silhouette Booleans and signed offsets,
  returning Z0-topped, independently triangulated 2.5D shapes. Not 3D mesh
  Booleans.
- `cam/`: cutter-aware toolpath generation, GRBL post, fixture-aware preflight
  and process workers. Toolpaths use stock-bottom-left XY0 and stock-top Z0.
- `rust/`: tested native raster/contact kernels; Python reference
  implementations remain available for comparison.

CPU-heavy CAM and mesh work must not run in the GUI event loop; the existing
background thread/process pipeline presents progress and applies validated
results on the Qt thread. Do not move Qt widget mutations into a worker.
Actual export must run mandatory preflight and split cutter stages for GRBL.

## Checks before merging

```bash
ruff check src tests
pytest -q
cargo fmt --manifest-path rust/Cargo.toml --check
cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path rust/Cargo.toml
```

The CI matrix runs Python 3.12 and 3.14. For UI tests, the
`tests/conftest.py` offscreen/software-OpenGL setup is required. Verify real
interaction, project save/reload and Undo/Redo when changing an interactive
tool, and geometry/motion/preflight tests when changing machinable results.
