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


class ProviderError(JarvisError):
    """A provider adapter failed (network, malformed response, service error)."""


class ProviderUnavailableError(ProviderError):
    """The provider endpoint is unreachable or the provider is not ready."""


class ProviderCapabilityError(ProviderError):
    """The requested behavior is not supported by this provider's capabilities."""


class RoutingError(JarvisError):
    """No provider could be selected for the request (policy + availability)."""


class MemoryError(JarvisError):
    """The memory subsystem failed (database, repository, or service)."""


class MemoryValidationError(MemoryError):
    """A memory model or request did not pass validation."""


class MemoryNotFoundError(MemoryError):
    """The requested memory id does not exist."""


class MemoryDatabaseError(MemoryError):
    """The memory database is inaccessible, corrupted, or schema-mismatched."""


class MemoryUnavailableError(MemoryError):
    """The memory subsystem failed to start and cannot serve requests."""
