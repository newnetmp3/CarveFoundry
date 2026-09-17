from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QPushButton,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from ..core.project import Project, ProjectItem
from ..core.tools import DEFAULT_TOOLS
from .ribbon import Ribbon


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
        project = QLabel("  •  Untitled Project")
        project.setObjectName("Muted")
        line.addWidget(project)
        line.addStretch(1)
        mode = QLabel("DESIGN + CAM")
        mode.setObjectName("AccentText")
        line.addWidget(mode)
        return row

    def _populate_ribbon(self) -> None:
        file_page = self.ribbon.add_page("File")
        project = file_page.add_group("Project")
        project.add_button("New", self._new_project)
        project.add_button("Open")
        project.add_button("Save")
        exchange = file_page.add_group("Import / Export")
        exchange.add_button("Import", self._import_file, primary=True)
        exchange.add_button("Export G-code")

        home = self.ribbon.add_page("Home")
        edit = home.add_group("Edit")
        for title in ("Undo", "Redo", "Cut", "Copy", "Paste", "Delete"):
            edit.add_button(title)
        arrange = home.add_group("Arrange")
        for title in ("Align", "Center", "Group", "Ungroup", "Duplicate"):
            arrange.add_button(title)

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
        for title in ("Orient", "Scale", "Position", "Boundary"):
            mesh.add_button(title)
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
        for title in ("2D", "3D", "Stock", "Grid", "Toolpaths", "Rapids"):
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
        self.project_list.addItem("Stock  300 × 200 × 19 mm")
        self.project_panel.body_layout.addWidget(self.project_list)

        canvas = QFrame()
        canvas.setObjectName("CanvasFrame")
        canvas_layout = QVBoxLayout(canvas)
        canvas_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel("CarveFoundry Workspace")
        title.setObjectName("CanvasTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        canvas_layout.addWidget(title)
        hint = QLabel("Import an SVG, DXF, STL, image, or G-code file to begin")
        hint.setObjectName("CanvasHint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        canvas_layout.addWidget(hint)
        import_button = QPushButton("Import Design")
        import_button.setObjectName("PrimaryButton")
        import_button.clicked.connect(self._import_file)
        canvas_layout.addWidget(import_button, alignment=Qt.AlignmentFlag.AlignCenter)

        self.properties_panel = Panel("Properties / Carve")
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

        splitter.addWidget(self.project_panel)
        splitter.addWidget(canvas)
        splitter.addWidget(self.properties_panel)
        splitter.setSizes([230, 1000, 280])
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)
        return wrapper

    def _new_project(self) -> None:
        self.project = Project()
        self.project_list.clear()
        self.project_list.addItem("Stock  300 × 200 × 19 mm")
        self.statusBar().showMessage("New project created", 3000)

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
            "Design files (*.svg *.dxf *.stl *.png *.jpg *.jpeg *.nc *.gcode *.tap);;All files (*)",
        )
        path, _ = QFileDialog.getOpenFileName(
            self,
            f"Import {kind or 'Design'}",
            str(Path.home()),
            selected_filter,
        )
        if not path:
            return
        source = Path(path)
        detected = kind or source.suffix.lstrip(".").upper()
        self.project.items.append(ProjectItem(source.name, source, detected.lower()))
        self.project_list.addItem(f"{detected}  {source.name}")
        self.statusBar().showMessage(f"Imported {source.name}", 5000)
