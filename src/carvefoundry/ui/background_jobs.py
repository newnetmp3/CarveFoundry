"""Qt-safe background jobs; CPU-bound jobs run in a separate Python process.

The QObject only lives on its QThread, so no worker directly touches Qt widgets.
For process jobs the input is pickled *inside* this thread, never in the GUI
event handler; progress is newline-delimited JSON, and results are unpickled
off the GUI thread as well.
"""
from __future__ import annotations

import json
import os
import pickle
import select
import subprocess
import sys
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot


class JobCancelled(Exception):
    """The user cancelled a job before its result was committed."""


class BackgroundWorker(QObject):
    progress = Signal(float, str)
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        task: Callable[[Callable[[float, str], None]], object] | None = None,
        *,
        process_request: object | None = None,
    ) -> None:
        super().__init__()
        if (task is None) == (process_request is None):
            raise ValueError("Pass exactly one of task or process_request.")
        self._task = task
        self._request = process_request
        self._cancel = threading.Event()
        self._process: subprocess.Popen[str] | None = None

    def cancel(self) -> None:
        """Thread-safe signal. Never destroy a running QThread or QObject."""
        self._cancel.set()
        process = self._process
        if process is not None and process.poll() is None:
            process.terminate()

    def _report(self, fraction: float, message: str) -> None:
        if self._cancel.is_set():
            raise JobCancelled()
        self.progress.emit(max(0.0, min(1.0, float(fraction))), str(message))

    def _run_process(self) -> object:
        with tempfile.TemporaryDirectory(prefix="carvefoundry-job-") as directory:
            request_path = Path(directory) / "request.pkl"
            result_path = Path(directory) / "result.pkl"
            stderr_path = Path(directory) / "worker.log"
            self._report(0.01, "Preparing job")
            with request_path.open("wb") as handle:
                pickle.dump(self._request, handle, protocol=pickle.HIGHEST_PROTOCOL)
            self._report(0.03, "Starting worker process")
            env = dict(os.environ)
            env["PYTHONUNBUFFERED"] = "1"
            error_log = stderr_path.open("wb")
            try:
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "carvefoundry.cam.job_worker_cli",
                        str(request_path),
                        str(result_path),
                    ],
                    stdout=subprocess.PIPE,
                    stderr=error_log,
                    text=True,
                    bufsize=1,
                    env=env,
                )
            except BaseException:
                error_log.close()
                raise
            self._process = process
            assert process.stdout is not None
            try:
                while process.poll() is None:
                    if self._cancel.is_set():
                        process.terminate()
                        try:
                            process.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                        raise JobCancelled()
                    readable, _, _ = select.select([process.stdout], [], [], 0.10)
                    if not readable:
                        continue
                    line = process.stdout.readline()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if data.get("type") == "progress":
                        self._report(data.get("fraction", 0), data.get("message", "Working"))
                    elif data.get("type") == "error":
                        raise RuntimeError(str(data.get("message", "Worker failed")))
                for line in process.stdout:
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if data.get("type") == "progress":
                        self._report(data.get("fraction", 0), data.get("message", "Working"))
                    elif data.get("type") == "error":
                        raise RuntimeError(str(data.get("message", "Worker failed")))
                if self._cancel.is_set():
                    raise JobCancelled()
                if process.returncode != 0:
                    error_log.flush()
                    error = stderr_path.read_text(
                        encoding="utf-8", errors="replace"
                    ).strip()
                    raise RuntimeError(error[-3000:] or f"Worker exited {process.returncode}")
                self._report(0.98, "Loading results")
                with result_path.open("rb") as handle:
                    return pickle.load(handle)
            finally:
                self._process = None
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                process.stdout.close()
                error_log.close()

    @Slot()
    def run(self) -> None:
        try:
            result = (
                self._run_process()
                if self._request is not None
                else self._task(self._report)  # type: ignore[misc]
            )
            if self._cancel.is_set():
                self.cancelled.emit()
            else:
                self.completed.emit(result)
        except JobCancelled:
            self.cancelled.emit()
        except Exception as exc:  # noqa: BLE001 - worker boundary must report/quit
            if self._cancel.is_set():
                self.cancelled.emit()
            else:
                self.failed.emit(f"{type(exc).__name__}: {exc}")


class JobState:
    """A UI-owned reference to a running worker and its QThread."""

    def __init__(self, worker: BackgroundWorker, thread: object) -> None:
        self.worker = worker
        self.thread = thread


class JobCallbacks(QObject):
    """Own GUI-thread Qt slots for cross-thread progress/result delivery.

    Connecting a worker signal directly to an ordinary Python closure can
    execute that closure in the worker's thread with some PySide versions.
    QObject slots are explicitly queued to this receiver's GUI thread.
    """

    def __init__(
        self,
        parent: QObject,
        *,
        progress: Callable[[float, str], None],
        completed: Callable[[object], None],
        failed: Callable[[str], None],
        cancelled: Callable[[], None],
        cleaned_up: Callable[[], None],
    ) -> None:
        super().__init__(parent)
        self._progress = progress
        self._completed = completed
        self._failed = failed
        self._cancelled = cancelled
        self._cleaned_up = cleaned_up

    @Slot(float, str)
    def on_progress(self, value: float, message: str) -> None:
        self._progress(value, message)

    @Slot(object)
    def on_completed(self, result: object) -> None:
        self._completed(result)

    @Slot(str)
    def on_failed(self, message: str) -> None:
        self._failed(message)

    @Slot()
    def on_cancelled(self) -> None:
        self._cancelled()

    @Slot()
    def on_cleaned_up(self) -> None:
        self._cleaned_up()
        self.deleteLater()
