class PortalError(Exception):
    """Base error for upstream portal failures."""


class PortalConfigurationError(PortalError):
    """Raised when live portal evidence/configuration is incomplete."""


class PortalAuthenticationError(PortalError):
    """Raised when the portal rejects credentials."""


class PortalUnavailableError(PortalError):
    """Raised when the portal cannot be reached or is circuit-open."""


class PortalCircuitOpenError(PortalUnavailableError):
    """Raised when the adapter is failing fast while the breaker is open."""


class PortalNotFoundError(PortalError):
    """Raised when the portal confirms a resource does not exist."""


class PortalSchemaDriftError(PortalError):
    """Raised when a non-empty response does not match known evidence shapes."""


class PortalSessionExpiredError(PortalAuthenticationError):
    """Raised when a response remains expired after reauthentication."""


class PortalTimeoutError(PortalUnavailableError):
    """Raised when an upstream request times out."""
