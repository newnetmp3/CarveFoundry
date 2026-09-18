from __future__ import annotations

from itertools import chain

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QFontDatabase,
    QKeySequence,
    QShortcut,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QSplitter,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from carvefoundry.cam.gcode import GrblPostSettings, render_grbl_program
from carvefoundry.cam.toolpath import Toolpath
from carvefoundry.core.project import Project, Stock

from .viewport import MeshViewport


class ToolpathPreviewWindow(QMainWindow):
    """NC Viewer-inspired standalone backplotter for calculated toolpaths."""

    def __init__(
        self,
        *,
        toolpaths: list[Toolpath],
        stock: Stock,
        post_settings: GrblPostSettings,
        parent=None,
    ) -> None:
        super().__init__(parent)
        if not toolpaths:
            raise ValueError("Toolpath preview requires at least one toolpath.")

        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setWindowTitle("CarveFoundry — Toolpath Preview")
        self.resize(1420, 860)
        self.setMinimumSize(960, 620)

        self._toolpaths = list(toolpaths)
        self._moves = list(chain.from_iterable(path.moves for path in toolpaths))
        self._post_settings = post_settings
        self._code_lines, self._move_code_lines = self._render_program()
        self._playing = False

        preview_project = Project(
            name="Toolpath Preview",
            stock=Stock(
                width_mm=stock.width_mm,
                height_mm=stock.height_mm,
                thickness_mm=stock.thickness_mm,
            ),
            toolpaths=list(toolpaths),
        )
        self.viewport = MeshViewport(preview_project)
        self.viewport.set_view_controls_visible(False)
        self.viewport.set_selected_item(None)
        self.viewport.set_toolpaths_visible(True)
        self.viewport.set_rapids_visible(True)

        self._timer = QTimer(self)
        self._timer.setInterval(35)
        self._timer.timeout.connect(self._playback_tick)

        self._build_ui()
        self._install_shortcuts()
        self._load_code()
        self._set_position(0 if self._moves else -1)
        self.viewport.set_isometric_view()

    def _render_program(self) -> tuple[list[str], list[int]]:
        program = render_grbl_program(
            self._toolpaths,
            self._post_settings,
        )
        lines = program.rstrip("\n").splitlines()
        command_lines = [
            index
            for index, line in enumerate(lines)
            if line.lstrip().startswith(("G0 ", "G1 "))
        ]

        move_lines: list[int] = []
        command_offset = 0
        for toolpath in self._toolpaths:
            # Each operation contributes one Safe-Z command before its moves and
            # one after. The commands in between map 1:1 to Toolpath.moves.
            command_offset += 1
            available = command_lines[
                command_offset : command_offset + len(toolpath.moves)
            ]
            if len(available) == len(toolpath.moves):
                move_lines.extend(available)
            else:
                fallback = command_lines[0] if command_lines else 0
                move_lines.extend([fallback] * len(toolpath.moves))
            command_offset += len(toolpath.moves) + 1

        return lines, move_lines


    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("BackplotRoot")
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        top_bar = QWidget()
        top_bar.setObjectName("BackplotTopBar")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(10, 7, 10, 7)
        title = QLabel("TOOLPATH PREVIEW")
        title.setObjectName("AccentText")
        top_layout.addWidget(title)
        top_layout.addSpacing(12)
        self._summary_label = QLabel()
        self._summary_label.setObjectName("Muted")
        top_layout.addWidget(self._summary_label)
        top_layout.addStretch(1)

        self._code_toggle = QPushButton("Code")
        self._code_toggle.setCheckable(True)
        self._code_toggle.setChecked(True)
        self._code_toggle.setToolTip("Show or hide the G-code / DRO sidebar")
        self._code_toggle.clicked.connect(self._toggle_code_panel)
        top_layout.addWidget(self._code_toggle)

        for label, callback in (
            ("Fit", self.viewport.fit_view),
            ("Top", lambda: self.viewport.set_standard_view("Top")),
            ("Front", lambda: self.viewport.set_standard_view("Front")),
            ("Right", lambda: self.viewport.set_standard_view("Right")),
            ("ISO", self.viewport.set_isometric_view),
        ):
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, fn=callback: fn())
            top_layout.addWidget(button)

        root_layout.addWidget(top_bar)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setChildrenCollapsible(True)
        self._left_panel = self._build_left_panel()
        self._splitter.addWidget(self._left_panel)
        self._splitter.addWidget(self._build_plot_panel())
        self._splitter.setSizes([390, 1030])
        self._splitter.setStretchFactor(1, 1)
        root_layout.addWidget(self._splitter, 1)

    def _panel_header(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("BackplotSectionHeader")
        return label

    def _build_left_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("BackplotSidebar")
        panel.setMinimumWidth(320)
        panel.setMaximumWidth(560)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        layout.addWidget(self._panel_header("G-code"))
        self.code_editor = QPlainTextEdit()
        self.code_editor.setReadOnly(True)
        self.code_editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.code_editor.setFont(
            QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        )
        self.code_editor.setObjectName("BackplotCode")
        layout.addWidget(self.code_editor, 1)

        layout.addWidget(self._panel_header("Position"))
        dro = QWidget()
        dro_grid = QGridLayout(dro)
        dro_grid.setContentsMargins(0, 2, 0, 2)
        dro_grid.setSpacing(4)
        self._dro: dict[str, QLabel] = {}
        for column, axis in enumerate(("X", "Y", "Z")):
            axis_label = QLabel(axis)
            axis_label.setObjectName("Muted")
            axis_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            dro_grid.addWidget(axis_label, 0, column)

            value = QLabel("0.0000")
            value.setObjectName("BackplotDRO")
            value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._dro[axis] = value
            dro_grid.addWidget(value, 1, column)
        layout.addWidget(dro)

        self._move_info = QLabel("Move 0 / 0")
        self._move_info.setObjectName("Muted")
        layout.addWidget(self._move_info)

        layout.addWidget(self._panel_header("View Orientation"))
        orientation_row = QHBoxLayout()
        orientation_row.addWidget(QLabel("Plot orientation"))
        orientation = QComboBox()
        orientation.addItems(("Vertical (Z-Up)", "Top / XY"))
        orientation.currentIndexChanged.connect(
            lambda index: (
                self.viewport.set_isometric_view()
                if index == 0
                else self.viewport.set_standard_view("Top")
            )
        )
        orientation_row.addWidget(orientation, 1)
        layout.addLayout(orientation_row)

        layout.addWidget(self._panel_header("Display"))
        self._grid_check = QCheckBox("Show grid")
        self._grid_check.setChecked(True)
        self._grid_check.toggled.connect(self._set_grid_visible)
        layout.addWidget(self._grid_check)

        self._stock_check = QCheckBox("Show stock")
        self._stock_check.setChecked(False)
        self._stock_check.toggled.connect(self._set_stock_visible)
        layout.addWidget(self._stock_check)
        self.viewport.show_stock = False

        self._rapids_check = QCheckBox("Show rapid movement")
        self._rapids_check.setChecked(True)
        self._rapids_check.toggled.connect(self.viewport.set_rapids_visible)
        layout.addWidget(self._rapids_check)

        self._points_check = QCheckBox("Show toolpath points")
        self._points_check.toggled.connect(
            self.viewport.set_toolpath_points_visible
        )
        layout.addWidget(self._points_check)

        self._hide_after_check = QCheckBox("Show completed path only")
        self._hide_after_check.setChecked(False)
        self._hide_after_check.toggled.connect(
            lambda _checked: self._apply_plot_position()
        )
        layout.addWidget(self._hide_after_check)

        operation_names = ", ".join(path.name for path in self._toolpaths)
        cutter_names = ", ".join(
            dict.fromkeys(path.cutter.name for path in self._toolpaths)
        )
        source_names = ", ".join(
            dict.fromkeys(
                path.source_item_name
                for path in self._toolpaths
                if path.source_item_name
            )
        )
        total_minutes = sum(
            path.estimated_cutting_minutes for path in self._toolpaths
        )
        source_prefix = f"{source_names}  •  " if source_names else ""
        self._summary_label.setText(
            f"{source_prefix}{operation_names}  •  {cutter_names}  •  "
            f"{len(self._moves):,} moves  •  ~{total_minutes:.1f} min cutting"
        )
        return panel

    def _build_plot_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("BackplotCanvas")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.viewport, 1)

        transport = QWidget()
        transport.setObjectName("BackplotTransport")
        controls = QHBoxLayout(transport)
        controls.setContentsMargins(10, 7, 10, 7)
        controls.setSpacing(5)

        for text, tip, callback in (
            ("|◀", "First move", self._first),
            ("◀", "Previous move", self._previous),
        ):
            button = QToolButton()
            button.setText(text)
            button.setToolTip(tip)
            button.clicked.connect(lambda _checked=False, fn=callback: fn())
            controls.addWidget(button)

        self._play_button = QToolButton()
        self._play_button.setText("▶")
        self._play_button.setToolTip("Play / Pause")
        self._play_button.clicked.connect(self._toggle_play)
        controls.addWidget(self._play_button)

        for text, tip, callback in (
            ("▶", "Next move", self._next),
            ("▶|", "Last move", self._last),
        ):
            button = QToolButton()
            button.setText(text)
            button.setToolTip(tip)
            button.clicked.connect(lambda _checked=False, fn=callback: fn())
            controls.addWidget(button)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, max(len(self._moves) - 1, 0))
        self._slider.valueChanged.connect(self._set_position)
        controls.addWidget(self._slider, 1)

        controls.addWidget(QLabel("Speed"))
        self._speed = QComboBox()
        self._speed.addItems(("0.25×", "0.5×", "1×", "2×", "5×", "10×"))
        self._speed.setCurrentText("1×")
        self._speed.currentTextChanged.connect(self._update_playback_interval)
        controls.addWidget(self._speed)

        layout.addWidget(transport)
        return panel

    def _install_shortcuts(self) -> None:
        shortcuts = (
            ("Space", self._toggle_play),
            ("Left", self._previous),
            ("Right", self._next),
            ("Home", self._first),
            ("End", self._last),
            ("Ctrl+0", self.viewport.fit_view),
            ("C", lambda: self._code_toggle.click()),
        )
        self._shortcuts: list[QShortcut] = []
        for sequence, callback in shortcuts:
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(callback)
            self._shortcuts.append(shortcut)

    def _toggle_code_panel(self) -> None:
        visible = self._code_toggle.isChecked()
        self._left_panel.setVisible(visible)
        if visible:
            sizes = self._splitter.sizes()
            total = max(sum(sizes), self.width())
            self._splitter.setSizes([390, max(570, total - 390)])

    def _load_code(self) -> None:
        numbered = "\n".join(
            f"{index + 1:>6}  {line}"
            for index, line in enumerate(self._code_lines)
        )
        self.code_editor.setPlainText(numbered)

    def _highlight_code_line(self, line_index: int) -> None:
        if line_index < 0:
            self.code_editor.setExtraSelections([])
            return

        block = self.code_editor.document().findBlockByNumber(line_index)
        if not block.isValid():
            return
        cursor = QTextCursor(block)
        cursor.select(QTextCursor.SelectionType.LineUnderCursor)

        selection = QTextEdit.ExtraSelection()
        selection.cursor = cursor
        selection.format.setBackground(QColor(52, 71, 45))
        selection.format.setForeground(QColor(236, 244, 224))
        self.code_editor.setExtraSelections([selection])
        self.code_editor.setTextCursor(cursor)
        self.code_editor.ensureCursorVisible()

    def _set_position(self, index: int) -> None:
        if not self._moves:
            self.viewport.set_toolpath_marker(None)
            return

        index = max(0, min(int(index), len(self._moves) - 1))
        if self._slider.value() != index:
            self._slider.blockSignals(True)
            try:
                self._slider.setValue(index)
            finally:
                self._slider.blockSignals(False)

        move = self._moves[index]
        self._dro["X"].setText(f"{move.x_mm:.4f}")
        self._dro["Y"].setText(f"{move.y_mm:.4f}")
        self._dro["Z"].setText(f"{move.z_mm:.4f}")
        feed = "Rapid" if move.feed_mm_min is None else f"F {move.feed_mm_min:g}"
        self._move_info.setText(
            f"Move {index + 1:,} / {len(self._moves):,}  •  "
            f"{move.kind.value.title()}  •  {feed}"
        )
        self.viewport.set_toolpath_marker(move.xyz)

        if index < len(self._move_code_lines):
            self._highlight_code_line(self._move_code_lines[index])
        self._apply_plot_position(index)

    def _apply_plot_position(self, index: int | None = None) -> None:
        if not self._moves:
            return
        if index is None:
            index = self._slider.value()
        if self._hide_after_check.isChecked():
            fraction = (int(index) + 1) / len(self._moves)
        else:
            fraction = 1.0
        self.viewport.set_simulation_fraction(fraction)

    def _set_grid_visible(self, visible: bool) -> None:
        self.viewport.show_grid = bool(visible)
        self.viewport.update()

    def _set_stock_visible(self, visible: bool) -> None:
        self.viewport.show_stock = bool(visible)
        self.viewport.update()

    def _speed_multiplier(self) -> float:
        text = self._speed.currentText().replace("×", "")
        try:
            return float(text)
        except ValueError:
            return 1.0

    def _update_playback_interval(self) -> None:
        speed = max(self._speed_multiplier(), 0.01)
        self._timer.setInterval(max(8, round(50.0 / speed)))

    def _toggle_play(self) -> None:
        if not self._moves:
            return
        self._playing = not self._playing
        if self._playing:
            if self._slider.value() >= len(self._moves) - 1:
                self._slider.setValue(0)
            self._play_button.setText("Ⅱ")
            self._update_playback_interval()
            self._timer.start()
        else:
            self._play_button.setText("▶")
            self._timer.stop()

    def _playback_tick(self) -> None:
        if not self._moves:
            self._toggle_play()
            return

        next_index = self._slider.value() + 1
        if next_index >= len(self._moves):
            self._slider.setValue(len(self._moves) - 1)
            self._playing = False
            self._timer.stop()
            self._play_button.setText("▶")
            return
        self._slider.setValue(next_index)

    def _first(self) -> None:
        self._slider.setValue(0)

    def _previous(self) -> None:
        self._slider.setValue(max(0, self._slider.value() - 1))

    def _next(self) -> None:
        self._slider.setValue(
            min(max(len(self._moves) - 1, 0), self._slider.value() + 1)
        )

    def _last(self) -> None:
        self._slider.setValue(max(len(self._moves) - 1, 0))

    def closeEvent(self, event) -> None:
        self._timer.stop()
        super().closeEvent(event)
