"""J.A.R.V.I.S.-specific exception hierarchy.

Small by design (see docs/DEVELOPMENT_RULES.md — no exception sprawl).
Every error preserves useful context via its message.
"""


class JarvisError(Exception):
    """Base class for all J.A.R.V.I.S. errors."""


class ConfigurationError(JarvisError):
    """Configuration could not be loaded or validated."""


class LifecycleError(JarvisError):
    """An invalid runtime state transition or lifecycle violation."""


class ServiceError(JarvisError):
    """Service registry registration, retrieval, or lifecycle failure."""


class EventError(JarvisError):
    """Event publication or bus lifecycle failure."""


class ValidationError(JarvisError):
    """Input did not pass validation."""
