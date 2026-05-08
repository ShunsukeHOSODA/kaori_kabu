"""Quality サブスコア — Buffett-Munger 風（Phase 3.1a 暫定）。

Phase 3.1a は ROIC/WACC 不在のため ROE/ROA 代理（"Buffett 型(暫定)" として
UI でラベル分離）。Phase 3.2 で:
    - ROIC vs WACC（自前 WACC 計算）
    - Sloan 1996 Accruals Ratio
    - Asness/Frazzini/Pedersen 2019 QMJ
を追加予定。

スコアリング設計（合計 100 点満点）:
    +50 ROE: 20%+ で満点（線形）
    +30 ROA: 10%+ で満点
    +20 Gross margin: 40%+ で満点
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class QualitySubScoreInputs:
    roe: Decimal | None
    roa: Decimal | None
    gross_margin: Decimal | None


@dataclass(frozen=True)
class QualitySubScoreResult:
    roe: Decimal | None
    roa: Decimal | None
    gross_margin: Decimal | None
    score: float
    components: dict[str, float]


def _ratio_pts(value: Decimal | None, max_pts: float, full_score_ratio: float) -> float:
    if value is None:
        return 0.0
    v = float(value)
    if v <= 0:
        return 0.0
    return max_pts * min(v / full_score_ratio, 1.0)


def compute_quality_subscore(
    inputs: QualitySubScoreInputs,
) -> QualitySubScoreResult:
    """Quality サブスコアを計算（0-100）。"""
    components: dict[str, float] = {
        "roe_pts": _ratio_pts(inputs.roe, max_pts=50.0, full_score_ratio=0.20),
        "roa_pts": _ratio_pts(inputs.roa, max_pts=30.0, full_score_ratio=0.10),
        "gross_margin_pts": _ratio_pts(
            inputs.gross_margin, max_pts=20.0, full_score_ratio=0.40
        ),
    }
    raw = sum(components.values())
    score = max(0.0, min(100.0, raw))

    return QualitySubScoreResult(
        roe=inputs.roe,
        roa=inputs.roa,
        gross_margin=inputs.gross_margin,
        score=score,
        components=components,
    )
