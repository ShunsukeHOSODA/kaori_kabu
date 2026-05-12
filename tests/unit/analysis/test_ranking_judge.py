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
            "Buffett_Munger": "質×価値の典型",
            "Burry": "クレジット観で警戒",
            "Lynch": "消費者目線で堅実",
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
            "Buffett_Munger": "質×価値の典型",
            "Burry": "クレジット観で警戒",
            "Lynch": "消費者目線で堅実",
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
            "Buffett_Munger": "質×価値の典型",
            "Burry": "クレジット観で警戒",
        }  # Lynch 欠落
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

    @pytest.mark.unit
    def test_supporting_signals_空タプルを_reject(self) -> None:
        from pydantic import ValidationError

        from src.analysis.ranking_judge import RankingResult

        payload = _valid_payload()
        payload["supporting_signals"] = ()
        with pytest.raises(ValidationError):
            RankingResult.model_validate(payload)

    @pytest.mark.unit
    def test_risk_signals_空タプルを_reject(self) -> None:
        from pydantic import ValidationError

        from src.analysis.ranking_judge import RankingResult

        payload = _valid_payload()
        payload["risk_signals"] = ()
        with pytest.raises(ValidationError):
            RankingResult.model_validate(payload)

    @pytest.mark.unit
    @pytest.mark.parametrize("empty_key", ["Buffett_Munger", "Burry", "Lynch"])
    def test_lens_views_値が空文字列を_reject(self, empty_key: str) -> None:
        from pydantic import ValidationError

        from src.analysis.ranking_judge import RankingResult

        payload = _valid_payload()
        payload["lens_views"] = {**payload["lens_views"], empty_key: ""}
        with pytest.raises(ValidationError, match="空文字列"):
            RankingResult.model_validate(payload)

    @pytest.mark.unit
    def test_lens_views_値が空白のみを_reject(self) -> None:
        from pydantic import ValidationError

        from src.analysis.ranking_judge import RankingResult

        payload = _valid_payload()
        payload["lens_views"] = {**payload["lens_views"], "Buffett_Munger": "   "}
        with pytest.raises(ValidationError, match="空文字列"):
            RankingResult.model_validate(payload)


class TestRankingSignalBundle:
    """Task 5.2.3 — RankingSignalBundle dataclass の TDD テスト。

    6 skill 統合の Stage 2 Sonnet 入力シグナル束（中スコープ B、PRD §FR2）。
    frozen dataclass で不変性を強制し、conftest fixture `make_bundle` から
    生成される標準インスタンスを通じて Bull/Choppy/Crisis レジーム別の
    テスト可能性を担保する。
    """

    @pytest.mark.unit
    def test_frozen_書き換え不可(self, make_bundle: Any) -> None:
        import dataclasses

        bundle = make_bundle()
        with pytest.raises(dataclasses.FrozenInstanceError):
            bundle.ticker = "MSFT"  # type: ignore[misc]

    @pytest.mark.unit
    @pytest.mark.parametrize("regime", ["Bull", "Choppy", "Crisis"])
    def test_regime_別の作成(self, make_bundle: Any, regime: str) -> None:
        bundle = make_bundle(regime=regime)
        assert bundle.regime == regime

    @pytest.mark.unit
    def test_デフォルト値の検証(self, make_bundle: Any) -> None:
        bundle = make_bundle()
        assert bundle.ticker == "AAPL"
        assert bundle.exchange == "US"
        assert bundle.sector == "Technology"
        assert bundle.composite_score == 72.5

    @pytest.mark.unit
    def test_ticker_のカスタマイズ(self, make_bundle: Any) -> None:
        bundle = make_bundle(ticker="MSFT")
        assert bundle.ticker == "MSFT"

    @pytest.mark.unit
    def test_composite_score_のカスタマイズ(self, make_bundle: Any) -> None:
        bundle = make_bundle(composite_score=50.0)
        assert bundle.composite_score == 50.0


class TestValidateNoPricePredictions:
    """Task 5.2.4 — validate_no_price_predictions の TDD テスト。

    CLAUDE.md §9.3 三層防御の最終層（テキストスキャン）。
    RankingResult の各テキストフィールドを `contains_forbidden_pattern` で
    走査し、一本線予測パターンが含まれていれば ValueError を送出する。
    """

    @pytest.mark.unit
    def test_recommendation_summary_の予測を検出(self) -> None:
        from src.analysis.ranking_judge import (
            RankingResult,
            validate_no_price_predictions,
        )

        payload = _valid_payload()
        payload["recommendation_summary"] = "AAPL は $200 になる"
        result = RankingResult.model_validate(payload)
        with pytest.raises(ValueError, match="forbidden pattern"):
            validate_no_price_predictions(result)

    @pytest.mark.unit
    def test_counter_view_の予測を検出(self) -> None:
        from src.analysis.ranking_judge import (
            RankingResult,
            validate_no_price_predictions,
        )

        payload = _valid_payload()
        payload["counter_view"] = "目標株価 $250 への到達は困難"
        result = RankingResult.model_validate(payload)
        with pytest.raises(ValueError, match="forbidden pattern"):
            validate_no_price_predictions(result)

    @pytest.mark.unit
    def test_supporting_signals_の予測を検出(self) -> None:
        from src.analysis.ranking_judge import (
            RankingResult,
            validate_no_price_predictions,
        )

        payload = _valid_payload()
        payload["supporting_signals"] = (
            "Magic Formula 上位",
            "短期で 5% 上昇予測",
        )
        result = RankingResult.model_validate(payload)
        with pytest.raises(ValueError, match="forbidden pattern"):
            validate_no_price_predictions(result)

    @pytest.mark.unit
    def test_risk_signals_の予測を検出(self) -> None:
        from src.analysis.ranking_judge import (
            RankingResult,
            validate_no_price_predictions,
        )

        payload = _valid_payload()
        payload["risk_signals"] = (
            "Value Trap 懸念",
            "3 ヶ月以内に高値更新が必要",
        )
        result = RankingResult.model_validate(payload)
        with pytest.raises(ValueError, match="forbidden pattern"):
            validate_no_price_predictions(result)

    @pytest.mark.unit
    def test_lens_views_Buffett_Munger_の予測を検出(self) -> None:
        from src.analysis.ranking_judge import (
            RankingResult,
            validate_no_price_predictions,
        )

        payload = _valid_payload()
        payload["lens_views"] = {
            **payload["lens_views"],
            "Buffett_Munger": "forecast price $200 が妥当",
        }
        result = RankingResult.model_validate(payload)
        with pytest.raises(ValueError, match="forbidden pattern"):
            validate_no_price_predictions(result)

    @pytest.mark.unit
    def test_正常_payload_はraiseしない(self) -> None:
        from src.analysis.ranking_judge import (
            RankingResult,
            validate_no_price_predictions,
        )

        result = RankingResult.model_validate(_valid_payload())
        # 例外が出ないことを確認
        validate_no_price_predictions(result)


class TestApplyRegimeConfidence:
    """Task 5.2.4 — apply_regime_confidence の TDD テスト。

    Crisis レジーム時に confidence を 0.5 倍に圧縮し、Bull/Choppy は等倍。
    Half-Kelly 強化（HMM Crisis 時にレバレッジ抑制）の前段。
    """

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("regime", "expected"),
        [
            ("Bull", Decimal("0.8")),
            ("Choppy", Decimal("0.8")),
            ("Crisis", Decimal("0.4")),
        ],
    )
    def test_regime別の倍率適用(self, regime: str, expected: Decimal) -> None:
        from src.analysis.ranking_judge import apply_regime_confidence

        adjusted = apply_regime_confidence(Decimal("0.8"), regime=regime)  # type: ignore[arg-type]
        assert adjusted == expected

    @pytest.mark.unit
    @pytest.mark.parametrize("regime", ["Bull", "Choppy", "Crisis"])
    def test_confidence_ゼロ時は全regimeで_ゼロ(self, regime: str) -> None:
        from src.analysis.ranking_judge import apply_regime_confidence

        adjusted = apply_regime_confidence(Decimal("0"), regime=regime)  # type: ignore[arg-type]
        assert adjusted == Decimal("0")


class TestComputeKellyMultiplier:
    """Task 5.2.4 — compute_kelly_multiplier の TDD テスト。

    Half-Kelly 段階適用:
        - score >= 80 → 1.0（Full Half-Kelly）
        - 50 <= score < 80 → 0.5（Quarter Kelly）
        - score < 50 → 0.0（買い見送り）
    """

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("score", "expected"),
        [
            (100, Decimal("1.0")),
            (85, Decimal("1.0")),
            (80, Decimal("1.0")),
            (79, Decimal("0.5")),
            (50, Decimal("0.5")),
            (49, Decimal("0.0")),
            (0, Decimal("0.0")),
        ],
    )
    def test_score境界値の乗数(self, score: int, expected: Decimal) -> None:
        from src.analysis.ranking_judge import compute_kelly_multiplier

        assert compute_kelly_multiplier(score) == expected


class TestSystemPrompt:
    """Task 5.2.5 — SYSTEM_PROMPT 定数の TDD テスト。

    Sonnet 4.6 ranking judge 用のシステムプロンプトが、
    Anthropic Prompt Caching（ephemeral）の 2,048 token 下限を確実に
    超える文字数を持ち、PRD §FR2/§FR3 の必須要素・禁止事項を
    すべて言及していることを検証する。

    char 数下限 2,400 は Japanese 混在テキストでの token 換算の
    安全側 proxy（Claude tokenizer で 1 token ≈ 1.0-1.5 char）。
    """

    @pytest.mark.unit
    def test_文字数下限_2400(self) -> None:
        """Prompt Caching 2,048 token 下限の char proxy（≥ 2,400）。

        Japanese 混在テキストにおける Claude tokenizer の
        実効レートを考慮した安全側下限。型チェックも統合。
        """
        from src.analysis.ranking_judge import SYSTEM_PROMPT

        assert isinstance(SYSTEM_PROMPT, str)
        assert len(SYSTEM_PROMPT) >= 2400, (
            f"SYSTEM_PROMPT char count={len(SYSTEM_PROMPT)}, "
            "Prompt Caching 2048 token 下限を満たさない可能性"
        )

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "keyword",
        [
            # lens_views 3 キー固定（PRD §FR2 line 136）
            "Buffett_Munger",
            "Burry",
            "Lynch",
            # 学術根拠 4 件
            "Greenblatt",
            "Tetlock",
            "Schroeder",
            "Pabrai",
            # リスク警告 3 件
            "Value Trap",
            "Recency Bias",
            "Overconfidence",
            # 出力スキーマ必須フィールド
            "counter_view",
            "ranking_score",
            "lens_views",
            "confidence",
        ],
    )
    def test_必須キーワード(self, keyword: str) -> None:
        from src.analysis.ranking_judge import SYSTEM_PROMPT

        assert keyword in SYSTEM_PROMPT, (
            f"必須キーワード '{keyword}' が SYSTEM_PROMPT に未記載"
        )

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "forbidden_topic",
        [
            "目標株価",
            "上昇率",
            "期限付き",
            "投資助言",
            # 文脈密着型サブストリング: SYSTEM_PROMPT の "$ や ¥ に続く具体的な数値" にマッチ
            "$ や ¥",
        ],
    )
    def test_禁止事項_明示(self, forbidden_topic: str) -> None:
        """PRD §FR3 禁止 5 種が prompt 本文に明示されていること。

        単純な `in` チェックでよい（禁止語が「禁止」コンテキスト下で
        参照されていることを SYSTEM_PROMPT 設計者責任で担保）。
        `"$"` 単体ではなく文脈密着型サブストリング `"$ や ¥"` を使い、
        将来の編集での偶発通過 例: 変数名 `$FILE_PATH` 等 を防ぐ。
        """
        from src.analysis.ranking_judge import SYSTEM_PROMPT

        assert forbidden_topic in SYSTEM_PROMPT, (
            f"禁止事項 '{forbidden_topic}' が SYSTEM_PROMPT に未記載"
        )

    @pytest.mark.unit
    def test_禁止コンテキスト言及(self) -> None:
        """SYSTEM_PROMPT に「禁止」または「❌」が含まれていること。

        パラメトライズした禁止事項が「禁止」文脈下で言及されている
        ことを担保する最低限のシグナル検査。
        """
        from src.analysis.ranking_judge import SYSTEM_PROMPT

        assert "禁止" in SYSTEM_PROMPT or "❌" in SYSTEM_PROMPT

    @pytest.mark.unit
    def test_計算側除外フィールドの明記(self) -> None:
        """confidence_adjusted / kelly_multiplier / metadata は呼び出し側で
        計算するため Sonnet 出力 JSON に含めない旨を SYSTEM_PROMPT で明記。
        """
        from src.analysis.ranking_judge import SYSTEM_PROMPT

        assert "confidence_adjusted" in SYSTEM_PROMPT
        assert "kelly_multiplier" in SYSTEM_PROMPT
        assert "metadata" in SYSTEM_PROMPT
