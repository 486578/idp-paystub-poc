"""Exceptions raised by the component."""


class PaystubAgiError(Exception):
    """Base class for every error this package raises on purpose."""


class ConfigError(PaystubAgiError):
    """The configuration is missing, unreadable or invalid."""


class ClassificationError(PaystubAgiError):
    """The rule list left a deduction undecided (it needs a catch-all last rule)."""
