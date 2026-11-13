"""Exceptions raised by the component."""


class PaystubAgiError(Exception):
    """Base class for every error this package raises on purpose."""


class ConfigError(PaystubAgiError):
    """The configuration is missing, unreadable or invalid."""


class ClassificationError(PaystubAgiError):
    """The rule list left a deduction undecided (it needs a catch-all last rule)."""


class InputMismatchError(PaystubAgiError):
    """Inputs that must belong together don't, e.g. decisions for other rows."""


class ReadingError(PaystubAgiError):
    """The stub couldn't be read. `code` is the OCR library's reason, if any."""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code
