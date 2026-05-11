"""ranking_judge.py のユニットテスト — Task 5.2.1 / 5.2.2 TDD（RED → GREEN）。"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest


def _valid_metadata() -> Any:
    """テスト用 RankingMetadata の有効インスタンスを返す。"""
    from src.analysis.ranking_judge import (
        ACADEMIC_SOURCE,
        DEFAULT_MODEL,
        DEFAULT_MODEL_VERSION,
        RankingMetadata,
    )

    return RankingMetadata(
        model=DEFAULT_MODEL,
        model_version=DEFAULT_MODEL_VERSION,
        calculation_method="ranking_judge_v1",
        input_bundle_hash="a" * 64,
        cache_hit=True,
        cache_age_sec=120,
        input_tokens=1200,
        output_tokens=512,
        input_tokens_cached=800,
        calculated_at=datetime(2026, 5, 12, 10, 0, 0, tzinfo=UTC),
        academic_source=ACADEMIC_SOURCE,
        code_commit="ff16b6d",
    )


def _valid_payload() -> dict[str, Any]:
    """RankingResult.model_validate に渡せる正常 payload を返す。"""
    return {
        "ranking_score": 80,
        "recommendation_summary": "質×価値の観点で魅力的",
        "supporting_signals": ("Magic Formula 上位",),
        "risk_signals": ("Value Trap 懸念",),
        "counter_view": "直近 PER 低下は一時的",
        "lens_views": {
            "short_term": "RSI 中立",
            "long_term": "ROC 28%",
            "dividend": "DY 2.5%",
        },
        "confidence": Decimal("0.7"),
        "confidence_adjusted": Decimal("0.6"),
        "kelly_multiplier": Decimal("0.5"),
        "fallback_reason": None,
        "metadata": _valid_metadata(),
    }


class TestForbiddenPatterns:
    @pytest.mark.unit
    @pytest.mark.parametrize(
        "text",
        [
            "AAPL は $200 になる",
            "予想値: ¥30,000",
            "5% 上昇予測",
            "目標株価 $180",
            "target price $250",
            "3 ヶ月以内に高値更新",
            "by 6 months target",
            "forecast price $200",
        ],
    )
    def test_禁止パターンを検出(self, text: str) -> None:
        from src.analysis.ranking_judge import contains_forbidden_pattern

        assert contains_forbidden_pattern(text), f"未検出: {text}"

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "text",
        [
            "Composite Score 85 は質×価値の観点で魅力的",
            "13F で Berkshire が新規買い、スマートマネー追従の余地",
            "Polymarket の Fed 利下げ確率 62% を踏まえ慎重に",
            "リスク要因として Recency Bias 懸念",
        ],
    )
    def test_正常テキストは検出しない(self, text: str) -> None:
        from src.analysis.ranking_judge import contains_forbidden_pattern

        assert not contains_forbidden_pattern(text), f"誤検出: {text}"


class TestRankingResult:
    """Task 5.2.2 — RankingResult Pydantic v2 スキーマの TDD テスト。

    notes-5.2.md §1.2 案 C 採用: extra='forbid' + model_validator(mode='before')
    による 2 層防御で一本線予測フィールドを reject する。
    """

    @pytest.mark.unit
    def test_正常_payload_でインスタンス化できる(self) -> None:
        from src.analysis.ranking_judge import RankingResult

        result = RankingResult.model_validate(_valid_payload())
        assert result.ranking_score == 80
        assert result.lens_views == {
            "short_term": "RSI 中立",
            "long_term": "ROC 28%",
            "dividend": "DY 2.5%",
        }
        assert result.confidence == Decimal("0.7")
        # frozen=True なので set 不可
        with pytest.raises((TypeError, ValueError)):
            result.ranking_score = 90  # type: ignore[misc]

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "forbidden_field",
        [
            "target_price",
            "expected_return",
            "time_horizon",
            "price_target",
            "forecast_price",
        ],
    )
    def test_禁止予測フィールドを_reject(self, forbidden_field: str) -> None:
        from pydantic import ValidationError

        from src.analysis.ranking_judge import RankingResult

        payload = _valid_payload()
        payload[forbidden_field] = "irrelevant_value"
        with pytest.raises(ValidationError, match="一本線予測フィールド検出"):
            RankingResult.model_validate(payload)

    @pytest.mark.unit
    @pytest.mark.parametrize("invalid_score", [-1, 101])
    def test_ranking_score_範囲外を_reject(self, invalid_score: int) -> None:
        from pydantic import ValidationError

        from src.analysis.ranking_judge import RankingResult

        payload = _valid_payload()
        payload["ranking_score"] = invalid_score
        with pytest.raises(ValidationError):
            RankingResult.model_validate(payload)

    @pytest.mark.unit
    def test_lens_views_3キー欠落を_reject(self) -> None:
        from pydantic import ValidationError

        from src.analysis.ranking_judge import RankingResult

        payload = _valid_payload()
        payload["lens_views"] = {
            "short_term": "RSI 中立",
            "long_term": "ROC 28%",
        }  # dividend 欠落
        with pytest.raises(ValidationError, match="3 キー固定"):
            RankingResult.model_validate(payload)

    @pytest.mark.unit
    def test_typo_extra_field_を_reject(self) -> None:
        from pydantic import ValidationError

        from src.analysis.ranking_judge import RankingResult

        payload = _valid_payload()
        payload["rankng_scor"] = 80  # typo
        with pytest.raises(ValidationError, match=r"[Ee]xtra"):
            RankingResult.model_validate(payload)

    @pytest.mark.unit
    def test_FORBIDDEN_PREDICTION_FIELDS_同期検証(self) -> None:
        from src.analysis.ranking_judge import FORBIDDEN_PREDICTION_FIELDS

        assert frozenset(
            {
                "target_price",
                "expected_return",
                "time_horizon",
                "price_target",
                "forecast_price",
            }
        ) == FORBIDDEN_PREDICTION_FIELDS
