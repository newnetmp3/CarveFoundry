from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ResolvedFontFace:
    """Requested and actual Qt font face used for text geometry."""

    requested_family: str
    requested_style: str
    family: str
    style: str
    exact_family: bool
    exact_style: bool

    @property
    def exact(self) -> bool:
        return self.exact_family and self.exact_style

    @property
    def display_name(self) -> str:
        return f"{self.family} — {self.style}" if self.style else self.family


def _match_casefold(value: str, choices: list[str]) -> str | None:
    requested = value.casefold()
    for choice in choices:
        if choice.casefold() == requested:
            return choice
    return None


def resolve_qt_font_face(
    family: str,
    style: str = "Regular",
    *,
    pixel_size: int = 1000,
    strict: bool = True,
):
    """Resolve a Qt font face without silently accepting a substitute."""

    from PySide6.QtGui import QFont, QFontDatabase, QFontInfo, QRawFont

    installed = list(QFontDatabase.families())
    if family:
        matched_family = _match_casefold(family, installed)
        if matched_family is None:
            if strict:
                raise ValueError(
                    f"Font family '{family}' is not installed. Install the "
                    "font or choose another family before generating text."
                )
            matched_family = QFontInfo(QFont()).family()
        requested_family = family
    else:
        # An empty family means "use the system default", not "require Qt's
        # generic alias literally". Resolve that alias up front so the actual
        # concrete face becomes the deterministic CNC font.
        matched_family = QFontInfo(QFont()).family()
        requested_family = matched_family

    styles = list(QFontDatabase.styles(matched_family))
    requested_style = style or "Regular"
    matched_style = _match_casefold(requested_style, styles)
    if matched_style is None and requested_style.casefold() == "regular":
        for alias in ("Regular", "Normal", "Book", "Roman"):
            matched_style = _match_casefold(alias, styles)
            if matched_style is not None:
                break
    if matched_style is None:
        if strict:
            available = ", ".join(styles[:12]) or "none"
            raise ValueError(
                f"Font style '{requested_style}' is not available for "
                f"'{matched_family}'. Available styles: {available}."
            )
        matched_style = styles[0] if styles else ""

    font = QFontDatabase.font(
        matched_family,
        matched_style or "",
        max(1, int(pixel_size)),
    )
    font.setPixelSize(max(1, int(pixel_size)))
    info = QFontInfo(font)
    raw = QRawFont.fromFont(font)
    if not raw.isValid():
        raise ValueError(
            f"Qt could not load usable glyph outlines for "
            f"'{matched_family} — {matched_style}'."
        )

    actual_family = info.family() or matched_family
    actual_style = info.styleName() or matched_style
    exact_family = actual_family.casefold() == matched_family.casefold()
    exact_style = (
        not matched_style
        or actual_style.casefold() == matched_style.casefold()
        or (
            requested_style.casefold() == "regular"
            and actual_style.casefold() in {"normal", "book", "roman"}
        )
    )
    if strict and not (exact_family and exact_style):
        raise ValueError(
            "Qt substituted a different font face: requested "
            f"'{matched_family} — {matched_style}', resolved "
            f"'{actual_family} — {actual_style}'."
        )

    return font, ResolvedFontFace(
        requested_family=requested_family,
        requested_style=requested_style,
        family=actual_family,
        style=actual_style,
        exact_family=exact_family,
        exact_style=exact_style,
    )


def describe_qt_font_face(family: str, style: str = "Regular") -> ResolvedFontFace:
    """Return the actual installed face Qt would use for CNC text."""

    _font, resolved = resolve_qt_font_face(
        family,
        style,
        pixel_size=1000,
        strict=True,
    )
    return resolved
