"""Cancellable timing primitives for experimental workflows."""

from __future__ import annotations

import math
from typing import Protocol
import time

from ._exceptions import WorkflowCancelledError


class CancellationEvent(Protocol):
    """Minimal interface accepted for workflow cancellation."""

    def is_set(self) -> bool:
        """Return whether cancellation has been requested."""


def _as_nonnegative_float(value: float, *, name: str) -> float:
    """Validate a finite nonnegative duration."""

    if isinstance(value, bool):
        raise TypeError(f"{name} must be a real scalar, not bool")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{name} must be a real scalar") from exc
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"{name} must be finite and >= 0")
    return result


def _as_positive_float(value: float, *, name: str) -> float:
    """Validate a finite positive duration."""

    result = _as_nonnegative_float(value, name=name)
    if result == 0.0:
        raise ValueError(f"{name} must be > 0")
    return result


def _validate_cancel_event(
    cancel_event: CancellationEvent | None,
) -> None:
    """Validate the structural cancellation interface."""

    if cancel_event is not None and not callable(
        getattr(cancel_event, "is_set", None)
    ):
        raise TypeError("cancel_event must provide a callable is_set() method")


def _raise_if_cancelled(
    cancel_event: CancellationEvent | None,
    *,
    operation: str,
    start: float,
) -> None:
    """Raise the common cancellation exception when requested."""

    if cancel_event is not None and cancel_event.is_set():
        raise WorkflowCancelledError(
            operation=operation,
            elapsed=time.monotonic() - start,
        )


def _sleep_until(
    deadline: float,
    *,
    cancel_event: CancellationEvent | None,
    check_interval: float,
    operation: str,
    start: float,
) -> None:
    """Sleep until an absolute monotonic deadline while checking cancellation."""

    while True:
        _raise_if_cancelled(
            cancel_event,
            operation=operation,
            start=start,
        )
        remaining = deadline - time.monotonic()
        if remaining <= 0.0:
            return
        time.sleep(min(remaining, check_interval))


def sleep(
    seconds: float,
    *,
    cancel_event: CancellationEvent | None = None,
    check_interval: float = 0.1,
) -> None:
    """Wait for a duration while remaining responsive to cancellation.

    ``check_interval`` only controls cancellation latency; it does not change
    the requested total duration.  A monotonic clock is used so wall-clock
    adjustments cannot shorten or extend the wait.
    """

    duration = _as_nonnegative_float(seconds, name="seconds")
    cancellation_interval = _as_positive_float(
        check_interval,
        name="check_interval",
    )
    _validate_cancel_event(cancel_event)

    start = time.monotonic()
    _sleep_until(
        start + duration,
        cancel_event=cancel_event,
        check_interval=cancellation_interval,
        operation="sleep",
        start=start,
    )


def delay(
    seconds: float,
    *,
    cancel_event: CancellationEvent | None = None,
    check_interval: float = 0.1,
) -> None:
    """Alias-style wrapper for :func:`sleep`."""

    sleep(
        seconds,
        cancel_event=cancel_event,
        check_interval=check_interval,
    )

