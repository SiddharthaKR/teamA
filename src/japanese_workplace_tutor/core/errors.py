"""Errors shared across layers."""


class GenerationError(RuntimeError):
    pass


class ContractViolation(ValueError):
    """An application-authored rejection whose message is safe to send back to the model."""
