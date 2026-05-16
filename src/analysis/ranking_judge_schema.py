"""Sonnet ranking judge のスキーマ層 (CLAUDE.md §9.3 三層防御の中間層)。

Phase 6.4.A 分割: :mod:`analysis.ranking_judge` から schema 定義と
禁止パターン検出を本モジュールへ切り出した。`ranking_judge.py` 1016 行
肥大化対策の最先発サブフェーズ (handoff-session-10.md §4.1)。

含まれるシンボル:
    - 定数: :data:`FORBIDDEN_PREDICTION_FIELDS` / :data:`FORBIDDEN_PATTERNS`
    - 関数: :func:`contains_forbidden_pattern`
    - dataclass: :class:`RankingMetadata` (Provenance §9.8.2 必須メタデータ)
    - Pydantic BaseModel: :class:`RankingResult` (Sonnet 出力検証)
    - dataclass: :class:`RankingSignalBundle` (Stage 2 入力シグナル束)

依存:
    pydantic / dataclasses / datetime / decimal / typing / re のみ。
    `analysis.ranking_judge` への循環依存なし (依存方向が schema → orchestrator
    の単方向、Phase 6.4 サブフェーズ全体で同じ規律を維持)。

後方互換性:
    `analysis.ranking_judge` 末尾で本モジュールの全 public シンボルを
    re-export するため、既存 consumer (`_screener_compute.py` /
    `_screener_display.py` / `widgets/ranking_card.py` /
    `test_ranking_judge.py` 等) は import 行を変更せずに動作する
    (Phase 5.5.0 cache split precedent と同じパターン)。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ---------------------------------------------------------------------------
# 内部定数 — ticker 文字種制約
# ---------------------------------------------------------------------------

# ticker 文字種制約 — `_cache_path` のパストラバーサル防御（security review H-1）。
# 米国株（A-Z 0-9）/ 日本株（数字 4 桁 + ``.T`` 等）の実在パターンを許容しつつ、
# ``/`` ``\`` ``..`` 等のパス成分を構造的に拒否する。__post_init__ で強制適用。
_TICKER_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9.\-]{1,20}$")


# ---------------------------------------------------------------------------
# 禁止予測フィールド (Pydantic スキーマレベルで一本線予測を構造的に拒否)
# CLAUDE.md §9.3 三層防御の中間層。FORBIDDEN_PATTERNS (正規表現) と組み合わせて
# システムプロンプト・スキーマ・出力テキストの 3 レイヤーで予測値の侵入を防ぐ。
# ---------------------------------------------------------------------------

FORBIDDEN_PREDICTION_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "target_price",
        "expected_return",
        "time_horizon",
        "price_target",
        "forecast_price",
    }
)


# ---------------------------------------------------------------------------
# 禁止パターン (一本線予測を 7 種の正規表現で検出)
# CLAUDE.md §9.3 「一本線の価格予測は禁止」を正規表現で機械的に強制する。
# ---------------------------------------------------------------------------

FORBIDDEN_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    # パターン 1: ドル建て価格（例: $200, $ 1,500）
    re.compile(r"\$\s*\d+"),
    # パターン 2: 円建て価格（例: ¥30,000, ¥ 1500）
    re.compile(r"¥\s*\d+"),
    # パターン 3: %＋上昇/下落系語句（例: 5% 上昇予測, 10% increase）
    re.compile(r"\d+\s*%\s*(上昇|下落|上がる|下がる|increase|decrease)", re.IGNORECASE),
    # パターン 4: 目標株価・価格目標（例: 目標株価, target price, price target）
    re.compile(r"目標株価|target\s*price|price\s*target", re.IGNORECASE),
    # パターン 5: 時期限定予測（例: いつまで, by 6 months）
    re.compile(r"いつまで|by\s+\d+\s*(month|year|月|年)", re.IGNORECASE),
    # パターン 6: 予想・予測価格（例: forecast price, expected price）
    re.compile(r"forecast\s+price|expected\s+price", re.IGNORECASE),
    # パターン 7: ○ヶ月/months 以内（例: 3 ヶ月以内, 6 months 以内）
    re.compile(r"(\d+\s*ヶ月|\d+\s*months?)\s*以内", re.IGNORECASE),
)


def contains_forbidden_pattern(text: str) -> bool:
    """テキストに一本線予測パターンが含まれていれば True を返す。

    CLAUDE.md §9.3 の禁止規約を機械的に検査する。
    FORBIDDEN_PATTERNS のいずれか 1 つでも一致した場合は True。

    Args:
        text: 検査対象の文字列（Sonnet の出力や要約テキスト等）

    Returns:
        禁止パターンを 1 つ以上含む場合 True、含まない場合 False
    """
    return any(p.search(text) for p in FORBIDDEN_PATTERNS)


# ---------------------------------------------------------------------------
# RankingMetadata — Provenance §9.8.2 必須メタデータ
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RankingMetadata:
    """Sonnet 判定結果の出所情報（CLAUDE.md §9.8.2 必須）。

    Attributes:
        model: 使用モデル名（例: "claude-sonnet-4-6"）
        model_version: 使用モデルバージョン（例: "claude-sonnet-4-6-20250514"）
        calculation_method: 計算手法識別子（例: "ranking_judge_v1"）
        input_bundle_hash: 入力シグナル束の SHA256 ハッシュ
        cache_hit: Prompt Caching ヒット有無
        cache_age_sec: キャッシュヒット時の経過秒数（ミスの場合 None）
        input_tokens: 非キャッシュ入力トークン数
        output_tokens: 出力トークン数
        input_tokens_cached: キャッシュヒット分のトークン数
        calculated_at: 計算実行日時（UTC）
        academic_source: 学術根拠の文献情報
        code_commit: 計算時の git commit short hash（取得失敗時 None）
    """

    model: str
    model_version: str
    calculation_method: str
    input_bundle_hash: str
    cache_hit: bool
    cache_age_sec: int | None
    input_tokens: int
    output_tokens: int
    input_tokens_cached: int
    calculated_at: datetime
    academic_source: str
    code_commit: str | None = None


# ---------------------------------------------------------------------------
# Pydantic v2 BaseModel — Sonnet 判定結果の検証スキーマ
# ---------------------------------------------------------------------------


class RankingResult(BaseModel):
    """Sonnet ランキング判定の構造化結果（CLAUDE.md §9.3 三層防御の中間層）。

    notes-5.2.md §1.2 案 C 採用:
        - ``extra='forbid'`` で未定義フィールドを構造的に reject
        - ``model_validator(mode='before')`` で `FORBIDDEN_PREDICTION_FIELDS`
          に該当するキーが含まれていれば即座に ValueError を送出
        - 2 層防御により ``target_price`` 等の予測フィールドが Sonnet 出力
          として返ってきても確実にパースに失敗させる

    Attributes:
        ranking_score: 0-100 の総合ランキングスコア
        recommendation_summary: 推奨サマリー（最大 150 文字）
        supporting_signals: 支持シグナル（最大 5 件のタプル）
        risk_signals: リスクシグナル（最大 5 件のタプル）
        counter_view: 反対意見・カウンタービュー（最大 200 文字）
        lens_views: 3 レンズ視点
            （キーは ``Buffett_Munger`` / ``Burry`` / ``Lynch`` 固定）
        confidence: 確信度（0.0-1.0 の Decimal）
        confidence_adjusted: HMM レジーム調整後の確信度（0.0-1.0）
        kelly_multiplier: Half-Kelly 乗数（0.0-1.0、Thorp 2006 準拠）
        fallback_reason: フォールバック理由（通常時 None）
        metadata: Provenance 必須メタデータ（CLAUDE.md §9.8.2）

    Raises:
        ValidationError: 一本線予測フィールド検出時、未定義 extra フィールド
            検出時、または各フィールドの制約違反時。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        arbitrary_types_allowed=True,
    )

    ranking_score: int = Field(ge=0, le=100)
    recommendation_summary: str = Field(max_length=150)
    supporting_signals: tuple[str, ...] = Field(min_length=1, max_length=5)
    risk_signals: tuple[str, ...] = Field(min_length=1, max_length=5)
    counter_view: str = Field(max_length=200)
    lens_views: dict[str, str]
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    confidence_adjusted: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    kelly_multiplier: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    fallback_reason: str | None = None
    metadata: RankingMetadata

    @model_validator(mode="before")
    @classmethod
    def _reject_prediction_fields(cls, data: object) -> object:
        """一本線予測フィールドが含まれていれば即座に reject する（案 C 防御層 1）。

        CLAUDE.md §9.3 違反を構造レベルで弾く。dict 以外は素通しして Pydantic
        の通常検証に任せる。
        """
        if not isinstance(data, dict):
            return data
        hit = FORBIDDEN_PREDICTION_FIELDS & data.keys()
        if hit:
            raise ValueError(
                f"一本線予測フィールド検出 (CLAUDE.md §9.3 違反): {sorted(hit)}"
            )
        return data

    @model_validator(mode="after")
    def _validate_lens_views_keys(self) -> RankingResult:
        """lens_views が必須 3 キー固定かつ値が空文字列でないか検証。

        Sonnet が空文字列を返した場合に UI で「シグナルなし」が silent pass する
        運用リスクを避けるため、`str.strip()` で空白のみのケースも reject する。
        """
        required = {"Buffett_Munger", "Burry", "Lynch"}
        actual = set(self.lens_views.keys())
        if actual != required:
            raise ValueError(
                "lens_views は 3 キー固定 (Buffett_Munger/Burry/Lynch) "
                f"が必須、実際: {sorted(actual)}"
            )
        empty_keys = [k for k, v in self.lens_views.items() if not v.strip()]
        if empty_keys:
            raise ValueError(
                f"lens_views の値が空文字列: {sorted(empty_keys)}"
            )
        return self


# ---------------------------------------------------------------------------
# RankingSignalBundle — Stage 2 Sonnet 判定の入力シグナル束
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RankingSignalBundle:
    """Stage 2 Sonnet 判定の入力シグナル束（中スコープ B、PRD §FR2）。

    6 skill 統合の入力データを 1 つの不変オブジェクトとして集約する。
    Magic Formula / sentiment / Polymarket / 13F / Regime / Composite Score の
    すべてのシグナルが含まれる。

    Attributes:
        ticker: 銘柄ティッカー (例: "AAPL", "7203.T")
        exchange: 取引所 ("US" or "JP")
        sector: 業種 (None 可)
        composite_score: Composite Score (0-100)
        sub_scores: サブスコア辞書 (Q/V/I/G/R/M/S の 7 因子)
        composite_preset: 採用プリセット名 (例: "Buffett_型_暫定")
        magic_formula_score: Magic Formula スコア (None 可)
        roc_pct: ROC % (None 可)
        earnings_yield_pct: Earnings Yield % (None 可)
        momentum_1m: 1ヶ月モメンタム (None 可)
        momentum_12m: 12ヶ月モメンタム (None 可)
        sentiment_score: ニュースセンチメント (-1 to +1)
        sentiment_confidence: センチメント信頼度 (0-1)
        sentiment_themes: センチメント主題タプル
        polymarket_macro: Polymarket 確率辞書 (例: {"fed_cut_2026": 0.62})
        fund_holdings_delta: 13F 差分辞書 (ファンド名 -> action / value_change)
        regime: HMM レジーム ("Bull"/"Choppy"/"Crisis")
        regime_state_probs: レジーム状態確率辞書
        fetched_at: 取得日時 (UTC)
    """

    ticker: str
    exchange: Literal["US", "JP"]
    sector: str | None
    composite_score: float
    sub_scores: dict[str, float]
    composite_preset: str
    magic_formula_score: float | None
    roc_pct: Decimal | None
    earnings_yield_pct: Decimal | None
    momentum_1m: Decimal | None
    momentum_12m: Decimal | None
    sentiment_score: Decimal
    sentiment_confidence: Decimal
    sentiment_themes: tuple[str, ...]
    polymarket_macro: dict[str, Decimal]
    fund_holdings_delta: dict[str, dict[str, object]]
    regime: Literal["Bull", "Choppy", "Crisis"]
    regime_state_probs: dict[str, Decimal]
    fetched_at: datetime

    def __post_init__(self) -> None:
        """ticker の文字種を ``_TICKER_PATTERN`` で検証。

        security review H-1 対策: ``_cache_path`` の SHA256 鍵に ticker prefix を
        付与している都合、``../`` 等の path traversal 文字が混入すると
        ``cache_dir`` 外へファイル書き込み可能になる。最上流で構造的に遮断する。
        """
        if not _TICKER_PATTERN.fullmatch(self.ticker):
            raise ValueError(
                f"ticker contains forbidden characters (A-Z 0-9 . - のみ許容): "
                f"{self.ticker!r}"
            )
