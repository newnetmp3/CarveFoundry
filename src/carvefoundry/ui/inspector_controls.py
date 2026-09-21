"""Compact, scroll-friendly stock and transform Inspector controls.

The workspace and CAM layer use this mixin; Qt widgets own their child
controls and change handlers still resolve to the live main window.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from carvefoundry.core.units import ModelUnits

from .layout_widgets import InspectorSection


class InspectorControlsMixin:
    def _transform_slider_started(self) -> None:
        """The project-history window snapshots one drag for Undo."""

    def _transform_slider_finished(self) -> None:
        """The project-history window commits one drag to Undo."""

    def _transform_axis_input(
        self, spin: QDoubleSpinBox, label: str,
    ) -> QWidget:
        """Precision number box with up/down arrows and a relative scrubber.

        The slider is relative to the value at press, not a fixed coordinate
        range. That keeps +/-100,000 mm Position precise and lets 0.001 mm
        Size be adjusted without assigning an impossible global slider scale.
        """
        row = QWidget()
        row.setMinimumWidth(0)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)
        spin.setMinimumWidth(100)
        spin.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        spin.setAccessibleName(label + " numerical value")
        spin.setToolTip(spin.toolTip() + "\nType precisely, click ▲/▼, or scrub.")
        layout.addWidget(spin, 3)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setObjectName("TransformScrubSlider")
        slider.setRange(-100, 100)
        slider.setValue(0)
        slider.setSingleStep(10)
        slider.setPageStep(10)
        slider.setMinimumWidth(55)
        slider.setAccessibleName(label + " relative scrub slider")
        slider.setToolTip(
            "Drag left/right to change the value relative to its starting "
            "point. Returns to center on release; precise numeric typing "
            "and up/down arrows remain available."
        )
        layout.addWidget(slider, 2)
        baseline = [spin.value()]

        def begin() -> None:
            baseline[0] = spin.value()
            self._transform_slider_started()

        def scrub(delta: int) -> None:
            # At full travel apply ten spin increments in either direction.
            spin.setValue(baseline[0] + delta * spin.singleStep() / 10.0)

        def end() -> None:
            slider.blockSignals(True)
            try:
                slider.setValue(0)
            finally:
                slider.blockSignals(False)
            self._transform_slider_finished()

        slider.sliderPressed.connect(begin)
        slider.valueChanged.connect(scrub)
        slider.sliderReleased.connect(end)
        if not hasattr(self, "transform_scrub_sliders"):
            self.transform_scrub_sliders = []
        self.transform_scrub_sliders.append(slider)
        return row

    def _set_inspector_context_sections(
        self, *, stock: bool = False, text: bool = False,
        transform: bool = False,
    ) -> None:
        """Apply all contextual Inspector sections as one coherent state."""
        self.stock_widget.setVisible(stock)
        self.text_widget.setVisible(text)
        self.transform_widget.setVisible(transform)

    @staticmethod
    def _configured_spin(
        *,
        minimum: float,
        maximum: float,
        decimals: int,
        step: float,
        suffix: str = "",
    ) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(decimals)
        spin.setSingleStep(step)
        spin.setSuffix(suffix)
        spin.setKeyboardTracking(False)
        spin.setMinimumWidth(0)
        spin.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        return spin

    @staticmethod
    def _configure_inspector_form(form: QFormLayout) -> None:
        """Make a form reflow instead of clipping in a narrow inspector."""

        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(6)
        form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setLabelAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )

    @staticmethod
    def _configure_inspector_field(widget: QWidget) -> None:
        widget.setMinimumWidth(0)
        policy = widget.sizePolicy()
        policy.setHorizontalPolicy(QSizePolicy.Policy.Expanding)
        widget.setSizePolicy(policy)

    def _build_stock_controls(self) -> QWidget:
        widget = QWidget()
        widget.setObjectName("StockControls")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 6, 0, 10)
        layout.setSpacing(6)

        heading = QLabel("Stock dimensions")
        heading.setObjectName("SectionHeading")
        layout.addWidget(heading)

        form = QFormLayout()
        self._configure_inspector_form(form)
        layout.addLayout(form)

        self.stock_spins = tuple(
            self._configured_spin(
                minimum=0.1,
                maximum=100000.0,
                decimals=3,
                step=1.0,
                suffix=" mm",
            )
            for _ in range(3)
        )
        for title, spin in zip(
            ("Width", "Height", "Thickness"),
            self.stock_spins,
            strict=True,
        ):
            form.addRow(title, spin)
            spin.valueChanged.connect(self._stock_control_changed)

        return widget

    def _build_transform_controls(self) -> QWidget:
        widget = QWidget()
        widget.setObjectName("TransformControls")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 6, 0, 10)
        layout.setSpacing(6)

        heading = QLabel("Model transform")
        heading.setObjectName("SectionHeading")
        layout.addWidget(heading)

        resize_hint = QLabel(
            "Drag a corner handle around the selected object in the viewport "
            "to resize its XY footprint live. Z/depth stays unchanged."
        )
        resize_hint.setObjectName("Muted")
        resize_hint.setWordWrap(True)
        layout.addWidget(resize_hint)

        self._transform_sections: dict[str, InspectorSection] = {}
        setup_section = InspectorSection(
            "Object & Gizmo Settings", key="setup",
            settings=self._settings, expanded=False,
        )
        self._transform_sections["setup"] = setup_section
        units_form = QFormLayout()
        self._configure_inspector_form(units_form)
        setup_section.content_layout.addLayout(units_form)
        layout.addWidget(setup_section)

        self.source_units_combo = QComboBox()
        for units in ModelUnits:
            self.source_units_combo.addItem(units.display_name, units)
        self._configure_inspector_field(self.source_units_combo)
        self.source_units_combo.currentIndexChanged.connect(
            self._source_units_changed
        )
        units_form.addRow("Model units", self.source_units_combo)

        self.transform_orientation_combo = QComboBox()
        self.transform_orientation_combo.addItem("Global", "global")
        self.transform_orientation_combo.addItem("Local", "local")
        self.transform_orientation_combo.setToolTip(
            "Global uses stock/world XYZ axes. Local rotates the move gizmo "
            "with the selected object."
        )
        self._configure_inspector_field(self.transform_orientation_combo)
        self.transform_orientation_combo.currentIndexChanged.connect(
            self._transform_orientation_changed
        )
        units_form.addRow("Gizmo orientation", self.transform_orientation_combo)

        self.transform_snap_check = QCheckBox("Snap translation")
        self.transform_snap_check.setToolTip(
            "Snap gizmo moves to a fixed increment. Ctrl temporarily enables "
            "snapping during a drag."
        )
        self.transform_snap_check.toggled.connect(
            self._transform_snap_changed
        )
        units_form.addRow("Precision", self.transform_snap_check)

        self.transform_snap_step_spin = QDoubleSpinBox()
        self.transform_snap_step_spin.setRange(0.001, 1000.0)
        self.transform_snap_step_spin.setDecimals(3)
        self.transform_snap_step_spin.setSingleStep(0.5)
        self.transform_snap_step_spin.setSuffix(" mm")
        self.transform_snap_step_spin.setValue(1.0)
        self.transform_snap_step_spin.setToolTip(
            "Translation snapping increment in millimeters."
        )
        self._configure_inspector_field(self.transform_snap_step_spin)
        self.transform_snap_step_spin.valueChanged.connect(
            self._transform_snap_changed
        )
        units_form.addRow("Snap step", self.transform_snap_step_spin)

        self.position_spins = tuple(
            self._configured_spin(
                minimum=-100000.0,
                maximum=100000.0,
                decimals=3,
                step=1.0,
                suffix=" mm",
            )
            for _ in range(3)
        )
        self.rotation_spins = tuple(
            self._configured_spin(
                minimum=-3600.0,
                maximum=3600.0,
                decimals=1,
                step=5.0,
                suffix="°",
            )
            for _ in range(3)
        )
        rotation_planes = (
            ("X", "YZ"),
            ("Y", "XZ"),
            ("Z", "XY"),
        )
        for spin, (axis, plane) in zip(
            self.rotation_spins,
            rotation_planes,
            strict=True,
        ):
            spin.setToolTip(
                f"Rotate around the {axis} axis; motion occurs in the {plane} plane."
            )
            spin.setAccessibleName(f"Rotation around {axis} axis")

        self.size_spins = tuple(
            self._configured_spin(
                minimum=0.001,
                maximum=100000.0,
                decimals=3,
                step=1.0,
                suffix=" mm",
            )
            for _ in range(3)
        )
        for spin, axis in zip(
            self.size_spins,
            ("X", "Y", "Z"),
            strict=True,
        ):
            spin.setToolTip(
                f"Set model Size {axis} directly in millimeters. "
                "Size is measured before rotation."
            )

        self.scale_spins = tuple(
            self._configured_spin(
                minimum=0.001,
                maximum=1000.0,
                decimals=4,
                step=0.05,
            )
            for _ in range(3)
        )

        def add_axis_group(
            key: str,
            title: str,
            spins: tuple[QDoubleSpinBox, ...],
            *,
            expanded: bool,
        ) -> InspectorSection:
            section = InspectorSection(
                title, key=key, settings=self._settings,
                expanded=expanded,
            )
            self._transform_sections[key] = section
            axis_form = QFormLayout()
            self._configure_inspector_form(axis_form)
            for axis, spin in zip(("X", "Y", "Z"), spins, strict=True):
                axis_form.addRow(
                    axis, self._transform_axis_input(spin, title + " " + axis)
                )
                spin.valueChanged.connect(self._transform_control_changed)
            section.content_layout.addLayout(axis_form)
            layout.addWidget(section)
            return section

        add_axis_group(
            "position", "Position · mm", self.position_spins, expanded=True,
        )
        rotation_section = add_axis_group(
            "rotation", "Rotation · degrees", self.rotation_spins,
            expanded=False,
        )

        rotation_note = QLabel(
            "Rotation axes: X → YZ plane   Y → XZ plane   Z → XY plane"
        )
        rotation_note.setObjectName("Muted")
        rotation_note.setWordWrap(True)
        rotation_note.setToolTip(
            "X/Y/Z name the axis being rotated around, not the plane being rotated."
        )
        rotation_section.content_layout.addWidget(rotation_note)

        add_axis_group(
            "size", "Size · mm", self.size_spins, expanded=True,
        )
        add_axis_group(
            "scale", "Scale · factor", self.scale_spins, expanded=False,
        )

        lock_bar = QWidget()
        lock_bar.setMinimumWidth(0)
        lock_layout = QHBoxLayout(lock_bar)
        lock_layout.setContentsMargins(0, 0, 0, 0)
        lock_layout.setSpacing(8)
        lock_layout.addWidget(QLabel("Lock Size / Scale axes"))
        self.lock_axis_checks = tuple(
            QCheckBox(axis)
            for axis in ("X", "Y", "Z")
        )
        for checkbox in self.lock_axis_checks:
            checkbox.setChecked(True)
            checkbox.setToolTip(
                "Locked axes resize proportionally together when Size or Scale changes."
            )
            lock_layout.addWidget(checkbox)
        lock_layout.addStretch(1)
        layout.addWidget(lock_bar)

        action_bar = QWidget()
        action_bar.setMinimumWidth(0)
        action_layout = QHBoxLayout(action_bar)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(6)

        center_button = QPushButton("Center XY")
        center_button.setMinimumWidth(0)
        center_button.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        center_button.clicked.connect(self._center_selected_xy)
        action_layout.addWidget(center_button)

        top_button = QPushButton("Top to Z0")
        top_button.setMinimumWidth(0)
        top_button.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        top_button.clicked.connect(self._top_selected_to_surface)
        action_layout.addWidget(top_button)
        layout.addWidget(action_bar)

        apply_bar = QWidget()
        apply_bar.setMinimumWidth(0)
        apply_layout = QHBoxLayout(apply_bar)
        apply_layout.setContentsMargins(0, 0, 0, 0)
        apply_layout.setSpacing(6)

        apply_scale_button = QPushButton("Apply Scale")
        apply_scale_button.setMinimumWidth(0)
        apply_scale_button.setToolTip(
            "Bake the selected object's current scale into its mesh and reset "
            "Scale to 1,1,1. Useful before CAM/export."
        )
        apply_scale_button.clicked.connect(self._apply_selected_scale)
        apply_layout.addWidget(apply_scale_button)

        apply_rotation_scale_button = QPushButton("Apply R+S")
        apply_rotation_scale_button.setMinimumWidth(0)
        apply_rotation_scale_button.setToolTip(
            "Bake rotation and scale into the selected mesh while preserving "
            "its placed position."
        )
        apply_rotation_scale_button.clicked.connect(
            self._apply_selected_rotation_scale
        )
        apply_layout.addWidget(apply_rotation_scale_button)
        layout.addWidget(apply_bar)

        reset_button = QPushButton("Reset Transform")
        reset_button.setMinimumWidth(0)
        reset_button.clicked.connect(self._reset_selected_transform)
        layout.addWidget(reset_button)

        widget.setVisible(False)
        return widget

