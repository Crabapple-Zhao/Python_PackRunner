"""Background subprocess lifecycle management."""

import os
import subprocess
import threading
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Callable, ContextManager, List, Optional, Sequence

from ..utils.encoding import decode_process_line


@dataclass(frozen=True)
class ProcessResult:
    return_code: Optional[int] = None
    error: Optional[BaseException] = None


class ProcessRunner:
    """一次只运行一个后台子进程，并管理停止及输出回调。"""

    def __init__(self):
        self._process = None
        self._running = False
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def start(
        self,
        command: Sequence[str],
        cwd: Optional[str],
        on_output: Callable[[str], None],
        on_started: Callable[[Sequence[str]], None],
        on_finished: Callable[[ProcessResult], None],
        command_context: Optional[Callable[[Sequence[str]], ContextManager[List[str]]]] = None,
    ) -> bool:
        with self._lock:
            if self._running:
                return False
            self._running = True
        thread = threading.Thread(
            target=self._execute,
            args=(list(command), cwd, on_output, on_started, on_finished, command_context),
            daemon=True,
        )
        thread.start()
        return True

    def _execute(self, command, cwd, on_output, on_started, on_finished, command_context):
        result = ProcessResult()
        try:
            context = command_context(command) if command_context else nullcontext(command)
            with context as actual_command:
                on_started(actual_command)
                creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                process = subprocess.Popen(
                    actual_command, cwd=cwd, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=False, bufsize=0,
                    creationflags=creationflags,
                )
                with self._lock:
                    self._process = process
                if process.stdout is not None:
                    try:
                        for raw_line in iter(process.stdout.readline, b""):
                            line = decode_process_line(raw_line).rstrip("\r\n")
                            if line:
                                on_output(line)
                    finally:
                        process.stdout.close()
                result = ProcessResult(return_code=process.wait())
        except Exception as exc:
            result = ProcessResult(error=exc)
        finally:
            with self._lock:
                self._process = None
                self._running = False
            on_finished(result)

    def stop(self) -> bool:
        with self._lock:
            process = self._process
        if process is None:
            return False
        if os.name == "nt":
            completed = subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
                check=False,
            )
            if completed.returncode == 0 or process.poll() is not None:
                return True
        process.terminate()
        return True
