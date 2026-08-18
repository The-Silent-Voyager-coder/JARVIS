"""Hardware benchmark tests: read-only, no downloads, graceful absence."""

from __future__ import annotations

from jarvis.intelligence.benchmark import (
    BenchmarkResult,
    collect_cpu,
    collect_memory,
    collect_platform,
    format_benchmark,
    run_benchmark,
)


def test_collect_platform() -> None:
    info = collect_platform()
    assert info["system"]
    assert info["python"]


def test_collect_cpu() -> None:
    info = collect_cpu()
    assert info["logical_cpus"] > 0


def test_collect_memory_shapes() -> None:
    info = collect_memory()
    assert isinstance(info.get("total_gib"), (int, float, type(None)))


def test_run_benchmark_never_raises() -> None:
    result = run_benchmark()
    assert isinstance(result, BenchmarkResult)
    assert result.platform_info["system"] == collect_platform()["system"]
    assert isinstance(result.notes, tuple)


def test_ollama_absence_reported() -> None:
    from jarvis.intelligence.benchmark import collect_ollama

    info = collect_ollama()
    assert "available" in info
    assert info["available"] is False or isinstance(info["models"], list)


def test_format_benchmark_renders() -> None:
    result = BenchmarkResult(notes=("nothing detected",))
    text = format_benchmark(result)
    assert "Hardware benchmark" in text
    assert "note" in text
