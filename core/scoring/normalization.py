from __future__ import annotations

import math


def _valid_numbers(values: list[float]) -> list[float]:
    result = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isnan(number) and not math.isinf(number):
            result.append(number)
    return result


def percentile_rank(values: list[float], x: float) -> float:
    """
    Return x's cross-sectional percentile in [0, 1].

    Ties use midpoint ranking, so a single identical universe returns 0.5
    instead of pretending the value is either weakest or strongest.
    """
    numbers = _valid_numbers(values)
    if not numbers:
        return 0.5
    target = float(x)
    if math.isnan(target) or math.isinf(target):
        return 0.5
    less = sum(1 for value in numbers if value < target)
    equal = sum(1 for value in numbers if value == target)
    return max(0.0, min(1.0, (less + equal * 0.5) / len(numbers)))
