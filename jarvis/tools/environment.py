"""Controlled environment policy (spec §30): tools never see secrets.

`scrub_environment` copies only an allowlisted set of platform basics from
the real environment; anything that looks like a credential is rejected
entirely. Explicit per-call environment additions are validated the same way.
"""

from __future__ import annotations

from collections.abc import Mapping

from jarvis.exceptions import ToolValidationError

ALLOWED_ENV_KEYS = frozenset(
    {
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "TEMP",
        "TMP",
        "PROCESSOR_ARCHITECTURE",
        "NUMBER_OF_PROCESSORS",
        "USERPROFILE",
        "HOME",
        "LANG",
        "LC_ALL",
    }
)
SECRET_ENV_MARKERS = frozenset(
    {"key", "token", "secret", "password", "passwd", "credential", "auth", "api"}
)


def _is_marker_token(token: str) -> bool:
    if token in SECRET_ENV_MARKERS:
        return True
    if token.endswith("s") and token[:-1] in SECRET_ENV_MARKERS:
        return True
    return False


def is_secret_name(name: str) -> bool:
    """True when `name` contains a credential marker as a token.

    Token-based so `monkey` and `author` are not flagged while
    `openai_api_key`, `my-token`, `credentials`, and `secret_file` are.
    """
    folded = name.casefold().replace("-", "_")
    tokens = [token for token in folded.split("_") if token]
    return any(
        _is_marker_token(token) or token.startswith("api") for token in tokens
    )


def scrub_environment(source: Mapping[str, str]) -> dict[str, str]:
    """Return a minimal, secret-free environment for tool execution."""
    return {
        key: value
        for key, value in source.items()
        if key in ALLOWED_ENV_KEYS and value
    }


def merge_environment(
    base: dict[str, str], additions: Mapping[str, str] | None
) -> dict[str, str]:
    """Merge validated per-call env additions into a scrubbed base env."""
    if not additions:
        return dict(base)
    if not isinstance(additions, Mapping):
        raise ToolValidationError("env must be a mapping of string to string")
    merged = dict(base)
    for key, value in additions.items():
        if not isinstance(key, str) or not key.strip():
            raise ToolValidationError("env keys must be non-empty strings")
        if not isinstance(value, str):
            raise ToolValidationError(f"env value for {key!r} must be a string")
        if is_secret_name(key):
            raise ToolValidationError(
                f"environment variable {key!r} is not allowed in tool execution"
            )
        merged[key] = value
    return merged
