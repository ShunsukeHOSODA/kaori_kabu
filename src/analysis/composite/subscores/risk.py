"""Risk サブスコア — Burry / Dalio 流のテールリスク回避。

学術根拠:
    Altman 1968 "Financial Ratios, Discriminant Analysis and the Prediction
    of Corporate Bankruptcy" — Z-Score 5 変数モデル
    Beneish 1999 "The Detection of Earnings Manipulation" — M-Score
    Dalio (Ray) — 純有利子負債/EBITDA は破綻より先に減配を予測

スコアリング設計（リスク低 = 高得点、合計 100 点満点）:
    +40 Altman Z（≥ 2.99 で満点、1.81-2.99 線形、< 1.81 ゼロ）
    +15 Beneish M（< -1.78 で満点、≥ -1.78 ゼロ）
    +25 Net Debt/EBITDA（≤ 0 で満点、3 まで線形、> 5 ゼロ）
    +10 Short interest（< 5% で満点、> 15% ゼロ）
    +10 連続赤字年数（0 年で満点、3+ 年で -10 ペナルティ）

備考:
    - Altman Z は 1968 年製造業前提のため IT 企業で誤発火しがち。
      Phase 3.2 で Merton Distance-to-Default を併記予定。
    - Beneish M は 8 変数の自前計算が複雑なため、Phase 3.1a では
      外部から受け取る形（None なら 0 点）。Phase 3.2 で完全実装。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class RiskSubScoreInputs:
    """Risk サブスコア計算の入力値。"""

    working_capital_jpy: Decimal
    retained_earnings_jpy: Decimal
    ebit_jpy: Decimal
    market_cap_jpy: Decimal
    total_liabilities_jpy: Decimal
    sales_jpy: Decimal
    total_assets_jpy: Decimal
    net_debt_jpy: Decimal
    ebitda_jpy: Decimal
    short_interest_pct: Decimal | None
    consecutive_loss_years: int
    beneish_m_score: float | None = None


@dataclass(frozen=True)
class RiskSubScoreResult:
    """Risk サブスコアの結果。"""

    altman_z_score: float | None
    beneish_m_score: float | None
    net_debt_ebitda_ratio: Decimal | None
    short_interest_pct: Decimal | None
    consecutive_loss_years: int
    score: float
    components: dict[str, float]


def calculate_altman_z(
    working_capital: Decimal,
    retained_earnings: Decimal,
    ebit: Decimal,
    market_cap: Decimal,
    total_liabilities: Decimal,
    sales: Decimal,
    total_assets: Decimal,
) -> float | None:
    """Altman Z-Score（公開企業 5 変数モデル、1968）。

    Z = 1.2 × (WC/TA) + 1.4 × (RE/TA) + 3.3 × (EBIT/TA) +
        0.6 × (MC/TL) + 1.0 × (Sales/TA)

    判定:
        Z ≥ 2.99: Safe Zone
        1.81 ≤ Z < 2.99: Grey Zone
        Z < 1.81: Distress Zone（破綻リスク）
    """
    if total_assets <= 0 or total_liabilities <= 0:
        return None
    a = float(working_capital / total_assets)
    b = float(retained_earnings / total_assets)
    c = float(ebit / total_assets)
    d = float(market_cap / total_liabilities)
    e = float(sales / total_assets)
    return 1.2 * a + 1.4 * b + 3.3 * c + 0.6 * d + 1.0 * e


def calculate_net_debt_ebitda(
    net_debt: Decimal,
    ebitda: Decimal,
) -> Decimal | None:
    """``Net Debt / EBITDA`` 比率。"""
    if ebitda <= 0:
        return None
    return net_debt / ebitda


def _altman_z_pts(z: float | None) -> float:
    if z is None:
        return 0.0
    if z >= 2.99:
        return 40.0
    if z < 1.81:
        return 0.0
    return 40.0 * (z - 1.81) / (2.99 - 1.81)


def _beneish_m_pts(m: float | None) -> float:
    if m is None:
        return 0.0
    return 15.0 if m < -1.78 else 0.0


def _net_debt_ebitda_pts(ratio: Decimal | None) -> float:
    if ratio is None:
        return 0.0
    r = float(ratio)
    if r <= 0:
        return 25.0
    if r >= 5:
        return 0.0
    if r <= 3:
        return 25.0 - (r / 3.0) * 15.0
    return 10.0 * (5 - r) / 2.0


def _short_interest_pts(short_pct: Decimal | None) -> float:
    if short_pct is None:
        return 0.0
    p = float(short_pct)
    if p < 0.05:
        return 10.0
    if p > 0.15:
        return 0.0
    return 10.0 * (0.15 - p) / 0.10


def _loss_years_pts(years: int) -> float:
    if years <= 0:
        return 10.0
    if years == 1:
        return 5.0
    if years == 2:
        return 0.0
    return -10.0


def compute_risk_subscore(inputs: RiskSubScoreInputs) -> RiskSubScoreResult:
    """Risk サブスコアを計算（0-100、リスク低=高得点）。"""
    z = calculate_altman_z(
        working_capital=inputs.working_capital_jpy,
        retained_earnings=inputs.retained_earnings_jpy,
        ebit=inputs.ebit_jpy,
        market_cap=inputs.market_cap_jpy,
        total_liabilities=inputs.total_liabilities_jpy,
        sales=inputs.sales_jpy,
        total_assets=inputs.total_assets_jpy,
    )
    nd_ebitda = calculate_net_debt_ebitda(inputs.net_debt_jpy, inputs.ebitda_jpy)

    components: dict[str, float] = {
        "altman_z_pts": _altman_z_pts(z),
        "beneish_m_pts": _beneish_m_pts(inputs.beneish_m_score),
        "net_debt_ebitda_pts": _net_debt_ebitda_pts(nd_ebitda),
        "short_interest_pts": _short_interest_pts(inputs.short_interest_pct),
        "loss_years_pts": _loss_years_pts(inputs.consecutive_loss_years),
    }
    raw_score = sum(components.values())
    score = max(0.0, min(100.0, raw_score))

    return RiskSubScoreResult(
        altman_z_score=z,
        beneish_m_score=inputs.beneish_m_score,
        net_debt_ebitda_ratio=nd_ebitda,
        short_interest_pct=inputs.short_interest_pct,
        consecutive_loss_years=inputs.consecutive_loss_years,
        score=score,
        components=components,
    )
