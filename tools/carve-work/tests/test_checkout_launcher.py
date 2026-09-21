"""Repository launcher must preserve pre-existing chats and honor overrides."""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
LAUNCHER = ROOT / "scripts" / "run-carvework.sh"
APP = ROOT / "tools" / "carve-work"


class CheckoutLauncherTests(unittest.TestCase):
    def _launch(self, *, old_data: bool, explicit_data: bool = False) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            legacy = home / "git" / "carve-work" / "data"
            if old_data:
                legacy.mkdir(parents=True)
                (legacy / "carve_work.sqlite3").write_bytes(b"keep me")
            fake_bin = home / "bin"
            fake_bin.mkdir()
            fake_python = fake_bin / "python3"
            fake_python.write_text(
                '#!/bin/sh\n'
                'printf "%s\\n" "$PWD" "$CARVE_WORK_DATA" '
                '"$CARVEFOUNDRY_REPO" "$1"\n'
            )
            fake_python.chmod(0o755)
            env = os.environ.copy()
            env["HOME"] = str(home)
            env["PATH"] = str(fake_bin) + os.pathsep + env["PATH"]
            env.pop("CARVEFOUNDRY_REPO", None)
            env.pop("CARVE_WORK_DATA", None)
            if explicit_data:
                env["CARVE_WORK_DATA"] = str(home / "custom" / "chats")
            output = subprocess.run(
                ["bash", str(LAUNCHER)],
                check=True, capture_output=True, text=True,
                env=env, cwd=ROOT, timeout=15,
            )
            if old_data and not explicit_data:
                self.assertEqual((legacy / "carve_work.sqlite3").read_bytes(), b"keep me")
            return output.stdout.splitlines()

    def test_reuses_existing_data_without_copying_it_into_checkout(self) -> None:
        result = self._launch(old_data=True)
        self.assertIn("using existing private data", result[0])
        self.assertTrue(result[2].endswith("/git/carve-work/data"))
        self.assertEqual(result[1], str(APP))
        self.assertEqual(result[3], str(ROOT))
        self.assertEqual(result[4], "server.py")

    def test_explicit_data_location_is_never_overridden(self) -> None:
        result = self._launch(old_data=True, explicit_data=True)
        self.assertFalse(any("using existing private data" in line for line in result))
        self.assertEqual(result[0], str(APP))
        self.assertTrue(result[1].endswith("/custom/chats"))
        self.assertEqual(result[2], str(ROOT))

    def test_no_legacy_data_uses_app_default(self) -> None:
        result = self._launch(old_data=False)
        self.assertEqual(result[0], str(APP))
        self.assertEqual(result[1], "")
        self.assertEqual(result[2], str(ROOT))
