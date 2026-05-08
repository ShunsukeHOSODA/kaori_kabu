"""Value サブスコア — Greenblatt EY ベースの割安度。

学術根拠:
    Greenblatt, J. (2010). *The Little Book That Still Beats the Market*. Ch.5
        Earnings Yield (EY) = EBIT / Enterprise Value
    Asness, Frazzini, Pedersen (2013). *Quality Minus Junk* — Value 軸の独立性。
    Fama-French 1992 — Value premium の長期実証。

設計方針:
    既存 ``src/analysis/magic_formula.py`` の ``calculate_earnings_yield`` の
    Decimal 計算ロジックを取り込み、composite 用に「単一銘柄入力 → 0-100 スコア」
    インターフェースに揃える。Phase 3.1b では EY 単独。PEG は ``growth.py`` 側
    （売上 CAGR との併用が学術的に整合するため）。

スコアリング設計（Phase 3.1b 暫定）:
    score = clip(EY / EY_SAT * 100, 0, 100)  # EY_SAT = 0.12
    EY = 12%+ で満点（Greenblatt Top 30 銘柄相当の上位 EY 水準）
    EY ≦ 0% （赤字会社）で 0 点
    線形補間
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Final

# ---------------------------------------------------------------------------
# 設定定数
# ---------------------------------------------------------------------------

EY_SATURATION: Final[Decimal] = Decimal("0.12")
"""EY 飽和点（12% で 100 点）。Greenblatt Top 30 銘柄相当の上位 EY 水準。"""


# ---------------------------------------------------------------------------
# データクラス
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValueSubScoreInputs:
    """Value サブスコア計算の入力値。"""

    ebit_jpy: Decimal | None
    enterprise_value_jpy: Decimal | None


@dataclass(frozen=True)
class ValueSubScoreResult:
    """Value サブスコアの結果。"""

    earnings_yield: Decimal | None
    score: float
    components: dict[str, float]


# ---------------------------------------------------------------------------
# 個別計算ヘルパー
# ---------------------------------------------------------------------------


def calculate_earnings_yield(
    ebit_jpy: Decimal | None,
    enterprise_value_jpy: Decimal | None,
) -> Decimal | None:
    """``EY = EBIT / Enterprise Value``。

    Greenblatt 2010 Ch.5 が PER の代わりに EBIT/EV を採用する理由:
        資本構成（負債比率）に依存せず純粋な事業稼ぐ力を測れる。
        EV = 時価総額 + 純有利子負債 で買収価格に近い概念。

    EV ≦ 0 (純現金 > 時価総額) は ``None`` を返す（ランキング解釈が破綻するため）。
    赤字会社（EBIT < 0）は負の EY を返し、スコアラー側で 0 点に丸める。
    """
    if ebit_jpy is None or enterprise_value_jpy is None:
        return None
    if enterprise_value_jpy <= 0:
        return None
    return ebit_jpy / enterprise_value_jpy


# ---------------------------------------------------------------------------
# 主関数
# ---------------------------------------------------------------------------


def compute_value_subscore(inputs: ValueSubScoreInputs) -> ValueSubScoreResult:
    """Value サブスコア（0-100）を算出。

    Args:
        inputs: :class:`ValueSubScoreInputs`

    Returns:
        :class:`ValueSubScoreResult`（EY + score + components）
    """
    ey = calculate_earnings_yield(
        ebit_jpy=inputs.ebit_jpy,
        enterprise_value_jpy=inputs.enterprise_value_jpy,
    )

    if ey is None:
        score = 0.0
    else:
        ey_pct = float(ey)
        sat = float(EY_SATURATION)
        score = max(0.0, min(100.0, ey_pct / sat * 100.0))

    return ValueSubScoreResult(
        earnings_yield=ey,
        score=score,
        components={"ey_pts": score},
    )
