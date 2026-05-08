"""保有銘柄の評価額・含み益損計算（CLAUDE.md §9.1 / §9.7）。

純粋関数で構成。USD 価格 → JPY 換算は呼び出し側で実施し、本モジュールは
JPY 統一の入出力のみ扱う（責務分離）。

Loss Aversion バイアス対策として評価額の見える化を担う。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .holdings import Holding, Portfolio


@dataclass(frozen=True)
class HoldingValuation:
    """1 銘柄の評価結果（immutable）。

    Attributes:
        ticker: ティッカーシンボル
        shares: 保有株数
        avg_cost_jpy: 取得平均単価（JPY）
        current_price_jpy: 現在単価（JPY）
        market_value_jpy: 評価額 = shares * current_price_jpy
        unrealized_pnl_jpy: 含み益損 = market_value - cost
        unrealized_pnl_pct: 含み益損率（小数、0.05 = 5%）
    """

    ticker: str
    shares: Decimal
    avg_cost_jpy: Decimal
    current_price_jpy: Decimal
    market_value_jpy: Decimal
    unrealized_pnl_jpy: Decimal
    unrealized_pnl_pct: Decimal


def evaluate_holding(
    holding: Holding,
    *,
    current_price_jpy: Decimal,
) -> HoldingValuation:
    """1 銘柄を現在価格で評価。

    cost が 0（理論上発生しない、ガード用）の場合 ``unrealized_pnl_pct`` は 0 を返す。
    """
    market_value = holding.shares * current_price_jpy
    cost = holding.shares * holding.avg_cost_jpy
    pnl = market_value - cost
    pnl_pct = (pnl / cost) if cost > 0 else Decimal("0")
    return HoldingValuation(
        ticker=holding.ticker,
        shares=holding.shares,
        avg_cost_jpy=holding.avg_cost_jpy,
        current_price_jpy=current_price_jpy,
        market_value_jpy=market_value,
        unrealized_pnl_jpy=pnl,
        unrealized_pnl_pct=pnl_pct,
    )


def evaluate_portfolio(
    portfolio: Portfolio,
    *,
    current_prices_jpy: dict[str, Decimal],
) -> list[HoldingValuation]:
    """全保有銘柄を評価。

    ``current_prices_jpy`` に存在しないティッカーはスキップ（取得失敗を許容）。
    呼び出し側は欠損銘柄を別途警告する責務を持つ。
    """
    valuations: list[HoldingValuation] = []
    for h in portfolio.holdings:
        price = current_prices_jpy.get(h.ticker)
        if price is None:
            continue
        valuations.append(evaluate_holding(h, current_price_jpy=price))
    return valuations


def total_market_value_jpy(valuations: list[HoldingValuation]) -> Decimal:
    """評価結果リストの合計時価（JPY）。"""
    return sum((v.market_value_jpy for v in valuations), Decimal("0"))


def total_unrealized_pnl_jpy(valuations: list[HoldingValuation]) -> Decimal:
    """評価結果リストの合計含み益損（JPY）。"""
    return sum((v.unrealized_pnl_jpy for v in valuations), Decimal("0"))
