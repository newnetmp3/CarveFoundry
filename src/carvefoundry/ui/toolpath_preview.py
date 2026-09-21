from __future__ import annotations

from itertools import chain

from PySide6.QtCore import Qt, QThread, QTimer
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
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSlider,
    QSplitter,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from carvefoundry.cam.gcode import GrblPostSettings, render_grbl_program
from carvefoundry.cam.job_process import GcodeRequest
from carvefoundry.cam.toolpath import Toolpath
from carvefoundry.core.project import Project, Stock

from .background_jobs import BackgroundWorker, JobCallbacks
from .viewport import MeshViewport


class ToolpathPreviewWindow(QMainWindow):
    """NC Viewer-inspired standalone backplotter for calculated toolpaths."""

    LAZY_CODE_MOVE_THRESHOLD = 150_000
    ASYNC_CODE_MOVE_THRESHOLD = 3_000
    CODE_APPEND_CHUNK = 1_500

    def __init__(
        self,
        *,
        toolpaths: list[Toolpath],
        stock: Stock,
        post_settings: GrblPostSettings,
        source_names: list[str] | None = None,
        render_geometry_data: dict[str, object] | None = None,
        estimated_minutes: float | None = None,
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
        self._source_names = list(source_names or [])
        self._moves = list(chain.from_iterable(path.moves for path in toolpaths))
        self._post_settings = post_settings
        self._estimated_minutes = estimated_minutes
        self._code_lines: list[str] = []
        self._move_code_lines: list[int] = []
        self._code_loaded = False
        self._code_loading = False
        self._code_offset = 0
        self._code_thread: QThread | None = None
        self._code_worker: BackgroundWorker | None = None
        self._code_bridge: JobCallbacks | None = None
        self._close_after_code = False
        self._code_append_timer = QTimer(self)
        self._code_append_timer.setInterval(0)
        self._code_append_timer.timeout.connect(self._append_code_chunk)
        self._defer_code = (
            len(self._moves) > self.LAZY_CODE_MOVE_THRESHOLD
        )
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
        if render_geometry_data is not None:
            self.viewport.prepare_toolpath_render_cache(
                self._toolpaths, render_geometry_data
            )
        self.viewport.set_view_controls_visible(False)
        self.viewport.set_selected_item(None)
        self.viewport.set_toolpaths_visible(True)
        self.viewport.set_rapids_visible(True)

        self._timer = QTimer(self)
        self._timer.setInterval(35)
        self._timer.timeout.connect(self._playback_tick)

        self._build_ui()
        self._install_shortcuts()
        if self._defer_code:
            self._left_panel.hide()
            self._code_toggle.setChecked(False)
            self.code_editor.setPlaceholderText(
                "G-code loading is deferred for this large toolpath. "
                "Click Code to load it."
            )
        else:
            self._ensure_code_loaded()
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

        self._code_progress = QProgressBar()
        self._code_progress.setObjectName("BackplotCodeProgress")
        self._code_progress.setRange(0, 100)
        self._code_progress.setFixedWidth(240)
        self._code_progress.hide()
        top_layout.addWidget(self._code_progress)

        self._code_toggle = QPushButton("Code")
        self._code_toggle.setCheckable(True)
        self._code_toggle.setChecked(not self._defer_code)
        self._code_toggle.setToolTip(
            "Show or hide the G-code / DRO sidebar. For very large "
            "toolpaths, G-code is loaded only when this panel is opened."
        )
        self._code_toggle.clicked.connect(self._toggle_code_panel)
        top_layout.addWidget(self._code_toggle)

        if callable(getattr(self.parent(), "_simulate_stock_removal", None)):
            verified_button = QPushButton("Virtual machining")
            verified_button.setToolTip(
                "Verify the actual posted G-code against stock, fixtures and "
                "the original paths, then simulate remaining material."
            )
            verified_button.clicked.connect(self._open_virtual_machining)
            top_layout.addWidget(verified_button)

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

    def _open_virtual_machining(self) -> None:
        """Launch the real project's verified-NC material-removal dialog."""
        host = self.parent()
        action = getattr(host, "_simulate_stock_removal", None)
        if not callable(action):
            return
        current = getattr(getattr(host, "project", None), "toolpaths", ())
        if len(current) != len(self._toolpaths) or any(
            a is not b for a, b in zip(current, self._toolpaths, strict=True)
        ):
            QMessageBox.information(
                self, "Toolpath preview is outdated",
                "Toolpaths changed after this preview opened. Close it and "
                "reopen Toolpath Preview before simulating the current job.",
            )
            return
        action()

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
            self._source_names
            or list(
                dict.fromkeys(
                    path.source_item_name
                    for path in self._toolpaths
                    if path.source_item_name
                )
            )
        )
        if self._estimated_minutes is not None:
            cutting_label = f"~{self._estimated_minutes:.1f} min cutting"
        elif len(self._moves) > self.ASYNC_CODE_MOVE_THRESHOLD:
            # Do not walk millions of moves just to show the viewer window.
            cutting_label = "cutting estimate pending"
        else:
            total_minutes = sum(
                path.estimated_cutting_minutes for path in self._toolpaths
            )
            cutting_label = f"~{total_minutes:.1f} min cutting"
        source_prefix = f"{source_names}  •  " if source_names else ""
        self._summary_label.setText(
            f"{source_prefix}{operation_names}  •  {cutter_names}  •  "
            f"{len(self._moves):,} moves  •  {cutting_label}"
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
        if visible:
            self._ensure_code_loaded()
        self._left_panel.setVisible(visible)
        if visible:
            sizes = self._splitter.sizes()
            total = max(sum(sizes), self.width())
            self._splitter.setSizes([390, max(570, total - 390)])

    def _ensure_code_loaded(self) -> None:
        if self._code_loaded or self._code_loading:
            return
        if len(self._moves) > self.ASYNC_CODE_MOVE_THRESHOLD:
            self._start_code_job()
            return

        self._code_lines, self._move_code_lines = self._render_program()
        self._load_code()
        self._code_loaded = True
        self._highlight_current_code_line()

    def _highlight_current_code_line(self) -> None:
        if self._moves and self._move_code_lines and hasattr(self, "_slider"):
            index = max(
                0,
                min(self._slider.value(), len(self._move_code_lines) - 1),
            )
            self._highlight_code_line(self._move_code_lines[index])

    def _start_code_job(self) -> None:
        """Backplot text generation runs in a cancellable child process."""

        if self._code_loaded or self._code_loading:
            return
        self._code_loading = True
        self._code_offset = 0
        self._code_progress.setRange(0, 100)
        self._code_progress.setValue(0)
        self._code_progress.setFormat("Preparing G-code · %p%")
        self._code_progress.show()
        self.code_editor.setPlaceholderText("Preparing G-code in a worker…")
        self._code_toggle.setEnabled(False)

        request = GcodeRequest(
            toolpaths=self._toolpaths,
            path="",
            settings=self._post_settings,
            mode="preview_code",
        )
        worker = BackgroundWorker(process_request=request)
        thread = QThread(self)
        worker.moveToThread(thread)
        self._code_worker = worker
        self._code_thread = thread

        def progress(fraction: float, status: str) -> None:
            # Leave the final 10% for adding the numbered lines to Qt.
            value = round(90 * max(0, min(1, fraction)))
            self._code_progress.setValue(value)
            self._code_progress.setFormat(f"{status} · %p%")

        def done(result: object) -> None:
            if not isinstance(result, dict):
                failed("Invalid G-code viewer result")
                return
            self._code_lines = result["code_lines"]
            self._move_code_lines = result["move_code_lines"]
            self._code_offset = 0
            self._code_progress.setValue(90)
            self._code_progress.setFormat("Displaying G-code · %p%")
            self.code_editor.clear()
            self._code_append_timer.start()

        def failed(message: str) -> None:
            self._code_loading = False
            self._code_progress.setFormat("G-code loading failed")
            self.code_editor.setPlaceholderText(
                f"Could not load G-code: {message}"
            )
            self._code_toggle.setEnabled(True)

        def cancelled() -> None:
            self._code_loading = False
            self._code_progress.setFormat("G-code loading canceled")
            self._code_toggle.setEnabled(True)

        def cleaned_up() -> None:
            self._code_worker = None
            self._code_thread = None
            self._code_bridge = None
            if self._close_after_code:
                self.close()

        bridge = JobCallbacks(
            self,
            progress=progress,
            completed=done,
            failed=failed,
            cancelled=cancelled,
            cleaned_up=cleaned_up,
        )
        self._code_bridge = bridge
        thread.started.connect(worker.run)
        worker.progress.connect(bridge.on_progress)
        worker.completed.connect(bridge.on_completed)
        worker.failed.connect(bridge.on_failed)
        worker.cancelled.connect(bridge.on_cancelled)
        for signal in (worker.completed, worker.failed, worker.cancelled):
            signal.connect(thread.quit)
            signal.connect(worker.deleteLater)
        thread.finished.connect(bridge.on_cleaned_up)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _append_code_chunk(self) -> None:
        """Incrementally populate the editor without monopolizing Qt events."""

        total = len(self._code_lines)
        start = self._code_offset
        end = min(total, start + self.CODE_APPEND_CHUNK)
        if end > start:
            numbered = "\n".join(
                f"{index + 1:>6}  {self._code_lines[index]}"
                for index in range(start, end)
            )
            self.code_editor.appendPlainText(numbered)
            self._code_offset = end
            self._code_progress.setValue(
                min(100, 90 + round(10 * end / max(1, total)))
            )
        if self._code_offset >= total:
            self._code_append_timer.stop()
            self._code_loading = False
            self._code_loaded = True
            self._code_toggle.setEnabled(True)
            self._code_progress.setRange(0, 100)
            self._code_progress.setValue(100)
            self._code_progress.setFormat("G-code ready · %p%")
            self._highlight_current_code_line()
            QTimer.singleShot(
                1600,
                lambda: (
                    self._code_progress.hide()
                    if self._code_loaded and not self._code_loading
                    else None
                ),
            )

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

        if self._code_loaded and index < len(self._move_code_lines):
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
        if self._code_thread is not None and self._code_thread.isRunning():
            self._close_after_code = True
            self._code_append_timer.stop()
            if self._code_worker is not None:
                self._code_worker.cancel()
            self.hide()
            event.ignore()
            return
        self._code_append_timer.stop()
        super().closeEvent(event)
