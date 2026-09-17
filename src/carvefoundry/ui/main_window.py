from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from ..core.importer import ImportFileError, inspect_import_file
from ..core.mesh import MeshAsset
from ..core.project import Project, ProjectItem
from ..core.project_file import (
    PROJECT_SUFFIX,
    ProjectFileError,
    load_project,
    save_project,
)
from ..core.tools import DEFAULT_TOOLS
from ..core.units import ModelUnits
from .ribbon import Ribbon
from .viewport import MeshViewport


class Panel(QFrame):
    def __init__(self, title: str):
        super().__init__()
        self.setObjectName("WorkspacePanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header = QLabel(title)
        header.setObjectName("PanelHeader")
        header.setContentsMargins(10, 8, 10, 8)
        layout.addWidget(header)
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.body, 1)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.project = Project()
        self.project_path: Path | None = None
        self._updating_transform_controls = False
        self._updating_stock_controls = False
        self._updating_project_list = False
        self.setWindowTitle("CarveFoundry")
        self.resize(1500, 900)
        self.setMinimumSize(1050, 650)

        root = QWidget()
        root.setObjectName("AppRoot")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_brand_row())
        self.ribbon = Ribbon()
        self._populate_ribbon()
        layout.addWidget(self.ribbon)
        layout.addWidget(self._build_workspace(), 1)

        status = QStatusBar()
        status.showMessage("Ready — no machine connected")
        self.setStatusBar(status)

    def _build_brand_row(self) -> QWidget:
        row = QWidget()
        row.setObjectName("TitleBar")
        row.setFixedHeight(42)
        line = QHBoxLayout(row)
        line.setContentsMargins(14, 0, 14, 0)
        line.setSpacing(5)
        name = QLabel("Carve")
        name.setObjectName("AppName")
        accent = QLabel("Foundry")
        accent.setObjectName("AppAccent")
        line.addWidget(name)
        line.addWidget(accent)
        self.project_title_label = QLabel("  •  Untitled Project")
        self.project_title_label.setObjectName("Muted")
        line.addWidget(self.project_title_label)
        line.addStretch(1)
        mode = QLabel("DESIGN + CAM")
        mode.setObjectName("AccentText")
        line.addWidget(mode)
        return row

    def _populate_ribbon(self) -> None:
        file_page = self.ribbon.add_page("File")
        project = file_page.add_group("Project")
        project.add_button("New", self._new_project)
        project.add_button("Open", self._open_project)
        project.add_button("Save", self._save_project, primary=True)
        project.add_button("Save As", self._save_project_as)
        exchange = file_page.add_group("Import / Export")
        exchange.add_button("Import", self._import_file, primary=True)
        exchange.add_button("Export G-code")

        home = self.ribbon.add_page("Home")
        edit = home.add_group("Edit")
        for title in ("Undo", "Redo", "Cut", "Copy", "Paste"):
            edit.add_button(title)
        edit.add_button("Delete", self._delete_selected_item)
        arrange = home.add_group("Arrange")
        for title in ("Align", "Center", "Group", "Ungroup"):
            arrange.add_button(title)
        arrange.add_button("Duplicate", self._duplicate_selected_item)
        layers = home.add_group("Layers")
        layers.add_button("Move Up", lambda: self._move_selected_item(-1))
        layers.add_button("Move Down", lambda: self._move_selected_item(1))

        create = self.ribbon.add_page("Create")
        shapes = create.add_group("Shapes")
        for title in ("Rectangle", "Ellipse", "Polygon", "Line", "Text"):
            shapes.add_button(title)
        vectors = create.add_group("Vectors")
        vectors.add_button("Pen")
        vectors.add_button("Trace Image")

        import_page = self.ribbon.add_page("Import")
        files = import_page.add_group("Design Files")
        files.add_button("SVG", lambda: self._import_file("SVG"))
        files.add_button("DXF", lambda: self._import_file("DXF"))
        files.add_button("STL", lambda: self._import_file("STL"), primary=True)
        files.add_button("Image", lambda: self._import_file("Image"))
        files.add_button("G-code", lambda: self._import_file("G-code"))

        carve = self.ribbon.add_page("Carve")
        operations = carve.add_group("2D / 2.5D Operations")
        for title in ("Profile", "Pocket", "V-Carve", "Engrave", "Drill", "Tabs"):
            operations.add_button(title)
        calculate = carve.add_group("Toolpaths")
        calculate.add_button("Calculate", primary=True)
        calculate.add_button("Preview")

        three_d = self.ribbon.add_page("3D")
        mesh = three_d.add_group("Mesh")
        for title in ("Orient", "Scale", "Position"):
            mesh.add_button(title, self._focus_transform_controls)
        mesh.add_button("Center XY", self._center_selected_xy)
        mesh.add_button("Top to Z0", self._top_selected_to_surface)
        strategies = three_d.add_group("Strategies")
        for title in ("Rough", "Finish", "Rest", "Waterline"):
            strategies.add_button(title, primary=title == "Finish")

        tools = self.ribbon.add_page("Tools")
        library = tools.add_group("Tool Library")
        library.add_button("Library", primary=True)
        library.add_button("New Tool")
        library.add_button("Custom Profile")
        feeds = tools.add_group("Feeds & Speeds")
        feeds.add_button("Calculator")

        machine = self.ribbon.add_page("Machine")
        setup = machine.add_group("Setup")
        for title in ("Machine Profile", "Work Area", "Origin", "Postprocessor"):
            setup.add_button(title)
        control = machine.add_group("Control")
        control.add_button("Connect", primary=True)
        control.add_button("Probe")
        control.add_button("Jog")

        view = self.ribbon.add_page("View")
        display = view.add_group("Display")
        display.add_button("Fit 3D", self._fit_view, primary=True)
        display.add_button("Stock", self._toggle_stock)
        display.add_button("Grid", self._toggle_grid)
        for title in ("2D", "Toolpaths", "Rapids"):
            display.add_button(title)
        simulation = view.add_group("Simulation")
        simulation.add_button("Simulate", primary=True)

    def _build_workspace(self) -> QWidget:
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(8, 8, 8, 8)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(True)

        self.project_panel = Panel("Project / Layers")
        self.project_list = QListWidget()
        self.project_panel.body_layout.addWidget(self.project_list)
        layer_buttons = QWidget()
        layer_layout = QGridLayout(layer_buttons)
        layer_layout.setContentsMargins(0, 0, 0, 0)
        layer_layout.setSpacing(5)
        up_button = QPushButton("Move Up")
        up_button.clicked.connect(lambda: self._move_selected_item(-1))
        layer_layout.addWidget(up_button, 0, 0)
        down_button = QPushButton("Move Down")
        down_button.clicked.connect(lambda: self._move_selected_item(1))
        layer_layout.addWidget(down_button, 0, 1)
        duplicate_button = QPushButton("Duplicate")
        duplicate_button.clicked.connect(self._duplicate_selected_item)
        layer_layout.addWidget(duplicate_button, 1, 0)
        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(self._delete_selected_item)
        layer_layout.addWidget(delete_button, 1, 1)
        self.project_panel.body_layout.addWidget(layer_buttons)

        canvas = QFrame()
        canvas.setObjectName("CanvasFrame")
        canvas_layout = QVBoxLayout(canvas)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.setSpacing(0)

        canvas_bar = QWidget()
        canvas_bar.setObjectName("ViewportBar")
        canvas_bar_layout = QHBoxLayout(canvas_bar)
        canvas_bar_layout.setContentsMargins(10, 7, 10, 7)
        canvas_bar_layout.addWidget(QLabel("3D Workspace"))
        canvas_bar_layout.addStretch(1)
        fit_button = QPushButton("Fit View")
        fit_button.clicked.connect(self._fit_view)
        canvas_bar_layout.addWidget(fit_button)
        import_button = QPushButton("Import Design")
        import_button.setObjectName("PrimaryButton")
        import_button.clicked.connect(self._import_file)
        canvas_bar_layout.addWidget(import_button)
        canvas_layout.addWidget(canvas_bar)

        self.viewport = MeshViewport(self.project)
        canvas_layout.addWidget(self.viewport, 1)

        self.properties_panel = Panel("Properties / Carve")
        self.selection_info = QLabel()
        self.selection_info.setWordWrap(True)
        self.selection_info.setObjectName("Muted")
        self.properties_panel.body_layout.addWidget(self.selection_info)

        self.stock_widget = self._build_stock_controls()
        self.properties_panel.body_layout.addWidget(self.stock_widget)

        self.transform_widget = self._build_transform_controls()
        self.properties_panel.body_layout.addWidget(self.transform_widget)

        self.properties_panel.body_layout.addWidget(QLabel("Selected cutter"))
        self.tool_combo = QComboBox()
        for tool in DEFAULT_TOOLS:
            self.tool_combo.addItem(tool.name, tool)
        self.properties_panel.body_layout.addWidget(self.tool_combo)
        info = QLabel(
            "Toolpaths will compensate for the selected cutter profile; "
            "3D finishing is not limited to ball-nose tools."
        )
        info.setWordWrap(True)
        info.setObjectName("Muted")
        self.properties_panel.body_layout.addWidget(info)
        self.properties_panel.body_layout.addStretch(1)

        self.project_list.currentRowChanged.connect(self._update_properties)
        self.project_list.itemChanged.connect(self._project_item_changed)
        self._refresh_project_list(0)

        splitter.addWidget(self.project_panel)
        splitter.addWidget(canvas)
        splitter.addWidget(self.properties_panel)
        splitter.setSizes([250, 970, 330])
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)
        return wrapper

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
        return spin

    def _build_stock_controls(self) -> QWidget:
        widget = QWidget()
        widget.setObjectName("StockControls")
        grid = QGridLayout(widget)
        grid.setContentsMargins(0, 6, 0, 10)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(5)

        heading = QLabel("Stock dimensions")
        heading.setObjectName("SectionHeading")
        grid.addWidget(heading, 0, 0, 1, 2)

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
        for row, (title, spin) in enumerate(
            zip(("Width", "Height", "Thickness"), self.stock_spins, strict=True),
            start=1,
        ):
            grid.addWidget(QLabel(title), row, 0)
            grid.addWidget(spin, row, 1)
            spin.valueChanged.connect(self._stock_control_changed)

        return widget

    def _build_transform_controls(self) -> QWidget:
        widget = QWidget()
        widget.setObjectName("TransformControls")
        grid = QGridLayout(widget)
        grid.setContentsMargins(0, 6, 0, 10)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(5)

        heading = QLabel("Model transform")
        heading.setObjectName("SectionHeading")
        grid.addWidget(heading, 0, 0, 1, 4)

        grid.addWidget(QLabel("Model units"), 1, 0)
        self.source_units_combo = QComboBox()
        for units in ModelUnits:
            self.source_units_combo.addItem(units.display_name, units)
        self.source_units_combo.currentIndexChanged.connect(self._source_units_changed)
        grid.addWidget(self.source_units_combo, 1, 1, 1, 3)

        grid.addWidget(QLabel(""), 2, 0)
        for column, axis in enumerate(("X", "Y", "Z"), start=1):
            label = QLabel(axis)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setObjectName("Muted")
            grid.addWidget(label, 2, column)

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
        self.scale_spins = tuple(
            self._configured_spin(
                minimum=0.001,
                maximum=1000.0,
                decimals=4,
                step=0.05,
            )
            for _ in range(3)
        )

        for row, (title, spins) in enumerate(
            (
                ("Position", self.position_spins),
                ("Rotation", self.rotation_spins),
                ("Scale", self.scale_spins),
            ),
            start=3,
        ):
            grid.addWidget(QLabel(title), row, 0)
            for column, spin in enumerate(spins, start=1):
                grid.addWidget(spin, row, column)
                spin.valueChanged.connect(self._transform_control_changed)

        self.lock_scale = QCheckBox("Lock XYZ scale")
        self.lock_scale.setChecked(True)
        grid.addWidget(self.lock_scale, 6, 0, 1, 4)

        center_button = QPushButton("Center XY")
        center_button.clicked.connect(self._center_selected_xy)
        grid.addWidget(center_button, 7, 0, 1, 2)

        top_button = QPushButton("Top to Z0")
        top_button.clicked.connect(self._top_selected_to_surface)
        grid.addWidget(top_button, 7, 2, 1, 2)

        reset_button = QPushButton("Reset Transform")
        reset_button.clicked.connect(self._reset_selected_transform)
        grid.addWidget(reset_button, 8, 0, 1, 4)

        widget.setVisible(False)
        return widget

    @staticmethod
    def _number(value: float) -> str:
        return f"{value:.3f}".rstrip("0").rstrip(".")

    @classmethod
    def _source_dimensions_text(cls, item: ProjectItem) -> str:
        if item.mesh is None:
            return ""
        dimensions = " × ".join(cls._number(value) for value in item.mesh.dimensions)
        return f"{dimensions} {item.source_units.value}"

    @classmethod
    def _mesh_properties_text(cls, item: ProjectItem) -> str:
        mesh = item.mesh
        if mesh is None:
            return f"{item.kind.upper()}\n{item.name}"

        transformed = item.transformed_mesh()
        assert transformed is not None
        placed_dimensions = " × ".join(
            cls._number(float(value)) for value in transformed.extents
        )
        placed_minimum = ", ".join(
            cls._number(float(value)) for value in transformed.bounds[0]
        )
        placed_maximum = ", ".join(
            cls._number(float(value)) for value in transformed.bounds[1]
        )
        metadata_units = mesh.units or "none (STL normally stores no unit)"
        return (
            f"STL mesh\n{item.name}\n\n"
            f"Source size: {cls._source_dimensions_text(item)}\n"
            f"Model units: {item.source_units.display_name}\n"
            f"File metadata units: {metadata_units}\n"
            f"Placed size: {placed_dimensions} mm\n"
            f"Vertices: {mesh.vertex_count:,}\n"
            f"Faces: {mesh.face_count:,}\n"
            f"Placed min: {placed_minimum}\n"
            f"Placed max: {placed_maximum}"
        )

    def _stock_list_text(self) -> str:
        stock = self.project.stock
        return (
            f"Stock  {self._number(stock.width_mm)} × "
            f"{self._number(stock.height_mm)} × "
            f"{self._number(stock.thickness_mm)} mm"
        )

    def _item_list_text(self, item: ProjectItem) -> str:
        if item.mesh is None:
            return f"{item.kind.upper()}  {item.name}"
        return f"STL  {item.name} — {self._source_dimensions_text(item)}"

    def _refresh_project_list(self, selected_row: int = 0) -> None:
        self._updating_project_list = True
        self.project_list.blockSignals(True)
        try:
            self.project_list.clear()
            self.project_list.addItem(self._stock_list_text())
            for project_item in self.project.items:
                list_item = QListWidgetItem(self._item_list_text(project_item))
                list_item.setFlags(
                    list_item.flags() | Qt.ItemFlag.ItemIsUserCheckable
                )
                list_item.setCheckState(
                    Qt.CheckState.Checked
                    if project_item.visible
                    else Qt.CheckState.Unchecked
                )
                self.project_list.addItem(list_item)
            selected_row = max(0, min(selected_row, self.project_list.count() - 1))
            self.project_list.setCurrentRow(selected_row)
        finally:
            self.project_list.blockSignals(False)
            self._updating_project_list = False
        self._update_properties(selected_row)

    def _project_item_changed(self, list_item: QListWidgetItem) -> None:
        if self._updating_project_list:
            return
        row = self.project_list.row(list_item)
        if row <= 0:
            return
        index = row - 1
        if index >= len(self.project.items):
            return
        visible = list_item.checkState() == Qt.CheckState.Checked
        self.project.items[index].visible = visible
        self.viewport.update()
        state = "visible" if visible else "hidden"
        self.statusBar().showMessage(f"{self.project.items[index].name} {state}", 2000)

    def _sync_stock_controls(self) -> None:
        self._updating_stock_controls = True
        try:
            for spin, value in zip(
                self.stock_spins,
                (
                    self.project.stock.width_mm,
                    self.project.stock.height_mm,
                    self.project.stock.thickness_mm,
                ),
                strict=True,
            ):
                spin.setValue(value)
        finally:
            self._updating_stock_controls = False

    def _stock_control_changed(self, _value: float) -> None:
        if self._updating_stock_controls:
            return
        width, height, thickness = (spin.value() for spin in self.stock_spins)
        self.project.stock.width_mm = width
        self.project.stock.height_mm = height
        self.project.stock.thickness_mm = thickness
        if self.project_list.count():
            self.project_list.item(0).setText(self._stock_list_text())
        self.selection_info.setText(
            "Stock\n"
            f"{self._number(width)} × {self._number(height)} × "
            f"{self._number(thickness)} mm"
        )
        self.viewport.update()

    def _selected_item(self) -> ProjectItem | None:
        row = self.project_list.currentRow()
        if row <= 0:
            return None
        index = row - 1
        if index >= len(self.project.items):
            return None
        return self.project.items[index]

    def _selected_item_index(self) -> int | None:
        row = self.project_list.currentRow()
        if row <= 0:
            return None
        index = row - 1
        if index >= len(self.project.items):
            return None
        return index

    def _update_properties(self, row: int) -> None:
        if row <= 0:
            stock = self.project.stock
            self.selection_info.setText(
                "Stock\n"
                f"{self._number(stock.width_mm)} × {self._number(stock.height_mm)} × "
                f"{self._number(stock.thickness_mm)} mm"
            )
            self._sync_stock_controls()
            self.stock_widget.setVisible(True)
            self.transform_widget.setVisible(False)
            self.viewport.set_selected_item(None)
            return

        item_index = row - 1
        if item_index >= len(self.project.items):
            self.selection_info.setText("No design selected")
            self.stock_widget.setVisible(False)
            self.transform_widget.setVisible(False)
            self.viewport.set_selected_item(None)
            return

        item = self.project.items[item_index]
        self.selection_info.setText(self._mesh_properties_text(item))
        self.viewport.set_selected_item(item_index)
        self.stock_widget.setVisible(False)
        has_mesh = item.mesh is not None
        self.transform_widget.setVisible(has_mesh)
        if has_mesh:
            self._sync_transform_controls(item)

    def _sync_transform_controls(self, item: ProjectItem) -> None:
        self._updating_transform_controls = True
        try:
            unit_index = self.source_units_combo.findData(item.source_units)
            if unit_index >= 0:
                self.source_units_combo.setCurrentIndex(unit_index)
            for spin, value in zip(
                self.position_spins,
                item.transform.translation_mm,
                strict=True,
            ):
                spin.setValue(value)
            for spin, value in zip(
                self.rotation_spins,
                item.transform.rotation_deg,
                strict=True,
            ):
                spin.setValue(value)
            for spin, value in zip(
                self.scale_spins,
                item.transform.scale_xyz,
                strict=True,
            ):
                spin.setValue(value)
        finally:
            self._updating_transform_controls = False

    def _source_units_changed(self, _index: int) -> None:
        if self._updating_transform_controls:
            return
        item = self._selected_item()
        if item is None or item.mesh is None:
            return
        units = self.source_units_combo.currentData()
        if not isinstance(units, ModelUnits) or units is item.source_units:
            return
        item.source_units = units
        item.transform = self.project.default_transform_for_mesh(item.mesh, units)
        self._refresh_project_list(self.project_list.currentRow())
        self.viewport.fit_view()
        self.statusBar().showMessage(
            f"Interpreting {item.name} as {units.display_name}; placement reset",
            5000,
        )

    def _transform_control_changed(self, value: float) -> None:
        if self._updating_transform_controls:
            return

        item = self._selected_item()
        if item is None or item.mesh is None:
            return

        sender = self.sender()
        if self.lock_scale.isChecked() and sender in self.scale_spins:
            self._updating_transform_controls = True
            try:
                for spin in self.scale_spins:
                    if spin is not sender:
                        spin.setValue(value)
            finally:
                self._updating_transform_controls = False

        item.transform.translation_mm = tuple(spin.value() for spin in self.position_spins)
        item.transform.rotation_deg = tuple(spin.value() for spin in self.rotation_spins)
        item.transform.scale_xyz = tuple(spin.value() for spin in self.scale_spins)
        item.transform.validate()
        self.selection_info.setText(self._mesh_properties_text(item))
        self.viewport.update()

    def _center_selected_xy(self) -> None:
        item = self._selected_item()
        if item is None or item.mesh is None:
            self.statusBar().showMessage("Select an STL mesh first", 3000)
            return

        transformed = item.transformed_mesh()
        assert transformed is not None
        bounds = np.asarray(transformed.bounds, dtype=float)
        center = bounds.mean(axis=0)
        tx, ty, tz = item.transform.translation_mm
        item.transform.translation_mm = (
            tx + self.project.stock.width_mm / 2.0 - center[0],
            ty + self.project.stock.height_mm / 2.0 - center[1],
            tz,
        )
        self._sync_transform_controls(item)
        self._update_properties(self.project_list.currentRow())
        self.viewport.update()
        self.statusBar().showMessage("Centered selected mesh on stock", 3000)

    def _top_selected_to_surface(self) -> None:
        item = self._selected_item()
        if item is None or item.mesh is None:
            self.statusBar().showMessage("Select an STL mesh first", 3000)
            return

        transformed = item.transformed_mesh()
        assert transformed is not None
        bounds = np.asarray(transformed.bounds, dtype=float)
        tx, ty, tz = item.transform.translation_mm
        item.transform.translation_mm = (tx, ty, tz - bounds[1, 2])
        self._sync_transform_controls(item)
        self._update_properties(self.project_list.currentRow())
        self.viewport.update()
        self.statusBar().showMessage("Placed selected mesh top at stock Z0", 3000)

    def _reset_selected_transform(self) -> None:
        item = self._selected_item()
        if item is None or item.mesh is None:
            self.statusBar().showMessage("Select an STL mesh first", 3000)
            return

        item.transform = self.project.default_transform_for_mesh(
            item.mesh,
            item.source_units,
        )
        self._sync_transform_controls(item)
        self._update_properties(self.project_list.currentRow())
        self.viewport.fit_view()
        self.statusBar().showMessage("Reset selected mesh transform", 3000)

    def _duplicate_selected_item(self) -> None:
        index = self._selected_item_index()
        if index is None:
            self.statusBar().showMessage("Select a design item to duplicate", 3000)
            return
        new_index, duplicate = self.project.duplicate_item(index)
        self._refresh_project_list(new_index + 1)
        self.viewport.update()
        self.statusBar().showMessage(f"Duplicated {duplicate.name}", 3000)

    def _delete_selected_item(self) -> None:
        index = self._selected_item_index()
        if index is None:
            self.statusBar().showMessage("Stock cannot be deleted", 3000)
            return
        removed = self.project.remove_item(index)
        next_row = min(index + 1, len(self.project.items))
        self._refresh_project_list(next_row)
        self.viewport.fit_view()
        self.statusBar().showMessage(f"Deleted {removed.name}", 3000)

    def _move_selected_item(self, offset: int) -> None:
        index = self._selected_item_index()
        if index is None:
            self.statusBar().showMessage("Select a design item to reorder", 3000)
            return
        new_index = self.project.move_item(index, offset)
        self._refresh_project_list(new_index + 1)
        self.viewport.update()

    def _focus_transform_controls(self) -> None:
        item = self._selected_item()
        if item is None or item.mesh is None:
            self.statusBar().showMessage("Select an STL mesh first", 3000)
            return
        self.position_spins[0].setFocus()

    def _fit_view(self) -> None:
        self.viewport.fit_view()

    def _toggle_stock(self) -> None:
        self.viewport.toggle_stock()
        state = "shown" if self.viewport.show_stock else "hidden"
        self.statusBar().showMessage(f"Stock {state}", 2000)

    def _toggle_grid(self) -> None:
        self.viewport.toggle_grid()
        state = "shown" if self.viewport.show_grid else "hidden"
        self.statusBar().showMessage(f"Grid {state}", 2000)

    def _set_project(
        self,
        project: Project,
        *,
        project_path: Path | None,
        selected_row: int = 0,
    ) -> None:
        self.project = project
        self.project_path = project_path
        self.project_title_label.setText(f"  •  {project.name} Project")
        self.viewport.set_project(project)
        self._refresh_project_list(selected_row)

    def _new_project(self) -> None:
        self._set_project(Project(), project_path=None)
        self.statusBar().showMessage("New project created", 3000)

    def _open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open CarveFoundry Project",
            str(self.project_path.parent if self.project_path else Path.home()),
            f"CarveFoundry Projects (*{PROJECT_SUFFIX});;All files (*)",
        )
        if not path:
            return
        project_path = Path(path)
        try:
            project = load_project(project_path)
        except ProjectFileError as exc:
            self.selection_info.setText(f"Project open failed\n{exc}")
            self.statusBar().showMessage(f"Could not open project: {exc}", 8000)
            return
        self._set_project(project, project_path=project_path)
        self.statusBar().showMessage(f"Opened {project_path.name}", 5000)

    def _save_project(self) -> None:
        if self.project_path is None:
            self._save_project_as()
            return
        self._save_project_to(self.project_path)

    def _save_project_as(self) -> None:
        suggested = (
            self.project_path
            if self.project_path is not None
            else Path.home() / f"{self.project.name}{PROJECT_SUFFIX}"
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save CarveFoundry Project",
            str(suggested),
            f"CarveFoundry Projects (*{PROJECT_SUFFIX})",
        )
        if not path:
            return
        self._save_project_to(Path(path))

    def _save_project_to(self, path: Path) -> None:
        if self.project.name == "Untitled":
            self.project.name = path.stem
        try:
            saved_path = save_project(self.project, path)
        except ProjectFileError as exc:
            self.selection_info.setText(f"Project save failed\n{exc}")
            self.statusBar().showMessage(f"Could not save project: {exc}", 8000)
            return
        self.project_path = saved_path
        self.project_title_label.setText(f"  •  {self.project.name} Project")
        self.statusBar().showMessage(f"Saved {saved_path.name}", 5000)

    def _import_file(self, kind: str | None = None) -> None:
        filters = {
            "SVG": "SVG files (*.svg)",
            "DXF": "DXF files (*.dxf)",
            "STL": "STL files (*.stl)",
            "Image": "Images (*.png *.jpg *.jpeg *.bmp *.webp)",
            "G-code": "G-code (*.nc *.gcode *.tap *.cnc)",
        }
        selected_filter = filters.get(
            kind,
            "Supported designs (*.stl *.svg *.dxf *.png *.jpg *.jpeg *.bmp *.webp "
            "*.nc *.gcode *.tap *.cnc);;All files (*)",
        )

        if kind is None:
            paths, _ = QFileDialog.getOpenFileNames(
                self,
                "Import Design Files",
                str(Path.home()),
                selected_filter,
            )
        else:
            path, _ = QFileDialog.getOpenFileName(
                self,
                f"Import {kind}",
                str(Path.home()),
                selected_filter,
            )
            paths = [path] if path else []

        if not paths:
            self.statusBar().showMessage("Import canceled", 3000)
            return

        imported: list[ProjectItem] = []
        failures: list[str] = []
        source_only_count = 0

        for path in paths:
            try:
                info = inspect_import_file(path, expected_kind=kind)
            except ImportFileError as exc:
                failures.append(f"{Path(path).name}: {exc}")
                continue

            mesh = info.mesh
            if mesh is None:
                item = ProjectItem(info.path.name, info.path, info.kind)
                source_only_count += 1
            else:
                source_units = ModelUnits.from_metadata(mesh.units)
                transform = self.project.default_transform_for_mesh(mesh, source_units)
                item = ProjectItem(
                    info.path.name,
                    info.path,
                    info.kind,
                    mesh=mesh,
                    transform=transform,
                    source_units=source_units,
                )

            self.project.items.append(item)
            imported.append(item)

        if imported:
            self._refresh_project_list(len(self.project.items))
            if any(item.mesh is not None for item in imported):
                self.viewport.fit_view()

        if failures:
            failure_text = "\n".join(failures[:8])
            if len(failures) > 8:
                failure_text += f"\n… and {len(failures) - 8} more"
            self.selection_info.setText(
                f"Import completed with {len(failures)} failure(s)\n\n{failure_text}"
            )

        if imported and failures:
            self.statusBar().showMessage(
                f"Imported {len(imported)} file(s); {len(failures)} failed",
                8000,
            )
        elif imported:
            message = f"Imported {len(imported)} file(s)"
            if source_only_count:
                message += (
                    f" — {source_only_count} stored as project source asset(s) "
                    "pending dedicated editor support"
                )
            self.statusBar().showMessage(message, 6000)
        else:
            self.statusBar().showMessage(
                f"Import failed for {len(failures)} file(s)",
                8000,
            )
