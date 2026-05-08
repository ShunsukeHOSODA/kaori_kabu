"""Composite Score 集約器（Phase 3.1b 主関数）。

各サブスコアを集計し、投資スタイル別プリセットの重みで合算する。
警告は並行して独立判定。

設計方針（architect レビュー反映）:
    - 薄い純粋計算層（キャッシュ持たず）
    - 単方向依存（composite → 各 subscore のみ）
    - Decimal/float 境界: 入力金額 = Decimal、サブスコア = float

7 軸対応（Phase 3.1b）:
    Q (Quality) / V (Value) / I (Income) / G (Growth) / R (Risk) /
    M (Momentum) / S (Sentiment)
    V/G/M の入力は **任意**（None なら該当軸 0 点、警告なし）。
    Conviction (C) は Phase 3.2 で 13F 統合時に追加。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .presets import INVESTOR_PRESETS_PHASE_3_1B
from .subscores.growth import (
    GrowthSubScoreInputs,
    GrowthSubScoreResult,
    compute_growth_subscore,
)
from .subscores.income import (
    IncomeSubScoreInputs,
    IncomeSubScoreResult,
    compute_income_subscore,
)
from .subscores.momentum import (
    MomentumSubScoreInputs,
    MomentumSubScoreResult,
    compute_momentum_subscore,
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
from .subscores.value import (
    ValueSubScoreInputs,
    ValueSubScoreResult,
    compute_value_subscore,
)
from .warnings import CompositeWarning, evaluate_warnings


@dataclass(frozen=True)
class CompositeScoreInputs:
    """compute_composite_score の入力一括（Phase 3.1b 7 軸対応）。

    Phase 3.1a 互換のため value/growth/momentum は省略可。None のとき
    該当軸サブスコアは 0 点となる。
    """

    income: IncomeSubScoreInputs
    risk: RiskSubScoreInputs
    quality: QualitySubScoreInputs
    sentiment_score: Decimal
    sentiment_confidence: Decimal
    momentum_12m_return: Decimal | None = None
    value: ValueSubScoreInputs | None = None
    growth: GrowthSubScoreInputs | None = None
    momentum: MomentumSubScoreInputs | None = None


@dataclass(frozen=True)
class CompositeScoreResult:
    """Composite Score の結果一式（Phase 3.1b 7 軸対応）。"""

    income: IncomeSubScoreResult
    risk: RiskSubScoreResult
    quality: QualitySubScoreResult
    sentiment: SentimentSubScoreResult
    value: ValueSubScoreResult | None
    growth: GrowthSubScoreResult | None
    momentum: MomentumSubScoreResult | None
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
    """7 軸（Q/V/I/G/R/M/S）を集約し、プリセット重みで合算する。

    Args:
        inputs: :class:`CompositeScoreInputs`（V/G/M は省略可）
        preset_name: ``Buffett_型_暫定`` / ``配当再投資型`` /
            ``Lynch_型`` / ``逆張り型`` のいずれか

    Returns:
        :class:`CompositeScoreResult`（7 サブスコア + 重み + 合算 + 警告）
    """
    if preset_name not in INVESTOR_PRESETS_PHASE_3_1B:
        raise ValueError(
            f"Unknown preset: {preset_name}. "
            f"Available: {list(INVESTOR_PRESETS_PHASE_3_1B.keys())}"
        )

    income = compute_income_subscore(inputs.income)
    risk = compute_risk_subscore(inputs.risk)
    quality = compute_quality_subscore(inputs.quality)
    sentiment = compute_sentiment_subscore(
        sentiment_score=inputs.sentiment_score,
        confidence=inputs.sentiment_confidence,
    )
    value = compute_value_subscore(inputs.value) if inputs.value is not None else None
    growth = (
        compute_growth_subscore(inputs.growth) if inputs.growth is not None else None
    )
    momentum = (
        compute_momentum_subscore(inputs.momentum)
        if inputs.momentum is not None
        else None
    )

    weights = INVESTOR_PRESETS_PHASE_3_1B[preset_name]
    sub_scores: dict[str, float] = {
        "Q": quality.score,
        "V": value.score if value is not None else 0.0,
        "I": income.score,
        "G": growth.score if growth is not None else 0.0,
        "R": risk.score,
        "M": momentum.score if momentum is not None else 0.0,
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
        value=value,
        growth=growth,
        momentum=momentum,
        preset_name=preset_name,
        weights=weights,
        sub_scores=sub_scores,
        composite_score=composite,
        warnings=warnings,
    )
