"""User-local Linux installer: no activation, sudo, or real dependency downloads.

Test the desktop-only route with a fake already-installed venv. The full
Python/Rust build remains covered by the project's regular CI installation.
"""
from __future__ import annotations

import configparser
import os
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "install-linux.sh"
APP_ID = "io.github.newnetmp3.CarveFoundry"


def test_native_installer_bash_and_help() -> None:
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)
    result = subprocess.run(
        ["bash", str(SCRIPT), "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "--desktop-only" in result.stdout
    assert "--with-ai" in result.stdout


def _sandbox(tmp_path: Path) -> tuple[dict[str, str], Path, Path]:
    home = tmp_path / "user home"
    home.mkdir()
    data = tmp_path / "user data"
    env = {**os.environ, "HOME": str(home), "XDG_DATA_HOME": str(data)}
    venv = tmp_path / "fake python environment"
    executable = venv / "bin" / "carvefoundry"
    executable.parent.mkdir(parents=True)
    executable.write_text(
        "#!/usr/bin/env bash\n"
        "# Fake CarveFoundry app for testing an already-installed environment\n"
        'printf "APP RUNS FROM %s\\n" "$PWD"\n',
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return env, home, venv


def test_desktop_only_install_registers_app_and_runs_without_activation(
    tmp_path: Path,
) -> None:
    env, home, venv = _sandbox(tmp_path)
    data = Path(env["XDG_DATA_HOME"])
    result = subprocess.run(
        ["bash", str(SCRIPT), "--desktop-only", "--venv", str(venv)],
        env=env,
        cwd="/",
        capture_output=True,
        text=True,
        check=True,
    )
    assert "CarveFoundry desktop installation is ready" in result.stdout

    launcher = home / ".local/bin/carvefoundry"
    assert launcher.is_file() and os.access(launcher, os.X_OK)
    command = subprocess.run(
        [str(launcher)], env=env, cwd="/", check=True,
        capture_output=True, text=True,
    )
    assert f"APP RUNS FROM {ROOT}" in command.stdout

    desktop = data / "applications" / f"{APP_ID}.desktop"
    config = configparser.ConfigParser(interpolation=None)
    config.read(desktop)
    entry = config["Desktop Entry"]
    assert entry["Name"] == "CarveFoundry"
    assert entry["Icon"] == APP_ID
    assert entry["Exec"] == f'"{launcher}"'
    assert entry["Terminal"] == "false"
    assert (data / "icons/hicolor/scalable/apps" / f"{APP_ID}.svg").is_file()
    ET.parse(data / "icons/hicolor/scalable/apps" / f"{APP_ID}.svg")

    # Repeated install must update (not duplicate) the launcher/menu entry.
    subprocess.run(
        ["bash", str(SCRIPT), "--desktop-only", "--venv", str(venv)],
        env=env, cwd="/", check=True, capture_output=True, text=True,
    )
    assert desktop.is_file()


def test_unmanaged_user_executable_is_never_overwritten(tmp_path: Path) -> None:
    env, home, venv = _sandbox(tmp_path)
    launcher = home / ".local/bin/carvefoundry"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("#!/bin/sh\necho do-not-touch\n", encoding="utf-8")
    result = subprocess.run(
        ["bash", str(SCRIPT), "--desktop-only", "--venv", str(venv)],
        env=env, capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0
    assert "not a CarveFoundry-managed launcher" in result.stderr
    assert "do-not-touch" in launcher.read_text(encoding="utf-8")


@pytest.mark.parametrize("option", ["--missing", "--venv"])
def test_install_rejects_incomplete_options(option: str) -> None:
    result = subprocess.run(
        ["bash", str(SCRIPT), option],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0
