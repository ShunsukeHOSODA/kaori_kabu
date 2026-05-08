"""Sentiment サブスコアの単体テスト（Phase 3.1a）。

既存 SentimentResult (-1〜+1) を 0-100 にマッピング。
"""

from __future__ import annotations

from decimal import Decimal

import pytest


@pytest.mark.unit
class TestComputeSentimentSubScore:
    def test_強気センチメントは高スコア(self) -> None:
        from analysis.composite.subscores.sentiment import (
            compute_sentiment_subscore,
        )

        result = compute_sentiment_subscore(
            sentiment_score=Decimal("0.8"), confidence=Decimal("0.9")
        )
        assert result.score >= 80.0

    def test_弱気センチメントは低スコア(self) -> None:
        from analysis.composite.subscores.sentiment import (
            compute_sentiment_subscore,
        )

        result = compute_sentiment_subscore(
            sentiment_score=Decimal("-0.7"), confidence=Decimal("0.9")
        )
        assert result.score <= 20.0

    def test_中立は50付近(self) -> None:
        from analysis.composite.subscores.sentiment import (
            compute_sentiment_subscore,
        )

        result = compute_sentiment_subscore(
            sentiment_score=Decimal("0"), confidence=Decimal("0.5")
        )
        assert 40.0 <= result.score <= 60.0

    def test_低confidenceは中立寄り(self) -> None:
        from analysis.composite.subscores.sentiment import (
            compute_sentiment_subscore,
        )

        high_conf_bull = compute_sentiment_subscore(
            sentiment_score=Decimal("0.8"), confidence=Decimal("1.0")
        )
        low_conf_bull = compute_sentiment_subscore(
            sentiment_score=Decimal("0.8"), confidence=Decimal("0.0")
        )
        assert abs(low_conf_bull.score - 50.0) < abs(high_conf_bull.score - 50.0)

    def test_スコアは0_100にクリップ(self) -> None:
        from analysis.composite.subscores.sentiment import (
            compute_sentiment_subscore,
        )

        result = compute_sentiment_subscore(
            sentiment_score=Decimal("2.0"), confidence=Decimal("1.0")
        )
        assert 0 <= result.score <= 100
