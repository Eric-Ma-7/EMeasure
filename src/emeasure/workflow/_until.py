"""Polling wait for an arbitrary user-provided condition."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import math
import time

from .._exceptions import ConditionEvaluationError, WaitTimeoutError
from .._timing import (
    CancellationEvent,
    _raise_if_cancelled,
    _sleep_until,
    _validate_cancel_event,
)


@dataclass(frozen=True, slots=True)
class WaitUntilPoll:
    """State reported after one condition evaluation."""

    value: object
    condition_met: bool
    elapsed: float
    attempt: int
    consecutive_successes: int
    required_confirmations: int


@dataclass(frozen=True, slots=True)
class WaitUntilResult:
    """Result returned after a condition remains satisfied."""

    value: object
    elapsed: float
    attempts: int
    consecutive_successes: int
    required_confirmations: int


def _as_duration(
    value: float,
    *,
    name: str,
    allow_zero: bool,
) -> float:
    """Validate a finite duration used by condition polling."""

    if isinstance(value, bool):
        raise TypeError(f"{name} must be a real scalar, not bool")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{name} must be a real scalar") from exc

    minimum_is_valid = result >= 0.0 if allow_zero else result > 0.0
    if not math.isfinite(result) or not minimum_is_valid:
        comparator = ">= 0" if allow_zero else "> 0"
        raise ValueError(f"{name} must be finite and {comparator}")
    return result


def wait_until(
    condition: Callable[[], object],
    *,
    timeout: float,
    interval: float = 0.5,
    min_wait: float = 0.0,
    confirmations: int = 1,
    cancel_event: CancellationEvent | None = None,
    cancel_check_interval: float = 0.1,
    on_poll: Callable[[WaitUntilPoll], None] | None = None,
) -> WaitUntilResult:
    """Poll until a condition is truthy for consecutive evaluations.

    Parameters
    ----------
    condition:
        Zero-argument callable.  Its return value is converted to ``bool`` for
        the decision and the original value is retained in the result.
    timeout:
        Maximum total duration, including ``min_wait`` and condition calls.
    interval:
        Delay between completed condition evaluations.
    min_wait:
        Cancellable delay before the first condition evaluation.
    confirmations:
        Number of consecutive truthy evaluations required for success.
    cancel_event:
        Optional object such as ``threading.Event`` providing ``is_set()``.
    cancel_check_interval:
        Maximum cancellation latency while sleeping between evaluations.
    on_poll:
        Optional callback receiving a :class:`WaitUntilPoll` after each
        successful condition call.

    Returns
    -------
    WaitUntilResult
        The last raw condition value and timing diagnostics.

    Raises
    ------
    WaitTimeoutError
        If the condition is not confirmed before ``timeout``.
    WorkflowCancelledError
        If ``cancel_event`` is set.
    ConditionEvaluationError
        If ``condition`` raises an exception.  The original exception is
        available through exception chaining.
    """

    if not callable(condition):
        raise TypeError("condition must be callable")
    if on_poll is not None and not callable(on_poll):
        raise TypeError("on_poll must be callable or None")

    timeout_value = _as_duration(
        timeout,
        name="timeout",
        allow_zero=False,
    )
    interval_value = _as_duration(
        interval,
        name="interval",
        allow_zero=False,
    )
    min_wait_value = _as_duration(
        min_wait,
        name="min_wait",
        allow_zero=True,
    )
    cancel_interval = _as_duration(
        cancel_check_interval,
        name="cancel_check_interval",
        allow_zero=False,
    )
    if min_wait_value >= timeout_value:
        raise ValueError("min_wait must be smaller than timeout")
    if (
        isinstance(confirmations, bool)
        or not isinstance(confirmations, int)
        or confirmations < 1
    ):
        raise ValueError("confirmations must be an integer >= 1")
    _validate_cancel_event(cancel_event)

    start = time.monotonic()
    deadline = start + timeout_value
    attempts = 0
    consecutive_successes = 0
    last_value: object = None

    _sleep_until(
        start + min_wait_value,
        cancel_event=cancel_event,
        check_interval=cancel_interval,
        operation="wait_until",
        start=start,
    )

    while True:
        _raise_if_cancelled(
            cancel_event,
            operation="wait_until",
            start=start,
        )
        now = time.monotonic()
        if now >= deadline:
            raise WaitTimeoutError(
                timeout=timeout_value,
                elapsed=now - start,
                attempts=attempts,
                last_value=last_value,
            )

        attempts += 1
        try:
            last_value = condition()
            condition_met = bool(last_value)
        except Exception as exc:
            raise ConditionEvaluationError(
                elapsed=time.monotonic() - start,
                attempt=attempts,
            ) from exc

        _raise_if_cancelled(
            cancel_event,
            operation="wait_until",
            start=start,
        )
        elapsed = time.monotonic() - start
        consecutive_successes = (
            consecutive_successes + 1 if condition_met else 0
        )

        poll = WaitUntilPoll(
            value=last_value,
            condition_met=condition_met,
            elapsed=elapsed,
            attempt=attempts,
            consecutive_successes=consecutive_successes,
            required_confirmations=confirmations,
        )
        if on_poll is not None:
            on_poll(poll)

        _raise_if_cancelled(
            cancel_event,
            operation="wait_until",
            start=start,
        )
        elapsed_after_callback = time.monotonic() - start
        if elapsed_after_callback >= timeout_value:
            raise WaitTimeoutError(
                timeout=timeout_value,
                elapsed=elapsed_after_callback,
                attempts=attempts,
                last_value=last_value,
            )

        if consecutive_successes >= confirmations:
            return WaitUntilResult(
                value=last_value,
                elapsed=elapsed_after_callback,
                attempts=attempts,
                consecutive_successes=consecutive_successes,
                required_confirmations=confirmations,
            )

        next_poll = min(time.monotonic() + interval_value, deadline)
        _sleep_until(
            next_poll,
            cancel_event=cancel_event,
            check_interval=cancel_interval,
            operation="wait_until",
            start=start,
        )