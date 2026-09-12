"""Process tools (spec §21-22): observational only.

process.list / process.info read process state through Windows tasklist and
never modify processes — there is no process.terminate tool in Phase 4
(spec §22), and shell taskkill is classified DANGEROUS by the policy.
"""

from __future__ import annotations

import csv
import io
import subprocess
import sys
from typing import Any

from greatsage.exceptions import ToolExecutionError
from greatsage.tools.models import BaseTool, ToolCategory, ToolContext, ToolResult, ToolRisk

MAX_PROCESSES = 2000


def _parse_tasklist_item(row: list[str]) -> dict[str, Any]:
    memory_bytes: int | None = None
    if len(row) >= 5:
        raw = row[4]
        try:
            raw = raw.strip()
            if raw.casefold().endswith(" k"):
                memory_bytes = int(raw[:-2].replace(",", "").strip()) * 1024
            elif raw.casefold().endswith(" m"):
                memory_bytes = int(raw[:-2].replace(",", "").strip()) * 1024 * 1024
            else:
                memory_bytes = int(raw.replace(",", "").strip())
        except ValueError:
            memory_bytes = None
    return {
        "name": row[0] if row else "",
        "pid": int(row[1]) if len(row) > 1 and row[1].isdigit() else None,
        "memory_bytes": memory_bytes,
    }


def _list_processes() -> list[dict[str, Any]]:
    if sys.platform != "win32":
        raise ToolExecutionError(
            "process.list requires Windows (tasklist); not available on this platform"
        )
    try:
        result = subprocess.run(  # noqa: S603
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ToolExecutionError(f"could not run tasklist: {exc}") from exc
    if result.returncode != 0:
        raise ToolExecutionError(
            f"tasklist failed (exit {result.returncode}): "
            f"{result.stderr.strip() or 'no error output'}"
        )
    rows = list(csv.reader(io.StringIO(result.stdout)))
    processes: list[dict[str, Any]] = []
    for row in rows:
        if not row or not row[0]:
            continue
        item = _parse_tasklist_item(row)
        if item["pid"] is not None:
            processes.append(item)
    return processes[:MAX_PROCESSES]


class ProcessListTool(BaseTool):
    id = "process.list"
    name = "List processes"
    description = "List running processes (name, pid, memory) via Windows tasklist."
    version = "1.0.0"
    risk_level = ToolRisk.SAFE
    category = ToolCategory.PROCESS
    capabilities = ("inspect",)
    input_schema = {"type": "object", "properties": {}, "required": []}
    output_schema = {
        "type": "object",
        "properties": {"processes": {"type": "array"}},
        "required": ["processes"],
    }

    def execute(
        self, arguments: dict[str, Any], context: ToolContext
    ) -> ToolResult:
        processes = _list_processes()
        metadata: dict[str, Any] = {}
        if len(processes) >= MAX_PROCESSES:
            metadata["truncated"] = True
        return ToolResult(
            request_id="",
            tool_id=self.id,
            success=True,
            output={"processes": processes},
            metadata=metadata,
        )


class ProcessInfoTool(BaseTool):
    id = "process.info"
    name = "Process details"
    description = "Report state for a single process by pid (read-only)."
    version = "1.0.0"
    risk_level = ToolRisk.LOW
    category = ToolCategory.PROCESS
    capabilities = ("inspect",)
    input_schema = {
        "type": "object",
        "properties": {
            "pid": {"type": "integer", "description": "process identifier"},
        },
        "required": ["pid"],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "pid": {"type": "integer"},
            "running": {"type": "boolean"},
            "name": {"type": "string"},
            "memory_bytes": {"type": "integer"},
        },
        "required": ["pid", "running"],
    }

    def execute(
        self, arguments: dict[str, Any], context: ToolContext
    ) -> ToolResult:
        pid = int(arguments["pid"])
        if pid < 0:
            raise ToolExecutionError(f"invalid pid: {pid}")
        for item in _list_processes():
            if item["pid"] == pid:
                return ToolResult(
                    request_id="",
                    tool_id=self.id,
                    success=True,
                    output={
                        "pid": pid,
                        "running": True,
                        "name": item["name"],
                        "memory_bytes": item["memory_bytes"],
                    },
                )
        return ToolResult(
            request_id="",
            tool_id=self.id,
            success=True,
            output={"pid": pid, "running": False, "name": None, "memory_bytes": None},
        )
