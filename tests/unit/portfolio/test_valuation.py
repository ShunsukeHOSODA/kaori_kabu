"""保有銘柄の評価額・含み益損計算の単体テスト。

CLAUDE.md §9.1 / §9.7（Loss Aversion 対策に評価額の見える化）に準拠:
    - 金額は Decimal、比率は小数（0.05 = 5%）
    - JPY 統一（USD → JPY 換算は呼び出し側で実施）
    - 純粋関数（副作用なし、テスト容易）
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest


def _aapl_holding():
    """AAPL 10 株、取得平均 25,000 円（合成）。"""
    from portfolio.holdings import Holding

    return Holding(
        ticker="AAPL",
        exchange="US",
        shares=Decimal("10"),
        avg_cost_jpy=Decimal("25000"),
        purchased_at=date(2025, 1, 15),
        account_type="NISA",
    )


def _toyota_holding():
    """7203 トヨタ 100 株、取得平均 2,800 円（合成）。"""
    from portfolio.holdings import Holding

    return Holding(
        ticker="7203",
        exchange="TO",
        shares=Decimal("100"),
        avg_cost_jpy=Decimal("2800"),
        purchased_at=date(2024, 12, 1),
        account_type="特定",
    )


@pytest.mark.unit
class TestEvaluateHolding:
    """1 銘柄の評価額・含み益損計算。"""

    def test_含み益_取得25000_現在30000(self) -> None:
        """取得 25,000 → 現在 30,000 = 1 株 +5,000、10 株で +50,000 円。"""
        from portfolio.valuation import evaluate_holding

        v = evaluate_holding(_aapl_holding(), current_price_jpy=Decimal("30000"))

        assert v.ticker == "AAPL"
        assert v.market_value_jpy == Decimal("300000")
        assert v.unrealized_pnl_jpy == Decimal("50000")
        # +50000 / 250000 = +0.2 (=20%)
        assert v.unrealized_pnl_pct == Decimal("0.2")

    def test_含み損_取得25000_現在20000(self) -> None:
        from portfolio.valuation import evaluate_holding

        v = evaluate_holding(_aapl_holding(), current_price_jpy=Decimal("20000"))

        assert v.market_value_jpy == Decimal("200000")
        assert v.unrealized_pnl_jpy == Decimal("-50000")
        assert v.unrealized_pnl_pct == Decimal("-0.2")

    def test_HoldingValuation_は_immutable(self) -> None:
        from dataclasses import FrozenInstanceError

        from portfolio.valuation import evaluate_holding

        v = evaluate_holding(_aapl_holding(), current_price_jpy=Decimal("30000"))

        with pytest.raises(FrozenInstanceError):
            v.market_value_jpy = Decimal("0")  # type: ignore[misc]


@pytest.mark.unit
class TestEvaluatePortfolio:
    """ポートフォリオ全体の評価。"""

    def test_2銘柄_全評価_合計値(self) -> None:
        """AAPL 30000、トヨタ 3000 で評価 → 合計時価/含み益。"""
        from portfolio.holdings import Portfolio
        from portfolio.valuation import (
            evaluate_portfolio,
            total_market_value_jpy,
            total_unrealized_pnl_jpy,
        )

        portfolio = Portfolio(holdings=(_aapl_holding(), _toyota_holding()))
        prices = {
            "AAPL": Decimal("30000"),  # 1 株含み益 +5,000
            "7203": Decimal("3000"),  # 1 株含み益 +200
        }

        valuations = evaluate_portfolio(portfolio, current_prices_jpy=prices)

        assert len(valuations) == 2
        # AAPL: 10*30000 = 300000、7203: 100*3000 = 300000、合計 600000
        assert total_market_value_jpy(valuations) == Decimal("600000")
        # AAPL pnl: 50000、7203 pnl: 100*200=20000、合計 70000
        assert total_unrealized_pnl_jpy(valuations) == Decimal("70000")

    def test_価格不明銘柄はスキップ(self) -> None:
        """current_prices_jpy に無いティッカーは valuations から除外。"""
        from portfolio.holdings import Portfolio
        from portfolio.valuation import evaluate_portfolio

        portfolio = Portfolio(holdings=(_aapl_holding(), _toyota_holding()))
        prices = {"AAPL": Decimal("30000")}  # 7203 なし

        valuations = evaluate_portfolio(portfolio, current_prices_jpy=prices)

        assert len(valuations) == 1
        assert valuations[0].ticker == "AAPL"
