"""Errors safe to display without leaking credential-bearing URLs."""


class ProviderError(Exception):
    """An external source could not provide usable data."""


class AuthError(ProviderError):
    """Credentials rejected."""


class CoverageError(ProviderError):
    """The source cannot cover the requested time or journey."""


class RateLimitError(ProviderError):
    """The source or configured budget rejected another request."""
