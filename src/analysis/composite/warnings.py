"""警告システム — Composite Score と並行して独立判定。

CLAUDE.md §9.4 シグナル + リスク警告併記の方針に従い、
Composite Score がいくら高くても警告がある銘柄はユーザーに明示。

警告 5 種:
    - ALTMAN_DISTRESS (RED): Altman Z < 1.81
    - HIGH_LEVERAGE (AMBER): Net Debt/EBITDA > 5
    - PAYOUT_HIGH (AMBER): 配当性向が業種別 severe 閾値超
    - LOSS_3Y (RED): 連続 3 年以上赤字
    - FALLING_KNIFE (AMBER): Quality 高 + 12m リターン < -20%
      （kabu-analyst レビュー反映、Frazzini-Pedersen 2018 "Buffett's Alpha"）
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from .subscores.income import IncomeSubScoreResult
from .subscores.quality import QualitySubScoreResult
from .subscores.risk import RiskSubScoreResult

Severity = Literal["RED", "AMBER", "NOTE"]


@dataclass(frozen=True)
class CompositeWarning:
    """個別警告。"""

    severity: Severity
    code: str
    message: str


def evaluate_warnings(
    income: IncomeSubScoreResult,
    risk: RiskSubScoreResult,
    quality: QualitySubScoreResult,
    *,
    momentum_12m_return: float | None = None,
) -> list[CompositeWarning]:
    """5 警告を独立判定して list で返す。"""
    warnings: list[CompositeWarning] = []

    if risk.altman_z_score is not None and risk.altman_z_score < 1.81:
        warnings.append(
            CompositeWarning(
                severity="RED",
                code="ALTMAN_DISTRESS",
                message=(
                    f"Altman Z = {risk.altman_z_score:.2f} < 1.81 "
                    "（Distress Zone、破綻リスク）"
                ),
            )
        )

    if (
        risk.net_debt_ebitda_ratio is not None
        and float(risk.net_debt_ebitda_ratio) > 5
    ):
        warnings.append(
            CompositeWarning(
                severity="AMBER",
                code="HIGH_LEVERAGE",
                message=(
                    f"Net Debt/EBITDA = "
                    f"{float(risk.net_debt_ebitda_ratio):.1f}x（> 5 倍）"
                ),
            )
        )

    payout_pen = income.components.get("payout_penalty", 0.0)
    if payout_pen <= -10.0 and income.payout_ratio is not None:
        warnings.append(
            CompositeWarning(
                severity="AMBER",
                code="PAYOUT_HIGH",
                message=(
                    f"配当性向 {income.payout_ratio * Decimal('100'):.0f}% "
                    "は業種別閾値の severe を超過、減配リスク"
                ),
            )
        )

    if risk.consecutive_loss_years >= 3:
        warnings.append(
            CompositeWarning(
                severity="RED",
                code="LOSS_3Y",
                message=(
                    f"連続 {risk.consecutive_loss_years} 年赤字、構造不振"
                ),
            )
        )

    if (
        quality.score >= 70.0
        and momentum_12m_return is not None
        and momentum_12m_return < -0.20
    ):
        warnings.append(
            CompositeWarning(
                severity="AMBER",
                code="FALLING_KNIFE",
                message=(
                    f"Quality 高 ({quality.score:.0f}) かつ 12m return "
                    f"{momentum_12m_return * 100:.1f}% で Falling Knife 候補"
                ),
            )
        )

    return warnings
