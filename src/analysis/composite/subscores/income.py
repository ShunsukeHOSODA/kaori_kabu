"""Income サブスコア — 真の株主リターン（配当 + Buyback + FCF + 優待）。

学術根拠:
    Asness 2014 — Total Shareholder Yield = dividend yield + buyback yield
    Buffett (Berkshire Annual Letters) — Coca-Cola 配当再投資モデル
    Sharpe 1991 — 配当の長期複利効果

スコアリング設計（合計 100 点満点）:
    +30 配当 yield: 5%+ で満点（線形）
    +25 Buyback yield: 5%+ で満点
    +20 FCF yield: 10%+ で満点（配当原資の健全性）
    +15 優待 yield: 3%+ で満点（日本株のみ、None なら 0）
    +10 連続増配年数: 25 年+ で満点
    -X  配当性向ペナルティ（GICS セクター別動的閾値）
        Tech/Communication: > 60% で -5、> 80% で -10
        Consumer/Industrial: > 70% で -5、> 90% で -10
        REIT/Utilities/Financials: > 90% で -5、> 95% で -10

最終 score = clip(合算, 0, 100)。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Final

# ---------------------------------------------------------------------------
# データクラス
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IncomeSubScoreInputs:
    """Income サブスコア計算の入力値。

    すべて optional な欠損値は ``None`` で受け、各計算側でガード。
    金額は Decimal、年数は int、セクターは str。
    """

    forward_dividend_per_share_jpy: Decimal | None
    current_price_jpy: Decimal
    payout_ratio: Decimal | None
    consecutive_dividend_years: int
    buybacks_4q_jpy: Decimal | None
    market_cap_jpy: Decimal
    free_cash_flow_jpy: Decimal | None
    enterprise_value_jpy: Decimal | None
    yutai_value_jpy: Decimal | None = None
    yutai_min_shares: int | None = None
    sector: str | None = None


@dataclass(frozen=True)
class IncomeSubScoreResult:
    """Income サブスコアの結果。"""

    forward_dividend_yield: Decimal | None
    buyback_yield: Decimal | None
    fcf_yield: Decimal | None
    yutai_yield: Decimal | None
    total_shareholder_yield: Decimal
    consecutive_dividend_years: int
    payout_ratio: Decimal | None
    score: float
    components: dict[str, float]


# ---------------------------------------------------------------------------
# 個別計算ヘルパー
# ---------------------------------------------------------------------------


def calculate_forward_dividend_yield(
    annual_dividend_jpy: Decimal | None,
    current_price_jpy: Decimal,
) -> Decimal | None:
    """``forward_yield = annual_dividend / current_price``。"""
    if annual_dividend_jpy is None or current_price_jpy <= 0:
        return None
    return annual_dividend_jpy / current_price_jpy


def calculate_buyback_yield(
    buybacks_4q_jpy: Decimal | None,
    market_cap_jpy: Decimal,
) -> Decimal | None:
    """``buyback_yield = 直近 4Q buyback / 時価総額``。"""
    if buybacks_4q_jpy is None or market_cap_jpy <= 0:
        return None
    return buybacks_4q_jpy / market_cap_jpy


def calculate_fcf_yield(
    free_cash_flow_jpy: Decimal | None,
    enterprise_value_jpy: Decimal | None,
) -> Decimal | None:
    """``fcf_yield = FCF / Enterprise Value``。配当原資の健全性指標。"""
    if (
        free_cash_flow_jpy is None
        or enterprise_value_jpy is None
        or enterprise_value_jpy <= 0
    ):
        return None
    return free_cash_flow_jpy / enterprise_value_jpy


def calculate_yutai_yield(
    *,
    yutai_value_jpy: Decimal | None,
    min_shares: int | None,
    current_price_jpy: Decimal,
) -> Decimal | None:
    """日本株株主優待利回り = 優待価値 / (最低保有株数 × 株価)。"""
    if yutai_value_jpy is None or min_shares is None or min_shares <= 0:
        return None
    if current_price_jpy <= 0:
        return None
    return yutai_value_jpy / (Decimal(min_shares) * current_price_jpy)


# ---------------------------------------------------------------------------
# 配当性向のセクター別動的閾値
# ---------------------------------------------------------------------------

_PAYOUT_THRESHOLDS_BY_SECTOR: Final[dict[str, tuple[float, float]]] = {
    "Technology": (0.60, 0.80),
    "Communication Services": (0.60, 0.80),
    "Consumer Discretionary": (0.65, 0.85),
    "Industrials": (0.70, 0.90),
    "Health Care": (0.70, 0.90),
    "Consumer Staples": (0.75, 0.90),
    "Materials": (0.70, 0.90),
    "Energy": (0.70, 0.90),
    "Real Estate": (0.95, 1.05),
    "Utilities": (0.90, 1.00),
    "Financials": (0.85, 1.00),
}
_DEFAULT_PAYOUT_THRESHOLDS: Final[tuple[float, float]] = (0.70, 0.90)


def _payout_penalty(payout: Decimal | None, sector: str | None) -> float:
    """配当性向ペナルティ。セクターごとの閾値で warn=-5、severe=-10。"""
    if payout is None or payout <= 0:
        return 0.0
    warn, severe = _PAYOUT_THRESHOLDS_BY_SECTOR.get(
        sector or "", _DEFAULT_PAYOUT_THRESHOLDS
    )
    p = float(payout)
    if p > severe:
        return -10.0
    if p > warn:
        return -5.0
    return 0.0


def _yield_pts(value: Decimal | None, max_pts: float, full_score_yield: float) -> float:
    """yield を 0-max_pts に線形マッピング。負値はゼロ、上限以上は満点。"""
    if value is None:
        return 0.0
    v = float(value)
    if v <= 0:
        return 0.0
    return max_pts * min(v / full_score_yield, 1.0)


def _consecutive_years_pts(years: int) -> float:
    """連続増配年数を 0-10 にマッピング。25 年以上で満点。"""
    if years <= 0:
        return 0.0
    return 10.0 * min(years / 25.0, 1.0)


def compute_income_subscore(
    inputs: IncomeSubScoreInputs,
) -> IncomeSubScoreResult:
    """Income サブスコアを計算（0-100）。

    Args:
        inputs: :class:`IncomeSubScoreInputs`

    Returns:
        :class:`IncomeSubScoreResult`（score + 各 yield + components 内訳）
    """
    div_y = calculate_forward_dividend_yield(
        inputs.forward_dividend_per_share_jpy, inputs.current_price_jpy
    )
    bb_y = calculate_buyback_yield(inputs.buybacks_4q_jpy, inputs.market_cap_jpy)
    fcf_y = calculate_fcf_yield(
        inputs.free_cash_flow_jpy, inputs.enterprise_value_jpy
    )
    yutai_y = calculate_yutai_yield(
        yutai_value_jpy=inputs.yutai_value_jpy,
        min_shares=inputs.yutai_min_shares,
        current_price_jpy=inputs.current_price_jpy,
    )

    div_pts = _yield_pts(div_y, max_pts=30.0, full_score_yield=0.05)
    bb_pts = _yield_pts(bb_y, max_pts=25.0, full_score_yield=0.05)
    fcf_pts = _yield_pts(fcf_y, max_pts=20.0, full_score_yield=0.10)
    yutai_pts = _yield_pts(yutai_y, max_pts=15.0, full_score_yield=0.03)
    years_pts = _consecutive_years_pts(inputs.consecutive_dividend_years)
    payout_pen = _payout_penalty(inputs.payout_ratio, inputs.sector)

    components: dict[str, float] = {
        "dividend_yield_pts": div_pts,
        "buyback_yield_pts": bb_pts,
        "fcf_yield_pts": fcf_pts,
        "yutai_yield_pts": yutai_pts,
        "consecutive_years_pts": years_pts,
        "payout_penalty": payout_pen,
    }

    raw_score = sum(components.values())
    score = max(0.0, min(100.0, raw_score))

    tsy = (div_y or Decimal("0")) + (bb_y or Decimal("0"))

    return IncomeSubScoreResult(
        forward_dividend_yield=div_y,
        buyback_yield=bb_y,
        fcf_yield=fcf_y,
        yutai_yield=yutai_y,
        total_shareholder_yield=tsy,
        consecutive_dividend_years=inputs.consecutive_dividend_years,
        payout_ratio=inputs.payout_ratio,
        score=score,
        components=components,
    )
