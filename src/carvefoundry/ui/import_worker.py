from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from carvefoundry.core.importer import ImportFileError, ImportFileInfo, inspect_import_file


class ImportWorker(QObject):
    """Run potentially expensive design-file parsing away from the GUI thread."""

    progress = Signal(int, int, str)
    finished = Signal(object, object)
    failed = Signal(str)

    def __init__(self, paths: list[str], expected_kind: str | None = None) -> None:
        super().__init__()
        self._paths = list(paths)
        self._expected_kind = expected_kind

    @Slot()
    def run(self) -> None:
        infos: list[ImportFileInfo] = []
        failures: list[str] = []
        total = len(self._paths)

        try:
            for index, raw_path in enumerate(self._paths, start=1):
                source = Path(raw_path)
                self.progress.emit(index, total, source.name)
                try:
                    info = inspect_import_file(
                        source,
                        expected_kind=self._expected_kind,
                    )
                except ImportFileError as exc:
                    failures.append(f"{source.name}: {exc}")
                    continue
                infos.append(info)
        except Exception as exc:  # keep the GUI alive on unexpected parser failures
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return

        self.finished.emit(infos, failures)
