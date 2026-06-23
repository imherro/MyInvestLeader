"""Factorized scoring engine exports."""

from .competition_graph import CompetitionLeader, ThemeCompetitionGraph, build_theme_competition_graph
from .engine import ScoringEngine, calculate_score, calculate_score_breakdown, default_stock_scoring_engine
from .factors import BaseFactor, CapQualityFactor, FundFlowFactor, ThemeFactor, VolumeFactor
from .lifecycle import LifecycleResult, detect_leader_lifecycle
from .normalization import percentile_rank
from .regime import MarketRegime, RegimeResult, detect_market_regime
from .schema import FactorResult

__all__ = [
    "BaseFactor",
    "CapQualityFactor",
    "CompetitionLeader",
    "FactorResult",
    "FundFlowFactor",
    "LifecycleResult",
    "MarketRegime",
    "RegimeResult",
    "ScoringEngine",
    "ThemeFactor",
    "ThemeCompetitionGraph",
    "VolumeFactor",
    "build_theme_competition_graph",
    "calculate_score",
    "calculate_score_breakdown",
    "default_stock_scoring_engine",
    "detect_leader_lifecycle",
    "detect_market_regime",
    "percentile_rank",
]
