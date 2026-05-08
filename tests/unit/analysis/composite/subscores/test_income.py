"""Income サブスコアの単体テスト（Phase 3.1a）。

学術根拠:
    - Buffett, Berkshire Annual Letters — 配当再投資 + Buyback yield = 真の株主リターン
    - Asness 2014 — Total Shareholder Yield (dividend + buyback)
    - Sharpe 1991 — Arithmetic of active management（配当の複利効果）

スコアリング設計:
    配当 yield (30) + Buyback yield (25) + FCF yield (20) +
    優待 yield (15) + 連続増配年数 (10) = 100 点満点
    配当性向は GICS セクター別動的閾値でペナルティ
"""

from __future__ import annotations

from decimal import Decimal

import pytest


# ---------------------------------------------------------------------------
# 計算式: yield 系
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestForwardDividendYield:
    """forward dividend per share / current price 比率（年率）。"""

    def test_配当40円_株価1000円_yield_4pct(self) -> None:
        from analysis.composite.subscores.income import (
            calculate_forward_dividend_yield,
        )

        y = calculate_forward_dividend_yield(
            Decimal("40"), Decimal("1000")
        )
        assert y == Decimal("0.04")

    def test_株価ゼロガード_None返却(self) -> None:
        from analysis.composite.subscores.income import (
            calculate_forward_dividend_yield,
        )

        assert (
            calculate_forward_dividend_yield(Decimal("40"), Decimal("0"))
            is None
        )

    def test_配当None_None返却(self) -> None:
        from analysis.composite.subscores.income import (
            calculate_forward_dividend_yield,
        )

        assert (
            calculate_forward_dividend_yield(None, Decimal("1000")) is None
        )


@pytest.mark.unit
class TestBuybackYield:
    """直近 4 四半期 buyback 総額 / 時価総額。"""

    def test_buyback50億_時価1000億_yield_5pct(self) -> None:
        from analysis.composite.subscores.income import calculate_buyback_yield

        y = calculate_buyback_yield(
            Decimal("5000000000"), Decimal("100000000000")
        )
        assert y == Decimal("0.05")

    def test_時価ゼロガード(self) -> None:
        from analysis.composite.subscores.income import calculate_buyback_yield

        assert (
            calculate_buyback_yield(Decimal("100"), Decimal("0")) is None
        )


@pytest.mark.unit
class TestFCFYield:
    """Free Cash Flow / Enterprise Value（配当原資の健全性）。"""

    def test_FCF100億_EV1000億_yield_10pct(self) -> None:
        from analysis.composite.subscores.income import calculate_fcf_yield

        y = calculate_fcf_yield(
            Decimal("10000000000"), Decimal("100000000000")
        )
        assert y == Decimal("0.10")


@pytest.mark.unit
class TestYutaiYield:
    """日本株優待利回り = 優待価値 / (最低保有株数 × 株価)。"""

    def test_5000円優待_100株保有_株価1000円_yield_5pct(self) -> None:
        from analysis.composite.subscores.income import calculate_yutai_yield

        y = calculate_yutai_yield(
            yutai_value_jpy=Decimal("5000"),
            min_shares=100,
            current_price_jpy=Decimal("1000"),
        )
        assert y == Decimal("0.05")

    def test_優待なしはNone返却(self) -> None:
        from analysis.composite.subscores.income import calculate_yutai_yield

        assert (
            calculate_yutai_yield(
                yutai_value_jpy=None,
                min_shares=None,
                current_price_jpy=Decimal("1000"),
            )
            is None
        )


# ---------------------------------------------------------------------------
# サブスコア合算
# ---------------------------------------------------------------------------


def _make_inputs(**overrides):  # type: ignore[no-untyped-def]
    """テスト用デフォルト Inputs（Coca-Cola 風: 高配当 + 連続増配 + buyback）。"""
    from analysis.composite.subscores.income import IncomeSubScoreInputs

    base = {
        "forward_dividend_per_share_jpy": Decimal("40"),
        "current_price_jpy": Decimal("1000"),
        "payout_ratio": Decimal("0.55"),
        "consecutive_dividend_years": 25,
        "buybacks_4q_jpy": Decimal("5000000000"),
        "market_cap_jpy": Decimal("100000000000"),
        "free_cash_flow_jpy": Decimal("8000000000"),
        "enterprise_value_jpy": Decimal("100000000000"),
        "yutai_value_jpy": None,
        "yutai_min_shares": None,
        "sector": "Consumer Staples",
    }
    base.update(overrides)
    return IncomeSubScoreInputs(**base)


@pytest.mark.unit
class TestComputeIncomeSubScore:
    """配当 + Buyback + FCF + 優待 + 連続増配 を 0-100 にマッピング。"""

    def test_Coca_Cola風_高スコア(self) -> None:
        """配当 4% + Buyback 5% + FCF 8% + 連続増配 25 年 → 70 点以上。"""
        from analysis.composite.subscores.income import compute_income_subscore

        result = compute_income_subscore(_make_inputs())

        assert result.score >= 70.0
        assert result.forward_dividend_yield == Decimal("0.04")
        assert result.buyback_yield == Decimal("0.05")
        assert result.fcf_yield == Decimal("0.08")
        # 真の株主リターン = 配当 + Buyback
        assert result.total_shareholder_yield == Decimal("0.09")
        assert result.consecutive_dividend_years == 25

    def test_無配当_買い戻しなし_低スコア(self) -> None:
        """配当ゼロ + buyback ゼロ + FCF ゼロ → 10 点未満。"""
        from analysis.composite.subscores.income import compute_income_subscore

        result = compute_income_subscore(
            _make_inputs(
                forward_dividend_per_share_jpy=None,
                payout_ratio=None,
                consecutive_dividend_years=0,
                buybacks_4q_jpy=Decimal("0"),
                free_cash_flow_jpy=Decimal("0"),
            )
        )

        assert result.score < 10.0
        assert result.forward_dividend_yield is None
        assert result.buyback_yield == Decimal("0")
        assert result.total_shareholder_yield == Decimal("0")

    def test_スコアは0_100にクリップ(self) -> None:
        """yield を極端な値に振っても 0-100 範囲を逸脱しない。"""
        from analysis.composite.subscores.income import compute_income_subscore

        high = compute_income_subscore(
            _make_inputs(
                forward_dividend_per_share_jpy=Decimal("500"),
                buybacks_4q_jpy=Decimal("50000000000"),
                free_cash_flow_jpy=Decimal("50000000000"),
                consecutive_dividend_years=100,
                yutai_value_jpy=Decimal("100000"),
                yutai_min_shares=100,
            )
        )
        assert 0 <= high.score <= 100

        low = compute_income_subscore(
            _make_inputs(
                forward_dividend_per_share_jpy=None,
                buybacks_4q_jpy=Decimal("0"),
                free_cash_flow_jpy=Decimal("-1000000000"),
                consecutive_dividend_years=0,
            )
        )
        assert 0 <= low.score <= 100

    def test_優待付き日本株は加点(self) -> None:
        """優待 yield 3% で +10 点以上の加点。"""
        from analysis.composite.subscores.income import compute_income_subscore

        without_yutai = compute_income_subscore(_make_inputs())
        with_yutai = compute_income_subscore(
            _make_inputs(
                yutai_value_jpy=Decimal("3000"),
                yutai_min_shares=100,
            )
        )

        assert with_yutai.score > without_yutai.score
        assert with_yutai.yutai_yield == Decimal("0.03")

    def test_配当性向高Tech企業はペナルティ(self) -> None:
        """Tech セクターは配当性向 60% 超でペナルティ（成長投資優先業界）。"""
        from analysis.composite.subscores.income import compute_income_subscore

        normal = compute_income_subscore(
            _make_inputs(payout_ratio=Decimal("0.40"), sector="Technology")
        )
        high_payout = compute_income_subscore(
            _make_inputs(payout_ratio=Decimal("0.85"), sector="Technology")
        )

        assert high_payout.score < normal.score

    def test_配当性向高REITはペナルティ少ない(self) -> None:
        """REIT は法律上 90% 配当義務、高 payout は正常。"""
        from analysis.composite.subscores.income import compute_income_subscore

        reit_high = compute_income_subscore(
            _make_inputs(payout_ratio=Decimal("0.90"), sector="Real Estate")
        )
        assert "payout_penalty" in reit_high.components
        assert reit_high.components["payout_penalty"] == 0.0


@pytest.mark.unit
class TestComponentsBreakdown:
    """components 辞書で内訳が確認できる（Provenance/UI 表示用）。"""

    def test_components_に各構成要素のスコアが含まれる(self) -> None:
        from analysis.composite.subscores.income import compute_income_subscore

        result = compute_income_subscore(_make_inputs())

        assert "dividend_yield_pts" in result.components
        assert "buyback_yield_pts" in result.components
        assert "fcf_yield_pts" in result.components
        assert "consecutive_years_pts" in result.components
        assert "yutai_yield_pts" in result.components
        assert "payout_penalty" in result.components
        total = sum(result.components.values())
        assert abs(total - result.score) < 0.01 or result.score in (0.0, 100.0)
