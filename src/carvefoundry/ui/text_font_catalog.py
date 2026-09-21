"""Installed-font discovery, alias normalization, and family/variant grouping."""
from __future__ import annotations

import subprocess

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase, QFontInfo

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





class TextFontCatalogMixin:
    """Resolve usable system font families and presentation variants."""

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

