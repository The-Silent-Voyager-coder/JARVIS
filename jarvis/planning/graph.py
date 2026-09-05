"""Task-graph utilities (Phase 7).

Steps may declare ``depends_on`` (step ids that must complete first).
An empty ``depends_on`` means sequential execution in ``sequence`` order,
which keeps every Phase 6 linear plan valid without modification.

All functions are pure (no I/O) and bounded: graphs larger than the
planning ceiling are rejected instead of sorted.
"""

from __future__ import annotations

from typing import Any

from jarvis.exceptions import PlanningValidationError
from jarvis.planning.limits import MAX_PLAN_STEPS_CEILING


def _ids(steps: Any) -> list[str]:
    return [str(s.id) for s in steps]


def find_missing_deps(steps: Any) -> list[tuple[str, str]]:
    """Return ``(step_id, missing_dep)`` pairs for deps with no matching step."""
    known = set(_ids(steps))
    missing: list[tuple[str, str]] = []
    for step in steps:
        for dep in getattr(step, "depends_on", ()):
            if str(dep) not in known:
                missing.append((str(step.id), str(dep)))
    return missing


def find_self_deps(steps: Any) -> list[str]:
    """Return step ids that (transitively, directly) depend on themselves."""
    bad: list[str] = []
    for step in steps:
        if str(step.id) in {str(d) for d in getattr(step, "depends_on", ())}:
            bad.append(str(step.id))
    return bad


def find_cycle(steps: Any) -> list[str] | None:
    """Return one dependency cycle as step ids, or None when acyclic.

    Iterative DFS over ``depends_on`` edges (dep -> step direction is
    reversed internally so the reported cycle reads in execution order).
    """
    deps: dict[str, list[str]] = {}
    for step in steps:
        deps[str(step.id)] = [str(d) for d in getattr(step, "depends_on", ())]
    visited: dict[str, int] = {}  # 0=unvisited 1=in-stack 2=done
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        visited[node] = 1
        stack.append(node)
        for dep in deps.get(node, []):
            if dep not in deps:
                continue  # missing dep; reported separately
            state = visited.get(dep, 0)
            if state == 1:
                cycle = stack[stack.index(dep):] + [dep]
                return cycle
            if state == 0:
                hit = visit(dep)
                if hit is not None:
                    return hit
        stack.pop()
        visited[node] = 2
        return None

    for node in deps:
        if visited.get(node, 0) == 0:
            hit = visit(node)
            if hit is not None:
                return hit
    return None


def topological_order(steps: Any) -> list[Any]:
    """Return steps in dependency order (Kahn's algorithm, stable).

    Steps with no deps keep their relative ``sequence`` order, so linear
    Phase 6 plans come back unchanged. Raises ``PlanningValidationError``
    on missing deps, self-deps, cycles, or graphs above the ceiling.
    """
    items = list(steps)
    if len(items) > MAX_PLAN_STEPS_CEILING:
        raise PlanningValidationError(
            f"task graph has {len(items)} steps, ceiling is {MAX_PLAN_STEPS_CEILING}"
        )
    missing = find_missing_deps(items)
    if missing:
        step_id, dep = missing[0]
        raise PlanningValidationError(
            f"step {step_id} depends on unknown step {dep}"
        )
    self_deps = find_self_deps(items)
    if self_deps:
        raise PlanningValidationError(f"step {self_deps[0]} depends on itself")
    cycle = find_cycle(items)
    if cycle is not None:
        raise PlanningValidationError(
            "dependency cycle: " + " -> ".join(cycle)
        )
    by_id = {str(s.id): s for s in items}
    indegree: dict[str, int] = {str(s.id): 0 for s in items}
    children: dict[str, list[str]] = {str(s.id): [] for s in items}
    for step in items:
        sid = str(step.id)
        for dep in {str(d) for d in getattr(step, "depends_on", ())}:
            children[dep].append(sid)
            indegree[sid] += 1
    # Stable: always pick the lowest-sequence ready step first.
    ready = sorted(
        (s for s in items if indegree[str(s.id)] == 0),
        key=lambda s: int(s.sequence),
    )
    ordered: list[Any] = []
    while ready:
        step = ready.pop(0)
        ordered.append(step)
        nxt: list[Any] = []
        for child_id in children[str(step.id)]:
            indegree[child_id] -= 1
            if indegree[child_id] == 0:
                nxt.append(by_id[child_id])
        ready.extend(nxt)
        ready.sort(key=lambda s: int(s.sequence))
    if len(ordered) != len(items):  # pragma: no cover - defensive
        raise PlanningValidationError("task graph could not be fully ordered")
    return ordered


def levels(steps: Any) -> dict[str, int]:
    """Return ``{step_id: depth}`` where depth 0 = no dependencies.

    Raises ``PlanningValidationError`` when the graph is invalid.
    """
    ordered = topological_order(steps)
    depth: dict[str, int] = {}
    for step in ordered:
        deps = [str(d) for d in getattr(step, "depends_on", ())]
        depth[str(step.id)] = 0 if not deps else max(depth[d] for d in deps) + 1
    return depth
