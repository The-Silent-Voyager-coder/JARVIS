"""Planning service facade (Phase 6)."""

from __future__ import annotations

import logging
from typing import Any

from jarvis.configuration.model import JarvisConfig
from jarvis.core.health import HealthRegistry, HealthStatus
from jarvis.events.models import PLAN_CREATED, PLAN_FAILED, Event
from jarvis.exceptions import PlanningUnavailableError, PlanningValidationError
from jarvis.planning.planner import Planner
from jarvis.planning.sqlite_repository import SqlitePlanningRepository
from jarvis.tools.redaction import redact_secrets

log = logging.getLogger("jarvis.planning.service")


class PlanningService:
    def __init__(self) -> None:
        self._config: JarvisConfig | None = None
        self._repository: SqlitePlanningRepository | None = None
        self._planner: Planner | None = None
        self._availability: str = "unavailable"
        self._detail: str = "planning service not started"
        self.publisher: Any = None

    def start(self, config: JarvisConfig | None = None) -> None:
        self._config = config
        if config is None:
            self._availability = "unavailable"
            self._detail = "no configuration provided"
            return
        if not config.planning.enabled:
            self._availability = "disabled"
            self._detail = "planning subsystem disabled by configuration"
            return
        try:
            repo = SqlitePlanningRepository(config.planning.database_path)
            repo.initialize()
            self._repository = repo
            self._planner = Planner(max_plan_steps=config.planning.max_plan_steps)
            self._availability = "healthy"
            self._detail = f"planning ready (max_steps<={config.planning.max_plan_steps})"
            log.info("planning service started", extra={"component": "planning"})
        except Exception as exc:  # pragma: no cover
            self._availability = "unavailable"
            self._detail = f"planning start failed: {exc}"
            log.error("planning start failed", exc_info=exc, extra={"component": "planning"})

    def shutdown(self) -> None:
        if self._repository is not None:
            try:
                self._repository.close()
            except Exception:
                pass
        self._repository = None
        self._planner = None
        self._availability = "disabled"
        self._detail = "planning service stopped"
        log.info("planning service stopped", extra={"component": "planning"})

    def _require_available(self) -> None:
        if self._availability != "healthy":
            raise PlanningUnavailableError(self._detail or "planning service not available")
        assert self._repository is not None
        assert self._planner is not None

    def create_plan(self, goal: str, workspace: Any = None, plan_id: str | None = None) -> dict[str, Any]:  # noqa: E501
        self._require_available()
        assert self._planner is not None
        assert self._repository is not None
        try:
            plan = self._planner.create_plan(goal, workspace, plan_id=plan_id)
            self._repository.save(plan)
            # Phase 9: goals can embed pasted secrets; audit keeps redacted form.
            self._publish(PLAN_CREATED, {"plan_id": plan.id, "goal": redact_secrets(plan.goal[:120]), "steps": len(plan.steps)})  # noqa: E501
            return plan.to_dict()
        except PlanningValidationError as exc:
            self._publish(PLAN_FAILED, {"error": redact_secrets(str(exc)[:200]), "goal": redact_secrets(goal[:120])})  # noqa: E501
            raise
        except Exception as exc:
            self._publish(PLAN_FAILED, {"error": redact_secrets(str(exc)[:200])})
            raise PlanningValidationError(str(exc)) from exc

    def get(self, plan_id: str) -> dict[str, Any] | None:
        self._require_available()
        assert self._repository is not None
        plan = self._repository.get(plan_id)
        return plan.to_dict() if plan else None

    def list(self) -> list[dict[str, Any]]:
        self._require_available()
        assert self._repository is not None
        return [p.to_dict() for p in self._repository.list()]

    def health(self) -> dict[str, Any]:
        base: dict[str, Any] = {
            "available": self._availability == "healthy",
            "status": self._availability,
            "detail": self._detail,
            "enabled": bool(self._config is not None and self._config.planning.enabled),
        }
        if self._repository is not None:
            h = self._repository.health()
            base.update({
                "accessible": h.accessible,
                "schema_valid": h.schema_valid,
                "migrations_current": h.migrations_current,
                "writable": h.writable,
                "schema_version": h.schema_version,
                "database_path": h.database_path,
            })
        return base

    def register_health_check(self, registry: HealthRegistry) -> None:
        def checker() -> HealthStatus:
            if self._availability == "disabled":
                return HealthStatus.HEALTHY
            if self._availability == "healthy":
                return HealthStatus.HEALTHY
            return HealthStatus.UNHEALTHY

        registry.register("planning", checker, "planning service (deterministic templates)")

    def _publish(self, event_type: str, payload: dict[str, Any]) -> None:
        if self.publisher is None:
            return
        try:
            self.publisher(Event(type=event_type, source="planning", payload=payload))
        except Exception as exc:  # pragma: no cover
            log.warning("planning event publish failed: %s", exc, extra={"component": "planning"})
