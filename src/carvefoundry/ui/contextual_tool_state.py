"""One source of truth for contextual drawing-toolbar visibility.

Inspector selection is independent of the current drawing tool: selecting an
object never silently resets the camera, vector drawing mode or in-progress
stock-plane tool.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ToolOptionsState:
    depth: bool = False
    fixture: bool = False
    measure: bool = False
    polygon: bool = False
    line: bool = False
    pen: bool = False
    text: bool = False

    @classmethod
    def for_mode(cls, mode: str | None) -> ToolOptionsState:
        if not mode or mode in {"camera", "select", "direct_select"}:
            return cls()
        return cls(
            depth=mode not in {"measure", "fixture"},
            fixture=mode == "fixture",
            measure=mode == "measure",
            polygon=mode == "polygon",
            line=mode == "line",
            pen=mode == "pen",
            text=mode == "text",
        )
