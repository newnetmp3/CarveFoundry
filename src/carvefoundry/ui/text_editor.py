from __future__ import annotations

import subprocess

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase, QFontInfo, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core.font_handler import describe_qt_font_face
from ..core.primitives import text_mesh
from ..core.project import ProjectItem, TextProperties

_FONT_FAMILY_VARIANT_SUFFIXES: tuple[tuple[str, str], ...] = (
    ("Extra Condensed", "Extra Condensed"),
    ("ExtraCondensed", "Extra Condensed"),
    ("Ultra Condensed", "Ultra Condensed"),
    ("UltraCondensed", "Ultra Condensed"),
    ("Semi Condensed", "Semi Condensed"),
    ("SemiCondensed", "Semi Condensed"),
    ("Semi Expanded", "Semi Expanded"),
    ("SemiExpanded", "Semi Expanded"),
    ("Extra Expanded", "Extra Expanded"),
    ("ExtraExpanded", "Extra Expanded"),
    ("Ultra Expanded", "Ultra Expanded"),
    ("UltraExpanded", "Ultra Expanded"),
    ("Extra Light", "ExtraLight"),
    ("ExtraLight", "ExtraLight"),
    ("Ultra Light", "UltraLight"),
    ("UltraLight", "UltraLight"),
    ("Semi Light", "SemiLight"),
    ("SemiLight", "SemiLight"),
    ("Demi Bold", "DemiBold"),
    ("DemiBold", "DemiBold"),
    ("Semi Bold", "SemiBold"),
    ("SemiBold", "SemiBold"),
    ("Extra Bold", "ExtraBold"),
    ("ExtraBold", "ExtraBold"),
    ("Ultra Bold", "UltraBold"),
    ("UltraBold", "UltraBold"),
    ("SemCond", "Semi Condensed"),
    ("SmCn", "Semi Condensed"),
    ("SemBd", "SemiBold"),
    ("SmBd", "SemiBold"),
    ("ExtCond", "Extra Condensed"),
    ("XCn", "Extra Condensed"),
    ("ExtLt", "ExtraLight"),
    ("XLt", "ExtraLight"),
    ("ExtBd", "ExtraBold"),
    ("XBd", "ExtraBold"),
    ("Med", "Medium"),
    ("Md", "Medium"),
    ("Lt", "Light"),
    ("Th", "Thin"),
    ("Blk", "Black"),
    ("Bk", "Book"),
    ("Ret", "Retina"),
    ("Condensed", "Condensed"),
    ("Cond", "Condensed"),
    ("Cn", "Condensed"),
    ("Mono", "Monospaced"),
    ("Propo", "Proportional"),
    ("NFM", "Nerd Font Mono"),
    ("NFP", "Nerd Font Proportional"),
    ("NF", "Nerd Font"),
    ("Compressed", "Compressed"),
    ("Expanded", "Expanded"),
    ("Extended", "Extended"),
    ("Narrow", "Narrow"),
    ("Display", "Display"),
    ("Headline", "Headline"),
    ("Caption", "Caption"),
    ("Text", "Text"),
    ("Thin", "Thin"),
    ("Light", "Light"),
    ("Book", "Book"),
    ("Medium", "Medium"),
    ("Bold", "Bold"),
    ("Black", "Black"),
    ("Heavy", "Heavy"),
    ("Regular", "Regular"),
)




class TextEditorMixin:
    """Editable CNC typography: system-font choices, inspector and mesh updates."""

    @staticmethod
    def _installed_text_font_families() -> list[str]:
        """Return installed font families suitable for editable CNC text."""

        symbol = QFontDatabase.WritingSystem.Symbol
        families: list[str] = []
        for family in QFontDatabase.families():
            writing_systems = QFontDatabase.writingSystems(family)
            if writing_systems and all(
                system == symbol for system in writing_systems
            ):
                continue
            families.append(family)

        # A pathological/minimal font setup should still leave the editor
        # usable rather than producing an empty selector.
        if not families:
            families = list(QFontDatabase.families())
        return families

    @staticmethod
    def _parse_fontconfig_text_font_aliases(
        output: str,
        families: list[str],
    ) -> dict[str, tuple[str, str]]:
        """Map full-name aliases back to their real family and style."""

        available = {family.casefold(): family for family in families}
        candidates: dict[str, set[tuple[str, str]]] = {}
        for line in output.splitlines():
            fields = line.split("\t")
            if len(fields) < 3:
                continue
            family_name, style_name, full_name = (
                field.strip() for field in fields[:3]
            )
            canonical = available.get(family_name.casefold())
            alias = available.get(full_name.casefold())
            if (
                canonical is None
                or alias is None
                or canonical.casefold() == alias.casefold()
            ):
                continue
            candidates.setdefault(alias.casefold(), set()).add(
                (canonical, style_name or "Regular")
            )

        # If Fontconfig reports one full name ambiguously for more than one
        # family/style, leave it visible instead of guessing.
        return {
            alias: next(iter(options))
            for alias, options in candidates.items()
            if len(options) == 1
        }

    @classmethod
    def _fontconfig_text_font_aliases(
        cls,
        families: list[str],
    ) -> dict[str, tuple[str, str]]:
        """Return Linux Fontconfig aliases when available.

        Qt sometimes exposes a font's full face name as another family.
        Fontconfig keeps the canonical family/style relationship, so use it
        to hide duplicates such as "... Med" or "... SemBd".  Non-Linux
        systems simply fall back to the suffix grouping below.
        """

        try:
            result = subprocess.run(
                (
                    "fc-list",
                    "-f",
                    "%{family[0]}\\t%{style[0]}\\t%{fullname[0]}\n",
                ),
                check=False,
                capture_output=True,
                text=True,
                timeout=3.0,
            )
        except (FileNotFoundError, OSError, subprocess.SubprocessError):
            return {}
        if result.returncode != 0:
            return {}
        return cls._parse_fontconfig_text_font_aliases(
            result.stdout,
            families,
        )

    def _canonical_text_font_family(
        self,
        family: str,
    ) -> tuple[str, str | None]:
        alias = getattr(self, "_text_font_aliases", {}).get(
            family.casefold()
        )
        if alias is None:
            return family, None
        return alias

    @staticmethod
    def _font_family_variant_candidate(family: str) -> tuple[str, str]:
        """Split common family-level alternatives from a font family name."""

        remaining = family.strip()
        qualifier = ""
        if remaining.endswith("]"):
            qualifier_start = remaining.rfind(" [")
            if qualifier_start > 0:
                qualifier = remaining[qualifier_start:]
                remaining = remaining[:qualifier_start].rstrip()

        parts: list[str] = []
        while remaining:
            matched = False
            folded = remaining.casefold()
            for suffix, label in _FONT_FAMILY_VARIANT_SUFFIXES:
                needle = f" {suffix}".casefold()
                if not folded.endswith(needle):
                    continue
                base = remaining[: -len(suffix)].rstrip()
                if not base:
                    continue
                remaining = base
                parts.insert(0, label)
                matched = True
                break
            if not matched:
                break
        base = remaining or family
        if qualifier and remaining:
            base = f"{remaining}{qualifier}"
        return base, " ".join(parts) or "Regular"

    @classmethod
    def _group_text_font_families(
        cls,
        families: list[str],
    ) -> dict[str, list[tuple[str, str]]]:
        """Group concrete installed families under uncluttered base names."""

        candidates = {
            family: cls._font_family_variant_candidate(family)
            for family in families
        }
        family_names = {family.casefold() for family in families}
        candidate_counts: dict[str, int] = {}
        for base, variant in candidates.values():
            if variant == "Regular":
                continue
            key = base.casefold()
            candidate_counts[key] = candidate_counts.get(key, 0) + 1

        grouped: dict[str, list[tuple[str, str]]] = {}
        for family in families:
            base, variant = candidates[family]
            can_group = variant != "Regular" and (
                base.casefold() in family_names
                or candidate_counts.get(base.casefold(), 0) >= 2
            )
            if not can_group:
                base, variant = family, "Regular"
            grouped.setdefault(base, []).append((variant, family))

        result: dict[str, list[tuple[str, str]]] = {}
        for base in sorted(grouped, key=str.casefold):
            variants = grouped[base]
            variants.sort(
                key=lambda item: (
                    item[0] != "Regular",
                    item[0].casefold(),
                    item[1].casefold(),
                )
            )
            result[base] = variants
        return result

    def _font_group_for_family(self, family: str) -> tuple[str, str]:
        family, _alias_style = self._canonical_text_font_family(family)
        for base, variants in self._text_font_groups.items():
            for variant, concrete_family in variants:
                if concrete_family == family:
                    return base, variant
        first_base = next(iter(self._text_font_groups), "")
        return first_base, "Regular"

    def _selected_text_font_family(self) -> str:
        if hasattr(self, "text_font_variant_combo"):
            family = self.text_font_variant_combo.currentData()
            if isinstance(family, str) and family:
                return family
        base = self.text_font_combo.currentText()
        variants = self._text_font_groups.get(base, [])
        if variants:
            return variants[0][1]
        return QFontInfo(QFont()).family()

    def _refresh_text_font_variants(
        self,
        base_family: str,
        preferred_family: str | None = None,
    ) -> None:
        variants = self._text_font_groups.get(base_family, [])
        if preferred_family:
            preferred_family, _alias_style = (
                self._canonical_text_font_family(preferred_family)
            )
        self.text_font_variant_combo.blockSignals(True)
        try:
            self.text_font_variant_combo.clear()
            for label, concrete_family in variants:
                self.text_font_variant_combo.addItem(label, concrete_family)
                index = self.text_font_variant_combo.count() - 1
                self.text_font_variant_combo.setItemData(
                    index,
                    QFont(concrete_family),
                    Qt.ItemDataRole.FontRole,
                )
            index = -1
            if preferred_family:
                index = self.text_font_variant_combo.findData(
                    preferred_family
                )
            if index < 0:
                index = self.text_font_variant_combo.findText("Regular")
            self.text_font_variant_combo.setCurrentIndex(max(0, index))
            self.text_font_variant_combo.setEnabled(
                self.text_font_variant_combo.count() > 1
            )
        finally:
            self.text_font_variant_combo.blockSignals(False)

    def _build_text_controls(self) -> QWidget:
        widget = QWidget()
        widget.setObjectName("TextControls")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 6, 0, 10)
        layout.setSpacing(6)

        heading = QLabel("Text")
        heading.setObjectName("SectionHeading")
        layout.addWidget(heading)

        self.text_editor = QPlainTextEdit()
        self.text_editor.setPlaceholderText("Enter text…")
        self.text_editor.setMinimumHeight(72)
        self.text_editor.setMaximumHeight(120)
        self.text_editor.setMinimumWidth(0)
        self.text_editor.setTabChangesFocus(True)
        self.text_editor.textChanged.connect(self._text_control_changed)
        layout.addWidget(self.text_editor)

        typography_heading = QLabel("Typography")
        typography_heading.setObjectName("TextSubheading")
        layout.addWidget(typography_heading)

        typography_form = QFormLayout()
        self._configure_inspector_form(typography_form)
        layout.addLayout(typography_form)

        installed_families = self._installed_text_font_families()
        self._text_font_aliases = self._fontconfig_text_font_aliases(
            installed_families
        )
        selectable_families = [
            family
            for family in installed_families
            if family.casefold() not in self._text_font_aliases
        ]
        self._text_font_groups = self._group_text_font_families(
            selectable_families
        )

        self.text_font_combo = QComboBox()
        for base_family, variants in self._text_font_groups.items():
            preview_family = variants[0][1]
            self.text_font_combo.addItem(base_family, preview_family)
            item_index = self.text_font_combo.count() - 1
            self.text_font_combo.setItemData(
                item_index,
                QFont(preview_family),
                Qt.ItemDataRole.FontRole,
            )
        self.text_font_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.text_font_combo.setMinimumContentsLength(10)
        self._configure_inspector_field(self.text_font_combo)
        self.text_font_combo.setToolTip(
            "Base font families, previewed in their own typeface. Family-level "
            "alternatives such as Condensed or SemiBold are in Variant."
        )
        typography_form.addRow("Font", self.text_font_combo)

        self.text_font_variant_combo = QComboBox()
        self.text_font_variant_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.text_font_variant_combo.setMinimumContentsLength(8)
        self._configure_inspector_field(self.text_font_variant_combo)
        self.text_font_variant_combo.setToolTip(
            "Installed alternatives belonging to the selected base family."
        )
        typography_form.addRow("Variant", self.text_font_variant_combo)

        default_family = QFontInfo(QFont()).family()
        default_base, _default_variant = self._font_group_for_family(
            default_family
        )
        default_index = self.text_font_combo.findText(default_base)
        self.text_font_combo.setCurrentIndex(max(0, default_index))
        self._refresh_text_font_variants(
            self.text_font_combo.currentText(),
            default_family,
        )
        self.text_font_combo.currentTextChanged.connect(
            self._text_font_group_changed
        )
        self.text_font_variant_combo.currentIndexChanged.connect(
            self._text_font_variant_changed
        )

        self.text_font_style_combo = QComboBox()
        self.text_font_style_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.text_font_style_combo.setMinimumContentsLength(8)
        self._configure_inspector_field(self.text_font_style_combo)
        self.text_font_style_combo.currentTextChanged.connect(
            self._text_style_changed
        )
        typography_form.addRow("Style", self.text_font_style_combo)

        self.text_size_spin = self._configured_spin(
            minimum=1.0,
            maximum=1000.0,
            decimals=1,
            step=1.0,
            suffix=" pt",
        )
        self.text_size_spin.setToolTip(
            "Font point size, matching conventional word-processor sizing."
        )
        self.text_size_spin.valueChanged.connect(self._text_control_changed)
        typography_form.addRow("Size", self.text_size_spin)

        format_bar = QWidget()
        format_bar.setMinimumWidth(0)
        format_layout = QHBoxLayout(format_bar)
        format_layout.setContentsMargins(0, 0, 0, 0)
        format_layout.setSpacing(4)
        self.text_bold_button = QPushButton("B")
        self.text_italic_button = QPushButton("I")
        self.text_underline_button = QPushButton("U")
        self.text_strike_button = QPushButton("S")
        for button, tooltip in (
            (self.text_bold_button, "Bold"),
            (self.text_italic_button, "Italic"),
            (self.text_underline_button, "Underline"),
            (self.text_strike_button, "Strikethrough"),
        ):
            button.setCheckable(True)
            button.setFixedWidth(34)
            button.setToolTip(tooltip)
            if button in (
                self.text_bold_button,
                self.text_italic_button,
            ):
                button.toggled.connect(self._text_emphasis_changed)
            else:
                button.toggled.connect(self._text_control_changed)
            format_layout.addWidget(button)
        format_layout.addStretch(1)
        typography_form.addRow("Effects", format_bar)

        self.text_alignment_combo = QComboBox()
        for title, value in (
            ("Left", "left"),
            ("Center", "center"),
            ("Right", "right"),
            ("Justified", "justify"),
        ):
            self.text_alignment_combo.addItem(title, value)
        self._configure_inspector_field(self.text_alignment_combo)
        self.text_alignment_combo.currentIndexChanged.connect(
            self._text_control_changed
        )
        typography_form.addRow("Align", self.text_alignment_combo)

        self.text_case_combo = QComboBox()
        for title, value in (
            ("Normal", "normal"),
            ("UPPERCASE", "uppercase"),
            ("lowercase", "lowercase"),
            ("Title Case", "title"),
        ):
            self.text_case_combo.addItem(title, value)
        self._configure_inspector_field(self.text_case_combo)
        self.text_case_combo.currentIndexChanged.connect(
            self._text_control_changed
        )
        typography_form.addRow("Case", self.text_case_combo)

        spacing_heading = QLabel("Spacing & layout")
        spacing_heading.setObjectName("TextSubheading")
        layout.addWidget(spacing_heading)

        spacing_form = QFormLayout()
        self._configure_inspector_form(spacing_form)
        layout.addLayout(spacing_form)

        self.text_kerning_check = QCheckBox("Pair kerning")
        self.text_kerning_check.setChecked(True)
        self.text_kerning_check.setToolTip(
            "Use the selected font's kerning pairs when positioning glyphs."
        )
        self.text_kerning_check.toggled.connect(self._text_control_changed)
        spacing_form.addRow(self.text_kerning_check)

        self.text_wrap_check = QCheckBox("Wrap to text box width")
        self.text_wrap_check.toggled.connect(self._text_layout_control_changed)
        spacing_form.addRow(self.text_wrap_check)

        self.text_character_spacing_spin = self._configured_spin(
            minimum=-25.0,
            maximum=100.0,
            decimals=3,
            step=0.1,
            suffix=" mm",
        )
        self.text_character_spacing_spin.valueChanged.connect(
            self._text_control_changed
        )
        spacing_form.addRow(
            "Character spacing",
            self.text_character_spacing_spin,
        )

        self.text_word_spacing_spin = self._configured_spin(
            minimum=-25.0,
            maximum=100.0,
            decimals=3,
            step=0.25,
            suffix=" mm",
        )
        self.text_word_spacing_spin.valueChanged.connect(
            self._text_control_changed
        )
        spacing_form.addRow("Word spacing", self.text_word_spacing_spin)

        self.text_line_spacing_spin = self._configured_spin(
            minimum=25.0,
            maximum=500.0,
            decimals=1,
            step=5.0,
            suffix=" %",
        )
        self.text_line_spacing_spin.valueChanged.connect(
            self._text_control_changed
        )
        spacing_form.addRow("Line spacing", self.text_line_spacing_spin)

        self.text_horizontal_scale_spin = self._configured_spin(
            minimum=10.0,
            maximum=400.0,
            decimals=1,
            step=5.0,
            suffix=" %",
        )
        self.text_horizontal_scale_spin.setToolTip(
            "Horizontally stretch or condense character width."
        )
        self.text_horizontal_scale_spin.valueChanged.connect(
            self._text_control_changed
        )
        spacing_form.addRow(
            "Character width",
            self.text_horizontal_scale_spin,
        )

        self.text_box_width_spin = self._configured_spin(
            minimum=0.1,
            maximum=100000.0,
            decimals=3,
            step=1.0,
            suffix=" mm",
        )
        self.text_box_width_spin.valueChanged.connect(
            self._text_control_changed
        )
        spacing_form.addRow("Text box width", self.text_box_width_spin)

        geometry_heading = QLabel("CNC geometry")
        geometry_heading.setObjectName("TextSubheading")
        layout.addWidget(geometry_heading)

        geometry_form = QFormLayout()
        self._configure_inspector_form(geometry_form)
        layout.addLayout(geometry_form)

        self.text_geometry_combo = QComboBox()
        self.text_geometry_combo.addItem("Filled", "filled")
        self.text_geometry_combo.addItem("Outline", "outline")
        self._configure_inspector_field(self.text_geometry_combo)
        self.text_geometry_combo.currentIndexChanged.connect(
            self._text_geometry_control_changed
        )
        geometry_form.addRow("Geometry", self.text_geometry_combo)

        self.text_outline_width_spin = self._configured_spin(
            minimum=0.05,
            maximum=50.0,
            decimals=3,
            step=0.1,
            suffix=" mm",
        )
        self.text_outline_width_spin.valueChanged.connect(
            self._text_control_changed
        )
        self.text_outline_label = QLabel("Outline width")
        geometry_form.addRow(
            self.text_outline_label,
            self.text_outline_width_spin,
        )

        self.text_depth_spin = self._configured_spin(
            minimum=0.05,
            maximum=1000.0,
            decimals=3,
            step=0.25,
            suffix=" mm",
        )
        self.text_depth_spin.setToolTip(
            "Extruded text thickness. Text top remains at the object's Z level."
        )
        self.text_depth_spin.valueChanged.connect(self._text_control_changed)
        geometry_form.addRow("Depth", self.text_depth_spin)

        self._text_shortcuts: list[QShortcut] = []
        for sequence, callback in (
            ("Ctrl+B", self.text_bold_button.toggle),
            ("Ctrl+I", self.text_italic_button.toggle),
            ("Ctrl+U", self.text_underline_button.toggle),
            ("Ctrl+Shift+X", self.text_strike_button.toggle),
            (
                "Ctrl+L",
                lambda: self.text_alignment_combo.setCurrentIndex(
                    self.text_alignment_combo.findData("left")
                ),
            ),
            (
                "Ctrl+E",
                lambda: self.text_alignment_combo.setCurrentIndex(
                    self.text_alignment_combo.findData("center")
                ),
            ),
            (
                "Ctrl+R",
                lambda: self.text_alignment_combo.setCurrentIndex(
                    self.text_alignment_combo.findData("right")
                ),
            ),
            (
                "Ctrl+J",
                lambda: self.text_alignment_combo.setCurrentIndex(
                    self.text_alignment_combo.findData("justify")
                ),
            ),
        ):
            shortcut = QShortcut(QKeySequence(sequence), widget)
            shortcut.setContext(
                Qt.ShortcutContext.WidgetWithChildrenShortcut
            )
            shortcut.activated.connect(callback)
            self._text_shortcuts.append(shortcut)

        note = QLabel(
            "Font geometry comes from the exact installed system font face. "
            "CarveFoundry refuses silent Qt font substitution when regenerating "
            "text so CNC geometry cannot quietly change typefaces. Selected text "
            "uses the same viewport resize handles as other design objects."
        )
        note.setObjectName("Muted")
        note.setWordWrap(True)
        layout.addWidget(note)

        self.text_font_face_status = QLabel()
        self.text_font_face_status.setObjectName("TextFontFaceStatus")
        self.text_font_face_status.setWordWrap(True)
        layout.addWidget(self.text_font_face_status)

        self.text_font_verify_button = QPushButton("Verify Font Face")
        self.text_font_verify_button.setToolTip(
            "Verify that Qt resolves the selected family and style to the exact "
            "installed face used to generate CNC outlines."
        )
        self.text_font_verify_button.clicked.connect(
            self._verify_selected_text_font_face
        )
        layout.addWidget(self.text_font_verify_button)

        self.text_font_warning = QLabel()
        self.text_font_warning.setObjectName("TextFontWarning")
        self.text_font_warning.setWordWrap(True)
        self.text_font_warning.hide()
        layout.addWidget(self.text_font_warning)

        self.text_cnc_hint = QLabel()
        self.text_cnc_hint.setObjectName("TextCncHint")
        self.text_cnc_hint.setWordWrap(True)
        layout.addWidget(self.text_cnc_hint)

        initial_family = self._selected_text_font_family()
        self._refresh_text_font_styles(initial_family, "Regular")
        self._update_text_editor_preview(initial_family)

        widget.setVisible(False)
        return widget

    def _legacy_text_properties(self, item: ProjectItem) -> TextProperties:
        dimensions = (
            np.asarray(item.mesh.dimensions, dtype=float)
            * float(item.source_units.millimeters_per_unit)
            if item.mesh is not None
            else np.array((40.0, 12.0, 1.0), dtype=float)
        )
        content = item.name.strip() or "Text"
        return TextProperties(
            content=content,
            font_family=QFontInfo(QFont()).family(),
            size_pt=max(6.0, float(dimensions[1]) * 72.0 / 25.4),
            box_width_mm=max(0.1, float(dimensions[0])),
            depth_mm=max(0.05, float(dimensions[2])),
        )

    def _refresh_text_font_styles(
        self,
        family: str,
        preferred: str | None = None,
    ) -> None:
        styles = list(QFontDatabase.styles(family))
        if not styles:
            styles = ["Regular"]

        current = preferred or self.text_font_style_combo.currentText()
        self.text_font_style_combo.blockSignals(True)
        try:
            self.text_font_style_combo.clear()
            self.text_font_style_combo.addItems(styles)
            index = self.text_font_style_combo.findText(current)
            if index < 0:
                index = self.text_font_style_combo.findText("Regular")
            self.text_font_style_combo.setCurrentIndex(max(0, index))
        finally:
            self.text_font_style_combo.blockSignals(False)

    def _update_text_editor_preview(
        self,
        requested_family: str | None = None,
    ) -> None:
        family = (
            requested_family
            or self._selected_text_font_family()
            or QFont().family()
        )
        preview_font = QFont(family)
        style = self.text_font_style_combo.currentText()
        if style:
            preview_font.setStyleName(style)
        if self.text_bold_button.isChecked():
            preview_font.setBold(True)
        if self.text_italic_button.isChecked():
            preview_font.setItalic(True)
        preview_font.setUnderline(self.text_underline_button.isChecked())
        preview_font.setStrikeOut(self.text_strike_button.isChecked())
        preview_font.setPointSizeF(
            max(10.0, min(22.0, float(self.text_size_spin.value())))
        )
        self.text_editor.setFont(preview_font)

    def _update_text_font_availability(self, requested_family: str) -> None:
        installed = set(QFontDatabase.families())
        if requested_family and requested_family not in installed:
            fallback = self._selected_text_font_family()
            self.text_font_face_status.setText("Font face: unresolved")
            self.text_font_warning.setText(
                f"Font “{requested_family}” is not installed. "
                f"Showing {fallback or 'the system fallback'} for editing only; "
                "CarveFoundry will not regenerate CNC text with a substituted font."
            )
            self.text_font_warning.show()
            return

        family = self._selected_text_font_family() or requested_family
        style = self.text_font_style_combo.currentText() or "Regular"
        try:
            face = describe_qt_font_face(family, style)
        except ValueError as exc:
            self.text_font_face_status.setText("Font face: unresolved")
            self.text_font_warning.setText(str(exc))
            self.text_font_warning.show()
            return

        self.text_font_face_status.setText(
            f"Font face: {face.display_name}  •  exact"
        )
        self.text_font_warning.clear()
        self.text_font_warning.hide()

    def _verify_selected_text_font_face(self) -> None:
        family = self._selected_text_font_family()
        style = self.text_font_style_combo.currentText() or "Regular"
        try:
            face = describe_qt_font_face(family, style)
        except ValueError as exc:
            self._update_text_font_availability(family)
            self.statusBar().showMessage(
                f"Font verification failed: {exc}",
                7000,
            )
            return
        self._update_text_font_availability(family)
        self.statusBar().showMessage(
            f"Exact font verified: {face.display_name}",
            4000,
        )

    def _sync_text_controls(self, item: ProjectItem) -> None:
        properties = item.text_properties or self._legacy_text_properties(item)
        family = properties.font_family or QFont().family()
        canonical_family, alias_style = self._canonical_text_font_family(
            family
        )
        installed_families = set(QFontDatabase.families())
        display_family = (
            canonical_family
            if canonical_family in installed_families
            else QFont().family()
        )

        self._updating_text_controls = True
        try:
            self.text_editor.setPlainText(properties.content)
            base_family, _variant = self._font_group_for_family(
                display_family
            )
            font_index = self.text_font_combo.findText(base_family)
            self.text_font_combo.setCurrentIndex(max(0, font_index))
            self._refresh_text_font_variants(
                self.text_font_combo.currentText(),
                display_family,
            )
            display_family = self._selected_text_font_family()
            self._refresh_text_font_styles(
                display_family,
                alias_style or properties.font_style,
            )
            self.text_size_spin.setValue(properties.size_pt)
            style_bold, style_italic = self._text_style_traits(
                display_family,
                self.text_font_style_combo.currentText(),
            )
            self.text_bold_button.setChecked(
                properties.bold or style_bold
            )
            self.text_italic_button.setChecked(
                properties.italic or style_italic
            )
            self.text_underline_button.setChecked(properties.underline)
            self.text_strike_button.setChecked(properties.strikeout)

            alignment_index = self.text_alignment_combo.findData(
                properties.alignment
            )
            self.text_alignment_combo.setCurrentIndex(
                max(0, alignment_index)
            )
            case_index = self.text_case_combo.findData(properties.case_mode)
            self.text_case_combo.setCurrentIndex(max(0, case_index))

            self.text_kerning_check.setChecked(properties.kerning)
            self.text_wrap_check.setChecked(properties.wrap_to_width)
            self.text_character_spacing_spin.setValue(
                properties.character_spacing_mm
            )
            self.text_word_spacing_spin.setValue(
                properties.word_spacing_mm
            )
            self.text_line_spacing_spin.setValue(
                properties.line_spacing_percent
            )
            self.text_horizontal_scale_spin.setValue(
                properties.horizontal_scale_percent
            )
            self.text_box_width_spin.setValue(
                max(0.1, properties.box_width_mm or 0.1)
            )

            geometry_index = self.text_geometry_combo.findData(
                properties.geometry_mode
            )
            self.text_geometry_combo.setCurrentIndex(
                max(0, geometry_index)
            )
            self.text_outline_width_spin.setValue(
                properties.outline_width_mm
            )
            self.text_depth_spin.setValue(properties.depth_mm)
        finally:
            self._updating_text_controls = False

        self._update_text_font_availability(family)
        self._update_text_editor_preview(display_family)
        self._update_text_control_enablement()

    @staticmethod
    def _text_style_traits(
        family: str,
        style: str,
    ) -> tuple[bool, bool]:
        font = QFontDatabase.font(family, style, 12)
        return font.bold(), font.italic()

    def _set_text_emphasis_buttons_from_style(self) -> None:
        family = self._selected_text_font_family()
        style = self.text_font_style_combo.currentText()
        style_bold, style_italic = self._text_style_traits(
            family,
            style,
        )
        self.text_bold_button.blockSignals(True)
        self.text_italic_button.blockSignals(True)
        try:
            self.text_bold_button.setChecked(style_bold)
            self.text_italic_button.setChecked(style_italic)
        finally:
            self.text_bold_button.blockSignals(False)
            self.text_italic_button.blockSignals(False)

    def _choose_text_style_for_emphasis(
        self,
        *,
        bold: bool,
        italic: bool,
    ) -> None:
        family = self._selected_text_font_family()
        styles = list(QFontDatabase.styles(family))
        if not styles:
            return

        current = self.text_font_style_combo.currentText()
        candidates = [
            style
            for style in styles
            if self._text_style_traits(family, style) == (bold, italic)
        ]
        if not candidates:
            return

        preferred = current if current in candidates else candidates[0]
        index = self.text_font_style_combo.findText(preferred)
        if index >= 0 and index != self.text_font_style_combo.currentIndex():
            self.text_font_style_combo.blockSignals(True)
            try:
                self.text_font_style_combo.setCurrentIndex(index)
            finally:
                self.text_font_style_combo.blockSignals(False)

    def _text_emphasis_changed(self, _checked: bool) -> None:
        if self._updating_text_controls:
            return
        self._choose_text_style_for_emphasis(
            bold=self.text_bold_button.isChecked(),
            italic=self.text_italic_button.isChecked(),
        )
        self._text_control_changed()

    def _text_style_changed(self, _style: str) -> None:
        if self._updating_text_controls:
            return
        self._set_text_emphasis_buttons_from_style()
        self._update_text_font_availability(
            self._selected_text_font_family()
        )
        self._text_control_changed()

    def _text_font_group_changed(self, base_family: str) -> None:
        if self._updating_text_controls:
            return
        self._refresh_text_font_variants(base_family)
        self._apply_text_font_selection_change()

    def _text_font_variant_changed(self, _index: int) -> None:
        if self._updating_text_controls:
            return
        self._apply_text_font_selection_change()

    def _apply_text_font_selection_change(self) -> None:
        family = self._selected_text_font_family()
        preferred_style = self.text_font_style_combo.currentText() or "Regular"
        self._refresh_text_font_styles(family, preferred_style)
        self._set_text_emphasis_buttons_from_style()
        self._update_text_font_availability(family)
        self._update_text_editor_preview(family)
        self._text_control_changed()

    def _text_layout_control_changed(self, _checked: bool) -> None:
        self._update_text_control_enablement()
        self._text_control_changed()

    def _text_geometry_control_changed(self, _index: int) -> None:
        self._update_text_control_enablement()
        self._text_control_changed()

    def _update_text_control_enablement(self) -> None:
        if not hasattr(self, "text_wrap_check"):
            return
        # Width also defines the alignment frame when wrapping is off, so it
        # remains editable at all times. Wrap only controls line breaking.
        self.text_box_width_spin.setEnabled(True)
        outline_enabled = (
            self.text_geometry_combo.currentData() == "outline"
        )
        self.text_outline_width_spin.setVisible(outline_enabled)
        self.text_outline_label.setVisible(outline_enabled)
        self.text_outline_width_spin.setEnabled(outline_enabled)
        self._update_text_cnc_hint()

    def _update_text_cnc_hint(self) -> None:
        if not hasattr(self, "text_cnc_hint"):
            return
        cutter = (
            self.tool_combo.currentData()
            if hasattr(self, "tool_combo")
            else None
        )
        diameter = getattr(cutter, "diameter_mm", None)
        if diameter is None:
            self.text_cnc_hint.setText(
                "Choose a cutter on Toolpaths to compare it with text geometry."
            )
            return

        diameter = float(diameter)
        if (
            self.text_geometry_combo.currentData() == "outline"
            and self.text_outline_width_spin.value() < diameter
        ):
            self.text_cnc_hint.setText(
                f"Machining warning: {self.text_outline_width_spin.value():.3f} mm "
                f"outline is narrower than the {diameter:.3f} mm active cutter. "
                "Use a smaller cutter, widen the outline, or use a V-carve strategy."
            )
            return

        self.text_cnc_hint.setText(
            f"Active cutter: {diameter:.3f} mm. Fine glyph details may require "
            "a smaller cutter or V-carve; Preview the calculated toolpath before cutting."
        )

    def _text_control_changed(self, *_args) -> None:
        if self._updating_text_controls:
            return
        self._update_text_control_enablement()
        self._update_text_editor_preview()
        self._text_update_timer.start()

    def _text_properties_from_controls(self) -> TextProperties:
        return TextProperties(
            content=self.text_editor.toPlainText(),
            font_family=self._selected_text_font_family(),
            font_style=self.text_font_style_combo.currentText() or "Regular",
            size_pt=float(self.text_size_spin.value()),
            bold=self.text_bold_button.isChecked(),
            italic=self.text_italic_button.isChecked(),
            underline=self.text_underline_button.isChecked(),
            strikeout=self.text_strike_button.isChecked(),
            alignment=str(
                self.text_alignment_combo.currentData() or "left"
            ),
            character_spacing_mm=float(
                self.text_character_spacing_spin.value()
            ),
            word_spacing_mm=float(self.text_word_spacing_spin.value()),
            kerning=self.text_kerning_check.isChecked(),
            line_spacing_percent=float(self.text_line_spacing_spin.value()),
            horizontal_scale_percent=float(
                self.text_horizontal_scale_spin.value()
            ),
            wrap_to_width=self.text_wrap_check.isChecked(),
            box_width_mm=float(self.text_box_width_spin.value()),
            depth_mm=float(self.text_depth_spin.value()),
            geometry_mode=str(
                self.text_geometry_combo.currentData() or "filled"
            ),
            outline_width_mm=float(
                self.text_outline_width_spin.value()
            ),
            case_mode=str(self.text_case_combo.currentData() or "normal"),
        )

    def _before_text_properties_change(self, _index: int) -> None:
        """History hook supplied by project_window.MainWindow."""

    def _after_text_properties_change(self, _index: int) -> None:
        """History hook supplied by project_window.MainWindow."""

    def _apply_text_properties_from_controls(self) -> None:
        if self._updating_text_controls:
            return
        index = self._selected_item_index()
        item = self._selected_item()
        if (
            index is None
            or item is None
            or item.kind.lower() != "text"
            or item.mesh is None
        ):
            return

        properties = self._text_properties_from_controls()
        if not properties.content.strip():
            self.statusBar().showMessage(
                "Text object cannot be blank",
                3500,
            )
            return
        if item.text_properties == properties:
            return

        try:
            properties.validate()
            generated_mesh = text_mesh(properties=properties)
        except (RuntimeError, ValueError) as exc:
            self._set_activity_info(f"Text update failed\n{exc}")
            self.statusBar().showMessage(
                f"Could not update text: {exc}",
                6000,
            )
            return

        self._before_text_properties_change(index)
        item.mesh = generated_mesh
        item.text_properties = properties
        # Loaded generated objects can point at a materialized embedded STL.
        # Once edited, saving must embed the newly generated mesh instead.
        item.source_path = None
        self._invalidate_toolpaths("Text geometry")
        self._sync_transform_controls(item)
        self.selection_info.setText(self._mesh_properties_text(item))
        row = index + 1
        self.object_selector.blockSignals(True)
        try:
            self.object_selector.setItemText(
                row,
                self._object_selector_text(item),
            )
        finally:
            self.object_selector.blockSignals(False)
        list_item = self.project_list.item(row)
        if list_item is not None:
            kind = item.kind.upper()
            content_preview = " ".join(
                properties.content.splitlines()
            ).strip()
            if len(content_preview) > 90:
                content_preview = content_preview[:87].rstrip() + "…"
            list_item.setToolTip(
                f"{kind} • {item.name}"
                + (
                    f"\nContent: {content_preview}"
                    if content_preview
                    else ""
                )
                + "\nDouble-click or press F2 to rename."
            )
        self.viewport.set_selected_item(index)
        self.viewport.update()
        self._after_text_properties_change(index)
        self.statusBar().showMessage(
            f"Updated text: {item.name}",
            2500,
        )

    def _focus_text_editor(self) -> None:
        item = self._selected_item()
        if item is None or item.kind.lower() != "text":
            return
        self._ensure_inspector_visible()
        self.text_editor.setFocus(Qt.FocusReason.OtherFocusReason)
        self.text_editor.selectAll()
