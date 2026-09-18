from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from multiprocessing import get_context
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from carvefoundry.core.import_process import prepare_stl_import_payload
from carvefoundry.core.importer import ImportFileError, ImportFileInfo, inspect_import_file


@dataclass(frozen=True, slots=True)
class PreparedImport:
    info: ImportFileInfo
    gpu_vertex_bytes: bytes | None = None
    gpu_vertex_count: int = 0


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
        prepared: list[PreparedImport] = []
        failures: list[str] = []
        total = len(self._paths)
        executor: ProcessPoolExecutor | None = None

        try:
            for index, raw_path in enumerate(self._paths, start=1):
                source = Path(raw_path)
                self.progress.emit(index, total, source.name)
                try:
                    if source.suffix.lower() == ".stl":
                        if executor is None:
                            executor = ProcessPoolExecutor(
                                max_workers=1,
                                mp_context=get_context("spawn"),
                            )
                        info, vertex_bytes, vertex_count = executor.submit(
                            prepare_stl_import_payload,
                            source,
                            self._expected_kind,
                        ).result()
                        prepared.append(
                            PreparedImport(
                                info=info,
                                gpu_vertex_bytes=vertex_bytes,
                                gpu_vertex_count=vertex_count,
                            )
                        )
                    else:
                        info = inspect_import_file(
                            source,
                            expected_kind=self._expected_kind,
                        )
                        prepared.append(PreparedImport(info=info))
                except ImportFileError as exc:
                    failures.append(f"{source.name}: {exc}")
                    continue
                except ValueError as exc:
                    failures.append(f"{source.name}: {exc}")
                    continue
        except Exception as exc:  # noqa: BLE001 - thread boundary must always report/quit
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        finally:
            if executor is not None:
                executor.shutdown(wait=True, cancel_futures=True)

        self.finished.emit(prepared, failures)
