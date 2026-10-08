"""Cross-project CAM settings preset safety and roundtrip regression tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from carvefoundry.cam.operation import CamOperation
from carvefoundry.cam.toolpath import MoveKind, Toolpath, ToolpathMove
from carvefoundry.core.cam_settings_template import (
    TemplateError,
    apply_template,
    export_template,
    main,
)
from carvefoundry.core.project import Project
from carvefoundry.core.project_file import load_project, save_project
from carvefoundry.core.rust_project_transaction import _file_sha256
from carvefoundry.core.tools import DEFAULT_TOOLS


def _job(path: Path, *, cutter_index: int = 0, rate: float = 400.0):
    cutter = DEFAULT_TOOLS[cutter_index]
    operation = CamOperation(
        "profile", cutter, parameters={
            "feed_mm_min": rate, "plunge_mm_min": 150.0,
            "tabs_enabled": True, "tab_count": 3,
        },
    )
    toolpath = Toolpath(
        "Old motion", "profile", cutter, safe_z_mm=8.0,
        cam_operation_id=operation.operation_id,
        moves=[ToolpathMove(1.0, 1.0, 8.0, MoveKind.RAPID)],
    )
    job = Project(
        name="Production", cam_operations=[operation], toolpaths=[toolpath],
    )
    save_project(job, path)
    return operation.operation_id, _file_sha256(path)


def test_template_export_and_cross_project_application_discard_motion(
    tmp_path: Path,
):
    source = tmp_path / "source.cf3d"
    target = tmp_path / "target.cf3d"
    preset = tmp_path / "my-template.json"
    output = tmp_path / "new-target.cf3d"
    source_id, source_hash = _job(source, rate=180.0)
    target_id, target_hash = _job(target, rate=600.0)
    original_bytes = target.read_bytes()

    exported = export_template(source, source_id, preset, source_hash)
    assert exported["is_gcode"] is False
    payload = json.loads(preset.read_text(encoding="utf-8"))
    assert payload["template_format_version"] == 1
    assert payload["strategy"] == "profile"
    assert payload["parameters"]["feed_mm_min"] == pytest.approx(180.0)

    applied = apply_template(target, target_id, preset, output, target_hash)
    assert applied["requires_regeneration_and_preflight"] is True
    assert applied["invalidated_generated_toolpaths"] == 1
    assert target.read_bytes() == original_bytes
    assert output.is_file()
    edited = load_project(output)
    assert edited.cam_operations[0].operation_id == target_id
    assert edited.cam_operations[0].parameters["feed_mm_min"] == 180.0
    assert edited.cam_operations[0].needs_recalculation
    assert edited.toolpaths == []
    assert load_project(target).cam_operations[0].parameters["feed_mm_min"] == 600.0


def test_template_rejects_cutter_mismatch_and_existing_output(tmp_path: Path):
    source = tmp_path / "source.cf3d"
    target = tmp_path / "target.cf3d"
    preset = tmp_path / "preset.json"
    output = tmp_path / "out.cf3d"
    source_id, source_hash = _job(source)
    target_id, target_hash = _job(target, cutter_index=1)
    export_template(source, source_id, preset, source_hash)
    with pytest.raises(TemplateError, match="Cutter geometry"):
        apply_template(target, target_id, preset, output, target_hash)
    assert not output.exists()
    output.write_bytes(b"KEEP")
    with pytest.raises(TemplateError, match="nonexistent"):
        apply_template(target, target_id, preset, output, target_hash)
    assert output.read_bytes() == b"KEEP"


def test_template_rejects_changed_source_fingerprint(tmp_path: Path):
    source = tmp_path / "source.cf3d"
    target = tmp_path / "target.cf3d"
    preset = tmp_path / "preset.json"
    operation_id, source_hash = _job(source)
    target_id, target_hash = _job(target)
    export_template(source, operation_id, preset, source_hash)
    with pytest.raises(TemplateError, match="changed"):
        apply_template(target, target_id, preset, tmp_path / "new.cf3d",
                       source_hash)
    assert source_hash != target_hash or source.read_bytes() == target.read_bytes()


def test_template_rejects_unknown_parameter_and_nonfinite_input(tmp_path: Path):
    source = tmp_path / "source.cf3d"
    preset = tmp_path / "preset.json"
    op_id, source_hash = _job(source)
    export_template(source, op_id, preset, source_hash)
    payload = json.loads(preset.read_text(encoding="utf-8"))
    payload["parameters"]["unsafe_extra_key"] = 123
    preset.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(TemplateError, match="schema"):
        apply_template(source, op_id, preset, tmp_path / "new.cf3d", source_hash)
    payload["parameters"].pop("unsafe_extra_key")
    payload["parameters"]["feed_mm_min"] = 1e100
    preset.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(TemplateError, match="bounds"):
        apply_template(source, op_id, preset, tmp_path / "new.cf3d", source_hash)


def test_template_export_never_overwrites_existing_file(tmp_path: Path):
    source = tmp_path / "source.cf3d"
    preset = tmp_path / "preset.json"
    op_id, source_hash = _job(source)
    preset.write_text("preserve", encoding="utf-8")
    with pytest.raises(TemplateError, match="overwrite"):
        export_template(source, op_id, preset, source_hash)
    assert preset.read_text(encoding="utf-8") == "preserve"


def test_template_commandline_exports_with_readonly_source(tmp_path: Path, capsys):
    source = tmp_path / "source.cf3d"
    preset = tmp_path / "preset.json"
    op_id, source_hash = _job(source)
    before = source.read_bytes()
    assert main(["export", str(source), op_id, str(preset),
                 "--expected-sha", source_hash]) == 0
    response = json.loads(capsys.readouterr().out)
    assert response["is_gcode"] is False
    assert source.read_bytes() == before
