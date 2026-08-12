"""Non-parametric trend algorithms for experimental data."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import math
from typing import Literal, TypeAlias

import numpy as np
from scipy.stats import norm, theilslopes


Number: TypeAlias = int | float
Trend: TypeAlias = Literal["increasing", "decreasing", "none"]
Alternative: TypeAlias = Literal["two-sided", "increasing", "decreasing"]
InterceptMethod: TypeAlias = Literal["separate", "joint"]


@dataclass(frozen=True, slots=True)
class MannKendallResult:
    """Result of a Mann-Kendall monotonic trend test."""

    has_trend: bool
    trend: Trend
    p_value: float
    z: float
    tau: float
    s: int
    variance_s: float
    alpha: float
    alternative: Alternative
    samples: int


@dataclass(frozen=True, slots=True)
class TheilSenResult:
    """Result of a Theil-Sen robust slope estimate and trend decision."""

    has_trend: bool
    trend: Trend
    slope: float
    intercept: float
    slope_low: float
    slope_high: float
    confidence: float
    method: InterceptMethod
    samples: int
    x_span: float

    @property
    def estimated_change(self) -> float:
        """Estimated change across the full x span."""

        return self.slope * self.x_span

    @property
    def change_low(self) -> float:
        """Lower slope confidence bound expressed over the full x span."""

        return self.slope_low * self.x_span

    @property
    def change_high(self) -> float:
        """Upper slope confidence bound expressed over the full x span."""

        return self.slope_high * self.x_span


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


def _validate_probability(value: float, *, name: str) -> float:
    """Validate an open-interval probability parameter."""

    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{name} must be a real scalar") from exc

    if not math.isfinite(result) or not 0.0 < result < 1.0:
        raise ValueError(f"{name} must be finite and between 0 and 1")
    return result


def mann_kendall_test(
    values: Iterable[Number] | np.ndarray,
    *,
    alpha: float = 0.05,
    alternative: Alternative = "two-sided",
) -> MannKendallResult:
    """Test a sequence for a significant monotonic trend.

    The null hypothesis is that the ordered observations have no monotonic
    trend.  The statistic uses the standard Mann-Kendall continuity correction
    and corrects ``Var(S)`` for repeated measurement values.

    Parameters
    ----------
    values:
        Ordered one-dimensional observations.  At least three finite values
        are required.
    alpha:
        Significance level used to decide whether a trend exists.
    alternative:
        ``"two-sided"`` detects either direction.  ``"increasing"`` and
        ``"decreasing"`` perform one-sided tests.

    Returns
    -------
    MannKendallResult
        Test decision, direction, p-value, normalized statistic, Kendall tau,
        raw S statistic, and tie-corrected variance.

    Notes
    -----
    A non-significant result means that no monotonic trend was detected.  It
    does not by itself prove that the sequence is stable.

    The standard variance assumes independent observations.  Strong serial
    correlation, for example from densely sampled low-pass filtered data, can
    make the reported p-value too optimistic.
    """

    y = _as_1d_finite_array(
        values,
        name="values",
        minimum_size=3,
    )
    alpha_value = _validate_probability(alpha, name="alpha")
    if alternative not in {"two-sided", "increasing", "decreasing"}:
        raise ValueError(
            "alternative must be 'two-sided', 'increasing', or 'decreasing'"
        )

    n = int(y.size)
    s = int(
        sum(
            np.sign(y[index + 1 :] - y[index]).sum(dtype=np.int64)
            for index in range(n - 1)
        )
    )

    _, tie_counts = np.unique(y, return_counts=True)
    tie_term = sum(
        int(count) * (int(count) - 1) * (2 * int(count) + 5)
        for count in tie_counts
        if count > 1
    )
    variance_s = (
        n * (n - 1) * (2 * n + 5) - tie_term
    ) / 18.0

    if variance_s <= 0.0:
        z = 0.0
    elif s > 0:
        z = (s - 1.0) / math.sqrt(variance_s)
    elif s < 0:
        z = (s + 1.0) / math.sqrt(variance_s)
    else:
        z = 0.0

    if variance_s <= 0.0:
        p_value = 1.0
    elif alternative == "two-sided":
        p_value = float(2.0 * norm.sf(abs(z)))
    elif alternative == "increasing":
        p_value = float(norm.sf(z))
    else:
        p_value = float(norm.cdf(z))

    total_pairs = n * (n - 1) / 2.0
    tied_pairs = sum(
        int(count) * (int(count) - 1) / 2.0
        for count in tie_counts
        if count > 1
    )
    tau_denominator = math.sqrt(total_pairs * (total_pairs - tied_pairs))
    tau = float(s / tau_denominator) if tau_denominator > 0.0 else 0.0

    has_trend = p_value < alpha_value
    if not has_trend:
        trend: Trend = "none"
    elif alternative == "increasing":
        trend = "increasing"
    elif alternative == "decreasing":
        trend = "decreasing"
    elif s > 0:
        trend = "increasing"
    else:
        trend = "decreasing"

    return MannKendallResult(
        has_trend=has_trend,
        trend=trend,
        p_value=p_value,
        z=z,
        tau=tau,
        s=s,
        variance_s=variance_s,
        alpha=alpha_value,
        alternative=alternative,
        samples=n,
    )


def theil_sen_test(
    values: Iterable[Number] | np.ndarray,
    x: Iterable[Number] | np.ndarray | None = None,
    *,
    confidence: float = 0.95,
    method: InterceptMethod = "separate",
) -> TheilSenResult:
    """Estimate a robust linear trend using the Theil-Sen method.

    The slope is the median of all pairwise slopes.  A significant increasing
    or decreasing trend is reported only when the slope confidence interval
    lies entirely above or below zero, respectively.

    Parameters
    ----------
    values:
        One-dimensional dependent values.  At least three finite values are
        required.
    x:
        Optional independent values.  Sample indices are used when omitted.
    confidence:
        Confidence level of the slope interval, normally 0.95.
    method:
        SciPy intercept method: ``"separate"`` or ``"joint"``.

    Returns
    -------
    TheilSenResult
        Robust slope, intercept, slope confidence bounds, trend decision, and
        change estimates across the full x span.
    """

    y = _as_1d_finite_array(
        values,
        name="values",
        minimum_size=3,
    )
    confidence_value = _validate_probability(
        confidence,
        name="confidence",
    )
    if method not in {"separate", "joint"}:
        raise ValueError("method must be 'separate' or 'joint'")

    if x is None:
        x_array = np.arange(y.size, dtype=float)
    else:
        x_array = _as_1d_finite_array(
            x,
            name="x",
            minimum_size=3,
        )
        if x_array.size != y.size:
            raise ValueError(
                "x and values must have the same number of elements"
            )

    if np.unique(x_array).size < 2:
        raise ValueError("x must contain at least two distinct values")

    estimate = theilslopes(
        y,
        x_array,
        alpha=confidence_value,
        method=method,
    )
    slope = float(estimate.slope)
    intercept = float(estimate.intercept)
    slope_low = float(estimate.low_slope)
    slope_high = float(estimate.high_slope)

    if slope_low > 0.0:
        has_trend = True
        trend: Trend = "increasing"
    elif slope_high < 0.0:
        has_trend = True
        trend = "decreasing"
    else:
        has_trend = False
        trend = "none"

    return TheilSenResult(
        has_trend=has_trend,
        trend=trend,
        slope=slope,
        intercept=intercept,
        slope_low=slope_low,
        slope_high=slope_high,
        confidence=confidence_value,
        method=method,
        samples=int(y.size),
        x_span=float(np.max(x_array) - np.min(x_array)),
    )
