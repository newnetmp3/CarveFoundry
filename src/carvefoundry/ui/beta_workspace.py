"""Beta2 workspace presentation over the shared project and machining commands."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class BetaWorkspaceMixin:
    """Design/Machine surfaces; never owns a second project or CAM pipeline."""

    def _build_workspace_switcher(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("BetaWorkspaceBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 5, 10, 5)
        badge = QLabel("BETA 2")
        badge.setObjectName("AccentText")
        layout.addWidget(badge)
        self.workspace_mode = QComboBox()
        self.workspace_mode.setAccessibleName("Workspace")
        self.workspace_mode.addItems(["Design", "Machine"])
        layout.addWidget(self.workspace_mode)
        self.workspace_hint = QLabel("Design geometry, then prepare your machining job.")
        self.workspace_hint.setWordWrap(True)
        layout.addWidget(self.workspace_hint, 1)
        layout.addWidget(QLabel("Experience"))
        self.experience_mode = QComboBox()
        self.experience_mode.setAccessibleName("Experience level")
        self.experience_mode.addItems(["Beginner", "Advanced"])
        layout.addWidget(self.experience_mode)
        return bar

    def _init_beta_workspace(self) -> None:
        dock = QDockWidget("Machining job", self)
        dock.setObjectName("BetaMachiningDock")
        dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea)
        dock.setMinimumWidth(300)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        layout = QVBoxLayout(body)
        self.machining_intro = QLabel(
            "Prepare stock and fixtures, generate operations, review the cut, "
            "then preflight and export. Work XY0 is stock bottom-left; Z0 is stock top."
        )
        self.machining_intro.setWordWrap(True)
        layout.addWidget(self.machining_intro)
        self.machining_next = QPushButton("Next step")
        self.machining_next.clicked.connect(self._next_machining_step)
        layout.addWidget(self.machining_next)
        self.machining_status = QLabel()
        self.machining_status.setWordWrap(True)
        layout.addWidget(self.machining_status)
        self.machining_steps = []
        commands = (
            ("Stock / work zero", self._focus_stock_section),
            ("Machine setup", self._show_beginner_machine_setup),
            ("Clamps / fences", self._fixture_editor),
            ("Edit design", self._show_layers_popup),
            ("Add operation", self._calculate_toolpath),
            ("Review job", self._show_job_planner),
            ("Run preflight", self._preflight_toolpaths),
            ("Export G-code", self._export_gcode),
        )
        for index, (caption, callback) in enumerate(commands):
            button = QPushButton(caption)
            button.setObjectName(f"MachiningStep{index}")
            button.clicked.connect(
                lambda _checked=False, i=index, fn=callback: self._run_machining_step(i, fn)
            )
            layout.addWidget(button)
            self.machining_steps.append(button)
        layout.addWidget(QLabel("Operations · export order"))
        self.machining_operations = QListWidget()
        self.machining_operations.setAccessibleName("Machining operations in export order")
        self.machining_operations.setMinimumHeight(110)
        self.machining_operations.setMaximumHeight(200)
        layout.addWidget(self.machining_operations)
        self.machining_edit_bar = QWidget()
        edit = QHBoxLayout(self.machining_edit_bar)
        edit.setContentsMargins(0, 0, 0, 0)
        self.machining_edit_buttons = []
        for caption, direction in (("Up", -1), ("Down", 1), ("Remove", 0)):
            button = QPushButton(caption)
            button.clicked.connect(
                lambda _checked=False, delta=direction: self._edit_machining_operation(delta)
            )
            edit.addWidget(button)
            self.machining_edit_buttons.append(button)
        layout.addWidget(self.machining_edit_bar)
        self.machining_review_buttons = []
        for caption, callback in (
            ("Preview toolpaths", self._preview_toolpaths),
            ("Simulate removed stock", self._simulate_stock_removal),
            ("Print setup sheet", self._export_setup_sheet),
        ):
            button = QPushButton(caption)
            button.clicked.connect(
                lambda _checked=False, fn=callback: self._run_machining_step(5, fn)
            )
            layout.addWidget(button)
            self.machining_review_buttons.append(button)
        note = QLabel(
            "Operations are session-only: regenerate after reopening CF3D. "
            "Export verifies posted motion and splits cutter changes into separate files. "
            "Stop, swap cutter and re-probe Z between files. Check physical setup."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()
        scroll.setWidget(body)
        dock.setWidget(scroll)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self.machining_dock = dock
        self._machining_paths_snapshot = None
        self._design_inspector_visible = not self.properties_panel.isHidden()
        self._beta_workspace_previous = "Design"
        self.workspace_mode.currentTextChanged.connect(self._set_beta_workspace)
        self.experience_mode.currentTextChanged.connect(self._set_beta_experience)
        legacy_mode = (
            "Beginner" if self._settings.value("cam/simple_mode", True, type=bool)
            else "Advanced"
        )
        experience = str(self._settings.value("beta2/experience", legacy_mode))
        if experience not in {"Beginner", "Advanced"}:
            experience = "Beginner"
        self.experience_mode.setCurrentText(experience)
        self._set_beta_experience(experience, persist=False)
        workspace = str(self._settings.value("beta2/workspace", "Design"))
        if workspace not in {"Design", "Machine"}:
            workspace = "Design"
        self.workspace_mode.setCurrentText(workspace)
        self._set_beta_workspace(workspace)
        self._machining_timer = QTimer(self)
        self._machining_timer.setInterval(400)
        self._machining_timer.timeout.connect(self._refresh_machining_panel)
        dock.visibilityChanged.connect(
            lambda visible: self._machining_timer.start() if visible
            else self._machining_timer.stop()
        )

    def _set_beta_workspace(self, mode: str) -> None:
        machine = mode == "Machine"
        self.machining_dock.setVisible(machine)
        if machine and self._beta_workspace_previous == "Design":
            self._design_inspector_visible = not self.properties_panel.isHidden()
        inspector_visible = not machine and self._design_inspector_visible
        self.properties_panel.setVisible(inspector_visible)
        self.inspector_button.setChecked(inspector_visible)
        self._beta_workspace_previous = mode
        # Keep drawing tools and machining controls grouped by task. Commands
        # remain available in the canonical menus and keyboard shortcuts.
        for key in ("cam", "cutter", "machine", "generate", "preview", "preflight", "export"):
            button = self.tool_rail.buttons.get(key)
            if button is not None:
                button.setVisible(machine)
        self._settings.setValue("beta2/workspace", mode)
        self._refresh_machining_panel()

    def _set_beta_experience(self, mode: str, *, persist: bool = True) -> None:
        beginner = mode == "Beginner"
        self.machining_intro.setVisible(beginner)
        self.machining_next.setVisible(beginner)
        self.machining_edit_bar.setVisible(not beginner)
        self.workspace_hint.setText(
            "Design your part → Machine: setup, preview, preflight, export."
            if beginner else "Design and machining share one project and selection."
        )
        if persist:
            self._settings.setValue("beta2/experience", mode)
            self._settings.setValue("cam/simple_mode", beginner)
        self._refresh_machining_panel()

    def _next_machining_step(self) -> None:
        stages = self._guided_stage_status()
        index = next(
            (i for i, (_title, _detail, ready, allowed) in enumerate(stages)
             if not ready and allowed),
            7,
        )
        self.machining_steps[index].click()

    def _machining_busy(self) -> bool:
        return self._background_job is not None or (
            self._import_thread is not None and self._import_thread.isRunning()
        )

    def _run_machining_step(self, index: int, callback) -> None:
        # Recheck on click: a timer's previous enabled state is not authorization
        # to export a changed job or mutate an active worker's inputs.
        if self._machining_busy() or not self._guided_stage_status()[index][3]:
            self._refresh_machining_panel()
            return
        callback()
        self._refresh_machining_panel()

    def _edit_machining_operation(self, direction: int) -> None:
        if self._machining_busy():
            return
        paths = list(self.project.toolpaths)
        row = self.machining_operations.currentRow()
        if not 0 <= row < len(paths):
            return
        if direction:
            target = row + direction
            if not 0 <= target < len(paths):
                return
            paths[row], paths[target] = paths[target], paths[row]
        else:
            paths.pop(row)
        try:
            self._apply_job_plan(paths)
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid machining order", str(exc))
        self._refresh_machining_panel()

    def _refresh_machining_panel(self) -> None:
        if not hasattr(self, "machining_dock"):
            return
        busy = self._machining_busy()
        stages = self._guided_stage_status()
        for button, (title, detail, _ready, allowed) in zip(
            self.machining_steps, stages, strict=True,
        ):
            button.setToolTip(f"{title}\n{detail}")
            button.setEnabled(allowed and not busy)
        next_index = next(
            (i for i, (_title, _detail, ready, allowed) in enumerate(stages)
             if not ready and allowed), 7,
        )
        self.machining_next.setText(f"Next: {self.machining_steps[next_index].text()}")
        self.machining_next.setEnabled(stages[next_index][3] and not busy)
        has_paths = bool(self.project.toolpaths)
        verified = stages[6][2]
        self.machining_status.setText(
            "Operation running…" if busy else
            "Preflight passed for current setup. Ready to export." if verified else
            "Review generated operations and run preflight." if has_paths else
            f"Recalculate: {self._toolpaths_stale_reason}." if self._toolpaths_stale_reason else
            "No operations yet. Set up your stock and add an operation."
        )
        for button in self.machining_review_buttons + self.machining_edit_buttons:
            button.setEnabled(has_paths and not busy)
        snapshot = tuple(id(path) for path in self.project.toolpaths)
        if snapshot != self._machining_paths_snapshot:
            selected = self.machining_operations.currentRow()
            self.machining_operations.clear()
            for index, path in enumerate(self.project.toolpaths, 1):
                self.machining_operations.addItem(
                    f"{index}. {path.name}\n{path.cutter.name} · "
                    f"{path.estimated_cutting_minutes:.1f} min cutting"
                )
            if has_paths:
                self.machining_operations.setCurrentRow(max(0, min(selected, len(snapshot) - 1)))
            self._machining_paths_snapshot = snapshot
