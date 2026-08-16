"""J.A.R.V.I.S. command-line interface.

Commands (Phase 1):

    jarvis config validate [--config PATH]    validate configuration
    jarvis health [--config PATH]             boot the runtime and report health

Exit codes: 0 success, 1 general failure, 2 invalid configuration/input.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version

from jarvis import __version__
from jarvis.configuration.loader import load_config
from jarvis.core.health import HealthStatus
from jarvis.core.runtime import Runtime
from jarvis.exceptions import ConfigurationError, JarvisError

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_INVALID = 2

COMPONENT_LABELS: dict[str, str] = {
    "core": "Core",
    "configuration": "Configuration",
    "event_bus": "Event Bus",
    "service_registry": "Service Registry",
    "storage": "Storage",
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

    parser.print_help()
    return EXIT_OK
