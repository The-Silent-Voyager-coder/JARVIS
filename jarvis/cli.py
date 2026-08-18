"""J.A.R.V.I.S. command-line interface.

Commands:

    jarvis config validate [--config PATH]    validate configuration
    jarvis health [--config PATH]             boot the runtime and report health
    jarvis ai health [--config PATH]          AI provider health table
    jarvis ai providers [--config PATH]       list registered AI providers
    jarvis ai benchmark [--config PATH]       read-only hardware benchmark

Exit codes: 0 success, 1 general failure, 2 invalid configuration/input.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version

from jarvis import __version__
from jarvis.configuration.loader import load_config
from jarvis.core.health import HealthStatus
from jarvis.core.runtime import Runtime
from jarvis.exceptions import ConfigurationError, JarvisError
from jarvis.intelligence.benchmark import format_benchmark, run_benchmark

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_INVALID = 2

COMPONENT_LABELS: dict[str, str] = {
    "core": "Core",
    "configuration": "Configuration",
    "event_bus": "Event Bus",
    "service_registry": "Service Registry",
    "storage": "Storage",
    "intelligence": "Intelligence",
}


def _installed_version() -> str:
    try:
        return version("jarvis")
    except PackageNotFoundError:
        return __version__


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jarvis",
        description="J.A.R.V.I.S. — Just A Rather Very Intelligent System",
    )
    parser.add_argument("--version", action="version", version=f"jarvis {_installed_version()}")
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    validate_parser = subparsers.add_parser("config", help="configuration commands")
    validate_sub = validate_parser.add_subparsers(dest="config_command", metavar="SUBCOMMAND")
    validate_cmd = validate_sub.add_parser("validate", help="validate the configuration")
    validate_cmd.add_argument(
        "--config", metavar="PATH", default=None, help="configuration file to validate"
    )

    health_parser = subparsers.add_parser("health", help="report runtime component health")
    health_parser.add_argument(
        "--config", metavar="PATH", default=None, help="configuration file to use"
    )

    ai_parser = subparsers.add_parser("ai", help="AI provider commands")
    ai_sub = ai_parser.add_subparsers(dest="ai_command", metavar="SUBCOMMAND")

    ai_health = ai_sub.add_parser("health", help="report AI provider health")
    ai_health.add_argument(
        "--config", metavar="PATH", default=None, help="configuration file to use"
    )
    ai_health.add_argument("--json", action="store_true", help="machine-readable output")

    ai_providers = ai_sub.add_parser("providers", help="list registered AI providers")
    ai_providers.add_argument(
        "--config", metavar="PATH", default=None, help="configuration file to use"
    )
    ai_providers.add_argument("--json", action="store_true", help="machine-readable output")

    ai_benchmark = ai_sub.add_parser("benchmark", help="read-only hardware benchmark")
    ai_benchmark.add_argument(
        "--config", metavar="PATH", default=None, help="configuration file to use"
    )
    ai_benchmark.add_argument("--json", action="store_true", help="machine-readable output")

    return parser


def _cmd_config_validate(args: argparse.Namespace) -> int:
    try:
        loaded = load_config(args.config)
    except ConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    print("Configuration valid.")
    print(f"Source: {loaded.source}")
    return EXIT_OK


def _cmd_ai_health(args: argparse.Namespace) -> int:
    try:
        runtime = _runtime_from_args(args)
    except ConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    try:
        registry_health = runtime.intelligence.health()
    except JarvisError as exc:
        print(f"jarvis ai health: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    finally:
        asyncio.run(runtime.stop())

    failed = any(not health.ok for health in registry_health.values())
    if args.json:
        print(json.dumps(
            {name: health.to_dict() for name, health in registry_health.items()},
            indent=2,
        ))
        return EXIT_FAILURE if failed else EXIT_OK

    if not registry_health:
        print("No AI providers configured.")
        return EXIT_OK
    print("J.A.R.V.I.S. AI Provider Health")
    for provider_id, health in sorted(registry_health.items()):
        state = health.state.value
        print(f"  {provider_id:<12} {state:<14} {health.detail or ''}")
    return EXIT_FAILURE if failed else EXIT_OK


def _cmd_ai_providers(args: argparse.Namespace) -> int:
    try:
        runtime = _runtime_from_args(args)
    except ConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    try:
        snapshot = runtime.intelligence.registry.snapshot()
    finally:
        asyncio.run(runtime.stop())

    if args.json:
        print(json.dumps(snapshot, indent=2))
        return EXIT_OK

    if not snapshot:
        print("No AI providers configured.")
        return EXIT_OK
    print("J.A.R.V.I.S. AI Providers")
    for provider_id, info in sorted(snapshot.items()):
        caps = ", ".join(info["capabilities"])
        print(f"  {provider_id:<12} state={info['state']:<14} caps=[{caps}]")
    return EXIT_OK


def _cmd_ai_benchmark(args: argparse.Namespace) -> int:
    try:
        result = run_benchmark()
    except Exception as exc:
        print(f"jarvis ai benchmark: {exc}", file=sys.stderr)
        return EXIT_FAILURE

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
        return EXIT_OK
    print(format_benchmark(result))
    return EXIT_OK


def _runtime_from_args(args: argparse.Namespace) -> Runtime:
    runtime = Runtime.create(args.config)
    asyncio.run(runtime.start())
    return runtime


def _cmd_health(args: argparse.Namespace) -> int:
    try:
        runtime = Runtime.create(args.config)
    except ConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID

    try:
        asyncio.run(runtime.start())
    except JarvisError as exc:
        print(f"jarvis health: {exc}", file=sys.stderr)
        return EXIT_FAILURE

    print("J.A.R.V.I.S. Health")
    try:
        reports = runtime.health_report()
        for report in reports:
            label = COMPONENT_LABELS.get(report.component, report.component)
            print(f"  {label:<18} {report.status.value}")
            if report.status is HealthStatus.UNHEALTHY:
                print(f"    detail: {report.detail}")
        overall = runtime.overall_health()
        print(f"\nOverall          {overall.value}")
    finally:
        asyncio.run(runtime.stop())

    return EXIT_OK if overall is not HealthStatus.UNHEALTHY else EXIT_FAILURE


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "config":
        if args.config_command == "validate":
            return _cmd_config_validate(args)
        parser.error("config requires a subcommand: validate")
    if args.command == "health":
        return _cmd_health(args)
    if args.command == "ai":
        if args.ai_command == "health":
            return _cmd_ai_health(args)
        if args.ai_command == "providers":
            return _cmd_ai_providers(args)
        if args.ai_command == "benchmark":
            return _cmd_ai_benchmark(args)
        parser.error("ai requires a subcommand: health, providers, benchmark")

    parser.print_help()
    return EXIT_OK
