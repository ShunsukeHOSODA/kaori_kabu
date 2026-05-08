"""Momentum サブスコアの単体テスト（Phase 3.1b）。

学術根拠:
    Jegadeesh & Titman (1993). "Returns to Buying Winners and Selling Losers."
        12 ヶ月モメンタムの上位 decile が長期 outperformance を生む。
    AQR Capital Management — Momentum factor (MOM) の標準実装。
    Druckenmiller — トレンドフォロー型の代表例。

スコアリング設計（Phase 3.1b）:
    +60 12m return (25%+ で満点、Jegadeesh-Titman top decile threshold)
    +40 1m return (5%+ で満点、短期トレンド確認)

    負リターンは 0 点（Falling Knife 警告は warnings.py 側が独立判定）。
"""

from __future__ import annotations

from decimal import Decimal

import pytest


@pytest.mark.unit
class TestComputeMomentumSubScore:
    def test_強モメンタム_満点(self) -> None:
        """12m=30% / 1m=8% → 満点。"""
        from analysis.composite.subscores.momentum import (
            MomentumSubScoreInputs,
            compute_momentum_subscore,
        )

        result = compute_momentum_subscore(
            MomentumSubScoreInputs(
                return_12m=Decimal("0.30"),
                return_1m=Decimal("0.08"),
            )
        )
        assert result.score == 100.0

    def test_中位モメンタム_中位スコア(self) -> None:
        """12m=12.5% / 1m=2.5% → 約 50%。"""
        from analysis.composite.subscores.momentum import (
            MomentumSubScoreInputs,
            compute_momentum_subscore,
        )

        result = compute_momentum_subscore(
            MomentumSubScoreInputs(
                return_12m=Decimal("0.125"),
                return_1m=Decimal("0.025"),
            )
        )
        # 12m_pts = 0.125/0.25 * 60 = 30, 1m_pts = 0.025/0.05 * 40 = 20 → 50
        assert 48.0 <= result.score <= 52.0

    def test_負return_スコア0(self) -> None:
        """マイナスリターンは 0 点（ペナルティはなし、警告は別途）。"""
        from analysis.composite.subscores.momentum import (
            MomentumSubScoreInputs,
            compute_momentum_subscore,
        )

        result = compute_momentum_subscore(
            MomentumSubScoreInputs(
                return_12m=Decimal("-0.20"),
                return_1m=Decimal("-0.05"),
            )
        )
        assert result.score == 0.0

    def test_None入力_スコア0(self) -> None:
        from analysis.composite.subscores.momentum import (
            MomentumSubScoreInputs,
            compute_momentum_subscore,
        )

        result = compute_momentum_subscore(
            MomentumSubScoreInputs(return_12m=None, return_1m=None)
        )
        assert result.score == 0.0

    def test_部分入力_12mのみ(self) -> None:
        """12m=20%, 1m=None → 12m 軸のみで点数（48/60）。"""
        from analysis.composite.subscores.momentum import (
            MomentumSubScoreInputs,
            compute_momentum_subscore,
        )

        result = compute_momentum_subscore(
            MomentumSubScoreInputs(
                return_12m=Decimal("0.20"), return_1m=None
            )
        )
        # 0.20/0.25 * 60 = 48
        assert 47.0 <= result.score <= 49.0

    def test_高12m_負1m_部分点(self) -> None:
        """12m=20%, 1m=-2% → 12m のみで点数（48）、1m は 0 点。"""
        from analysis.composite.subscores.momentum import (
            MomentumSubScoreInputs,
            compute_momentum_subscore,
        )

        result = compute_momentum_subscore(
            MomentumSubScoreInputs(
                return_12m=Decimal("0.20"),
                return_1m=Decimal("-0.02"),
            )
        )
        assert 47.0 <= result.score <= 49.0
        assert result.components["return_1m_pts"] == 0.0

    def test_components_breakdown(self) -> None:
        from analysis.composite.subscores.momentum import (
            MomentumSubScoreInputs,
            compute_momentum_subscore,
        )

        result = compute_momentum_subscore(
            MomentumSubScoreInputs(
                return_12m=Decimal("0.25"),
                return_1m=Decimal("0.05"),
            )
        )
        assert "return_12m_pts" in result.components
        assert "return_1m_pts" in result.components
        assert result.components["return_12m_pts"] == 60.0
        assert result.components["return_1m_pts"] == 40.0

    def test_returns_passthrough(self) -> None:
        """入力 returns を結果オブジェクトに保持する。"""
        from analysis.composite.subscores.momentum import (
            MomentumSubScoreInputs,
            compute_momentum_subscore,
        )

        result = compute_momentum_subscore(
            MomentumSubScoreInputs(
                return_12m=Decimal("0.18"),
                return_1m=Decimal("0.03"),
            )
        )
        assert result.return_12m == Decimal("0.18")
        assert result.return_1m == Decimal("0.03")
