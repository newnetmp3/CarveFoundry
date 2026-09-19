"""Crash recovery never overwrites deliberate saves or accepts corrupted snapshots."""
from __future__ import annotations

import json
from uuid import uuid4

import pytest

from carvefoundry.core.primitives import rectangle_mesh
from carvefoundry.core.project import Project, ProjectItem
from carvefoundry.core.project_file import load_project, save_project
from carvefoundry.core.recovery import (
    discard_key,
    discard_recovery,
    list_recoveries,
    load_recovery,
    prune_recoveries,
    save_recovery,
)


def _project(name):
    return Project(
        name=name,
        items=[ProjectItem(
            name="part", kind="rectangle", mesh=rectangle_mesh(10, 12, 2),
        )],
    )


def test_full_recovery_roundtrip_without_overwriting_saved_project(tmp_path):
    document = tmp_path / "original.cf3d"
    save_project(_project("Original"), document)
    original_bytes = document.read_bytes()
    root = tmp_path / "recovery"
    key = uuid4().hex
    modified = _project("Unsaved edits")
    checkpoint = save_recovery(
        modified, root, key=key, state_id=23, original_path=document,
    )
    assert checkpoint.original_path == document.resolve()
    assert checkpoint.original_changed() is False
    assert len(list(root.iterdir())) == 2
    assert document.read_bytes() == original_bytes
    assert list_recoveries(root) == (checkpoint,)
    loaded = load_recovery(checkpoint)
    assert loaded.name == "Unsaved edits"
    assert loaded.items[0].mesh is not None
    assert len(loaded.items[0].mesh.mesh.faces) == 12
    assert loaded.items[0].mesh.mesh.bounds.tolist() == pytest.approx(
        [[-5.0, -6.0, -2.0], [5.0, 6.0, 0.0]],
    )
    assert load_project(document).name == "Original"


def test_detect_changed_original_but_still_allow_explicit_recovery(tmp_path):
    document = save_project(_project("First"), tmp_path / "project.cf3d")
    entry = save_recovery(
        _project("Recover"), tmp_path / "recovery",
        key=uuid4().hex, state_id=1, original_path=document,
    )
    assert not entry.original_changed()
    save_project(_project("Second"), document)
    # Filesystems with timestamp granularity may report same nanosecond;
    # force a measured change without relying on sleep.
    import os
    os.utime(document, ns=(
        document.stat().st_atime_ns,
        entry.original_mtime_ns + 10_000_000,
    ))
    assert entry.original_changed()
    assert load_recovery(entry).name == "Recover"
    assert load_project(document).name == "Second"


def test_checksum_refuses_modified_checkpoint_and_discard_is_isolated(tmp_path):
    root = tmp_path / "recover"
    a = save_recovery(_project("A"), root, key=uuid4().hex, state_id=1, original_path=None)
    b = save_recovery(_project("B"), root, key=uuid4().hex, state_id=2, original_path=None)
    a.project_file.write_bytes(a.project_file.read_bytes() + b"corrupt")
    with pytest.raises(ValueError, match="corrupted"):
        load_recovery(a)
    assert load_recovery(b).name == "B"
    discard_recovery(a)
    assert list_recoveries(root) == (b,)
    discard_key(root, b.key)
    assert not list_recoveries(root)


def test_invalid_keys_and_metadata_are_never_trusted(tmp_path):
    root = tmp_path / "recover"
    with pytest.raises(ValueError, match="key"):
        save_recovery(_project("bad"), root, key="../../escape", state_id=0,
                      original_path=None)
    with pytest.raises(ValueError, match="key"):
        discard_key(root, "../escape")
    entry = save_recovery(_project("Valid"), root, key=uuid4().hex,
                          state_id=1, original_path=None)
    entry.metadata_file.write_text(json.dumps({"key": entry.key, "version": 999}))
    assert not list_recoveries(root)


def test_retention_keeps_newest_and_never_touches_source_document(tmp_path):
    root = tmp_path / "recover"
    doc = save_project(_project("Original"), tmp_path / "source.cf3d")
    first = save_recovery(_project("Old"), root, key=uuid4().hex,
                          state_id=1, original_path=doc)
    # Fake timestamp using manifest field, not platform clock resolution.
    payload = json.loads(first.metadata_file.read_text())
    payload["timestamp_utc"] = "2020-01-01T00:00:00+00:00"
    first.metadata_file.write_text(json.dumps(payload))
    second = save_recovery(_project("New"), root, key=uuid4().hex,
                           state_id=2, original_path=doc)
    prune_recoveries(root, keep=1)
    assert list_recoveries(root) == (second,)
    assert not first.project_file.exists()
    assert load_project(doc).name == "Original"
