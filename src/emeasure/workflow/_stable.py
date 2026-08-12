"""Stable-measurement waits for several common experimental scenarios."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
import math
import time
from typing import Literal, Protocol, TypeAlias

import numpy as np

from ..statistics import (
    MannKendallResult,
    TOSTResult,
    TheilSenResult,
    hampel_filter,
    mann_kendall_test,
    theil_sen_test,
    tost_independent,
)

from ._exceptions import MeasurementReadError, StabilityTimeoutError
from ._timing import (
    CancellationEvent,
    _raise_if_cancelled,
    _sleep_until,
    _validate_cancel_event,
)


Number: TypeAlias = int | float
StabilityMethod: TypeAlias = Literal["range", "target", "statistical"]


@dataclass(frozen=True, slots=True)
class RangeStabilityDiagnostics:
    """Diagnostics for a peak-to-peak stability decision."""

    peak_to_peak: float
    tolerance: float


@dataclass(frozen=True, slots=True)
class TargetStabilityDiagnostics:
    """Diagnostics for a known-target stability decision."""

    target: float
    maximum_error: float
    tolerance: float


@dataclass(frozen=True, slots=True)
class StatisticalStabilityDiagnostics:
    """Diagnostics for the MK, Theil-Sen, and TOST decision."""

    mann_kendall: MannKendallResult
    theil_sen: TheilSenResult
    tost: TOSTResult
    drift_tolerance: float
    equivalence_tolerance: float


StabilityDiagnostics: TypeAlias = (
    RangeStabilityDiagnostics
    | TargetStabilityDiagnostics
    | StatisticalStabilityDiagnostics
)


@dataclass(frozen=True, slots=True)
class StabilitySample:
    """State reported after one raw measurement."""

    value: float
    elapsed: float
    sample: int


@dataclass(frozen=True, slots=True)
class StabilityCheck:
    """State reported after one complete stability evaluation."""

    method: StabilityMethod
    stable_now: bool
    value: float
    elapsed: float
    samples: int
    window_size: int
    window_outlier_count: int
    consecutive_successes: int
    required_confirmations: int
    filtered_window: tuple[float, ...]
    diagnostics: StabilityDiagnostics


@dataclass(frozen=True, slots=True)
class StabilityResult:
    """Result returned when a measurement is declared stable."""

    method: StabilityMethod
    value: float
    elapsed: float
    samples: int
    window_size: int
    window_outlier_count: int
    consecutive_successes: int
    filtered_window: tuple[float, ...]
    last_check: StabilityCheck


class _Evaluator(Protocol):
    """Internal interface shared by stability decision strategies."""

    def __call__(
        self,
        values: np.ndarray,
    ) -> tuple[bool, float, StabilityDiagnostics]:
        """Return decision, representative value, and diagnostics."""


def _as_finite_float(value: float, *, name: str) -> float:
    """Validate a finite real scalar."""

    if isinstance(value, bool):
        raise TypeError(f"{name} must be a real scalar, not bool")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{name} must be a real scalar") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _as_positive_float(value: float, *, name: str) -> float:
    """Validate a finite positive scalar."""

    result = _as_finite_float(value, name=name)
    if result <= 0.0:
        raise ValueError(f"{name} must be > 0")
    return result


def _as_nonnegative_float(value: float, *, name: str) -> float:
    """Validate a finite nonnegative scalar."""

    result = _as_finite_float(value, name=name)
    if result < 0.0:
        raise ValueError(f"{name} must be >= 0")
    return result


def _as_positive_int(value: int, *, name: str, minimum: int = 1) -> int:
    """Validate a non-boolean integer with a configurable minimum."""

    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _validate_callback(callback: object, *, name: str) -> None:
    """Validate an optional callback."""

    if callback is not None and not callable(callback):
        raise TypeError(f"{name} must be callable or None")


def _wait_stable_core(
    getter: Callable[[], Number],
    evaluator: _Evaluator,
    *,
    method: StabilityMethod,
    required_samples: int,
    reported_window_size: int,
    sample_interval: float,
    timeout: float,
    min_wait: float,
    confirmations: int,
    check_every: int | None,
    cancel_event: CancellationEvent | None,
    cancel_check_interval: float,
    hampel_window: int | None,
    hampel_threshold: float,
    hampel_absolute_tolerance: float,
    on_sample: Callable[[StabilitySample], None] | None,
    on_check: Callable[[StabilityCheck], None] | None,
) -> StabilityResult:
    """Collect scalar measurements and apply one stability strategy."""

    if not callable(getter):
        raise TypeError("getter must be callable")
    _validate_callback(on_sample, name="on_sample")
    _validate_callback(on_check, name="on_check")
    _validate_cancel_event(cancel_event)

    interval_value = _as_positive_float(
        sample_interval,
        name="sample_interval",
    )
    timeout_value = _as_positive_float(timeout, name="timeout")
    min_wait_value = _as_nonnegative_float(min_wait, name="min_wait")
    cancel_interval = _as_positive_float(
        cancel_check_interval,
        name="cancel_check_interval",
    )
    confirmation_count = _as_positive_int(
        confirmations,
        name="confirmations",
    )
    if min_wait_value >= timeout_value:
        raise ValueError("min_wait must be smaller than timeout")

    if check_every is None:
        check_step = max(1, reported_window_size // 2)
    else:
        check_step = _as_positive_int(check_every, name="check_every")

    threshold_value = _as_positive_float(
        hampel_threshold,
        name="hampel_threshold",
    )
    absolute_tolerance = _as_nonnegative_float(
        hampel_absolute_tolerance,
        name="hampel_absolute_tolerance",
    )
    if hampel_window is not None:
        if (
            isinstance(hampel_window, bool)
            or not isinstance(hampel_window, int)
            or hampel_window < 3
            or hampel_window % 2 == 0
        ):
            raise ValueError("hampel_window must be None or an odd integer >= 3")

    values: deque[float] = deque(maxlen=required_samples)
    start = time.monotonic()
    deadline = start + timeout_value
    samples = 0
    checks = 0
    samples_since_check = 0
    consecutive_successes = 0
    last_check: StabilityCheck | None = None

    _sleep_until(
        start + min_wait_value,
        cancel_event=cancel_event,
        check_interval=cancel_interval,
        operation=method + " stability wait",
        start=start,
    )

    while True:
        _raise_if_cancelled(
            cancel_event,
            operation=method + " stability wait",
            start=start,
        )
        now = time.monotonic()
        if now >= deadline:
            raise StabilityTimeoutError(
                timeout=timeout_value,
                elapsed=now - start,
                samples=samples,
                last_check=last_check,
            )

        next_sample_number = samples + 1
        try:
            raw_value = getter()
            value = float(raw_value)
            if not math.isfinite(value):
                raise ValueError(
                    f"getter returned a non-finite value: {value!r}"
                )
        except Exception as exc:
            raise MeasurementReadError(
                elapsed=time.monotonic() - start,
                sample=next_sample_number,
            ) from exc

        samples = next_sample_number
        samples_since_check += 1
        values.append(value)

        sample_status = StabilitySample(
            value=value,
            elapsed=time.monotonic() - start,
            sample=samples,
        )
        if on_sample is not None:
            on_sample(sample_status)

        _raise_if_cancelled(
            cancel_event,
            operation=method + " stability wait",
            start=start,
        )
        elapsed_after_sample = time.monotonic() - start
        if elapsed_after_sample >= timeout_value:
            raise StabilityTimeoutError(
                timeout=timeout_value,
                elapsed=elapsed_after_sample,
                samples=samples,
                last_check=last_check,
            )

        buffer_is_full = len(values) == required_samples
        check_is_due = checks == 0 or samples_since_check >= check_step

        if buffer_is_full and check_is_due:
            raw_window = np.asarray(values, dtype=float)
            if hampel_window is None:
                filtered_window = raw_window.copy()
                outlier_count = 0
            else:
                hampel_result = hampel_filter(
                    raw_window,
                    window_size=hampel_window,
                    threshold=threshold_value,
                    absolute_tolerance=absolute_tolerance,
                    replacement="median",
                )
                filtered_window = hampel_result.filtered
                outlier_count = hampel_result.outlier_count

            stable_now, representative_value, diagnostics = evaluator(
                filtered_window
            )
            consecutive_successes = (
                consecutive_successes + 1 if stable_now else 0
            )
            checks += 1
            samples_since_check = 0

            last_check = StabilityCheck(
                method=method,
                stable_now=stable_now,
                value=representative_value,
                elapsed=time.monotonic() - start,
                samples=samples,
                window_size=reported_window_size,
                window_outlier_count=outlier_count,
                consecutive_successes=consecutive_successes,
                required_confirmations=confirmation_count,
                filtered_window=tuple(float(item) for item in filtered_window),
                diagnostics=diagnostics,
            )
            if on_check is not None:
                on_check(last_check)

            _raise_if_cancelled(
                cancel_event,
                operation=method + " stability wait",
                start=start,
            )
            elapsed_after_check = time.monotonic() - start
            if elapsed_after_check >= timeout_value:
                raise StabilityTimeoutError(
                    timeout=timeout_value,
                    elapsed=elapsed_after_check,
                    samples=samples,
                    last_check=last_check,
                )

            if consecutive_successes >= confirmation_count:
                return StabilityResult(
                    method=method,
                    value=representative_value,
                    elapsed=elapsed_after_check,
                    samples=samples,
                    window_size=reported_window_size,
                    window_outlier_count=outlier_count,
                    consecutive_successes=consecutive_successes,
                    filtered_window=last_check.filtered_window,
                    last_check=last_check,
                )

        next_sample = min(time.monotonic() + interval_value, deadline)
        _sleep_until(
            next_sample,
            cancel_event=cancel_event,
            check_interval=cancel_interval,
            operation=method + " stability wait",
            start=start,
        )


def wait_stable_range(
    getter: Callable[[], Number],
    *,
    tolerance: float,
    window_size: int = 10,
    sample_interval: float = 0.5,
    timeout: float = 120.0,
    min_wait: float = 0.0,
    confirmations: int = 2,
    check_every: int | None = None,
    cancel_event: CancellationEvent | None = None,
    cancel_check_interval: float = 0.1,
    hampel_window: int | None = 7,
    hampel_threshold: float = 3.5,
    hampel_absolute_tolerance: float = 0.0,
    on_sample: Callable[[StabilitySample], None] | None = None,
    on_check: Callable[[StabilityCheck], None] | None = None,
) -> StabilityResult:
    """Wait until the peak-to-peak range of recent values is small enough.

    This method is simple and fast.  It is suitable for low-noise data when a
    physical range tolerance can be specified, but it does not separately test
    for a statistically significant slow trend.
    """

    tolerance_value = _as_positive_float(tolerance, name="tolerance")
    size = _as_positive_int(window_size, name="window_size", minimum=3)

    def evaluate(
        values: np.ndarray,
    ) -> tuple[bool, float, RangeStabilityDiagnostics]:
        peak_to_peak = float(np.ptp(values))
        diagnostics = RangeStabilityDiagnostics(
            peak_to_peak=peak_to_peak,
            tolerance=tolerance_value,
        )
        return (
            peak_to_peak <= tolerance_value,
            float(np.mean(values)),
            diagnostics,
        )

    return _wait_stable_core(
        getter,
        evaluate,
        method="range",
        required_samples=size,
        reported_window_size=size,
        sample_interval=sample_interval,
        timeout=timeout,
        min_wait=min_wait,
        confirmations=confirmations,
        check_every=check_every,
        cancel_event=cancel_event,
        cancel_check_interval=cancel_check_interval,
        hampel_window=hampel_window,
        hampel_threshold=hampel_threshold,
        hampel_absolute_tolerance=hampel_absolute_tolerance,
        on_sample=on_sample,
        on_check=on_check,
    )


def wait_stable_target(
    getter: Callable[[], Number],
    *,
    target: float,
    tolerance: float,
    window_size: int = 5,
    sample_interval: float = 0.5,
    timeout: float = 120.0,
    min_wait: float = 0.0,
    confirmations: int = 2,
    check_every: int | None = None,
    cancel_event: CancellationEvent | None = None,
    cancel_check_interval: float = 0.1,
    hampel_window: int | None = 7,
    hampel_threshold: float = 3.5,
    hampel_absolute_tolerance: float = 0.0,
    on_sample: Callable[[StabilitySample], None] | None = None,
    on_check: Callable[[StabilityCheck], None] | None = None,
) -> StabilityResult:
    """Wait until every recent value lies inside a known target band.

    This is appropriate for controlled quantities such as temperature, field,
    voltage, or position when the desired final value is known.
    """

    target_value = _as_finite_float(target, name="target")
    tolerance_value = _as_positive_float(tolerance, name="tolerance")
    size = _as_positive_int(window_size, name="window_size", minimum=3)

    def evaluate(
        values: np.ndarray,
    ) -> tuple[bool, float, TargetStabilityDiagnostics]:
        maximum_error = float(np.max(np.abs(values - target_value)))
        diagnostics = TargetStabilityDiagnostics(
            target=target_value,
            maximum_error=maximum_error,
            tolerance=tolerance_value,
        )
        return (
            maximum_error <= tolerance_value,
            float(np.mean(values)),
            diagnostics,
        )

    return _wait_stable_core(
        getter,
        evaluate,
        method="target",
        required_samples=size,
        reported_window_size=size,
        sample_interval=sample_interval,
        timeout=timeout,
        min_wait=min_wait,
        confirmations=confirmations,
        check_every=check_every,
        cancel_event=cancel_event,
        cancel_check_interval=cancel_check_interval,
        hampel_window=hampel_window,
        hampel_threshold=hampel_threshold,
        hampel_absolute_tolerance=hampel_absolute_tolerance,
        on_sample=on_sample,
        on_check=on_check,
    )


def wait_stable(
    getter: Callable[[], Number],
    *,
    equivalence_tolerance: float,
    drift_tolerance: float | None = None,
    window_size: int = 10,
    alpha: float = 0.05,
    sample_interval: float = 0.5,
    timeout: float = 120.0,
    min_wait: float = 0.0,
    confirmations: int = 2,
    check_every: int | None = None,
    cancel_event: CancellationEvent | None = None,
    cancel_check_interval: float = 0.1,
    hampel_window: int | None = 7,
    hampel_threshold: float = 3.5,
    hampel_absolute_tolerance: float = 0.0,
    on_sample: Callable[[StabilitySample], None] | None = None,
    on_check: Callable[[StabilityCheck], None] | None = None,
) -> StabilityResult:
    """Wait for an unknown final value using statistical stability criteria.

    Two adjacent windows are analyzed.  Stability requires all of the
    following:

    1. Mann-Kendall detects no significant monotonic trend.
    2. The absolute Theil-Sen change across both windows is no larger than
       ``drift_tolerance``.
    3. Welch TOST establishes that the two window means differ by less than
       ``equivalence_tolerance``.

    Optional Hampel filtering replaces isolated spikes only for the stability
    calculation; raw measurements remain available through ``on_sample``.
    Adjacent measurements should be approximately independent for the MK and
    TOST p-values to be calibrated correctly.
    """

    equivalence_value = _as_positive_float(
        equivalence_tolerance,
        name="equivalence_tolerance",
    )
    drift_value = (
        equivalence_value
        if drift_tolerance is None
        else _as_positive_float(drift_tolerance, name="drift_tolerance")
    )
    size = _as_positive_int(window_size, name="window_size", minimum=2)
    alpha_value = _as_finite_float(alpha, name="alpha")
    if not 0.0 < alpha_value < 0.5:
        raise ValueError("alpha must be between 0 and 0.5")

    required_samples = 2 * size

    def evaluate(
        values: np.ndarray,
    ) -> tuple[bool, float, StatisticalStabilityDiagnostics]:
        old_window = values[:size]
        new_window = values[size:]
        mk_result = mann_kendall_test(values, alpha=alpha_value)
        sen_result = theil_sen_test(
            values,
            confidence=1.0 - alpha_value,
        )
        tost_result = tost_independent(
            old_window,
            new_window,
            low=-equivalence_value,
            high=equivalence_value,
            alpha=alpha_value,
        )

        diagnostics = StatisticalStabilityDiagnostics(
            mann_kendall=mk_result,
            theil_sen=sen_result,
            tost=tost_result,
            drift_tolerance=drift_value,
            equivalence_tolerance=equivalence_value,
        )
        stable_now = (
            not mk_result.has_trend
            and abs(sen_result.estimated_change) <= drift_value
            and tost_result.equivalent
        )
        return stable_now, float(np.mean(new_window)), diagnostics

    return _wait_stable_core(
        getter,
        evaluate,
        method="statistical",
        required_samples=required_samples,
        reported_window_size=size,
        sample_interval=sample_interval,
        timeout=timeout,
        min_wait=min_wait,
        confirmations=confirmations,
        check_every=check_every,
        cancel_event=cancel_event,
        cancel_check_interval=cancel_check_interval,
        hampel_window=hampel_window,
        hampel_threshold=hampel_threshold,
        hampel_absolute_tolerance=hampel_absolute_tolerance,
        on_sample=on_sample,
        on_check=on_check,
    )