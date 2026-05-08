"""Quality サブスコアの単体テスト（Phase 3.1a 暫定）。

Phase 3.2 で Sloan 1996 Accruals + AQR QMJ に拡張予定。
暫定スコアリング:
    +50 ROE: 20%+ で満点（線形）
    +30 ROA: 10%+ で満点
    +20 Gross margin: 40%+ で満点
"""

from __future__ import annotations

from decimal import Decimal

import pytest


@pytest.mark.unit
class TestComputeQualitySubScore:
    def test_高品質企業_高スコア(self) -> None:
        from analysis.composite.subscores.quality import (
            QualitySubScoreInputs,
            compute_quality_subscore,
        )

        result = compute_quality_subscore(
            QualitySubScoreInputs(
                roe=Decimal("0.25"),
                roa=Decimal("0.12"),
                gross_margin=Decimal("0.45"),
            )
        )
        assert result.score >= 90.0

    def test_低品質企業_低スコア(self) -> None:
        from analysis.composite.subscores.quality import (
            QualitySubScoreInputs,
            compute_quality_subscore,
        )

        result = compute_quality_subscore(
            QualitySubScoreInputs(
                roe=Decimal("-0.05"),
                roa=Decimal("-0.02"),
                gross_margin=Decimal("0.10"),
            )
        )
        assert result.score < 15.0

    def test_None入力ガード(self) -> None:
        from analysis.composite.subscores.quality import (
            QualitySubScoreInputs,
            compute_quality_subscore,
        )

        result = compute_quality_subscore(
            QualitySubScoreInputs(roe=None, roa=None, gross_margin=None)
        )
        assert result.score == 0.0

    def test_components_breakdown(self) -> None:
        from analysis.composite.subscores.quality import (
            QualitySubScoreInputs,
            compute_quality_subscore,
        )

        result = compute_quality_subscore(
            QualitySubScoreInputs(
                roe=Decimal("0.20"),
                roa=Decimal("0.10"),
                gross_margin=Decimal("0.40"),
            )
        )
        assert "roe_pts" in result.components
        assert "roa_pts" in result.components
        assert "gross_margin_pts" in result.components
