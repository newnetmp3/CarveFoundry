"""Verified, non-overwriting native CF3D recovery checkpoints.

A checkpoint is a complete native project alongside an atomic JSON manifest.
The user decides whether to recover; automatic snapshots never replace the
last deliberate Save and do not mark the project clean.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .project import Project
from .project_file import load_project, save_project

_KEY = re.compile(r"^[0-9a-f]{32}$")
MAX_RECOVERIES = 12


@dataclass(frozen=True, slots=True)
class RecoveryEntry:
    key: str
    name: str
    timestamp: str
    state_id: int
    original_path: Path | None
    original_mtime_ns: int | None
    project_file: Path
    metadata_file: Path
    sha256: str

    def original_changed(self) -> bool:
        if self.original_path is None or self.original_mtime_ns is None:
            return False
        try:
            return self.original_path.stat().st_mtime_ns != self.original_mtime_ns
        except OSError:
            return True


def _validate_key(key: str) -> None:
    if _KEY.fullmatch(key) is None:
        raise ValueError("Recovery key must be a 32-character lowercase hex UUID.")


def _atomic_json(path: Path, record: dict[str, object]) -> None:
    temporary = path.with_suffix(".json.tmp")
    try:
        temporary.write_text(
            json.dumps(record, indent=2, sort_keys=True), encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def save_recovery(
    project: Project,
    directory: Path,
    *,
    key: str,
    state_id: int,
    original_path: Path | None,
) -> RecoveryEntry:
    _validate_key(key)
    if state_id < 0:
        raise ValueError("Recovery state ID cannot be negative.")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    checkpoint = directory / f"{key}.cf3d"
    metadata = directory / f"{key}.json"
    # Native save uses temporary + replace. The previous complete checkpoint
    # remains present if compression or writing fails.
    save_project(project, checkpoint)
    checksum = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    source = original_path.expanduser().resolve() if original_path else None
    try:
        mtime = source.stat().st_mtime_ns if source is not None else None
    except OSError:
        mtime = None
    timestamp = datetime.now(UTC).isoformat(timespec="seconds")
    _atomic_json(metadata, {
        "version": 1,
        "key": key,
        "project_name": project.name,
        "timestamp_utc": timestamp,
        "state_id": state_id,
        "original_path": str(source) if source is not None else None,
        "original_mtime_ns": mtime,
        "sha256": checksum,
    })
    return RecoveryEntry(
        key=key, name=project.name, timestamp=timestamp,
        state_id=state_id, original_path=source,
        original_mtime_ns=mtime,
        project_file=checkpoint, metadata_file=metadata, sha256=checksum,
    )


def list_recoveries(directory: Path) -> tuple[RecoveryEntry, ...]:
    root = Path(directory)
    if not root.is_dir():
        return ()
    entries = []
    for metadata in root.glob("*.json"):
        try:
            if not _KEY.fullmatch(metadata.stem):
                continue
            data = json.loads(metadata.read_text(encoding="utf-8"))
            if data.get("version") != 1 or data.get("key") != metadata.stem:
                continue
            source = data.get("original_path")
            if source is not None and (not isinstance(source, str) or not source):
                continue
            timestamp = data["timestamp_utc"]
            datetime.fromisoformat(timestamp)
            checksum = data["sha256"]
            name = data["project_name"]
            state_id = data["state_id"]
            mtime = data["original_mtime_ns"]
            if (
                not isinstance(checksum, str)
                or re.fullmatch(r"[0-9a-f]{64}", checksum) is None
                or not isinstance(name, str)
                or not isinstance(state_id, int) or state_id < 0
                or mtime is not None and (not isinstance(mtime, int) or mtime < 0)
            ):
                continue
            candidate = metadata.with_suffix(".cf3d")
            if not candidate.is_file():
                continue
            entries.append(RecoveryEntry(
                key=metadata.stem, name=name,
                timestamp=timestamp, state_id=state_id,
                original_path=Path(source) if source else None,
                original_mtime_ns=mtime,
                project_file=candidate, metadata_file=metadata,
                sha256=checksum,
            ))
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            # Broken metadata must not crash app startup or hide other entries.
            continue
    return tuple(sorted(entries, key=lambda item: item.timestamp, reverse=True))


def load_recovery(entry: RecoveryEntry) -> Project:
    digest = hashlib.sha256(entry.project_file.read_bytes()).hexdigest()
    if digest != entry.sha256:
        raise ValueError(
            "Recovery checkpoint was modified or corrupted; the original project "
            "has not been changed."
        )
    return load_project(entry.project_file)


def discard_recovery(entry: RecoveryEntry) -> None:
    entry.project_file.unlink(missing_ok=True)
    entry.metadata_file.unlink(missing_ok=True)


def discard_key(directory: Path, key: str) -> None:
    _validate_key(key)
    root = Path(directory)
    (root / f"{key}.cf3d").unlink(missing_ok=True)
    (root / f"{key}.json").unlink(missing_ok=True)


def prune_recoveries(directory: Path, *, keep: int = MAX_RECOVERIES) -> None:
    if keep < 1:
        raise ValueError("Keep at least one recovery checkpoint.")
    for entry in list_recoveries(directory)[keep:]:
        discard_recovery(entry)
