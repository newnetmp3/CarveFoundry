"""Browser-inspired Beta2 desktop workspaces over existing CAM and project services.

The panels are views on the canonical project, Python/Rust background workers,
machine profiles and export safety checks. No second CAM engine or job state.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
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

from .stock_simulation import stock_image
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
        self.machining_setup_summary = self._machine_note(
            "Stock and machine readiness", name="BetaSetupSummary"
        )
        setup.addWidget(self.machining_setup_summary)
        setup.addWidget(self._machine_note(
            "Fixture top Z is measured relative to stock-top Z0, not bed height. "
            "For a bed-mounted 23 mm fence, enter 23 mm minus stock thickness."
        ))
        setup.addStretch()

        operations.addWidget(self._machine_note(
            "Select an operation to edit it here. The same Python/Rust CAM "
            "process handles calculation in both Beginner and Advanced modes."
        ))
        operations.addWidget(self._machine_note(
            "Operation type", name="BetaSectionTitle"
        ))
        self.machining_operation_picker = QComboBox()
        self.machining_operation_picker.setObjectName("BetaOperationPicker")
        self.machining_operation_picker.setAccessibleName("New cutter operation")
        for op in (
            "profile", "silhouette", "pocket", "surface", "vcarve",
            "engrave", "drill", "center_drill", "rough", "finish",
            "height_map", "rest", "waterline",
        ):
            self.machining_operation_picker.addItem(self._cam_operation_title(op), op)
        self.machining_operation_picker.setCurrentIndex(
            max(0, self.machining_operation_picker.findData(self._active_cam_operation))
        )
        self.machining_operation_picker.activated.connect(
            self._select_machine_operation
        )
        operations.addWidget(self.machining_operation_picker)
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
            "Review planned toolpaths, simulate the posted NC, then run "
            "preflight. Physical fixtures and machine offsets require your inspection."
        ))
        self.machining_job_summary = self._machine_note(
            "No generated operations.", name="BetaJobSummary"
        )
        review.addWidget(self.machining_job_summary)
        overlays = QHBoxLayout()
        self.machining_paths_toggle = QPushButton("Show toolpaths")
        self.machining_paths_toggle.setCheckable(True)
        self.machining_paths_toggle.setObjectName("BetaPathOverlay")
        self.machining_paths_toggle.clicked.connect(
            lambda _checked=False: self._toggle_toolpaths_view()
        )
        overlays.addWidget(self.machining_paths_toggle)
        self.machining_rapids_toggle = QPushButton("Show rapid moves")
        self.machining_rapids_toggle.setCheckable(True)
        self.machining_rapids_toggle.setObjectName("BetaPathOverlay")
        self.machining_rapids_toggle.clicked.connect(
            lambda _checked=False: self._toggle_rapids_view()
        )
        overlays.addWidget(self.machining_rapids_toggle)
        review.addLayout(overlays)
        self.machining_review_buttons = []
        for caption, callback in (
            ("Preview toolpaths", self._preview_toolpaths),
            ("Simulate verified NC stock", self._simulate_stock_in_workspace),
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
        review.addWidget(self._machine_note(
            "Stock simulation quality", name="BetaSectionTitle"
        ))
        sample_row = QHBoxLayout()
        sample_row.addWidget(QLabel("XY sample spacing"))
        self.machining_sample_spacing = QDoubleSpinBox()
        self.machining_sample_spacing.setObjectName("BetaStockSampleSpacing")
        self.machining_sample_spacing.setRange(0.1, 10.0)
        self.machining_sample_spacing.setDecimals(2)
        self.machining_sample_spacing.setSingleStep(0.25)
        self.machining_sample_spacing.setValue(0.75)
        self.machining_sample_spacing.setSuffix(" mm")
        self.machining_sample_spacing.setToolTip(
            "Smaller samples improve visible detail but use more memory and time."
        )
        sample_row.addWidget(self.machining_sample_spacing)
        review.addLayout(sample_row)
        self.machining_verify_posted_nc = QCheckBox(
            "Verify posted G-code before simulation (recommended)"
        )
        self.machining_verify_posted_nc.setObjectName("BetaSimPostedNC")
        self.machining_verify_posted_nc.setChecked(True)
        self.machining_verify_posted_nc.setToolTip(
            "The existing verifier decodes the actual post-processed NC and "
            "checks its motion before running the stock sweep."
        )
        review.addWidget(self.machining_verify_posted_nc)
        self.machining_stock_summary = self._machine_note(
            "Run stock simulation to see estimated remaining material.",
            name="BetaStockSummary",
        )
        review.addWidget(self.machining_stock_summary)
        self.machining_stock_image = QLabel()
        self.machining_stock_image.setObjectName("BetaStockImage")
        self.machining_stock_image.setMinimumHeight(175)
        self.machining_stock_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.machining_stock_image.setText("Stock preview appears here")
        review.addWidget(self.machining_stock_image)
        self.machining_stock_deviations = QCheckBox(
            "Highlight residual material (blue) and gouges (red)"
        )
        self.machining_stock_deviations.setObjectName("BetaStockDeviations")
        self.machining_stock_deviations.setEnabled(False)
        self.machining_stock_deviations.toggled.connect(
            self._render_inline_stock_image
        )
        review.addWidget(self.machining_stock_deviations)
        self.machining_stock_details = QPushButton("Open full-size stock viewer")
        self.machining_stock_details.setEnabled(False)
        self.machining_stock_details.clicked.connect(
            self._open_stock_details
        )
        review.addWidget(self.machining_stock_details)
        self._beta_stock_result = None
        self._beta_stock_fingerprint = None
        self._beta_stock_posted_nc = False
        review.addWidget(self._machine_note(
            "Simulation is sampled 2.5D stock, not exact volumetric cutting. "
            "It cannot detect cutter holders, runout, or unrecorded clamps."
        ))
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
        self.machining_export_summary = self._machine_note(
            "Generate toolpaths and run preflight before export.",
            name="BetaExportSummary",
        )
        export.addWidget(self.machining_export_summary)
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
        self.machining_verify_posted_nc.setVisible(not beginner)
        if beginner:
            self.machining_verify_posted_nc.setChecked(True)
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
            self._active_cam_operation,
            repr(self.tool_combo.currentData()),
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

    def _select_machine_operation(self, index: int) -> None:
        """Pick a real CAM operation; specialized cuts require Advanced mode."""
        if self._machining_busy():
            return
        operation = self.machining_operation_picker.itemData(index)
        if not isinstance(operation, str) or not operation:
            return
        if operation not in {
            "profile", "pocket", "vcarve", "engrave", "rough", "finish",
        } and self.experience_mode.currentText() == "Beginner":
            self.experience_mode.setCurrentText("Advanced")
        self._select_cam_operation(operation)
        self._open_inline_cam_form()

    def _simulate_stock_in_workspace(self) -> None:
        """Run existing background simulation without an extra settings dialog."""
        if self._machining_busy() or not self.project.toolpaths:
            return
        posted = self.machining_verify_posted_nc.isChecked()
        started = self._run_stock_removal(
            spacing_mm=self.machining_sample_spacing.value(),
            posted_nc=posted,
        )
        if started:
            self._beta_stock_result = None
            self._beta_stock_fingerprint = None
            self.machining_stock_image.clear()
            self.machining_stock_image.setText("Calculating stock removal…")
            self.machining_stock_summary.setText(
                "Verifying posted NC and simulating removal in the background…"
                if posted else
                "Simulating planned toolpaths in the background (not posted NC)…"
            )
            self.machining_stock_details.setEnabled(False)
            self.machining_stock_deviations.setEnabled(False)
            self.machining_tabs.setCurrentIndex(2)

    def _show_stock_removal_result(self, result, *, posted_nc: bool = False) -> None:
        """Reuse the native stock-sweep result; show inline only in Machine."""
        if (
            not hasattr(self, "machining_tabs")
            or self.workspace_mode.currentText() != "Machine"
        ):
            super()._show_stock_removal_result(result, posted_nc=posted_nc)
            return
        self._beta_stock_result = result
        self._beta_stock_fingerprint = self._guided_job_fingerprint()
        self._beta_stock_posted_nc = posted_nc
        uncut, gouged, compared = result.deviation_counts()
        identity = "Verified posted NC" if posted_nc else "Planned toolpaths only"
        detail = (
            f"{uncut:,} residual / {gouged:,} gouged of "
            f"{compared:,} model samples (±0.15 mm)" if compared else
            "Model surface comparison unavailable"
        )
        self.machining_stock_summary.setText(
            f"{identity} · {result.grid_spacing_mm:.2f} mm sample grid · "
            f"{result.removed_volume_cm3:.2f} cm³ estimated removed · "
            f"{len(result.stages)} cutter stages.\n{detail}\n"
            "Sampled stock cannot verify holders, actual fixturing, or work offsets."
        )
        self.machining_stock_deviations.setEnabled(compared > 0)
        self.machining_stock_deviations.setChecked(compared > 0)
        self.machining_stock_details.setEnabled(True)
        self._render_inline_stock_image()
        self.machining_tabs.setCurrentIndex(2)

    def _render_inline_stock_image(self, _checked: bool = False) -> None:
        result = getattr(self, "_beta_stock_result", None)
        if result is None:
            return
        image = stock_image(
            result, deviations=self.machining_stock_deviations.isChecked()
        )
        width = max(240, min(self.machining_stock_image.width() - 14, 640))
        pixmap = QPixmap.fromImage(image).scaled(
            width, 340,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.machining_stock_image.setPixmap(pixmap)

    def _open_stock_details(self) -> None:
        """Offer the existing high-resolution viewer for close inspection."""
        result = self._beta_stock_result
        if result is None:
            return
        if self._beta_stock_fingerprint != self._guided_job_fingerprint():
            self._refresh_machining_panel()
            return
        super()._show_stock_removal_result(
            result, posted_nc=self._beta_stock_posted_nc,
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
        form.generation_fields["mode"].currentTextChanged.connect(
            lambda mode: self.experience_mode.setCurrentText(
                "Beginner" if mode == "Simple" else "Advanced"
            )
        )
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
        self.machining_operation_picker.setEnabled(not busy)
        selected_index = self.machining_operation_picker.findData(
            self._active_cam_operation
        )
        if selected_index >= 0 and selected_index != self.machining_operation_picker.currentIndex():
            self.machining_operation_picker.setCurrentIndex(selected_index)
        for overlay in (self.machining_paths_toggle, self.machining_rapids_toggle):
            overlay.setEnabled(has_paths)
        self.machining_paths_toggle.setChecked(self.viewport.toolpaths_visible)
        self.machining_rapids_toggle.setChecked(self.viewport.rapids_visible)
        self.machining_sample_spacing.setEnabled(not busy)
        self.machining_verify_posted_nc.setEnabled(not busy)
        self.machining_setup_sheet.setEnabled(has_paths and not busy)
        stock = self.project.stock
        machine = self._active_machine_profile()
        self.machining_setup_summary.setText(
            f"Stock {stock.width_mm:g} × {stock.height_mm:g} × "
            f"{stock.thickness_mm:g} mm · XY0 bottom-left · Z0 stock top.\n"
            f"Machine: {machine.name} "
            f"({'confirmed' if stages[1][2] else 'needs operator confirmation'}). "
            f"Fixtures: {len(self.project.fixtures)}."
        )
        self.machining_export_summary.setText(
            "Planned-motion preflight passed for this exact setup. The export "
            "step independently verifies posted NC. Confirm workholding and "
            "probe stock-top Z0 on each cutter change."
            if verified else
            "Export locked until the current setup passes planned-motion "
            "preflight. Run Review → CNC preflight."
        )
        if (
            self._beta_stock_result is not None
            and self._beta_stock_fingerprint != self._guided_job_fingerprint()
        ):
            self._beta_stock_result = None
            self._beta_stock_fingerprint = None
            self.machining_stock_image.clear()
            self.machining_stock_image.setText("Stock simulation is out of date")
            self.machining_stock_summary.setText(
                "Stock, job, or machine settings changed. Simulate the current "
                "posted NC again before relying on this preview."
            )
            self.machining_stock_details.setEnabled(False)
            self.machining_stock_deviations.setEnabled(False)
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
            cutter_stages = sum(
                index == 0 or path.cutter != self.project.toolpaths[index - 1].cutter
                for index, path in enumerate(self.project.toolpaths)
            )
            cutting_minutes = sum(
                path.estimated_cutting_minutes for path in self.project.toolpaths
            )
            self.machining_job_summary.setText(
                f"{len(snapshot)} operations · {cutter_stages} cutter "
                f"stage(s) · {cutting_minutes:.1f} min cutting (estimate)."
                if has_paths else "No generated operations yet."
            )
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
