from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class MachineProfile:
    """Connection, travel, work-zero, and parking preferences for one CNC."""

    name: str = "Onefinity / GRBL"
    port: str = ""
    baud_rate: int = 115200
    work_x_mm: float = 816.0
    work_y_mm: float = 816.0
    work_z_mm: float = 133.0
    parking_enabled: bool = False
    park_x_mm: float = 0.0
    park_y_mm: float = 0.0
    park_z_mm: float = 10.0

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("Machine profile name cannot be empty.")
        if not 1200 <= int(self.baud_rate) <= 2_000_000:
            raise ValueError("Machine baud rate is outside the supported range.")
        travel = (self.work_x_mm, self.work_y_mm, self.work_z_mm)
        if not all(math.isfinite(value) and value > 0 for value in travel):
            raise ValueError("Machine travel dimensions must be positive and finite.")
        parking = (self.park_x_mm, self.park_y_mm, self.park_z_mm)
        if not all(math.isfinite(value) for value in parking):
            raise ValueError("Machine parking coordinates must be finite.")
        if self.park_z_mm < 0:
            raise ValueError("Parking Z must be at or above work Z0.")


def profiles_to_json(
    profiles: list[MachineProfile],
    *,
    active_name: str | None = None,
) -> str:
    for profile in profiles:
        profile.validate()
    return json.dumps(
        {
            "active_name": active_name,
            "profiles": [asdict(profile) for profile in profiles],
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def profiles_from_json(text: str) -> tuple[list[MachineProfile], str | None]:
    if not str(text).strip():
        return [], None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("Saved machine profiles are not valid JSON.") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("profiles"), list):
        raise ValueError("Saved machine profile data has an invalid structure.")

    profiles: list[MachineProfile] = []
    for value in payload["profiles"]:
        if not isinstance(value, dict):
            raise ValueError("Saved machine profile entry is invalid.")
        profile = MachineProfile(
            name=str(value.get("name", "Machine")),
            port=str(value.get("port", "")),
            baud_rate=int(value.get("baud_rate", 115200)),
            work_x_mm=float(value.get("work_x_mm", 816.0)),
            work_y_mm=float(value.get("work_y_mm", 816.0)),
            work_z_mm=float(value.get("work_z_mm", 133.0)),
            parking_enabled=bool(value.get("parking_enabled", False)),
            park_x_mm=float(value.get("park_x_mm", 0.0)),
            park_y_mm=float(value.get("park_y_mm", 0.0)),
            park_z_mm=float(value.get("park_z_mm", 10.0)),
        )
        profile.validate()
        profiles.append(profile)

    active = payload.get("active_name")
    return profiles, str(active) if isinstance(active, str) and active else None
