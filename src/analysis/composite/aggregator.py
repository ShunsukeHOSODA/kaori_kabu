"""Composite Score 集約器（Phase 3.1a 主関数）。

各サブスコアを集計し、投資スタイル別プリセットの重みで合算する。
警告は並行して独立判定。

設計方針（architect レビュー反映）:
    - 薄い純粋計算層（キャッシュ持たず）
    - 単方向依存（composite → 各 subscore のみ）
    - Decimal/float 境界: 入力金額 = Decimal、サブスコア = float
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .presets import INVESTOR_PRESETS_PHASE_3_1A
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
from .warnings import CompositeWarning, evaluate_warnings


@dataclass(frozen=True)
class CompositeScoreInputs:
    """compute_composite_score の入力一括。"""

    income: IncomeSubScoreInputs
    risk: RiskSubScoreInputs
    quality: QualitySubScoreInputs
    sentiment_score: Decimal
    sentiment_confidence: Decimal
    momentum_12m_return: Decimal | None = None


@dataclass(frozen=True)
class CompositeScoreResult:
    """Composite Score の結果一式。"""

    income: IncomeSubScoreResult
    risk: RiskSubScoreResult
    quality: QualitySubScoreResult
    sentiment: SentimentSubScoreResult
    preset_name: str
    weights: dict[str, float]
    sub_scores: dict[str, float]
    composite_score: float
    warnings: list[CompositeWarning]


def compute_composite_score(
    inputs: CompositeScoreInputs,
    *,
    preset_name: str = "Buffett_型_暫定",
) -> CompositeScoreResult:
    """Phase 3.1a 利用可能な 4 軸（Q/I/R/S）を集約。

    Args:
        inputs: :class:`CompositeScoreInputs`
        preset_name: ``"Buffett_型_暫定"`` か ``"配当再投資型"``

    Returns:
        :class:`CompositeScoreResult`（4 サブスコア + 重み + 合算 + 警告）
    """
    if preset_name not in INVESTOR_PRESETS_PHASE_3_1A:
        raise ValueError(
            f"Unknown preset: {preset_name}. "
            f"Available: {list(INVESTOR_PRESETS_PHASE_3_1A.keys())}"
        )

    income = compute_income_subscore(inputs.income)
    risk = compute_risk_subscore(inputs.risk)
    quality = compute_quality_subscore(inputs.quality)
    sentiment = compute_sentiment_subscore(
        sentiment_score=inputs.sentiment_score,
        confidence=inputs.sentiment_confidence,
    )

    weights = INVESTOR_PRESETS_PHASE_3_1A[preset_name]
    sub_scores: dict[str, float] = {
        "Q": quality.score,
        "I": income.score,
        "R": risk.score,
        "S": sentiment.score,
    }

    composite = sum(
        sub_scores[axis] * weights[axis] / 100.0 for axis in weights.keys()
    )
    composite = max(0.0, min(100.0, composite))

    warnings = evaluate_warnings(
        income,
        risk,
        quality,
        momentum_12m_return=(
            float(inputs.momentum_12m_return)
            if inputs.momentum_12m_return is not None
            else None
        ),
    )

    return CompositeScoreResult(
        income=income,
        risk=risk,
        quality=quality,
        sentiment=sentiment,
        preset_name=preset_name,
        weights=weights,
        sub_scores=sub_scores,
        composite_score=composite,
        warnings=warnings,
    )
