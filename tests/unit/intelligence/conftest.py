"""Shared fixtures for intelligence tests: fake HTTP servers for adapters.

Tests never talk to real Ollama/OpenCode servers, the internet, or any
external service — everything is an in-process stdlib HTTP server.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest


class FakeHttpServer(ThreadingHTTPServer):
    """In-process HTTP server with canned, inspectable routes."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), FakeHandler)
        self.routes: dict[tuple[str, str], tuple[int, str]] = {}
        self.requests: list[dict[str, Any]] = []
        self.sleep_seconds: float = 0.0
        self.respond_slowly_for: set[str] = set()

    @property
    def url(self) -> str:
        host, port = self.server_address
        return f"http://127.0.0.1:{port}"

    def route(self, method: str, path: str, status: int, body: Any) -> None:
        """Register a canned response (body serialized to JSON text)."""
        if isinstance(body, str):
            payload = body
            content_type = "text/plain"
        else:
            payload = json.dumps(body)
            content_type = "application/json"
        self.routes[(method.upper(), path)] = (status, payload)
        self._content_type = content_type

    def slow(self, path: str) -> None:
        self.respond_slowly_for.add(path)


class FakeHandler(BaseHTTPRequestHandler):
    server: FakeHttpServer

    def _handle(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0) or 0)
        raw_body = self.rfile.read(content_length) if content_length else b""
        request_entry = {
            "method": self.command,
            "path": self.path,
            "headers": dict(self.headers),
            "body": raw_body.decode("utf-8", errors="replace"),
        }
        self.server.requests.append(request_entry)

        if self.path in self.server.respond_slowly_for:
            time.sleep(3.0)

        key = (self.command, self.path)
        if key not in self.server.routes:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'{"error": "not found"}')
            return
        status, payload = self.server.routes[key]
        body = payload.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", getattr(self.server, "_content_type", "application/json"))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        self._handle()

    def do_POST(self) -> None:  # noqa: N802
        self._handle()

    def do_DELETE(self) -> None:  # noqa: N802
        self._handle()

    def log_message(self, *args: Any) -> None:  # silence request logs
        return None


@pytest.fixture
def fake_server() -> Any:
    """A running FakeHttpServer, torn down after the test."""
    server = FakeHttpServer()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
