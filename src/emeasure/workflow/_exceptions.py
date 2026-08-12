"""Exceptions raised by instrument-independent workflows."""

from __future__ import annotations


class WorkflowError(Exception):
    """Base class for workflow errors."""


class WorkflowCancelledError(WorkflowError):
    """Raised when a workflow operation is cancelled."""

    def __init__(self, operation: str, elapsed: float) -> None:
        self.operation = operation
        self.elapsed = elapsed
        super().__init__(
            f"{operation} was cancelled after {elapsed:.6g} s"
        )


class WaitTimeoutError(WorkflowError, TimeoutError):
    """Raised when a wait operation exceeds its timeout."""

    def __init__(
        self,
        *,
        timeout: float,
        elapsed: float,
        attempts: int,
        last_value: object = None,
    ) -> None:
        self.timeout = timeout
        self.elapsed = elapsed
        self.attempts = attempts
        self.last_value = last_value
        super().__init__(
            f"Condition was not satisfied within {timeout:.6g} s "
            f"after {attempts} attempt(s)"
        )


class ConditionEvaluationError(WorkflowError):
    """Raised when a condition callable fails during evaluation."""

    def __init__(
        self,
        *,
        elapsed: float,
        attempt: int,
    ) -> None:
        self.elapsed = elapsed
        self.attempt = attempt
        super().__init__(
            f"Condition evaluation failed on attempt {attempt} "
            f"after {elapsed:.6g} s"
        )

