"""Statistical utilities and significance testing for UOW-NATIVE-2."""

import math
from typing import List, Sequence, Tuple
import numpy as np


def compute_bootstrap_ci(
    values: Sequence[float], n_bootstrap: int = 1000, ci: float = 0.95, seed: int = 42
) -> Tuple[float, float]:
    """Compute non-parametric bootstrap confidence interval."""
    if not values:
        return (0.0, 0.0)
    rng = np.random.default_rng(seed)
    arr = np.array(values, dtype=float)
    n = len(arr)
    boot_means = [rng.choice(arr, size=n, replace=True).mean() for _ in range(n_bootstrap)]
    lower = float(np.percentile(boot_means, (1.0 - ci) / 2.0 * 100))
    upper = float(np.percentile(boot_means, (1.0 + ci) / 2.0 * 100))
    return (lower, upper)


def compute_rank_p_value(effect: float, controls: Sequence[float]) -> float:
    """Compute exact empirical rank p-value: fraction of controls with effect >= observed."""
    if not controls:
        raise ValueError("At least one control value is required")
    count_gte = sum(1 for c in controls if c >= effect)
    return (1.0 + count_gte) / (1.0 + len(controls))


def paired_difference_sign_test(differences: Sequence[float]) -> Tuple[int, int, int]:
    """Tally positive, negative, and zero differences for paired comparisons."""
    pos = sum(1 for d in differences if d > 0)
    neg = sum(1 for d in differences if d < 0)
    zero = sum(1 for d in differences if d == 0)
    return (pos, neg, zero)
