"""Statistical algorithms for experimental data analysis."""

from ._equivalence import TOSTResult, tost_independent, tost_paired
from ._outlier import (
    HampelResult,
    MADPointResult,
    hampel_filter,
    mad_outlier_test,
    median_absolute_deviation,
    robust_standard_deviation,
)
from ._trend import (
    MannKendallResult,
    TheilSenResult,
    mann_kendall_test,
    theil_sen_test,
)

__all__ = [
    "HampelResult",
    "MADPointResult",
    "MannKendallResult",
    "TOSTResult",
    "TheilSenResult",
    "hampel_filter",
    "mad_outlier_test",
    "mann_kendall_test",
    "median_absolute_deviation",
    "robust_standard_deviation",
    "theil_sen_test",
    "tost_independent",
    "tost_paired",
]