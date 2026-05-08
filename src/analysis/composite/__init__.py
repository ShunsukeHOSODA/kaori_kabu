"""Composite Investment Score（Phase 3）公開 API。

世界一の投資家視座（Buffett-Munger / Lynch / Druckenmiller / Dalio /
Pabrai / Burry / Ackman / AQR / Coca-Cola Buffett モデル）を 8 サブスコア
で網羅し、投資スタイル別プリセットで重み付け合算する。

Phase 3.1a 公開:
    - 4 サブスコア（Quality / Income / Risk / Sentiment）
    - 2 プリセット（Buffett 型(暫定) / 配当再投資型）
    - 5 警告（Altman / 高 leverage / 配当性向 / 連続赤字 / Falling Knife）
    - compute_composite_score 主関数

Phase 3.1b 以降で V/G/M/C サブスコア + 4 プリセット追加予定。

設計詳細は :doc:`docs/long-term-investment-architecture.md` 参照。
"""

from __future__ import annotations

from .aggregator import (
    CompositeScoreInputs,
    CompositeScoreResult,
    compute_composite_score,
)
from .presets import (
    INVESTOR_PRESETS_PHASE_3_1A,
    PRESET_DISPLAY_LABELS,
    PRESET_RATIONALE,
    validate_preset_weights,
)
from .subscores.income import (
    IncomeSubScoreInputs,
    IncomeSubScoreResult,
    compute_income_subscore,
)
from .subscores.quality import (
    QualitySubScoreInputs,
    QualitySubScoreResult,
    compute_quality_subscore,
)
from .subscores.risk import (
    RiskSubScoreInputs,
    RiskSubScoreResult,
    compute_risk_subscore,
)
from .subscores.sentiment import (
    SentimentSubScoreResult,
    compute_sentiment_subscore,
)
from .subscores.growth import (
    GrowthSubScoreInputs,
    GrowthSubScoreResult,
    calculate_peg,
    compute_growth_subscore,
)
from .subscores.value import (
    ValueSubScoreInputs,
    ValueSubScoreResult,
    calculate_earnings_yield,
    compute_value_subscore,
)
from .warnings import CompositeWarning, evaluate_warnings

__all__ = [
    # Aggregator
    "CompositeScoreInputs",
    "CompositeScoreResult",
    "compute_composite_score",
    # Presets
    "INVESTOR_PRESETS_PHASE_3_1A",
    "PRESET_DISPLAY_LABELS",
    "PRESET_RATIONALE",
    "validate_preset_weights",
    # Subscores
    "IncomeSubScoreInputs",
    "IncomeSubScoreResult",
    "compute_income_subscore",
    "QualitySubScoreInputs",
    "QualitySubScoreResult",
    "compute_quality_subscore",
    "RiskSubScoreInputs",
    "RiskSubScoreResult",
    "compute_risk_subscore",
    "SentimentSubScoreResult",
    "compute_sentiment_subscore",
    "ValueSubScoreInputs",
    "ValueSubScoreResult",
    "calculate_earnings_yield",
    "compute_value_subscore",
    "GrowthSubScoreInputs",
    "GrowthSubScoreResult",
    "calculate_peg",
    "compute_growth_subscore",
    # Warnings
    "CompositeWarning",
    "evaluate_warnings",
]
