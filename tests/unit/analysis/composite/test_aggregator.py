"""Composite Score aggregator の統合テスト（Phase 3.1b）。

各サブスコア単体テストは subscores/ 配下、本テストは aggregator
（presets + warnings + 7 軸合算）の振る舞いを担保する。

Phase 3.1b で軸を 4 → 7 に拡張（Q/V/I/G/R/M/S）。V/G/M 入力を省略した場合は
Phase 3.1a 互換動作（該当軸 0 点）を維持する。
"""

from __future__ import annotations

from decimal import Decimal

import pytest


def _coca_cola_inputs():  # type: ignore[no-untyped-def]
    """Coca-Cola 風: 高品質 + 高配当 + 低リスク + 中立センチメント。"""
    from analysis.composite.aggregator import CompositeScoreInputs
    from analysis.composite.subscores.income import IncomeSubScoreInputs
    from analysis.composite.subscores.quality import QualitySubScoreInputs
    from analysis.composite.subscores.risk import RiskSubScoreInputs

    return CompositeScoreInputs(
        income=IncomeSubScoreInputs(
            forward_dividend_per_share_jpy=Decimal("40"),
            current_price_jpy=Decimal("1000"),
            payout_ratio=Decimal("0.55"),
            consecutive_dividend_years=25,
            buybacks_4q_jpy=Decimal("5000000000"),
            market_cap_jpy=Decimal("100000000000"),
            free_cash_flow_jpy=Decimal("8000000000"),
            enterprise_value_jpy=Decimal("100000000000"),
            sector="Consumer Staples",
        ),
        risk=RiskSubScoreInputs(
            working_capital_jpy=Decimal("300"),
            retained_earnings_jpy=Decimal("400"),
            ebit_jpy=Decimal("150"),
            market_cap_jpy=Decimal("2000"),
            total_liabilities_jpy=Decimal("1000"),
            sales_jpy=Decimal("1000"),
            total_assets_jpy=Decimal("1000"),
            net_debt_jpy=Decimal("100"),
            ebitda_jpy=Decimal("200"),
            short_interest_pct=Decimal("0.02"),
            consecutive_loss_years=0,
            beneish_m_score=-2.5,
        ),
        quality=QualitySubScoreInputs(
            roe=Decimal("0.25"),
            roa=Decimal("0.12"),
            gross_margin=Decimal("0.45"),
        ),
        sentiment_score=Decimal("0.3"),
        sentiment_confidence=Decimal("0.7"),
        momentum_12m_return=Decimal("0.10"),
    )


def _distressed_inputs():  # type: ignore[no-untyped-def]
    """破綻寸前: 連続赤字 + 負債過多 + 低品質。"""
    from analysis.composite.aggregator import CompositeScoreInputs
    from analysis.composite.subscores.income import IncomeSubScoreInputs
    from analysis.composite.subscores.quality import QualitySubScoreInputs
    from analysis.composite.subscores.risk import RiskSubScoreInputs

    return CompositeScoreInputs(
        income=IncomeSubScoreInputs(
            forward_dividend_per_share_jpy=None,
            current_price_jpy=Decimal("100"),
            payout_ratio=None,
            consecutive_dividend_years=0,
            buybacks_4q_jpy=Decimal("0"),
            market_cap_jpy=Decimal("100000000"),
            free_cash_flow_jpy=Decimal("-50000000"),
            enterprise_value_jpy=Decimal("100000000"),
            sector="Industrials",
        ),
        risk=RiskSubScoreInputs(
            working_capital_jpy=Decimal("-200"),
            retained_earnings_jpy=Decimal("-100"),
            ebit_jpy=Decimal("-50"),
            market_cap_jpy=Decimal("100"),
            total_liabilities_jpy=Decimal("1000"),
            sales_jpy=Decimal("500"),
            total_assets_jpy=Decimal("1000"),
            net_debt_jpy=Decimal("1200"),
            ebitda_jpy=Decimal("200"),
            short_interest_pct=Decimal("0.20"),
            consecutive_loss_years=4,
            beneish_m_score=-1.0,
        ),
        quality=QualitySubScoreInputs(
            roe=Decimal("-0.05"),
            roa=Decimal("-0.02"),
            gross_margin=Decimal("0.10"),
        ),
        sentiment_score=Decimal("-0.5"),
        sentiment_confidence=Decimal("0.6"),
        momentum_12m_return=Decimal("-0.40"),
    )


@pytest.mark.unit
class TestComputeCompositeScore:
    def test_Coca_Cola風_配当再投資型_高スコア(self) -> None:
        from analysis.composite.aggregator import compute_composite_score

        result = compute_composite_score(
            _coca_cola_inputs(), preset_name="配当再投資型"
        )
        assert result.composite_score >= 60.0
        assert result.preset_name == "配当再投資型"
        assert set(result.sub_scores.keys()) == {"Q", "V", "I", "G", "R", "M", "S"}

    def test_破綻寸前企業_低スコア_警告複数(self) -> None:
        from analysis.composite.aggregator import compute_composite_score

        result = compute_composite_score(
            _distressed_inputs(), preset_name="Buffett_型_暫定"
        )
        assert result.composite_score < 40.0
        warning_codes = {w.code for w in result.warnings}
        assert "ALTMAN_DISTRESS" in warning_codes
        assert "LOSS_3Y" in warning_codes

    def test_プリセット切替で重みが変わる(self) -> None:
        from analysis.composite.aggregator import compute_composite_score

        buf = compute_composite_score(
            _coca_cola_inputs(), preset_name="Buffett_型_暫定"
        )
        div = compute_composite_score(
            _coca_cola_inputs(), preset_name="配当再投資型"
        )
        assert buf.weights["I"] != div.weights["I"]

    def test_未知のプリセット_例外(self) -> None:
        from analysis.composite.aggregator import compute_composite_score

        with pytest.raises(ValueError, match="Unknown preset"):
            compute_composite_score(
                _coca_cola_inputs(), preset_name="存在しない型"
            )

    def test_スコアは0_100にクリップ(self) -> None:
        from analysis.composite.aggregator import compute_composite_score

        for preset in ("Buffett_型_暫定", "配当再投資型", "Lynch_型", "逆張り型"):
            for inp in (_coca_cola_inputs(), _distressed_inputs()):
                result = compute_composite_score(inp, preset_name=preset)
                assert 0.0 <= result.composite_score <= 100.0
                for axis_score in result.sub_scores.values():
                    assert 0.0 <= axis_score <= 100.0


@pytest.mark.unit
class TestPresetWeights:
    def test_全プリセットの重み合計100(self) -> None:
        from analysis.composite.presets import (
            INVESTOR_PRESETS_PHASE_3_1B,
            validate_preset_weights,
        )

        for _name, weights in INVESTOR_PRESETS_PHASE_3_1B.items():
            validate_preset_weights(weights)

    def test_Phase_3_1A_エイリアスは_3_1B_と同一(self) -> None:
        """下位互換エイリアスが Phase 3.1B 本体を指していることを確認。"""
        from analysis.composite.presets import (
            INVESTOR_PRESETS_PHASE_3_1A,
            INVESTOR_PRESETS_PHASE_3_1B,
        )

        assert INVESTOR_PRESETS_PHASE_3_1A is INVESTOR_PRESETS_PHASE_3_1B

    def test_5プリセット存在(self) -> None:
        from analysis.composite.presets import INVESTOR_PRESETS_PHASE_3_1B

        assert set(INVESTOR_PRESETS_PHASE_3_1B.keys()) == {
            "Buffett_型_暫定",
            "配当再投資型",
            "Lynch_型",
            "逆張り型",
            "モメンタム型",
        }

    def test_全プリセット_7軸定義済み(self) -> None:
        from analysis.composite.presets import INVESTOR_PRESETS_PHASE_3_1B

        for _name, weights in INVESTOR_PRESETS_PHASE_3_1B.items():
            assert set(weights.keys()) == {"Q", "V", "I", "G", "R", "M", "S"}


def _growth_star_inputs():  # type: ignore[no-untyped-def]
    """成長株: 高 EY/CAGR/PEG 良好、配当少 + 高モメンタム。"""
    from analysis.composite.aggregator import CompositeScoreInputs
    from analysis.composite.subscores.growth import GrowthSubScoreInputs
    from analysis.composite.subscores.income import IncomeSubScoreInputs
    from analysis.composite.subscores.momentum import MomentumSubScoreInputs
    from analysis.composite.subscores.quality import QualitySubScoreInputs
    from analysis.composite.subscores.risk import RiskSubScoreInputs
    from analysis.composite.subscores.value import ValueSubScoreInputs

    return CompositeScoreInputs(
        income=IncomeSubScoreInputs(
            forward_dividend_per_share_jpy=Decimal("5"),
            current_price_jpy=Decimal("1000"),
            payout_ratio=Decimal("0.10"),
            consecutive_dividend_years=2,
            buybacks_4q_jpy=Decimal("0"),
            market_cap_jpy=Decimal("100000000000"),
            free_cash_flow_jpy=Decimal("4000000000"),
            enterprise_value_jpy=Decimal("100000000000"),
            sector="Technology",
        ),
        risk=RiskSubScoreInputs(
            working_capital_jpy=Decimal("500"),
            retained_earnings_jpy=Decimal("600"),
            ebit_jpy=Decimal("200"),
            market_cap_jpy=Decimal("3000"),
            total_liabilities_jpy=Decimal("500"),
            sales_jpy=Decimal("1500"),
            total_assets_jpy=Decimal("2000"),
            net_debt_jpy=Decimal("0"),
            ebitda_jpy=Decimal("250"),
            short_interest_pct=Decimal("0.03"),
            consecutive_loss_years=0,
            beneish_m_score=-2.0,
        ),
        quality=QualitySubScoreInputs(
            roe=Decimal("0.20"),
            roa=Decimal("0.10"),
            gross_margin=Decimal("0.50"),
        ),
        sentiment_score=Decimal("0.5"),
        sentiment_confidence=Decimal("0.7"),
        momentum_12m_return=Decimal("0.30"),
        value=ValueSubScoreInputs(
            ebit_jpy=Decimal("200"),
            enterprise_value_jpy=Decimal("2000"),
        ),
        growth=GrowthSubScoreInputs(
            revenue_5y_cagr=Decimal("0.25"),
            eps_5y_cagr=Decimal("0.30"),
            dividend_5y_cagr=Decimal("0.10"),
            pe_ratio=Decimal("18"),
            earnings_growth_rate=Decimal("0.20"),
        ),
        momentum=MomentumSubScoreInputs(
            return_12m=Decimal("0.30"),
            return_1m=Decimal("0.06"),
        ),
    )


@pytest.mark.unit
class TestSevenAxisAggregation:
    """Phase 3.1b で追加された V/G/M 軸の統合動作を担保。"""

    def test_成長株_Lynch型_高スコア(self) -> None:
        from analysis.composite.aggregator import compute_composite_score

        result = compute_composite_score(
            _growth_star_inputs(), preset_name="Lynch_型"
        )
        assert result.composite_score >= 70.0
        assert result.value is not None
        assert result.growth is not None
        assert result.momentum is not None

    def test_配当王_逆張り型_深割安銘柄選好(self) -> None:
        """逆張り型は V=35 重みなので、Coca-Cola 風（V=20%）でも合計が伸びる。"""
        from analysis.composite.aggregator import compute_composite_score
        from analysis.composite.subscores.value import ValueSubScoreInputs

        base = _coca_cola_inputs()
        # Coca-Cola 風 + V 軸を追加（EBIT/EV=10%）
        from analysis.composite.aggregator import CompositeScoreInputs

        with_value = CompositeScoreInputs(
            income=base.income,
            risk=base.risk,
            quality=base.quality,
            sentiment_score=base.sentiment_score,
            sentiment_confidence=base.sentiment_confidence,
            momentum_12m_return=base.momentum_12m_return,
            value=ValueSubScoreInputs(
                ebit_jpy=Decimal("100"),
                enterprise_value_jpy=Decimal("1000"),
            ),
        )
        result = compute_composite_score(with_value, preset_name="逆張り型")
        assert result.value is not None
        assert result.value.score > 50.0  # 10% EY → スコア 83 程度

    def test_VGM入力なし_該当軸0点(self) -> None:
        """Phase 3.1a 互換動作: V/G/M を渡さなければ 0 点固定。"""
        from analysis.composite.aggregator import compute_composite_score

        result = compute_composite_score(
            _coca_cola_inputs(), preset_name="Buffett_型_暫定"
        )
        assert result.sub_scores["V"] == 0.0
        assert result.sub_scores["G"] == 0.0
        assert result.sub_scores["M"] == 0.0
        assert result.value is None
        assert result.growth is None
        assert result.momentum is None

    def test_新プリセット_Lynch型_例外ならない(self) -> None:
        from analysis.composite.aggregator import compute_composite_score

        result = compute_composite_score(
            _growth_star_inputs(), preset_name="Lynch_型"
        )
        assert result.preset_name == "Lynch_型"

    def test_新プリセット_逆張り型_例外ならない(self) -> None:
        from analysis.composite.aggregator import compute_composite_score

        result = compute_composite_score(
            _growth_star_inputs(), preset_name="逆張り型"
        )
        assert result.preset_name == "逆張り型"


@pytest.mark.unit
class TestFallingKnifeWarning:
    """kabu-analyst 推奨 Falling Knife 警告の検証。"""

    def test_Falling_Knife警告発火(self) -> None:
        from analysis.composite.aggregator import (
            CompositeScoreInputs,
            compute_composite_score,
        )

        base = _coca_cola_inputs()
        falling_inputs = CompositeScoreInputs(
            income=base.income,
            risk=base.risk,
            quality=base.quality,
            sentiment_score=base.sentiment_score,
            sentiment_confidence=base.sentiment_confidence,
            momentum_12m_return=Decimal("-0.30"),
        )
        result = compute_composite_score(
            falling_inputs, preset_name="Buffett_型_暫定"
        )
        codes = {w.code for w in result.warnings}
        assert "FALLING_KNIFE" in codes
