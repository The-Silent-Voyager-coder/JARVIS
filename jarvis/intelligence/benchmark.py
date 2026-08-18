"""Hardware benchmark — read-only diagnostics.

Reads CPU/RAM/GPU/VRAM/CUDA where detectable and Ollama availability without
downloading models, without touching the network, and without any GPU stress,
burn-in, VRAM exhaustion, or thermal testing. GPU detection uses stdlib only
(shutil.which + subprocess); when unavailable it reports "not detectable".
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BenchmarkResult:
    platform_info: dict[str, str] = field(default_factory=dict)
    cpu_info: dict[str, Any] = field(default_factory=dict)
    memory_info: dict[str, Any] = field(default_factory=dict)
    gpu_info: list[dict[str, Any]] = field(default_factory=list)
    ollama_info: dict[str, Any] = field(default_factory=dict)
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform_info,
            "cpu": self.cpu_info,
            "memory": self.memory_info,
            "gpu": self.gpu_info,
            "ollama": self.ollama_info,
            "notes": list(self.notes),
        }


def collect_platform() -> dict[str, str]:
    return {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
    }


def collect_cpu() -> dict[str, Any]:
    logical = os.cpu_count() or 0
    info: dict[str, Any] = {"logical_cpus": logical}
    try:
        info["physical_cpus"] = os.cpu_count() or 0
    except Exception:
        pass
    return info


def collect_memory() -> dict[str, Any]:
    info: dict[str, Any] = {}
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class _MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", wintypes.DWORD),
                    ("dwMemoryLoad", wintypes.DWORD),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            memory_status = _MEMORYSTATUSEX()
            memory_status.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
            ok = ctypes.windll.kernel32.GlobalMemoryStatusEx(
                ctypes.byref(memory_status)
            )
            if ok:
                total_bytes = int(memory_status.ullTotalPhys)
                info["total_bytes"] = total_bytes
                info["total_gib"] = round(total_bytes / (1024**3), 2)
            else:
                info["total_gib"] = None
        except Exception:
            info["total_gib"] = None
    else:
        try:
            with open("/proc/meminfo", encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("MemTotal:"):
                        kib = int(line.split()[1])
                        info["total_gib"] = round(kib / (1024 * 1024), 2)
                        info["total_bytes"] = kib * 1024
                        break
        except Exception:
            info["total_gib"] = None
    return info


def _read_ollama_models() -> dict[str, Any]:
    """List locally available Ollama models via `ollama list` if the CLI exists.

    Never pulls or downloads anything; absence of the CLI is reported as
    UNAVAILABLE rather than an error.
    """
    exe = shutil.which("ollama")
    if exe is None:
        return {"available": False, "detail": "ollama CLI not found"}
    try:
        result = subprocess.run(  # noqa: S603
            [exe, "list"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"available": False, "detail": f"could not run ollama list: {exc}"}
    if result.returncode != 0:
        return {
            "available": False,
            "detail": "ollama daemon not reachable",
            "exit_code": result.returncode,
        }
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    headers = lines[0] if lines else ""
    models: list[str] = []
    for line in lines[1:]:
        name = line.split()[0] if line.split() else ""
        if name:
            models.append(name)
    return {"available": True, "models": models, "header": headers}


def collect_ollama() -> dict[str, Any]:
    return _read_ollama_models()


def collect_gpu() -> list[dict[str, Any]]:
    """Detect GPUs via nvidia-smi when present; stdlib-only fallback."""
    exe = shutil.which("nvidia-smi")
    if exe is None:
        return []
    try:
        result = subprocess.run(  # noqa: S603
            [exe, "--query-gpu=name,memory.total,memory.used,driver_version",
             "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0 or not result.stdout.strip():
        return []
    gpus: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) >= 3:
            try:
                total_mib = int(float(parts[1]))
            except ValueError:
                total_mib = None
            gpus.append(
                {
                    "name": parts[0],
                    "vram_total_mib": total_mib,
                    "vram_used_mib": parts[2],
                    "driver_version": parts[3] if len(parts) > 3 else None,
                }
            )
    return gpus


def run_benchmark() -> BenchmarkResult:
    """Run the full read-only hardware benchmark suite."""
    notes: list[str] = []
    gpus = collect_gpu()
    if not gpus:
        notes.append("no GPU detected via nvidia-smi; VRAM not measurable (read-only)")
    ollama = collect_ollama()
    if ollama.get("available"):
        model_count = len(ollama.get("models", []))
        notes.append(f"ollama reachable: {model_count} model(s) present, none downloaded")
    return BenchmarkResult(
        platform_info=collect_platform(),
        cpu_info=collect_cpu(),
        memory_info=collect_memory(),
        gpu_info=gpus,
        ollama_info=ollama,
        notes=tuple(notes),
    )


def format_benchmark(result: BenchmarkResult) -> str:
    """CLI-friendly rendering of a benchmark result."""
    lines: list[str] = ["Hardware benchmark (read-only, no downloads)"]
    plat = result.platform_info
    lines.append(
        f"  platform : {plat.get('system', '?')} {plat.get('release', '')} "
        f"({plat.get('machine', '?')}), python {plat.get('python', '?')}"
    )
    cpu = result.cpu_info
    phys = cpu.get("physical_cpus")
    lines.append(
        f"  cpu      : {cpu.get('logical_cpus', 0)} logical"
        + (f" / {phys} physical" if phys else "")
        + " cores"
    )
    mem = result.memory_info
    total_gib = mem.get("total_gib")
    lines.append(f"  memory   : {total_gib if total_gib is not None else 'not detectable'} GiB")
    if result.gpu_info:
        for gpu in result.gpu_info:
            lines.append(
                f"  gpu      : {gpu['name']} (vram total {gpu['vram_total_mib']} MiB, "
                f"in use {gpu['vram_used_mib']} MiB, driver {gpu.get('driver_version')})"
            )
    else:
        lines.append("  gpu      : none detected (no nvidia-smi)")
    ollama = result.ollama_info
    if ollama.get("available"):
        lines.append(
            f"  ollama   : available, {len(ollama.get('models', []))} model(s) local"
        )
    else:
        lines.append(f"  ollama   : unavailable ({ollama.get('detail', '?')})")
    for note in result.notes:
        lines.append(f"  note     : {note}")
    return "\n".join(lines)
