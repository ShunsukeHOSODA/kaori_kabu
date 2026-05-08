"""Growth サブスコアの単体テスト（Phase 3.1b）。

学術根拠:
    Lynch 1989 "One Up On Wall Street" — PEG 1.0 fair value 基準、テンバガー条件
    Buffett-Munger — 高 ROE × 内部成長の複利効果
    DGR (Dividend Growth Rate) — 配当持続力の代理指標

スコアリング設計（Phase 3.1b）:
    +30 売上 5y CAGR (15%+ で満点、線形)
    +30 EPS 5y CAGR (15%+ で満点)
    +20 配当 5y CAGR (8%+ で満点)
    +20 PEG (≤1.0 で満点、≥2.0 で 0、線形補間)

    PEG = pe_ratio / (earnings_growth_rate * 100)
"""

from __future__ import annotations

from decimal import Decimal

import pytest


@pytest.mark.unit
class TestCalculatePeg:
    def test_正常_PER_成長率_計算(self) -> None:
        from analysis.composite.subscores.growth import calculate_peg

        # PER=20, growth=20% → PEG = 20 / 20 = 1.0
        peg = calculate_peg(
            pe_ratio=Decimal("20"),
            earnings_growth_rate=Decimal("0.20"),
        )
        assert peg == Decimal("1.0")

    def test_ゼロ成長率_None返す(self) -> None:
        from analysis.composite.subscores.growth import calculate_peg

        assert (
            calculate_peg(pe_ratio=Decimal("20"), earnings_growth_rate=Decimal("0"))
            is None
        )

    def test_負成長率_None返す(self) -> None:
        """マイナス成長は PEG 計算が破綻するため None。"""
        from analysis.composite.subscores.growth import calculate_peg

        assert (
            calculate_peg(
                pe_ratio=Decimal("20"), earnings_growth_rate=Decimal("-0.05")
            )
            is None
        )

    def test_負PER_None返す(self) -> None:
        """赤字 PER は無効値として扱う。"""
        from analysis.composite.subscores.growth import calculate_peg

        assert (
            calculate_peg(
                pe_ratio=Decimal("-15"), earnings_growth_rate=Decimal("0.10")
            )
            is None
        )

    def test_None入力_None返す(self) -> None:
        from analysis.composite.subscores.growth import calculate_peg

        assert (
            calculate_peg(pe_ratio=None, earnings_growth_rate=Decimal("0.10")) is None
        )
        assert calculate_peg(pe_ratio=Decimal("20"), earnings_growth_rate=None) is None


@pytest.mark.unit
class TestComputeGrowthSubScore:
    def test_テンバガー候補_満点(self) -> None:
        """売上 25% / EPS 30% / 配当 12% / PEG 0.8 → 満点付近。"""
        from analysis.composite.subscores.growth import (
            GrowthSubScoreInputs,
            compute_growth_subscore,
        )

        result = compute_growth_subscore(
            GrowthSubScoreInputs(
                revenue_5y_cagr=Decimal("0.25"),
                eps_5y_cagr=Decimal("0.30"),
                dividend_5y_cagr=Decimal("0.12"),
                pe_ratio=Decimal("16"),
                earnings_growth_rate=Decimal("0.20"),
            )
        )
        assert result.score >= 95.0

    def test_停滞企業_低スコア(self) -> None:
        """売上 1% / EPS 0% / 配当 0% / PEG 3.0 → 低スコア。"""
        from analysis.composite.subscores.growth import (
            GrowthSubScoreInputs,
            compute_growth_subscore,
        )

        result = compute_growth_subscore(
            GrowthSubScoreInputs(
                revenue_5y_cagr=Decimal("0.01"),
                eps_5y_cagr=Decimal("0.00"),
                dividend_5y_cagr=Decimal("0.00"),
                pe_ratio=Decimal("30"),
                earnings_growth_rate=Decimal("0.10"),
            )
        )
        assert result.score < 10.0

    def test_中位成長_中位スコア(self) -> None:
        """売上 7.5% / EPS 7.5% / 配当 4% / PEG 1.5 → 約 50%。"""
        from analysis.composite.subscores.growth import (
            GrowthSubScoreInputs,
            compute_growth_subscore,
        )

        result = compute_growth_subscore(
            GrowthSubScoreInputs(
                revenue_5y_cagr=Decimal("0.075"),
                eps_5y_cagr=Decimal("0.075"),
                dividend_5y_cagr=Decimal("0.04"),
                pe_ratio=Decimal("15"),
                earnings_growth_rate=Decimal("0.10"),
            )
        )
        # rev=15, eps=15, div=10, peg=10 → 50
        assert 45.0 <= result.score <= 55.0

    def test_PEG_1以下_満点(self) -> None:
        """PEG ≤ 1.0 は割安成長として PEG 軸満点。"""
        from analysis.composite.subscores.growth import (
            GrowthSubScoreInputs,
            compute_growth_subscore,
        )

        result = compute_growth_subscore(
            GrowthSubScoreInputs(
                revenue_5y_cagr=Decimal("0.0"),
                eps_5y_cagr=Decimal("0.0"),
                dividend_5y_cagr=Decimal("0.0"),
                pe_ratio=Decimal("10"),
                earnings_growth_rate=Decimal("0.20"),
            )
        )
        # PEG = 10 / 20 = 0.5 → 満点 20
        assert result.components["peg_pts"] == 20.0

    def test_PEG_2以上_ゼロ(self) -> None:
        """PEG ≥ 2.0 は割高成長として PEG 軸ゼロ。"""
        from analysis.composite.subscores.growth import (
            GrowthSubScoreInputs,
            compute_growth_subscore,
        )

        result = compute_growth_subscore(
            GrowthSubScoreInputs(
                revenue_5y_cagr=Decimal("0.0"),
                eps_5y_cagr=Decimal("0.0"),
                dividend_5y_cagr=Decimal("0.0"),
                pe_ratio=Decimal("40"),
                earnings_growth_rate=Decimal("0.10"),
            )
        )
        # PEG = 40 / 10 = 4.0 → 0 点
        assert result.components["peg_pts"] == 0.0

    def test_負成長_スコア0(self) -> None:
        """マイナス成長は CAGR 各軸 0 点（ペナルティはなし）。"""
        from analysis.composite.subscores.growth import (
            GrowthSubScoreInputs,
            compute_growth_subscore,
        )

        result = compute_growth_subscore(
            GrowthSubScoreInputs(
                revenue_5y_cagr=Decimal("-0.05"),
                eps_5y_cagr=Decimal("-0.10"),
                dividend_5y_cagr=Decimal("-0.02"),
                pe_ratio=Decimal("-15"),  # 赤字
                earnings_growth_rate=Decimal("-0.05"),
            )
        )
        assert result.score == 0.0

    def test_None入力_スコア0(self) -> None:
        from analysis.composite.subscores.growth import (
            GrowthSubScoreInputs,
            compute_growth_subscore,
        )

        result = compute_growth_subscore(
            GrowthSubScoreInputs(
                revenue_5y_cagr=None,
                eps_5y_cagr=None,
                dividend_5y_cagr=None,
                pe_ratio=None,
                earnings_growth_rate=None,
            )
        )
        assert result.score == 0.0
        assert result.peg is None

    def test_部分入力_利用可能軸のみ計算(self) -> None:
        """配当なし企業（成長株）でも他軸でスコアが付く。"""
        from analysis.composite.subscores.growth import (
            GrowthSubScoreInputs,
            compute_growth_subscore,
        )

        result = compute_growth_subscore(
            GrowthSubScoreInputs(
                revenue_5y_cagr=Decimal("0.20"),
                eps_5y_cagr=Decimal("0.20"),
                dividend_5y_cagr=None,  # 無配グロース
                pe_ratio=Decimal("18"),
                earnings_growth_rate=Decimal("0.20"),
            )
        )
        # rev=30, eps=30, div=0, peg=20 → 80
        assert 78.0 <= result.score <= 82.0

    def test_components_breakdown(self) -> None:
        from analysis.composite.subscores.growth import (
            GrowthSubScoreInputs,
            compute_growth_subscore,
        )

        result = compute_growth_subscore(
            GrowthSubScoreInputs(
                revenue_5y_cagr=Decimal("0.15"),
                eps_5y_cagr=Decimal("0.15"),
                dividend_5y_cagr=Decimal("0.08"),
                pe_ratio=Decimal("15"),
                earnings_growth_rate=Decimal("0.15"),
            )
        )
        assert "revenue_cagr_pts" in result.components
        assert "eps_cagr_pts" in result.components
        assert "dividend_cagr_pts" in result.components
        assert "peg_pts" in result.components
