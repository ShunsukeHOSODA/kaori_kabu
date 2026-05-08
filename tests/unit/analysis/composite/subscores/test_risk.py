"""Risk サブスコアの単体テスト（Phase 3.1a）。

学術根拠:
    Altman 1968 — Z-Score（破綻予測 Z < 1.81 で Distress Zone）
    Beneish 1999 — M-Score（不正会計検知 M > -1.78 で疑い）
    Dalio (Ray) — 純有利子負債/EBITDA で減配・破綻を予測

スコアリング設計（リスク低 = 高得点、合計 100 点満点）:
    +40 Altman Z（≥ 2.99 で満点、< 1.81 でゼロ）
    +15 Beneish M（< -1.78 で満点、≥ -1.78 でゼロ）
    +25 Net Debt/EBITDA（≤ 0 で満点、> 5 でゼロ）
    +10 Short interest（< 5% で満点、> 15% でゼロ）
    +10 連続赤字（0 年で満点、3+ 年で -10 ペナルティ）
"""

from __future__ import annotations

from decimal import Decimal

import pytest


@pytest.mark.unit
class TestAltmanZScore:
    """Z = 1.2A + 1.4B + 3.3C + 0.6D + 1.0E。"""

    def test_健全企業_Z_3_以上(self) -> None:
        from analysis.composite.subscores.risk import calculate_altman_z

        z = calculate_altman_z(
            working_capital=Decimal("300"),
            retained_earnings=Decimal("400"),
            ebit=Decimal("150"),
            market_cap=Decimal("2000"),
            total_liabilities=Decimal("1000"),
            sales=Decimal("1000"),
            total_assets=Decimal("1000"),
        )
        assert z is not None
        assert z >= 3.0

    def test_破綻リスク企業_Z_1_8未満(self) -> None:
        from analysis.composite.subscores.risk import calculate_altman_z

        z = calculate_altman_z(
            working_capital=Decimal("-200"),
            retained_earnings=Decimal("-100"),
            ebit=Decimal("10"),
            market_cap=Decimal("100"),
            total_liabilities=Decimal("1000"),
            sales=Decimal("500"),
            total_assets=Decimal("1000"),
        )
        assert z is not None
        assert z < 1.81

    def test_総資産ゼロガード(self) -> None:
        from analysis.composite.subscores.risk import calculate_altman_z

        assert (
            calculate_altman_z(
                working_capital=Decimal("0"),
                retained_earnings=Decimal("0"),
                ebit=Decimal("0"),
                market_cap=Decimal("0"),
                total_liabilities=Decimal("100"),
                sales=Decimal("0"),
                total_assets=Decimal("0"),
            )
            is None
        )


@pytest.mark.unit
class TestNetDebtEbitdaRatio:
    """純有利子負債 / EBITDA。3 倍超で警戒、5 倍超で危険。"""

    def test_負債100億_EBITDA50億_ratio_2(self) -> None:
        from analysis.composite.subscores.risk import calculate_net_debt_ebitda

        r = calculate_net_debt_ebitda(
            net_debt=Decimal("10000000000"),
            ebitda=Decimal("5000000000"),
        )
        assert r == Decimal("2")

    def test_NetCash_負の比率(self) -> None:
        from analysis.composite.subscores.risk import calculate_net_debt_ebitda

        r = calculate_net_debt_ebitda(
            net_debt=Decimal("-5000000000"),
            ebitda=Decimal("5000000000"),
        )
        assert r == Decimal("-1")

    def test_EBITDAゼロガード(self) -> None:
        from analysis.composite.subscores.risk import calculate_net_debt_ebitda

        assert (
            calculate_net_debt_ebitda(Decimal("100"), Decimal("0")) is None
        )


def _make_inputs(**overrides):  # type: ignore[no-untyped-def]
    """テスト用デフォルト Inputs（健全企業）。"""
    from analysis.composite.subscores.risk import RiskSubScoreInputs

    base = {
        "working_capital_jpy": Decimal("300"),
        "retained_earnings_jpy": Decimal("400"),
        "ebit_jpy": Decimal("150"),
        "market_cap_jpy": Decimal("2000"),
        "total_liabilities_jpy": Decimal("1000"),
        "sales_jpy": Decimal("1000"),
        "total_assets_jpy": Decimal("1000"),
        "net_debt_jpy": Decimal("100"),
        "ebitda_jpy": Decimal("200"),
        "short_interest_pct": Decimal("0.02"),
        "consecutive_loss_years": 0,
        "beneish_m_score": -2.5,
    }
    base.update(overrides)
    return RiskSubScoreInputs(**base)


@pytest.mark.unit
class TestComputeRiskSubScore:
    """5 構成要素を 0-100 にマッピング。リスク低=高得点。"""

    def test_健全企業_高スコア(self) -> None:
        from analysis.composite.subscores.risk import compute_risk_subscore

        result = compute_risk_subscore(_make_inputs())

        assert result.score >= 80.0
        assert result.altman_z_score is not None
        assert result.altman_z_score >= 2.99

    def test_破綻リスク企業_低スコア(self) -> None:
        from analysis.composite.subscores.risk import compute_risk_subscore

        result = compute_risk_subscore(
            _make_inputs(
                working_capital_jpy=Decimal("-200"),
                retained_earnings_jpy=Decimal("-100"),
                ebit_jpy=Decimal("10"),
                market_cap_jpy=Decimal("100"),
                net_debt_jpy=Decimal("1200"),
                ebitda_jpy=Decimal("200"),
                consecutive_loss_years=4,
                beneish_m_score=-1.0,
            )
        )

        assert result.score < 30.0
        assert result.altman_z_score is not None
        assert result.altman_z_score < 1.81

    def test_NetCash企業はボーナス(self) -> None:
        from analysis.composite.subscores.risk import compute_risk_subscore

        net_cash = compute_risk_subscore(
            _make_inputs(net_debt_jpy=Decimal("-500000000000"))
        )
        normal = compute_risk_subscore(_make_inputs())

        assert net_cash.score >= normal.score

    def test_スコアは0_100にクリップ(self) -> None:
        from analysis.composite.subscores.risk import compute_risk_subscore

        bad = compute_risk_subscore(
            _make_inputs(
                working_capital_jpy=Decimal("-10000"),
                retained_earnings_jpy=Decimal("-10000"),
                ebit_jpy=Decimal("-1000"),
                market_cap_jpy=Decimal("10"),
                net_debt_jpy=Decimal("100000"),
                ebitda_jpy=Decimal("100"),
                short_interest_pct=Decimal("0.40"),
                consecutive_loss_years=10,
                beneish_m_score=0.5,
            )
        )
        assert 0 <= bad.score <= 100

        good = compute_risk_subscore(
            _make_inputs(
                net_debt_jpy=Decimal("-10000000000000"),
                short_interest_pct=Decimal("0"),
            )
        )
        assert 0 <= good.score <= 100


@pytest.mark.unit
class TestComponentsBreakdown:
    """components 辞書で内訳が確認できる。"""

    def test_components_に各構成要素のスコアが含まれる(self) -> None:
        from analysis.composite.subscores.risk import compute_risk_subscore

        result = compute_risk_subscore(_make_inputs())

        assert "altman_z_pts" in result.components
        assert "beneish_m_pts" in result.components
        assert "net_debt_ebitda_pts" in result.components
        assert "short_interest_pts" in result.components
        assert "loss_years_pts" in result.components
