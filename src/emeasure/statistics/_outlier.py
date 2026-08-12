"""Robust MAD-based outlier detection for experimental data."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import math
from typing import Literal, TypeAlias

import numpy as np


Number: TypeAlias = int | float
Replacement: TypeAlias = Literal["median", "nan", "drop", "none"]

# Converts the MAD of normally distributed data to a standard-deviation scale.
NORMAL_MAD_SCALE = 1.482602218505602


@dataclass(frozen=True, slots=True)
class MADPointResult:
    """MAD decision for one new value relative to a reference window."""

    is_outlier: bool
    value: float
    median: float
    mad: float
    robust_std: float
    deviation: float
    cutoff: float
    threshold: float
    absolute_tolerance: float
    reference_samples: int


@dataclass(frozen=True, slots=True)
class HampelResult:
    """Result of a sliding Hampel spike detector and filter."""

    original: np.ndarray
    filtered: np.ndarray
    outlier_mask: np.ndarray
    local_median: np.ndarray
    local_mad: np.ndarray
    local_robust_std: np.ndarray
    local_cutoff: np.ndarray
    window_size: int
    threshold: float
    absolute_tolerance: float
    replacement: Replacement

    @property
    def outlier_indices(self) -> np.ndarray:
        """Indices flagged as isolated spikes."""

        return np.flatnonzero(self.outlier_mask)

    @property
    def outlier_count(self) -> int:
        """Number of values flagged as spikes."""

        return int(np.count_nonzero(self.outlier_mask))


def _as_1d_finite_array(
    values: Iterable[Number] | np.ndarray,
    *,
    name: str,
    minimum_size: int,
) -> np.ndarray:
    """Convert input to a one-dimensional finite float array."""

    if isinstance(values, (str, bytes)):
        raise TypeError(f"{name} must be a numeric sequence, not text")

    try:
        if isinstance(values, np.ndarray):
            array = np.asarray(values, dtype=float)
        else:
            array = np.asarray(tuple(values), dtype=float)
    except TypeError as exc:
        raise TypeError(f"{name} must be an iterable of real scalars") from exc
    except ValueError as exc:
        raise ValueError(f"{name} must contain only real scalars") from exc

    if array.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    if array.size < minimum_size:
        raise ValueError(
            f"{name} must contain at least {minimum_size} values; "
            f"got {array.size}"
        )
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must contain only finite values")

    return array


def _validate_detection_parameters(
    *,
    threshold: float,
    absolute_tolerance: float,
) -> tuple[float, float]:
    """Validate common MAD detector parameters."""

    try:
        threshold_value = float(threshold)
        tolerance_value = float(absolute_tolerance)
    except (TypeError, ValueError) as exc:
        raise TypeError(
            "threshold and absolute_tolerance must be real scalars"
        ) from exc

    if not math.isfinite(threshold_value) or threshold_value <= 0.0:
        raise ValueError("threshold must be finite and > 0")
    if not math.isfinite(tolerance_value) or tolerance_value < 0.0:
        raise ValueError("absolute_tolerance must be finite and >= 0")

    return threshold_value, tolerance_value


def median_absolute_deviation(
    values: Iterable[Number] | np.ndarray,
) -> float:
    """Return the unscaled median absolute deviation of a sequence."""

    data = _as_1d_finite_array(
        values,
        name="values",
        minimum_size=1,
    )
    center = float(np.median(data))
    return float(np.median(np.abs(data - center)))


def robust_standard_deviation(
    values: Iterable[Number] | np.ndarray,
) -> float:
    """Estimate standard deviation as ``1.4826 * MAD``."""

    return NORMAL_MAD_SCALE * median_absolute_deviation(values)


def mad_outlier_test(
    value: Number,
    reference: Iterable[Number] | np.ndarray,
    *,
    threshold: float = 3.5,
    absolute_tolerance: float = 0.0,
) -> MADPointResult:
    """Test one new measurement against a robust reference window.

    A value is flagged when its distance from the reference median exceeds
    both the robust statistical threshold and ``absolute_tolerance``::

        abs(value - median) > max(
            threshold * 1.4826 * MAD,
            absolute_tolerance,
        )

    The absolute tolerance is particularly useful for quantized or nearly
    constant instrument readings where MAD may be zero.
    """

    data = _as_1d_finite_array(
        reference,
        name="reference",
        minimum_size=3,
    )
    threshold_value, tolerance_value = _validate_detection_parameters(
        threshold=threshold,
        absolute_tolerance=absolute_tolerance,
    )

    try:
        measured_value = float(value)
    except (TypeError, ValueError) as exc:
        raise TypeError("value must be a real scalar") from exc
    if not math.isfinite(measured_value):
        raise ValueError("value must be finite")

    center = float(np.median(data))
    mad = float(np.median(np.abs(data - center)))
    robust_std = NORMAL_MAD_SCALE * mad
    deviation = abs(measured_value - center)
    cutoff = max(threshold_value * robust_std, tolerance_value)

    return MADPointResult(
        is_outlier=deviation > cutoff,
        value=measured_value,
        median=center,
        mad=mad,
        robust_std=robust_std,
        deviation=deviation,
        cutoff=cutoff,
        threshold=threshold_value,
        absolute_tolerance=tolerance_value,
        reference_samples=int(data.size),
    )


def hampel_filter(
    values: Iterable[Number] | np.ndarray,
    *,
    window_size: int = 11,
    threshold: float = 3.5,
    absolute_tolerance: float = 0.0,
    replacement: Replacement = "median",
) -> HampelResult:
    """Detect and optionally replace isolated spikes in a sequence.

    Each value is compared with the median and MAD of a centered local window.
    The original data and outlier mask are always returned.  The default
    filtered output replaces spikes with the corresponding local median.

    Parameters
    ----------
    values:
        One-dimensional finite measurement sequence.
    window_size:
        Odd local window size.  Values between 7 and 21 are typical.
    threshold:
        Robust standard-deviation multiplier.  The default is 3.5.
    absolute_tolerance:
        Minimum absolute deviation required before a point can be flagged.
    replacement:
        ``"median"`` replaces spikes with local medians; ``"nan"`` marks
        them with NaN; ``"drop"`` removes them from the filtered output; and
        ``"none"`` performs detection without modifying output values.

    Notes
    -----
    Several consecutive flagged values may indicate a real state change rather
    than isolated spikes.  The caller should retain the returned mask and make
    that decision at the workflow level.
    """

    data = _as_1d_finite_array(
        values,
        name="values",
        minimum_size=3,
    )
    threshold_value, tolerance_value = _validate_detection_parameters(
        threshold=threshold,
        absolute_tolerance=absolute_tolerance,
    )

    if (
        isinstance(window_size, bool)
        or not isinstance(window_size, int)
        or window_size < 3
        or window_size % 2 == 0
    ):
        raise ValueError("window_size must be an odd integer >= 3")
    if replacement not in {"median", "nan", "drop", "none"}:
        raise ValueError(
            "replacement must be 'median', 'nan', 'drop', or 'none'"
        )

    n = int(data.size)
    effective_window = min(window_size, n)
    if effective_window % 2 == 0:
        effective_window -= 1
    half_window = effective_window // 2

    local_median = np.empty(n, dtype=float)
    local_mad = np.empty(n, dtype=float)
    local_robust_std = np.empty(n, dtype=float)
    local_cutoff = np.empty(n, dtype=float)
    outlier_mask = np.zeros(n, dtype=bool)

    for index in range(n):
        start = min(
            max(0, index - half_window),
            n - effective_window,
        )
        stop = start + effective_window
        window = data[start:stop]

        center = float(np.median(window))
        mad = float(np.median(np.abs(window - center)))
        robust_std = NORMAL_MAD_SCALE * mad
        cutoff = max(threshold_value * robust_std, tolerance_value)

        local_median[index] = center
        local_mad[index] = mad
        local_robust_std[index] = robust_std
        local_cutoff[index] = cutoff
        outlier_mask[index] = abs(data[index] - center) > cutoff

    if replacement == "median":
        filtered = data.copy()
        filtered[outlier_mask] = local_median[outlier_mask]
    elif replacement == "nan":
        filtered = data.copy()
        filtered[outlier_mask] = np.nan
    elif replacement == "drop":
        filtered = data[~outlier_mask].copy()
    else:
        filtered = data.copy()

    return HampelResult(
        original=data.copy(),
        filtered=filtered,
        outlier_mask=outlier_mask,
        local_median=local_median,
        local_mad=local_mad,
        local_robust_std=local_robust_std,
        local_cutoff=local_cutoff,
        window_size=effective_window,
        threshold=threshold_value,
        absolute_tolerance=tolerance_value,
        replacement=replacement,
    )
