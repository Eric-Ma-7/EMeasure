"""Two one-sided tests for statistical equivalence."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import math
from typing import Literal, TypeAlias

import numpy as np
from scipy.stats import t as student_t


Number: TypeAlias = int | float
TOSTMethod: TypeAlias = Literal[
    "independent-welch",
    "independent-pooled",
    "paired",
]


@dataclass(frozen=True, slots=True)
class TOSTResult:
    """Result of a two one-sided tests equivalence procedure."""

    equivalent: bool
    method: TOSTMethod
    mean_a: float
    mean_b: float
    mean_difference: float
    equivalence_low: float
    equivalence_high: float
    standard_error: float
    degrees_of_freedom: float
    t_lower: float
    p_lower: float
    t_upper: float
    p_upper: float
    p_value: float
    alpha: float
    confidence_level: float
    confidence_low: float
    confidence_high: float
    samples_a: int
    samples_b: int


def _as_sample(
    values: Iterable[Number] | np.ndarray,
    *,
    name: str,
) -> np.ndarray:
    """Convert input to a one-dimensional finite sample."""

    if isinstance(values, (str, bytes)):
        raise TypeError(f"{name} must be a numeric sequence, not text")

    try:
        if isinstance(values, np.ndarray):
            sample = np.asarray(values, dtype=float)
        else:
            sample = np.asarray(tuple(values), dtype=float)
    except TypeError as exc:
        raise TypeError(f"{name} must be an iterable of real scalars") from exc
    except ValueError as exc:
        raise ValueError(f"{name} must contain only real scalars") from exc

    if sample.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    if sample.size < 2:
        raise ValueError(f"{name} must contain at least two values")
    if not np.all(np.isfinite(sample)):
        raise ValueError(f"{name} must contain only finite values")

    return sample


def _validate_test_parameters(
    *,
    low: float,
    high: float,
    alpha: float,
) -> tuple[float, float, float]:
    """Validate equivalence bounds and significance level."""

    try:
        low_value = float(low)
        high_value = float(high)
        alpha_value = float(alpha)
    except (TypeError, ValueError) as exc:
        raise TypeError("low, high, and alpha must be real scalars") from exc

    if not math.isfinite(low_value) or not math.isfinite(high_value):
        raise ValueError("low and high must be finite")
    if low_value >= high_value:
        raise ValueError("low must be smaller than high")
    if not math.isfinite(alpha_value) or not 0.0 < alpha_value < 0.5:
        raise ValueError("alpha must be finite and between 0 and 0.5")

    return low_value, high_value, alpha_value


def _zero_scale_statistic(numerator: float) -> float:
    """Return the limiting test statistic for a zero standard error."""

    if numerator > 0.0:
        return math.inf
    if numerator < 0.0:
        return -math.inf
    return 0.0


def _finish_tost(
    *,
    method: TOSTMethod,
    mean_a: float,
    mean_b: float,
    standard_error: float,
    degrees_of_freedom: float,
    low: float,
    high: float,
    alpha: float,
    samples_a: int,
    samples_b: int,
) -> TOSTResult:
    """Calculate both one-sided tests and the equivalence confidence interval."""

    difference = mean_b - mean_a

    if standard_error == 0.0:
        t_lower = _zero_scale_statistic(difference - low)
        t_upper = _zero_scale_statistic(difference - high)

        if difference > low:
            p_lower = 0.0
        elif difference == low:
            p_lower = 0.5
        else:
            p_lower = 1.0

        if difference < high:
            p_upper = 0.0
        elif difference == high:
            p_upper = 0.5
        else:
            p_upper = 1.0

        confidence_low = difference
        confidence_high = difference
    else:
        t_lower = (difference - low) / standard_error
        t_upper = (difference - high) / standard_error
        p_lower = float(student_t.sf(t_lower, degrees_of_freedom))
        p_upper = float(student_t.cdf(t_upper, degrees_of_freedom))

        critical = float(
            student_t.ppf(1.0 - alpha, degrees_of_freedom)
        )
        confidence_low = difference - critical * standard_error
        confidence_high = difference + critical * standard_error

    p_value = max(p_lower, p_upper)

    return TOSTResult(
        equivalent=p_value < alpha,
        method=method,
        mean_a=mean_a,
        mean_b=mean_b,
        mean_difference=difference,
        equivalence_low=low,
        equivalence_high=high,
        standard_error=standard_error,
        degrees_of_freedom=degrees_of_freedom,
        t_lower=t_lower,
        p_lower=p_lower,
        t_upper=t_upper,
        p_upper=p_upper,
        p_value=p_value,
        alpha=alpha,
        confidence_level=1.0 - 2.0 * alpha,
        confidence_low=confidence_low,
        confidence_high=confidence_high,
        samples_a=samples_a,
        samples_b=samples_b,
    )


def tost_independent(
    sample_a: Iterable[Number] | np.ndarray,
    sample_b: Iterable[Number] | np.ndarray,
    *,
    low: float,
    high: float,
    alpha: float = 0.05,
    equal_var: bool = False,
) -> TOSTResult:
    """Test equivalence of two independent sample means.

    The tested difference is ``mean(sample_b) - mean(sample_a)``.  Equivalence
    is accepted only when both one-sided null hypotheses are rejected:

    ``H01: difference <= low`` and ``H02: difference >= high``.

    Welch's unequal-variance standard error is used by default.  Set
    ``equal_var=True`` only when a common population variance is justified.

    A 90% confidence interval is reported when ``alpha=0.05``.  Equivalence is
    mathematically identical to this interval lying strictly inside
    ``(low, high)``.
    """

    a = _as_sample(sample_a, name="sample_a")
    b = _as_sample(sample_b, name="sample_b")
    low_value, high_value, alpha_value = _validate_test_parameters(
        low=low,
        high=high,
        alpha=alpha,
    )
    if not isinstance(equal_var, bool):
        raise TypeError("equal_var must be a bool")

    n_a = int(a.size)
    n_b = int(b.size)
    mean_a = float(np.mean(a))
    mean_b = float(np.mean(b))
    variance_a = float(np.var(a, ddof=1))
    variance_b = float(np.var(b, ddof=1))

    if equal_var:
        degrees_of_freedom = float(n_a + n_b - 2)
        pooled_variance = (
            (n_a - 1) * variance_a + (n_b - 1) * variance_b
        ) / degrees_of_freedom
        standard_error = math.sqrt(
            pooled_variance * (1.0 / n_a + 1.0 / n_b)
        )
        method: TOSTMethod = "independent-pooled"
    else:
        variance_term_a = variance_a / n_a
        variance_term_b = variance_b / n_b
        variance_sum = variance_term_a + variance_term_b
        standard_error = math.sqrt(variance_sum)
        denominator = (
            variance_term_a**2 / (n_a - 1)
            + variance_term_b**2 / (n_b - 1)
        )
        degrees_of_freedom = (
            variance_sum**2 / denominator
            if denominator > 0.0
            else math.inf
        )
        method = "independent-welch"

    return _finish_tost(
        method=method,
        mean_a=mean_a,
        mean_b=mean_b,
        standard_error=standard_error,
        degrees_of_freedom=degrees_of_freedom,
        low=low_value,
        high=high_value,
        alpha=alpha_value,
        samples_a=n_a,
        samples_b=n_b,
    )


def tost_paired(
    sample_a: Iterable[Number] | np.ndarray,
    sample_b: Iterable[Number] | np.ndarray,
    *,
    low: float,
    high: float,
    alpha: float = 0.05,
) -> TOSTResult:
    """Test equivalence of two paired sample means.

    The tested differences are ``sample_b - sample_a``.  Both inputs must have
    the same length and observations at matching positions must correspond to
    each other.
    """

    a = _as_sample(sample_a, name="sample_a")
    b = _as_sample(sample_b, name="sample_b")
    low_value, high_value, alpha_value = _validate_test_parameters(
        low=low,
        high=high,
        alpha=alpha,
    )
    if a.size != b.size:
        raise ValueError("paired samples must have the same length")

    differences = b - a
    n = int(differences.size)
    standard_error = float(np.std(differences, ddof=1) / math.sqrt(n))

    return _finish_tost(
        method="paired",
        mean_a=float(np.mean(a)),
        mean_b=float(np.mean(b)),
        standard_error=standard_error,
        degrees_of_freedom=float(n - 1),
        low=low_value,
        high=high_value,
        alpha=alpha_value,
        samples_a=n,
        samples_b=n,
    )

