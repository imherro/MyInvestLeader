from __future__ import annotations

from core.scoring import build_correlation_guard, calculate_ulls


def test_correlation_guard_downgrades_redundant_dominance() -> None:
    guard = build_correlation_guard(
        [0.91, 0.86, 0.80, 0.72],
        [0.92, 0.87, 0.79, 0.73],
        threshold=0.78,
    )

    assert guard.action == "downgrade_competition_to_explanation"
    assert guard.dominance_weight == 0.04
    assert guard.factor_weight > 0.65


def test_ulls_keeps_factor_primary_and_smooths_history() -> None:
    guard = build_correlation_guard([0.90, 0.80, 0.70], [0.40, 0.80, 0.50])

    result = calculate_ulls(
        factor_score=0.90,
        lifecycle_state="Expansion",
        regime_multiplier=1.0,
        dominance=0.60,
        guard=guard,
        previous_ulls=0.70,
    )

    assert result.explanations["weights"]["factor_score"] > result.explanations["weights"]["dominance_normalizer"]
    assert result.smoothed is True
    assert result.previous_ulls == 0.70
    assert result.raw_ulls > result.ulls
