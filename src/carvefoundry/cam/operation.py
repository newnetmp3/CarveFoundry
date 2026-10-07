from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from uuid import uuid4

from carvefoundry.core.tools import Cutter

CamParameter = str | int | float | bool | None


@dataclass(slots=True)
class CamOperation:
    """Persistent machining intent independent from generated machine motion."""

    operation: str
    cutter: Cutter
    source_item_ids: tuple[str, ...] = ()
    parameters: dict[str, CamParameter] = field(default_factory=dict)
    operation_id: str = field(default_factory=lambda: uuid4().hex)
    enabled: bool = True
    stale_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.operation:
            raise ValueError("CAM operation type cannot be empty.")
        if not self.operation_id:
            raise ValueError("CAM operation ID cannot be empty.")
        if any(not item_id for item_id in self.source_item_ids):
            raise ValueError("CAM source item IDs cannot be empty.")
        if len(set(self.source_item_ids)) != len(self.source_item_ids):
            raise ValueError("CAM source item IDs must be unique.")
        if not isinstance(self.enabled, bool):
            raise ValueError("CAM enabled state must be boolean.")

        for key, value in self.parameters.items():
            if not isinstance(key, str) or not key:
                raise ValueError("CAM parameter names must be non-empty strings.")
            if value is not None and not isinstance(value, (str, int, float, bool)):
                raise ValueError(f"Unsupported CAM parameter value for {key}.")
            if isinstance(value, float) and not isfinite(value):
                raise ValueError(f"CAM parameter {key} must be finite.")

        if self.stale_reason is not None and not self.stale_reason.strip():
            raise ValueError("CAM stale reason cannot be blank.")

    @property
    def needs_recalculation(self) -> bool:
        return self.stale_reason is not None

    def mark_stale(self, reason: str) -> None:
        reason = reason.strip()
        if not reason:
            raise ValueError("CAM stale reason cannot be blank.")
        self.stale_reason = reason

    def mark_ready(self) -> None:
        self.stale_reason = None
