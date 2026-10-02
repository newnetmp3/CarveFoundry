"""Browser-inspired Beta2 desktop workspaces over existing CAM and project services.

The panels are views on the canonical project, Python/Rust background workers,
machine profiles and export safety checks. No second CAM engine or job state.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .workspace_icons import workspace_icon


class BetaWorkspaceMixin:
    """Web-like Design/Machine UI; delegates every machining action."""

    def _build_workspace_switcher(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("BetaWorkspaceBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(12)
        badge = QLabel("BETA 2")
        badge.setObjectName("BetaWorkspaceBadge")
        layout.addWidget(badge)
        layout.addWidget(QLabel("Workspace"))
        self.workspace_mode = QComboBox()
        self.workspace_mode.setObjectName("BetaWorkspacePicker")
        self.workspace_mode.setAccessibleName("Workspace")
        self.workspace_mode.addItems(["Design", "Machine"])
        layout.addWidget(self.workspace_mode)
        self.workspace_hint = QLabel("Design your part, then prepare your machining job.")
        self.workspace_hint.setObjectName("BetaWorkspaceHint")
        self.workspace_hint.setWordWrap(True)
        layout.addWidget(self.workspace_hint, 1)
        layout.addWidget(QLabel("Experience"))
        self.experience_mode = QComboBox()
        self.experience_mode.setObjectName("BetaExperiencePicker")
        self.experience_mode.setAccessibleName("Experience level")
        self.experience_mode.addItems(["Beginner", "Advanced"])
        layout.addWidget(self.experience_mode)
        return bar

    @staticmethod
    def _machine_tab_layout(tabs: QTabWidget, name: str) -> QVBoxLayout:
        """Create scrollable content; keep the actual Qt viewport outside scroll."""
        scroll = QScrollArea(tabs)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        body = QWidget(scroll)
        body.setObjectName("BetaMachineTabBody")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(11, 12, 11, 15)
        layout.setSpacing(10)
        scroll.setWidget(body)
        tabs.addTab(scroll, workspace_icon(name.split("·")[-1].strip().lower()), name)
        return layout

    @staticmethod
    def _machine_note(text: str, *, name: str = "BetaMachineNote") -> QLabel:
        label = QLabel(text)
        label.setObjectName(name)
        label.setWordWrap(True)
        label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        return label

    def _init_beta_workspace(self) -> None:
        dock = QDockWidget("Machining workspace", self)
        dock.setObjectName("BetaMachiningDock")
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
        )
        dock.setMinimumWidth(340)
        frame = QWidget(dock)
        frame.setObjectName("BetaMachineFrame")
        root = QVBoxLayout(frame)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        heading = QWidget(frame)
        heading.setObjectName("BetaMachineHeading")
        head = QVBoxLayout(heading)
        head.setContentsMargins(12, 12, 12, 10)
        self.machining_intro = self._machine_note(
            "Setup → Operations → Review → Export. "
            "XY0 is stock bottom-left; Z0 is the top of the material."
        )
        head.addWidget(self.machining_intro)
        progress_row = QHBoxLayout()
        self.machining_progress = QProgressBar()
        self.machining_progress.setObjectName("BetaMachineProgress")
        self.machining_progress.setRange(0, 8)
        self.machining_progress.setFormat("%v of %m checks")
        self.machining_progress.setToolTip(
            "Software input readiness only. This is NOT a physical safety inspection."
        )
        progress_row.addWidget(self.machining_progress, 1)
        self.machining_next = QPushButton("Next step")
        self.machining_next.setObjectName("BetaMachineNext")
        self.machining_next.clicked.connect(self._next_machining_step)
        progress_row.addWidget(self.machining_next)
        head.addLayout(progress_row)
        self.machining_status = self._machine_note(
            "Choose a setup task to begin.", name="BetaMachineStatus"
        )
        head.addWidget(self.machining_status)
        root.addWidget(heading)

        tabs = QTabWidget(frame)
        tabs.setObjectName("BetaMachiningTabs")
        tabs.setDocumentMode(True)
        self.machining_tabs = tabs
        setup = self._machine_tab_layout(tabs, "1 · Setup")
        operations = self._machine_tab_layout(tabs, "2 · Operations")
        review = self._machine_tab_layout(tabs, "3 · Review")
        export = self._machine_tab_layout(tabs, "4 · Export")

        setup.addWidget(self._machine_note(
            "Set stock size and work zero; verify machine travel and physical "
            "fixtures before generating any operation."
        ))
        self.machining_steps = []
        commands = (
            ("Stock / work zero", self._focus_stock_section),
            ("Machine setup", self._show_beginner_machine_setup),
            ("Clamps / fences", self._fixture_editor),
            ("Edit design", self._show_layers_popup),
            ("Edit / generate operation", self._open_inline_cam_form),
            ("Review job order", self._show_job_planner),
            ("Run CNC preflight", self._preflight_toolpaths),
            ("Export per-cutter G-code", self._export_gcode),
        )
        for index, (caption, callback) in enumerate(commands):
            button = QPushButton(caption)
            button.setObjectName(f"MachiningStep{index}")
            button.setIcon(workspace_icon((
                "stock", "machine", "fixtures", "layers",
                "operations", "review", "preflight", "export",
            )[index]))
            button.clicked.connect(
                lambda _checked=False, i=index, fn=callback: self._run_machining_step(i, fn)
            )
            self.machining_steps.append(button)
            if index < 4:
                setup.addWidget(button)
            elif index == 4:
                operations.addWidget(button)
            elif index in {5, 6}:
                review.addWidget(button)
            else:
                export.addWidget(button)
        setup.addWidget(self._machine_note(
            "Fixture top Z is measured relative to stock-top Z0, not bed height. "
            "For a bed-mounted 23 mm fence, enter 23 mm minus stock thickness."
        ))
        setup.addStretch()

        operations.addWidget(self._machine_note(
            "Add or edit a cutter stage without leaving the machining workspace. "
            "Generate runs the existing background CAM process."
        ))
        self.machining_form_prompt = self._machine_note(
            "Choose 'Edit / generate operation' to show the full CAM form here."
        )
        operations.addWidget(self.machining_form_prompt)
        self.machining_form_host = QWidget()
        self.machining_form_host.setObjectName("BetaEmbeddedCamHost")
        self.machining_form_layout = QVBoxLayout(self.machining_form_host)
        self.machining_form_layout.setContentsMargins(0, 0, 0, 0)
        self.machining_form_layout.setSpacing(0)
        operations.addWidget(self.machining_form_host)
        self._machining_embedded_dialog = None
        self.machining_form_host.hide()

        operations.addWidget(self._machine_note("Cutter operations · export order", name="BetaSectionTitle"))
        self.machining_operations = QListWidget()
        self.machining_operations.setAccessibleName("Machining operations in export order")
        self.machining_operations.setObjectName("BetaMachiningOperations")
        self.machining_operations.setMinimumHeight(110)
        self.machining_operations.setMaximumHeight(185)
        operations.addWidget(self.machining_operations)
        self.machining_edit_bar = QWidget()
        edit = QHBoxLayout(self.machining_edit_bar)
        edit.setContentsMargins(0, 0, 0, 0)
        self.machining_edit_buttons = []
        for caption, direction in (("Move up", -1), ("Move down", 1), ("Remove", 0)):
            button = QPushButton(caption)
            button.clicked.connect(
                lambda _checked=False, delta=direction: self._edit_machining_operation(delta)
            )
            edit.addWidget(button)
            self.machining_edit_buttons.append(button)
        operations.addWidget(self.machining_edit_bar)
        operations.addStretch()

        review.addWidget(self._machine_note(
            "Review the actual planned motion, remaining stock and cutter order. "
            "Preflight runs separately in the background; it cannot see physical clamps."
        ))
        self.machining_review_buttons = []
        for caption, callback in (
            ("Preview toolpaths", self._preview_toolpaths),
            ("Simulate removed stock", self._simulate_stock_removal),
        ):
            button = QPushButton(caption)
            button.setIcon(workspace_icon(
                "simulate" if "Simulate" in caption else "review"
            ))
            button.clicked.connect(
                lambda _checked=False, fn=callback: self._run_machining_step(5, fn)
            )
            review.addWidget(button)
            self.machining_review_buttons.append(button)
        self.machining_preflight_state = self._machine_note(
            "No preflight result for this job.", name="BetaPreflightState"
        )
        review.addWidget(self.machining_preflight_state)
        self.machining_preflight_report = QPlainTextEdit()
        self.machining_preflight_report.setObjectName("BetaPreflightReport")
        self.machining_preflight_report.setAccessibleName("CNC preflight report")
        self.machining_preflight_report.setReadOnly(True)
        self.machining_preflight_report.setPlaceholderText(
            "Run CNC preflight to see the detailed report here."
        )
        self.machining_preflight_report.setMinimumHeight(160)
        review.addWidget(self.machining_preflight_report)
        review.addStretch()

        export.addWidget(self._machine_note(
            "Export is enabled only after preflight succeeds for the current "
            "machine, stock, fixtures and toolpaths."
        ))
        self.machining_setup_sheet = QPushButton("Print job setup sheet")
        self.machining_setup_sheet.setIcon(workspace_icon("job_sheet"))
        self.machining_setup_sheet.clicked.connect(
            lambda _checked=False: self._run_machining_step(5, self._export_setup_sheet)
        )
        export.addWidget(self.machining_setup_sheet)
        export.addWidget(self._machine_note(
            "A new NC file is produced for each cutter stage. Stop the machine, "
            "change cutters, and RE-PROBE stock-top Z0 before each file. "
            "Inspect physical fences, clamps, spindle and travel limits before cutting.",
            name="BetaExportWarning",
        ))
        export.addStretch()

        root.addWidget(tabs, 1)
        last_tab = self._settings.value("beta2/machine_tab", 0, type=int)
        tabs.setCurrentIndex(max(0, min(int(last_tab), tabs.count() - 1)))
        tabs.currentChanged.connect(
            lambda index: self._settings.setValue("beta2/machine_tab", index)
        )
        dock.setWidget(frame)
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
        if dock.isVisible():
            self._machining_timer.start()

    def _set_beta_workspace(self, mode: str) -> None:
        machine = mode == "Machine"
        self.machining_dock.setVisible(machine)
        if machine and self._beta_workspace_previous == "Design":
            self._design_inspector_visible = not self.properties_panel.isHidden()
        inspector_visible = not machine and self._design_inspector_visible
        self.properties_panel.setVisible(inspector_visible)
        self.inspector_button.setChecked(inspector_visible)
        # The compact viewport bar follows the workspace instead of
        # displaying both editing and machining commands at once.
        self.generate_toolpaths_button.setVisible(machine)
        self.cam_status_label.setVisible(machine)
        for widget in (
            self.layers_button,
            self.object_selector,
            self._viewport_import_button,
            self.inspector_button,
        ):
            widget.setVisible(not machine)
        self._beta_workspace_previous = mode
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
        self.machining_progress.setVisible(beginner)
        self.workspace_hint.setText(
            "Design your part → Machine: setup, operations, review, export."
            if beginner else "Design and machining share one project and selection."
        )
        form = getattr(self, "_machining_embedded_dialog", None)
        if form is not None and not form.isHidden():
            combo = form.generation_fields.get("mode")
            if isinstance(combo, QComboBox):
                combo.setCurrentText("Simple" if beginner else "Advanced")
        if persist:
            self._settings.setValue("beta2/experience", mode)
            self._settings.setValue("cam/simple_mode", beginner)
        self._refresh_machining_panel()

    def _cam_form_context_key(self) -> tuple:
        """Cheap immutable fingerprints; never hash giant meshes on the Qt thread."""
        return (
            id(self.project),
            getattr(self, "_history_state_id", None),
            (
                self.project.stock.width_mm,
                self.project.stock.height_mm,
                self.project.stock.thickness_mm,
                self.project.stock.xy_zero,
            ),
            tuple(
                (item.item_id, id(item), id(item.mesh), item.visible,
                 repr(item.transform))
                for item in self.project.items
            ),
            tuple(
                (id(path), len(path.moves), path.cutter)
                for path in self.project.toolpaths
            ),
            tuple(repr(fixture) for fixture in self.project.fixtures),
            repr(self._active_machine_profile()),
        )

    def _open_cam_generation_workspace(self) -> None:
        """Route the visible viewport CTA to Machine, not another window."""
        if not hasattr(self, "machining_dock"):
            self._show_toolpath_generation_dialog()
            return
        if self.workspace_mode.currentText() != "Machine":
            self.workspace_mode.setCurrentText("Machine")
        self._open_inline_cam_form()

    def _open_inline_cam_form(self) -> None:
        """Render the canonical CAM options directly inside the Machine tab."""
        if self._machining_busy():
            return
        existing = self._machining_embedded_dialog
        if existing is not None:
            self.machining_form_layout.removeWidget(existing)
            existing.hide()
            existing.deleteLater()
        self._machining_form_snapshot = self._cam_form_context_key()
        form = self._build_toolpath_generation_dialog(embedded=True)
        self._machining_embedded_dialog = form
        self.machining_form_layout.addWidget(form)
        self.machining_form_host.show()
        self.machining_form_prompt.hide()
        self.machining_tabs.setCurrentIndex(1)
        form.finished.connect(
            lambda _result: self._on_inline_cam_finished(form)
        )
        form.show()

    def _on_inline_cam_finished(self, form) -> None:
        if self._machining_embedded_dialog is form:
            self.machining_form_prompt.setText(
                "Generation submitted. Open the operation form again to add another stage."
            )
            self.machining_form_prompt.show()
            self.machining_form_host.hide()

    def _next_machining_step(self) -> None:
        stages = self._guided_stage_status()
        index = next(
            (i for i, (_title, _detail, ready, allowed) in enumerate(stages)
             if not ready and allowed),
            7,
        )
        self.machining_tabs.setCurrentIndex(
            0 if index < 4 else 1 if index == 4 else 2 if index < 7 else 3
        )
        self.machining_steps[index].click()

    def _machining_busy(self) -> bool:
        return self._background_job is not None or (
            self._import_thread is not None and self._import_thread.isRunning()
        )

    def _run_machining_step(self, index: int, callback) -> None:
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

    def _handle_beta_preflight_result(self, payload: object) -> bool:
        """Mirror the real background preflight report inline; never bypass it."""
        if not hasattr(self, "machining_preflight_report"):
            return False
        report = str(payload["report"])
        self.machining_preflight_report.setPlainText(report)
        self.machining_tabs.setCurrentIndex(2)
        self._refresh_machining_panel()
        return self.workspace_mode.currentText() == "Machine"

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
             if not ready and allowed),
            7,
        )
        self.machining_next.setText(f"Next: {self.machining_steps[next_index].text()}")
        self.machining_next.setEnabled(stages[next_index][3] and not busy)
        self.machining_progress.setValue(sum(ready for _, _, ready, _ in stages))
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
        self.machining_setup_sheet.setEnabled(has_paths and not busy)
        if verified:
            self.machining_preflight_state.setText(
                "PASS for current stock, machine, fixtures and toolpaths. "
                "Review the full report and verify the physical machine."
            )
        elif self.machining_preflight_report.toPlainText():
            self.machining_preflight_state.setText(
                "NOT CLEARED. Failed preflight or job changed since this report. "
                "Run CNC preflight again before exporting."
            )
        else:
            self.machining_preflight_state.setText(
                "Not yet verified. Run CNC preflight before exporting."
            )
        # Invalidate a visible docked CAM form as soon as anything it depends
        # on changes. The Generate handler also checks immediately on click.
        form = getattr(self, "_machining_embedded_dialog", None)
        if (
            form is not None and not form.isHidden()
            and self._machining_form_snapshot != self._cam_form_context_key()
        ):
            form.generation_fields["generate"].setEnabled(False)
            if not busy:
                self.machining_status.setText(
                    "CAM settings are out of date. Reopen Edit / generate operation."
                )
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
                self.machining_operations.setCurrentRow(
                    max(0, min(selected, len(snapshot) - 1))
                )
            self._machining_paths_snapshot = snapshot
