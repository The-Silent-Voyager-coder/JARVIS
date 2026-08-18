"""J.A.R.V.I.S. command-line interface.

Commands:

    jarvis config validate [--config PATH]    validate configuration
    jarvis health [--config PATH]             boot the runtime and report health
    jarvis ai health [--config PATH]          AI provider health table
    jarvis ai providers [--config PATH]       list registered AI providers
    jarvis ai benchmark [--config PATH]       read-only hardware benchmark
    jarvis memory health [--config PATH]      memory database health
    jarvis memory list [--config PATH]        list memories (filters + ranking)
    jarvis memory get <id> [--config PATH]    show one memory
    jarvis memory delete <id> [--config PATH] delete a memory (auditable)
    jarvis memory stats [--config PATH]       counts by type + subsystem state
    jarvis memory search <query> [--config PATH]
    jarvis tools list [--config PATH]         list registered tools
    jarvis tools info <tool> [--config PATH]  tool metadata + schemas
    jarvis tools health [--config PATH]       tool subsystem health
    jarvis tools execute <tool> NAME=VALUE …  run a tool through the security
            pipeline (denied by default; --approve opts into approvals)

Exit codes: 0 success, 1 general failure, 2 invalid configuration/input.
Memory content is never printed unless --content is passed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version

from jarvis import __version__
from jarvis.configuration.loader import load_config
from jarvis.core.health import HealthStatus
from jarvis.core.runtime import Runtime
from jarvis.exceptions import (
    ConfigurationError,
    JarvisError,
    MemoryError,
    MemoryNotFoundError,
    MemoryValidationError,
    ToolNotFoundError,
    ToolPermissionDeniedError,
    ToolUnavailableError,
    ToolValidationError,
)
from jarvis.intelligence.benchmark import format_benchmark, run_benchmark
from jarvis.memory.models import MemoryType
from jarvis.memory.service import MemoryService
from jarvis.tools.approval import DeterministicApprovalProvider
from jarvis.tools.models import ApprovalOutcome, ToolRequest

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
    "memory": "Memory",
    "tools": "Tools",
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

    memory_parser = subparsers.add_parser("memory", help="memory commands")
    memory_sub = memory_parser.add_subparsers(dest="memory_command", metavar="SUBCOMMAND")

    mem_health = memory_sub.add_parser("health", help="report memory subsystem health")
    mem_health.add_argument(
        "--config", metavar="PATH", default=None, help="configuration file to use"
    )
    mem_health.add_argument("--json", action="store_true", help="machine-readable output")

    mem_list = memory_sub.add_parser("list", help="list memories (ranked)")
    mem_list.add_argument(
        "--config", metavar="PATH", default=None, help="configuration file to use"
    )
    mem_list.add_argument("--json", action="store_true", help="machine-readable output")
    mem_list.add_argument("--content", action="store_true", help="include memory content")
    _add_memory_filter_args(mem_list)

    mem_get = memory_sub.add_parser("get", help="show one memory by id")
    mem_get.add_argument("memory_id", metavar="ID", help="memory id")
    mem_get.add_argument(
        "--config", metavar="PATH", default=None, help="configuration file to use"
    )
    mem_get.add_argument("--json", action="store_true", help="machine-readable output")
    mem_get.add_argument("--content", action="store_true", help="include memory content")
    mem_get.add_argument("--include-expired", action="store_true", help="allow expired memories")
    mem_get.add_argument("--include-deleted", action="store_true", help="allow deleted memories")

    mem_delete = memory_sub.add_parser("delete", help="delete memory(ies) — auditable")
    mem_delete.add_argument("memory_id", metavar="ID", nargs="?", help="memory id to delete")
    mem_delete.add_argument(
        "--config", metavar="PATH", default=None, help="configuration file to use"
    )
    mem_delete.add_argument("--json", action="store_true", help="machine-readable output")
    _add_memory_filter_args(mem_delete)
    mem_delete.add_argument(
        "--yes",
        action="store_true",
        help="confirm bulk deletion by filters (required for bulk deletes)",
    )

    mem_stats = memory_sub.add_parser("stats", help="memory counts and subsystem state")
    mem_stats.add_argument(
        "--config", metavar="PATH", default=None, help="configuration file to use"
    )
    mem_stats.add_argument("--json", action="store_true", help="machine-readable output")

    mem_search = memory_sub.add_parser("search", help="full-text search (FTS5 or LIKE)")
    mem_search.add_argument("query", metavar="QUERY", help="search text")
    mem_search.add_argument(
        "--config", metavar="PATH", default=None, help="configuration file to use"
    )
    mem_search.add_argument("--json", action="store_true", help="machine-readable output")
    mem_search.add_argument("--content", action="store_true", help="include memory content")
    _add_memory_filter_args(mem_search)

    tools_parser = subparsers.add_parser("tools", help="tool commands")
    tools_sub = tools_parser.add_subparsers(dest="tools_command", metavar="SUBCOMMAND")

    tools_list = tools_sub.add_parser("list", help="list registered tools")
    tools_list.add_argument(
        "--config", metavar="PATH", default=None, help="configuration file to use"
    )
    tools_list.add_argument("--json", action="store_true", help="machine-readable output")

    tools_info = tools_sub.add_parser("info", help="tool metadata and schemas")
    tools_info.add_argument("tool_id", metavar="TOOL", help="tool id")
    tools_info.add_argument(
        "--config", metavar="PATH", default=None, help="configuration file to use"
    )
    tools_info.add_argument("--json", action="store_true", help="machine-readable output")

    tools_health = tools_sub.add_parser("health", help="report tool subsystem health")
    tools_health.add_argument(
        "--config", metavar="PATH", default=None, help="configuration file to use"
    )
    tools_health.add_argument("--json", action="store_true", help="machine-readable output")

    tools_execute = tools_sub.add_parser(
        "execute",
        help="run a tool through the security pipeline (denied unless --approve)",
    )
    tools_execute.add_argument("tool_id", metavar="TOOL", help="tool id")
    tools_execute.add_argument(
        "assignments", metavar="NAME=VALUE", nargs="*", help="arguments (JSON values)"
    )
    tools_execute.add_argument(
        "--config", metavar="PATH", default=None, help="configuration file to use"
    )
    tools_execute.add_argument("--json", action="store_true", help="machine-readable output")
    tools_execute.add_argument(
        "--approve",
        action="store_true",
        help="use an approving approval provider (default: denials)",
    )
    tools_execute.add_argument("--session-id", default=None, help="session isolation context")

    return parser


def _add_memory_filter_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--type", metavar="TYPE", default=None,
        help=f"memory type in {sorted(t.value for t in MemoryType)}",
    )
    parser.add_argument("--source", metavar="SOURCE", default=None, help="source filter")
    parser.add_argument(
        "--provenance", metavar="PROVENANCE", default=None, help="provenance filter"
    )
    parser.add_argument("--min-confidence", metavar="VALUE", type=float, default=None,
                        help="minimum confidence 0.0..1.0")
    parser.add_argument("--session", metavar="ID", default=None, help="session isolation context")
    parser.add_argument("--limit", metavar="N", type=int, default=50, help="max results")
    parser.add_argument("--offset", metavar="N", type=int, default=0, help="skip N results")
    parser.add_argument("--include-expired", action="store_true", help="include expired memories")
    parser.add_argument("--include-deleted", action="store_true", help="include deleted memories")


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


# --- memory --------------------------------------------------------------


def _memory_runtime(args: argparse.Namespace) -> Runtime:
    runtime = Runtime.create(args.config)
    asyncio.run(runtime.start())
    return runtime


def _memory_type_from_args(value: str | None) -> MemoryType | None:
    if value is None:
        return None
    try:
        return MemoryType(value)
    except ValueError as exc:
        raise MemoryValidationError(
            f"invalid memory type: {value!r} (expected one of "
            f"{sorted(t.value for t in MemoryType)})"
        ) from exc


def _memory_filter_kwargs(args: argparse.Namespace) -> dict:
    kwargs: dict = {
        "memory_type": _memory_type_from_args(getattr(args, "type", None)),
        "source": getattr(args, "source", None),
        "provenance": getattr(args, "provenance", None),
        "session_id": getattr(args, "session", None),
        "include_expired": getattr(args, "include_expired", False),
        "include_deleted": getattr(args, "include_deleted", False),
    }
    if getattr(args, "min_confidence", None) is not None:
        kwargs["minimum_confidence"] = args.min_confidence
    return {k: v for k, v in kwargs.items() if v is not None}


def _print_memories(
    service: MemoryService,
    items: list,
    total: int,
    *,
    include_content: bool,
    json_mode: bool,
    header: str,
) -> None:
    if json_mode:
        print(json.dumps(
            {"items": [item.to_dict(include_content=include_content) for item in items],
             "total": total},
            indent=2,
        ))
        return
    print(header)
    if not items:
        print("  (none)")
        return
    for item in items:
        memory = item.memory
        row = (
            f"  {memory.id[:24]:<24} {memory.memory_type.value:<10} "
            f"conf={memory.confidence:.2f} "
            f"expires={memory.expires_at.strftime('%Y-%m-%d') if memory.expires_at else '-'} "
            f"({item.match_reason})"
        )
        print(row)
        if include_content:
            text = memory.content if isinstance(memory.content, str) else json.dumps(memory.content)
            print(f"    content: {text[:80]}")
    if total > len(items):
        print(f"  … {total - len(items)} more (total {total}; use --offset/--limit)")


def _cmd_memory_health(args: argparse.Namespace) -> int:
    try:
        runtime = _memory_runtime(args)
    except ConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    try:
        data = runtime.memory.health()
    finally:
        asyncio.run(runtime.stop())
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print("J.A.R.V.I.S. Memory Health")
        print(f"  status       {data.get('status', 'unknown')}")
        print(f"  detail       {data.get('detail') or ''}")
        for key in (
            "accessible", "schema_valid", "migrations_current",
            "writable", "fts_enabled", "schema_version",
        ):
            if key in data:
                print(f"  {key:<13} {data[key]}")
        print(f"  database     {data.get('database_path', '')}")
    return EXIT_OK if data.get("available", False) else EXIT_FAILURE


def _cmd_memory_list(args: argparse.Namespace) -> int:
    try:
        runtime = _memory_runtime(args)
    except ConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    try:
        result = runtime.memory.retrieve(
            **{
                **_memory_filter_kwargs(args),
                "limit": args.limit,
                "offset": args.offset,
            }
        )
    except MemoryError as exc:
        print(f"jarvis memory list: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    finally:
        asyncio.run(runtime.stop())
    _print_memories(
        runtime.memory, result.items, result.total,
        include_content=args.content, json_mode=args.json,
        header="J.A.R.V.I.S. Memory",
    )
    return EXIT_OK


def _cmd_memory_get(args: argparse.Namespace) -> int:
    try:
        runtime = _memory_runtime(args)
    except ConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    try:
        memory = runtime.memory.get(
            args.memory_id,
            include_expired=args.include_expired,
            include_deleted=args.include_deleted,
        )
    except MemoryError as exc:
        print(f"jarvis memory get: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    finally:
        asyncio.run(runtime.stop())
    if memory is None:
        print(f"jarvis memory get: memory not found: {args.memory_id}", file=sys.stderr)
        return EXIT_FAILURE
    if args.json:
        print(json.dumps(memory.to_dict(include_content=args.content), indent=2))
        return EXIT_OK
    print("J.A.R.V.I.S. Memory")
    print(f"  id           {memory.id}")
    print(f"  type         {memory.memory_type.value}")
    print(f"  source       {memory.source}")
    print(f"  provenance   {memory.provenance}")
    print(f"  confidence   {memory.confidence:.2f}")
    print(f"  created_at   {memory.created_at.isoformat()}")
    print(f"  updated_at   {memory.updated_at.isoformat()}")
    print(f"  expires_at   {memory.expires_at.isoformat() if memory.expires_at else '-'}")
    print(f"  session_id   {memory.session_id or '-'}")
    if args.content:
        text = (
            memory.content
            if isinstance(memory.content, str)
            else json.dumps(memory.content)
        )
        print(f"  content      {text}")
    else:
        print("  content      (hidden; pass --content to show)")
    return EXIT_OK


def _cmd_memory_delete(args: argparse.Namespace) -> int:
    try:
        runtime = _memory_runtime(args)
    except ConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    try:
        if args.memory_id:
            runtime.memory.forget(args.memory_id)
            deleted = [args.memory_id]
        else:
            filters = _memory_filter_kwargs(args)
            if not any(k in filters for k in ("memory_type", "source", "provenance", "session_id")):
                print(
                    "jarvis memory delete: provide a memory id or at least one filter "
                    "(--type/--source/--provenance)",
                    file=sys.stderr,
                )
                return EXIT_INVALID
            if not args.yes:
                print(
                    "jarvis memory delete: bulk deletion requires --yes confirmation",
                    file=sys.stderr,
                )
                return EXIT_INVALID
            result = runtime.memory.retrieve(limit=None, **filters)
            deleted = [item.memory.id for item in result.items]
            for memory_id in deleted:
                runtime.memory.forget(memory_id)
    except MemoryNotFoundError as exc:
        print(f"jarvis memory delete: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    except MemoryError as exc:
        print(f"jarvis memory delete: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    finally:
        asyncio.run(runtime.stop())
    if args.json:
        print(json.dumps({"deleted": deleted, "deleted_count": len(deleted)}, indent=2))
    else:
        print(f"Deleted {len(deleted)} memory(ies).")
    return EXIT_OK


def _cmd_memory_stats(args: argparse.Namespace) -> int:
    try:
        runtime = _memory_runtime(args)
    except ConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    try:
        stats = runtime.memory.stats()
    except MemoryError as exc:
        print(f"jarvis memory stats: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    finally:
        asyncio.run(runtime.stop())
    if args.json:
        print(json.dumps(stats, indent=2))
        return EXIT_OK
    print("J.A.R.V.I.S. Memory Stats")
    for memory_type in MemoryType:
        count = stats["by_type"].get(memory_type.value, 0)
        print(f"  {memory_type.value:<12} {count}")
    print(f"  {'expired':<12} {stats.get('expired', 0)}")
    print(f"  {'deleted':<12} {stats.get('deleted', 0)}")
    print(f"  {'total':<12} {stats.get('total', 0)}")
    print(f"  fts          {'enabled' if stats.get('fts_enabled') else 'fallback (LIKE)'}")
    print(f"  schema       v{stats.get('schema_version', 0)}")
    print(f"  database     {stats.get('database_path', '')}")
    return EXIT_OK


def _cmd_memory_search(args: argparse.Namespace) -> int:
    try:
        runtime = _memory_runtime(args)
    except ConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    try:
        result = runtime.memory.retrieve(
            query=args.query,
            **{
                **_memory_filter_kwargs(args),
                "limit": args.limit,
                "offset": args.offset,
            },
        )
    except MemoryError as exc:
        print(f"jarvis memory search: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    finally:
        asyncio.run(runtime.stop())
    _print_memories(
        runtime.memory, result.items, result.total,
        include_content=args.content, json_mode=args.json,
        header=f"J.A.R.V.I.S. Memory Search: {args.query!r}",
    )
    return EXIT_OK


# --- tools ---------------------------------------------------------------


def _parse_tool_arguments(assignments: Sequence[str]) -> dict:
    arguments: dict = {}
    for item in assignments:
        if "=" not in item or item.startswith("="):
            raise ToolValidationError(
                f"invalid argument {item!r} (expected NAME=VALUE with a JSON value)"
            )
        name, raw = item.split("=", 1)
        if not name:
            raise ToolValidationError(
                f"invalid argument {item!r} (empty name)"
            )
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = raw
        arguments[name] = value
    return arguments


def _cmd_tools_list(args: argparse.Namespace) -> int:
    try:
        runtime = _runtime_from_args(args)
    except ConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    try:
        registry = runtime.tools.registry()
        descriptions = [
            registry.describe(tool_id)
            for tool_id in registry.list_ids()
        ]
    finally:
        asyncio.run(runtime.stop())
    if args.json:
        print(json.dumps({"tools": descriptions}, indent=2))
        return EXIT_OK
    print("J.A.R.V.I.S. Tools")
    for info in descriptions:
        print(
            f"  {info['id']:<22} {info['risk_level']:<9} "
            f"{info['category']:<10} {info['name']}"
        )
    return EXIT_OK


def _cmd_tools_info(args: argparse.Namespace) -> int:
    try:
        runtime = _runtime_from_args(args)
    except ConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    try:
        info = runtime.tools.registry().describe(args.tool_id)
    except ToolNotFoundError as exc:
        print(f"jarvis tools info: {exc}", file=sys.stderr)
        return EXIT_INVALID
    finally:
        asyncio.run(runtime.stop())
    if args.json:
        print(json.dumps(info, indent=2))
        return EXIT_OK
    print(f"Tool: {info['id']}")
    print(f"  name         {info['name']}")
    print(f"  description  {info['description']}")
    print(f"  version      {info['version']}")
    print(f"  risk_level   {info['risk_level']}")
    print(f"  category     {info['category']}")
    print(f"  capabilities {', '.join(info['capabilities']) or '-'}")
    print(f"  input_schema {json.dumps(info['input_schema'])}")
    print(f"  output_schema {json.dumps(info['output_schema'])}")
    return EXIT_OK


def _cmd_tools_health(args: argparse.Namespace) -> int:
    try:
        runtime = _runtime_from_args(args)
    except ConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    try:
        data = runtime.tools.health()
    finally:
        asyncio.run(runtime.stop())
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print("J.A.R.V.I.S. Tool Health")
        print(f"  status    {data.get('status', 'unknown')}")
        print(f"  mode      {data.get('mode', '-')}")
        print(f"  detail    {data.get('detail') or ''}")
        if "tool_count" in data:
            print(f"  tools     {data['tool_count']} — {', '.join(data.get('tools', []))}")
    return EXIT_OK if data.get("available", False) else EXIT_FAILURE


def _cmd_tools_execute(args: argparse.Namespace) -> int:
    try:
        runtime = _runtime_from_args(args)
    except ConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    try:
        try:
            arguments = _parse_tool_arguments(args.assignments)
        except ToolValidationError as exc:
            print(f"jarvis tools execute: {exc}", file=sys.stderr)
            return EXIT_INVALID
        if args.approve:
            runtime.tools.approval = DeterministicApprovalProvider(
                ApprovalOutcome.APPROVED
            )
        request = ToolRequest(
            request_id=uuid.uuid4().hex,
            tool_id=args.tool_id,
            arguments=arguments,
            source="cli",
            session_id=args.session_id,
        )
        result = runtime.tools.execute(request)
    except (ToolNotFoundError, ToolValidationError) as exc:
        print(f"jarvis tools execute: {exc}", file=sys.stderr)
        return EXIT_INVALID
    except (ToolPermissionDeniedError, ToolUnavailableError) as exc:
        print(f"jarvis tools execute: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    finally:
        asyncio.run(runtime.stop())
    if args.json:
        print(json.dumps(
            {
                "request_id": result.request_id,
                "tool_id": result.tool_id,
                "success": result.success,
                "output": result.output,
                "error": result.error,
                "duration_ms": result.duration_ms,
            },
            indent=2,
        ))
        return EXIT_OK if result.success else EXIT_FAILURE
    print(f"Tool: {result.tool_id}")
    if result.success:
        print(f"Result: success ({result.duration_ms} ms)")
    else:
        print(f"Result: failed ({result.duration_ms} ms)")
        print(f"Error: {result.error}")
    if result.output is not None:
        print(json.dumps(result.output, indent=2))
    return EXIT_OK if result.success else EXIT_FAILURE


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
    if args.command == "memory":
        if args.memory_command == "health":
            return _cmd_memory_health(args)
        if args.memory_command == "list":
            return _cmd_memory_list(args)
        if args.memory_command == "get":
            return _cmd_memory_get(args)
        if args.memory_command == "delete":
            return _cmd_memory_delete(args)
        if args.memory_command == "stats":
            return _cmd_memory_stats(args)
        if args.memory_command == "search":
            return _cmd_memory_search(args)
        parser.error(
            "memory requires a subcommand: health, list, get, delete, stats, search"
        )
    if args.command == "tools":
        if args.tools_command == "list":
            return _cmd_tools_list(args)
        if args.tools_command == "info":
            return _cmd_tools_info(args)
        if args.tools_command == "health":
            return _cmd_tools_health(args)
        if args.tools_command == "execute":
            return _cmd_tools_execute(args)
        parser.error("tools requires a subcommand: list, info, health, execute")

    parser.print_help()
    return EXIT_OK
