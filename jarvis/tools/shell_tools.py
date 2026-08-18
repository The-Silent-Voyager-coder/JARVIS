"""Controlled shell tool (spec §25-29, §31).

shell.execute is HIGH risk and always goes through the security pipeline:
command class is checked by the policy (FORBIDDEN/DANGEROUS are denied before
execution), execution uses argument vectors (never shell=True), always has a
timeout, captures bounded output, runs with a scrubbed environment, and uses
an explicit working directory.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from threading import Thread
from typing import Any

from jarvis.exceptions import ToolExecutionError
from jarvis.tools.environment import merge_environment, scrub_environment
from jarvis.tools.models import BaseTool, ToolCategory, ToolContext, ToolResult, ToolRisk


class _LimitedReader:
    """Reads a stream but keeps at most `limit` bytes (memory bounded)."""

    def __init__(self, stream: Any, limit: int) -> None:
        self._stream = stream
        self._limit = limit
        self.data = bytearray()
        self.truncated = False

    def run(self) -> None:
        try:
            while True:
                chunk = self._stream.read(8192)
                if not chunk:
                    break
                remaining = self._limit - len(self.data)
                if remaining > 0:
                    self.data.extend(chunk[:remaining])
                    if len(chunk) > remaining:
                        self.truncated = True
                else:
                    self.truncated = True
        finally:
            try:
                self._stream.close()
            except OSError:  # pragma: no cover - defensive
                pass


def _decode(data: bytearray, limit: int) -> str:
    return bytes(data[:limit]).decode("utf-8", errors="replace")


def _run_limited(
    command: list[str],
    cwd: Path,
    env: dict[str, str],
    timeout: float,
    max_bytes: int,
) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        proc = subprocess.Popen(
            command,
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(cwd),
            env=env,
        )
    except OSError as exc:
        raise ToolExecutionError(f"could not start command: {exc}") from exc

    stdout_reader = _LimitedReader(proc.stdout, max_bytes)
    stderr_reader = _LimitedReader(proc.stderr, max_bytes)
    threads = [
        Thread(target=stdout_reader.run, daemon=True),
        Thread(target=stderr_reader.run, daemon=True),
    ]
    for thread in threads:
        thread.start()

    timed_out = False
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover - defensive
            pass
    for thread in threads:
        thread.join(timeout=5)
    duration_ms = (time.perf_counter() - start) * 1000

    return {
        "exit_code": None if timed_out else proc.returncode,
        "stdout": _decode(stdout_reader.data, max_bytes),
        "stderr": _decode(stderr_reader.data, max_bytes),
        "timed_out": timed_out,
        "stdout_truncated": stdout_reader.truncated,
        "stderr_truncated": stderr_reader.truncated,
        "duration_ms": round(duration_ms, 3),
    }


class ShellExecuteTool(BaseTool):
    id = "shell.execute"
    name = "Execute a shell command"
    description = (
        "Run a command as an argument vector (no shell), with timeout, "
        "bounded output, scrubbed environment, and explicit working directory."
    )
    version = "1.0.0"
    risk_level = ToolRisk.HIGH
    category = ToolCategory.SHELL
    capabilities = ("execute",)
    PATH_ARGUMENTS = ("cwd",)
    input_schema = {
        "type": "object",
        "properties": {
            "command": {
                "type": "array",
                "items": {"type": "string"},
                "description": "command vector, e.g. ['where', 'python']",
            },
            "cwd": {
                "type": "string",
                "description": "working directory (must be inside allowed roots)",
            },
            "timeout_seconds": {
                "type": "number",
                "description": "optional timeout, capped by the tool limit",
            },
            "env": {
                "type": "object",
                "description": "extra environment variables (secret names rejected)",
            },
        },
        "required": ["command"],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "exit_code": {"type": "integer"},
            "stdout": {"type": "string"},
            "stderr": {"type": "string"},
            "timed_out": {"type": "boolean"},
            "stdout_truncated": {"type": "boolean"},
            "stderr_truncated": {"type": "boolean"},
            "duration_ms": {"type": "number"},
        },
        "required": ["stdout", "stderr", "timed_out"],
    }

    def execute(
        self, arguments: dict[str, Any], context: ToolContext
    ) -> ToolResult:
        command = [str(item) for item in arguments["command"]]
        if not command or not all(command):
            raise ToolExecutionError("command must be a non-empty list of strings")

        cwd = context.working_directory
        raw_cwd = arguments.get("cwd")
        if raw_cwd is not None:
            candidate = Path(str(raw_cwd)).expanduser()
            if not candidate.is_absolute():
                candidate = context.working_directory / candidate
            cwd = candidate.resolve()
        if not cwd.is_dir():
            raise ToolExecutionError(f"working directory does not exist: {cwd}")

        base_env = scrub_environment(os.environ)
        env = merge_environment(base_env, arguments.get("env"))

        requested_timeout = arguments.get("timeout_seconds")
        timeout = (
            min(float(requested_timeout), context.timeout_seconds)
            if requested_timeout is not None
            else context.timeout_seconds
        )

        info = _run_limited(command, cwd, env, timeout, context.max_output_bytes)
        success = not info["timed_out"] and info["exit_code"] == 0
        error = None
        if info["timed_out"]:
            error = f"command timed out after {timeout}s"
        elif info["exit_code"] != 0:
            error = f"command failed with exit code {info['exit_code']}"
        return ToolResult(
            request_id="",
            tool_id=self.id,
            success=success,
            output={
                "exit_code": info["exit_code"],
                "stdout": info["stdout"],
                "stderr": info["stderr"],
                "timed_out": info["timed_out"],
                "stdout_truncated": info["stdout_truncated"],
                "stderr_truncated": info["stderr_truncated"],
                "duration_ms": info["duration_ms"],
                "cwd": str(cwd),
            },
            error=error,
        )
