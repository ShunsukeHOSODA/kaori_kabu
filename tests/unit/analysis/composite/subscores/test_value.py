"""Value サブスコアの単体テスト（Phase 3.1b）。

学術根拠:
    Greenblatt 2010 — Magic Formula の EY (Earnings Yield = EBIT/EV)
    Asness et al. 2013 — Value factor (HML) は B/P, E/P, CF/P の合成
    Fama-French 1992 — Value premium の存在実証

スコアリング設計（Phase 3.1b 暫定 — EY 単独）:
    score = clip(EY / 0.12 * 100, 0, 100)
    - EY = 12%+ で満点（Greenblatt Top 30 銘柄相当の上位 EY 水準）
    - EY ≦ 0% （赤字会社）で 0 点
    - 線形補間
"""

from __future__ import annotations

from decimal import Decimal

import pytest


@pytest.mark.unit
class TestCalculateEarningsYield:
    def test_正常_EBIT_EV_計算(self) -> None:
        from analysis.composite.subscores.value import calculate_earnings_yield

        ey = calculate_earnings_yield(
            ebit_jpy=Decimal("1200"), enterprise_value_jpy=Decimal("10000")
        )
        assert ey == Decimal("0.12")

    def test_ゼロEV_None返す(self) -> None:
        from analysis.composite.subscores.value import calculate_earnings_yield

        ey = calculate_earnings_yield(
            ebit_jpy=Decimal("100"), enterprise_value_jpy=Decimal("0")
        )
        assert ey is None

    def test_負EV_None返す(self) -> None:
        """純現金 > 時価総額（実質マイナス EV）— ランキング解釈が破綻するため None。"""
        from analysis.composite.subscores.value import calculate_earnings_yield

        ey = calculate_earnings_yield(
            ebit_jpy=Decimal("100"), enterprise_value_jpy=Decimal("-500")
        )
        assert ey is None

    def test_None入力_None返す(self) -> None:
        from analysis.composite.subscores.value import calculate_earnings_yield

        assert (
            calculate_earnings_yield(
                ebit_jpy=None, enterprise_value_jpy=Decimal("10000")
            )
            is None
        )
        assert (
            calculate_earnings_yield(
                ebit_jpy=Decimal("1000"), enterprise_value_jpy=None
            )
            is None
        )

    def test_負EBIT_負EY返す(self) -> None:
        """赤字会社の EY は負の値で返し、スコアラー側で 0 点に丸める。"""
        from analysis.composite.subscores.value import calculate_earnings_yield

        ey = calculate_earnings_yield(
            ebit_jpy=Decimal("-500"), enterprise_value_jpy=Decimal("10000")
        )
        assert ey == Decimal("-0.05")


@pytest.mark.unit
class TestComputeValueSubScore:
    def test_深割安_満点(self) -> None:
        from analysis.composite.subscores.value import (
            ValueSubScoreInputs,
            compute_value_subscore,
        )

        result = compute_value_subscore(
            ValueSubScoreInputs(
                ebit_jpy=Decimal("1500"),
                enterprise_value_jpy=Decimal("10000"),
            )
        )
        assert result.score == 100.0
        assert result.earnings_yield == Decimal("0.15")

    def test_中位EY_中位スコア(self) -> None:
        from analysis.composite.subscores.value import (
            ValueSubScoreInputs,
            compute_value_subscore,
        )

        result = compute_value_subscore(
            ValueSubScoreInputs(
                ebit_jpy=Decimal("600"),
                enterprise_value_jpy=Decimal("10000"),
            )
        )
        # EY = 6% → 6/12 * 100 = 50
        assert 49.0 <= result.score <= 51.0

    def test_低EY_低スコア(self) -> None:
        from analysis.composite.subscores.value import (
            ValueSubScoreInputs,
            compute_value_subscore,
        )

        result = compute_value_subscore(
            ValueSubScoreInputs(
                ebit_jpy=Decimal("200"),
                enterprise_value_jpy=Decimal("10000"),
            )
        )
        # EY = 2% → 2/12 * 100 ≈ 16.67
        assert 16.0 <= result.score <= 18.0

    def test_負EBIT_スコア0(self) -> None:
        from analysis.composite.subscores.value import (
            ValueSubScoreInputs,
            compute_value_subscore,
        )

        result = compute_value_subscore(
            ValueSubScoreInputs(
                ebit_jpy=Decimal("-500"),
                enterprise_value_jpy=Decimal("10000"),
            )
        )
        assert result.score == 0.0

    def test_None入力_スコア0(self) -> None:
        from analysis.composite.subscores.value import (
            ValueSubScoreInputs,
            compute_value_subscore,
        )

        result = compute_value_subscore(
            ValueSubScoreInputs(ebit_jpy=None, enterprise_value_jpy=None)
        )
        assert result.score == 0.0
        assert result.earnings_yield is None

    def test_ゼロEV_スコア0(self) -> None:
        from analysis.composite.subscores.value import (
            ValueSubScoreInputs,
            compute_value_subscore,
        )

        result = compute_value_subscore(
            ValueSubScoreInputs(
                ebit_jpy=Decimal("100"),
                enterprise_value_jpy=Decimal("0"),
            )
        )
        assert result.score == 0.0
        assert result.earnings_yield is None

    def test_components_breakdown(self) -> None:
        from analysis.composite.subscores.value import (
            ValueSubScoreInputs,
            compute_value_subscore,
        )

        result = compute_value_subscore(
            ValueSubScoreInputs(
                ebit_jpy=Decimal("1200"),
                enterprise_value_jpy=Decimal("10000"),
            )
        )
        assert "ey_pts" in result.components
        assert result.components["ey_pts"] == result.score
