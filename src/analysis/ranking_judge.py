"""Claude Sonnet 4.6 Stage 2 ranking judge 実装。

CLAUDE.md §9.3 一本線予測禁止を 3 層強制（system prompt + Pydantic + 正規表現）。
Provenance §9.8.2 準拠の RankingMetadata を全結果に付与。

学術根拠:
    Greenblatt 2010 "The Little Book That Still Beats the Market"
    Tetlock 2007 "Giving Content to Investor Sentiment"
    Schroeder & Posch 2024 (スマートマネー追従分析)
    Pabrai "The Dhandho Investor"
    Thorp 2006 "The Kelly Criterion in Blackjack Sports Betting and the Stock Market"
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Final, Literal

import anthropic

from src.analysis.anthropic_types import AnthropicLike
from src.analysis._common import extract_json
from src.analysis._provenance import get_current_git_commit
from src.analysis.ranking_judge_prompt import (
    SYSTEM_PROMPT,
    _compute_bundle_hash,
    _format_holdings,
    _format_macro,
    _format_optional,
    build_ranking_user_message,
)
from src.analysis.ranking_judge_schema import (
    FORBIDDEN_PATTERNS,
    FORBIDDEN_PREDICTION_FIELDS,
    RankingMetadata,
    RankingResult,
    RankingSignalBundle,
    contains_forbidden_pattern,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

DEFAULT_MODEL: Final[str] = "claude-sonnet-4-6"
DEFAULT_MODEL_VERSION: Final[str] = "claude-sonnet-4-6-20250514"
DEFAULT_MAX_TOKENS: Final[int] = 2048
ACADEMIC_SOURCE: Final[str] = (
    "Greenblatt 2010 + Tetlock 2007 + Schroeder & Posch 2024 + "
    "Pabrai Dhandho + Thorp 2006"
)

# ---------------------------------------------------------------------------
# プロンプト層への分割 (Phase 6.4.B、handoff-session-10 §4.1):
#     ``SYSTEM_PROMPT`` / ``build_ranking_user_message`` /
#     ``_format_holdings`` / ``_format_macro`` / ``_format_optional`` /
#     ``_compute_bundle_hash`` は :mod:`analysis.ranking_judge_prompt` に
#     切り出した。本モジュール冒頭で import して以降の orchestrator から
#     直接呼び出す。consumer 8 ファイルからの import は本モジュール経由で
#     維持される (Phase 6.4.A schema と同じ規律)。
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# スキーマ層への分割 (Phase 6.4.A、handoff-session-10 §4.1):
#     ``RankingMetadata`` / ``RankingResult`` / ``RankingSignalBundle`` および
#     ``FORBIDDEN_PREDICTION_FIELDS`` / ``FORBIDDEN_PATTERNS`` /
#     ``contains_forbidden_pattern`` は :mod:`analysis.ranking_judge_schema` に
#     切り出した。本モジュール冒頭で import し、末尾の re-export と合わせて
#     既存 consumer (``_screener_compute`` / ``_screener_display`` / pytest 群)
#     からの import path 互換性を保つ (Phase 5.5.0 cache split precedent)。
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Stage 3 純粋関数 — テキストスキャン / レジーム調整 / Half-Kelly 乗数
# CLAUDE.md §9.3 三層防御の最終層と、Thorp 2006 Half-Kelly 強化の前段。
# ---------------------------------------------------------------------------


def validate_no_price_predictions(result: RankingResult) -> None:
    """RankingResult の全テキストフィールドを一本線予測パターンで走査する。

    CLAUDE.md §9.3 三層防御の最終層 (テキストスキャン)。
    SYSTEM_PROMPT (層 1) / Pydantic スキーマ (層 2) を通過した Sonnet 出力に対し、
    自由文中の "$200 になる" 等の予測表現を ``FORBIDDEN_PATTERNS`` で検出する。

    検査対象フィールド:
        - ``recommendation_summary``
        - ``counter_view``
        - ``supporting_signals`` の各要素
        - ``risk_signals`` の各要素
        - ``lens_views`` の各値

    Args:
        result: 検査対象の :class:`RankingResult` インスタンス。

    Raises:
        ValueError: いずれかのテキストに ``FORBIDDEN_PATTERNS`` の予測パターン
            が検出された場合。メッセージは ``"forbidden pattern in text: ..."``
            形式で、検出した文字列の先頭 60 文字を含む。
    """
    texts: tuple[str, ...] = (
        result.recommendation_summary,
        result.counter_view,
        *result.supporting_signals,
        *result.risk_signals,
        *result.lens_views.values(),
    )
    for txt in texts:
        if contains_forbidden_pattern(txt):
            raise ValueError(f"forbidden pattern in text: {txt[:60]}...")


def apply_regime_confidence(
    confidence: Decimal,
    *,
    regime: Literal["Bull", "Choppy", "Crisis"],
) -> Decimal:
    """HMM レジームに応じて confidence を調整する。

    Crisis レジーム時は確信度を 0.5 倍に圧縮し、過信を抑制する。
    Bull / Choppy は等倍 (1.0 倍) で通過させる。
    Half-Kelly 強化 (Thorp 2006) + HMM レジーム検出の連携。

    Args:
        confidence: 元の確信度 (0.0-1.0 の Decimal)。
        regime: HMM レジーム識別子 (``"Bull"`` / ``"Choppy"`` / ``"Crisis"``)。

    Returns:
        調整後の確信度。Crisis なら ``confidence * 0.5``、それ以外は等倍。
    """
    factor = Decimal("0.5") if regime == "Crisis" else Decimal("1.0")
    return confidence * factor


def compute_kelly_multiplier(ranking_score: int) -> Decimal:
    """ranking_score から Half-Kelly 乗数を 3 段階で決定する。

    段階適用:
        - ``score >= 80``         -> ``Decimal("1.0")`` (Full Half-Kelly)
        - ``50 <= score < 80``    -> ``Decimal("0.5")`` (Quarter Kelly)
        - ``score < 50``          -> ``Decimal("0.0")`` (買い見送り)

    Thorp 2006 の Half-Kelly に対し、Sonnet のランキングスコア帯に応じて
    更に半減・ゼロ化することで、低確信度時の損失リスクを抑制する。

    Args:
        ranking_score: 0-100 の整数スコア。

    Returns:
        Half-Kelly に乗算する係数 (``Decimal``)。
    """
    if ranking_score >= 80:
        return Decimal("1.0")
    if ranking_score >= 50:
        return Decimal("0.5")
    return Decimal("0.0")


def compute_mu_for_monte_carlo(momentum_12m: Decimal | None) -> float:
    """12 ヶ月モメンタム (年率パーセント) を Monte Carlo の ``mu`` 引数に変換。

    Stage 3 純粋関数。``apply_regime_confidence`` / ``compute_kelly_multiplier``
    と同じくスカラー引数 (``Decimal | None``) を受け、Stage 3 関数群の引数粒度
    一貫性を保つ (Phase 6.3 reviewer 2 視点一致 fix、bundle 全体受けの設計負債解消)。

    Args:
        momentum_12m: 年率パーセント (例: ``Decimal('12.5')`` = +12.5%)。
            ``RankingSignalBundle.momentum_12m`` から取り出した値を直接渡す。
            ``None`` の場合は ``0.0`` を返す (ドリフトなしの純 Brownian motion)。

    Returns:
        :func:`monte_carlo.simulate_gbm_paths` の ``mu: float`` 引数で使う
        相対値 (例: ``Decimal('12.5')`` → ``0.125``)。

    Note:
        CLAUDE.md §9.1: Decimal 演算で完結してから、Monte Carlo の
        ``mu: float`` 引数のため最後だけ float 化する。
        移管経緯: Phase 5.4.2 display 層 → Phase 6.2 compute 層 (handoff §4.16)
        → Phase 6.3 analysis 層 (handoff §2.4、reviewer HIGH-2)。
    """
    if momentum_12m is None:
        return 0.0
    return float(momentum_12m / Decimal("100"))


# ---------------------------------------------------------------------------
# Fallback reason 分類 helper — UI 漏洩防止 (handoff §4.6)
# ---------------------------------------------------------------------------


FallbackReason = Literal[
    "auth_error",
    "rate_limit",
    "api_status_error",
    "network_error",
    "unknown_api_error",
    "schema_error",
    "forbidden_pattern_detected",
]


# fallback_reason enum → 人間可読日本語ラベル (handoff §4.6 / Phase 6.3 §4.2 派生)。
# UI には抽象化された enum 値ではなく日本語表記を出す。
# Phase 6.3 で ``widgets/ranking_card.py`` から本モジュールに移管し、
# FallbackReason Literal の真理値と同じ場所に集約することで、
# ``_screener_compute.py`` / ``ranking_card.py`` の両 consumer が
# 単一情報源を共有する（循環 import 回避、handoff §2.3）。
#
# 網羅性保証: mypy/pyright は dict literal の key 数を Literal 値と
# 構造的に照合しないため、``tests/unit/analysis/test_ranking_judge.py``
# の ``TestFallbackReasonLabelsCoverage`` で ``typing.get_args`` ベースの
# 集合一致を pytest レベルで保証する (Phase 6.3 reviewer LOW-1 fix)。
FALLBACK_REASON_LABELS: Final[dict[FallbackReason, str]] = {
    "auth_error": "認証エラー (API キー失効の可能性)",
    "rate_limit": "レート制限 (短時間に過剰リクエスト)",
    "api_status_error": "API ステータスエラー",
    "network_error": "ネットワークエラー",
    "unknown_api_error": "不明な API エラー",
    "schema_error": "Sonnet 応答スキーマ違反",
    "forbidden_pattern_detected": "禁止パターン検出 (一本線予測等)",
}


def classify_api_exception(exc: BaseException) -> FallbackReason:
    """Anthropic SDK / Python 標準例外を閉じた enum 値に分類する (handoff §4.6)。

    Args:
        exc: 任意の例外 (Anthropic SDK の例外 / ConnectionError 等)。

    Returns:
        UI 露出可能な抽象化された理由文字列。詳細なクラス名 (``AuthenticationError``
        等) は呼び出し側の ``logger.warning`` で内部記録され、UI には enum 値
        だけが渡る。

    Note:
        以前は ``f"api_error: {type(exc).__name__}"`` を直接 ``fallback_reason``
        に格納していたが、``AuthenticationError`` 等の SDK クラス名が UI に
        漏れて「API キー失効」のような内部状態を露出していた (handoff §4.6)。
        本 helper でクラス名 → 抽象 enum 値に変換する。``AuthenticationError``
        と ``RateLimitError`` は ``APIStatusError`` のサブクラスのため、
        ``isinstance`` 判定の順序を維持すること。
    """
    if isinstance(exc, anthropic.AuthenticationError):
        return "auth_error"
    if isinstance(exc, anthropic.RateLimitError):
        return "rate_limit"
    if isinstance(exc, anthropic.APIStatusError):
        return "api_status_error"
    if isinstance(
        exc, anthropic.APIConnectionError | ConnectionError | TimeoutError
    ):
        return "network_error"
    return "unknown_api_error"


def _build_fallback_result(
    bundle: RankingSignalBundle,
    *,
    reason: str,
    started_at: datetime,
) -> RankingResult:
    """PRD §FR5 多段縮退の核 — Sonnet 不在時に Composite Score で埋めた

    :class:`RankingResult` を構築する。``fallback_reason`` に失敗理由を記録し、
    ``lens_views`` は 3 キー固定 ``"(不在)"``、``confidence`` は floor 値
    ``Decimal("0.3")`` を採用する。``apply_regime_confidence`` /
    ``compute_kelly_multiplier`` は通常パスと同じく実行され、Stage 3 純粋
    関数の出力契約を保つ。

    Args:
        bundle: 入力シグナル束（``composite_score`` を埋め値として利用）。
        reason: 縮退理由文字列。``FallbackReason`` Literal 値
            （``"auth_error"`` / ``"rate_limit"`` / ``"api_status_error"`` /
            ``"network_error"`` / ``"unknown_api_error"`` / ``"schema_error"`` /
            ``"forbidden_pattern_detected"``）を指定する。
            Phase 6.2 (handoff §4.6) 前の ``"api_error: <ExcClass>"`` 形式は
            ``classify_api_exception`` 経由で抽象 enum 値に変換するため廃止。
        started_at: 元の呼び出し開始時刻（UTC、Provenance 用）。

    Returns:
        埋め値で構築された :class:`RankingResult`。

    Note:
        本関数は ``validate_no_price_predictions`` を呼ばずに結果を返す。
        lens_views / recommendation_summary / counter_view / signals の
        文字列は全てこの関数内のハードコード定数で forbidden pattern を含まない
        ことが静的に保証されているため安全。**将来これらの文字列を変更する
        場合は、必ず forbidden pattern を含まないことを確認すること。**
    """
    score = int(bundle.composite_score)
    return RankingResult(
        ranking_score=score,
        recommendation_summary=(
            f"Claude 判定不可、Composite Score {score} で代替（{reason}）。"
        ),
        supporting_signals=(f"Composite={bundle.composite_score:.1f}",),
        risk_signals=("Claude 判定取得失敗、数式スコアのみで判断中",),
        counter_view=(
            "Claude 不在のため反対意見生成不可。ユーザー自身で他根拠を確認推奨。"
        ),
        lens_views={
            "Buffett_Munger": "(不在)",
            "Burry": "(不在)",
            "Lynch": "(不在)",
        },
        confidence=Decimal("0.3"),
        confidence_adjusted=apply_regime_confidence(
            Decimal("0.3"), regime=bundle.regime
        ),
        kelly_multiplier=compute_kelly_multiplier(score),
        fallback_reason=reason,
        metadata=RankingMetadata(
            model="(fallback)",
            model_version="(fallback)",
            calculation_method="ranking_judge_v1_fallback",
            input_bundle_hash=_compute_bundle_hash(bundle),
            cache_hit=False,
            cache_age_sec=None,
            input_tokens=0,
            output_tokens=0,
            input_tokens_cached=0,
            calculated_at=started_at,
            academic_source=ACADEMIC_SOURCE,
            code_commit=get_current_git_commit(),
        ),
    )


# ---------------------------------------------------------------------------
# rank_single_with_claude — Sonnet 4.6 ranking judge 本体（PRD §FR5 多段縮退）
# ---------------------------------------------------------------------------


def rank_single_with_claude(
    bundle: RankingSignalBundle,
    *,
    anthropic_client: AnthropicLike,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> RankingResult:
    """1 銘柄を Sonnet 4.6 でランキング判定する（PRD §FR2/§FR5）。

    3 つの recovery path（PRD §FR5 多段縮退）で `RankingResult` を必ず返却:

    1. **API 例外** (network / 401 / 429 / 503 / SDK error / JSON 抽出失敗):
       ``classify_api_exception(exc)`` で抽象 enum 値
       （``"auth_error"`` / ``"rate_limit"`` / ``"api_status_error"`` /
       ``"network_error"`` / ``"unknown_api_error"``）に変換して
       ``_build_fallback_result`` に渡す。SDK 例外クラス名は
       ``logger.warning`` で内部記録される（handoff §4.6、UI 漏洩防止）。
    2. **Pydantic スキーマ違反** (未定義 extra / 範囲外 / 一本線予測フィールド):
       ``_build_fallback_result(reason="schema_error")``。
       詳細クラス名 (``ValidationError`` 等) は ``logger.warning`` で記録。
    3. **一本線予測パターン検出** (``validate_no_price_predictions`` 違反):
       ``_build_fallback_result(reason="forbidden_pattern_detected")``

    Prompt Caching API call (cache_control ephemeral、notes-5.2.md §1.3):
        SYSTEM_PROMPT を ``cache_control: ephemeral`` で送り、5 分 TTL の
        プロンプトキャッシュを利用する。``cache_read_input_tokens`` は SDK が
        フィールドを省略する場合があるため ``getattr(... , 0) or 0`` で
        安全に取得する。

    ``confidence_adjusted`` と ``kelly_multiplier`` は Sonnet 出力からではなく
    呼び出し側 Python で Stage 3 純粋関数（``apply_regime_confidence`` /
    ``compute_kelly_multiplier``）から計算する（SYSTEM_PROMPT 契約と整合）。

    Args:
        bundle: 入力シグナル束（PRD §FR2 で定義された 6 skill 統合）。
        anthropic_client: ``anthropic.Anthropic`` 互換クライアント（DI）。
        model: Sonnet モデル ID（既定 :data:`DEFAULT_MODEL`）。
        max_tokens: 出力上限トークン数（既定 :data:`DEFAULT_MAX_TOKENS`）。

    Returns:
        :class:`RankingResult` — 正常時は Sonnet 判定、失敗時は Composite Score
        埋め値で fallback_reason を立てて返す。
    """
    started_at = datetime.now(UTC)
    user_msg = build_ranking_user_message(bundle)

    # Path 1: API 呼び出し + JSON 抽出 — 例外は api_error にまとめる
    try:
        response = anthropic_client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_msg}],
        )
        text = response.content[0].text
        parsed = extract_json(text, context="ranking judge response")
    except Exception as exc:  # noqa: BLE001 — PRD §FR5 多段縮退、Anthropic SDK の多様な例外型を一括受け
        reason = classify_api_exception(exc)
        logger.warning(
            "Sonnet API call failed: ticker=%s reason=%s exc_type=%s exc_msg=%s",
            bundle.ticker,
            reason,
            type(exc).__name__,
            str(exc),
        )
        return _build_fallback_result(
            bundle,
            reason=reason,
            started_at=started_at,
        )

    # Provenance §9.8.2 メタデータを構築（cache_read_input_tokens は省略され得る）
    raw_metadata = RankingMetadata(
        model=model,
        model_version=DEFAULT_MODEL_VERSION,
        calculation_method="ranking_judge_v1",
        input_bundle_hash=_compute_bundle_hash(bundle),
        cache_hit=False,
        cache_age_sec=None,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        # cache_read_input_tokens は Prompt Caching ヒット時のみ Anthropic SDK が
        # 設定する。キャッシュ未使用時は属性自体が省略されるため getattr ガードが必要。
        input_tokens_cached=(
            getattr(response.usage, "cache_read_input_tokens", 0) or 0
        ),
        calculated_at=started_at,
        academic_source=ACADEMIC_SOURCE,
        code_commit=get_current_git_commit(),
    )

    # Path 2: Pydantic 検証 — extra='forbid' / 範囲制約 / 予測フィールド reject
    # python-review HIGH 対策: ``parsed`` を mutate せず immutable コピーから構築する。
    try:
        confidence = Decimal(str(parsed.get("confidence", 0)))
        ranking_score = parsed.get("ranking_score", 0)
        sonnet_fields = {k: v for k, v in parsed.items() if k != "confidence"}
        result = RankingResult(
            **sonnet_fields,
            confidence=confidence,
            confidence_adjusted=apply_regime_confidence(
                confidence, regime=bundle.regime
            ),
            kelly_multiplier=compute_kelly_multiplier(ranking_score),
            fallback_reason=None,
            metadata=raw_metadata,
        )
    except Exception as exc:  # noqa: BLE001 — PRD §FR5 多段縮退、ValidationError 等を一括受け
        logger.warning(
            "Sonnet response schema error: ticker=%s exc_type=%s exc_msg=%s",
            bundle.ticker,
            type(exc).__name__,
            str(exc),
        )
        return _build_fallback_result(
            bundle,
            reason="schema_error",
            started_at=started_at,
        )

    # Path 3: 自由文中の一本線予測パターンスキャン（CLAUDE.md §9.3 三層目）
    try:
        validate_no_price_predictions(result)
    except ValueError:
        return _build_fallback_result(
            bundle,
            reason="forbidden_pattern_detected",
            started_at=started_at,
        )

    return result


# ---------------------------------------------------------------------------
# Phase 6 第 2 弾 refactor (Session 5): 24h ディスクキャッシュ層と
# ``rank_with_claude_batch`` を :mod:`analysis.ranking_judge_cache` に切り出した。
# 既存呼び出しコードの後方互換のため re-export する。
#
# **テストでの monkeypatch 注意**: ``_now_utc`` を時刻操作する場合、本モジュール
# の再エクスポート binding を ``setattr`` しても効かないため、必ず
# ``ranking_judge_cache`` モジュールを直接 patch 対象にすること。
# ---------------------------------------------------------------------------

from .ranking_judge_cache import (  # noqa: E402, F401
    CACHE_TTL_SEC,
    _cache_path,
    _now_utc,
    _read_cache,
    _write_cache,
    rank_with_claude_batch,
)
