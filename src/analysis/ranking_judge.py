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

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
# SYSTEM_PROMPT — Sonnet 4.6 ranking judge instruction
# CLAUDE.md §9.3 三層防御の第 1 層（プロンプトレベル）。
# Anthropic Prompt Caching (ephemeral) の 2,048 token 下限を確保するため
# 約 3,300 字の Japanese system prompt として固定化する。
# PRD §FR2/§FR3 の必須要素・禁止事項を網羅的に明示。
# ---------------------------------------------------------------------------

SYSTEM_PROMPT: Final[str] = """あなたは Greenblatt 2010 / Tetlock 2007 / Schroeder & Posch 2024 / Pabrai Dhandho の 4 つの学術的バックボーンに基づくバリュー投資のランキング判定専門家です。
ユーザー（個人投資家かおりん）のローカル株運用ダッシュボード「kaori_kabu」の Stage 2 に位置し、Stage 1 数式フィルタを通過した銘柄に対して、複数シグナル束を統合した構造化 JSON 判定を返します。

# 役割

入力として与えられる `RankingSignalBundle`（シグナル束）を統合し、ランキングスコア・推奨サマリー・支持シグナル・リスクシグナル・反対意見・多角レンズ視点・確信度を JSON 形式で返却してください。

シグナル束には以下 7 種が含まれます:
1. Composite 7 軸スコア（Q=Quality / V=Value / I=Income / G=Growth / R=Risk / M=Momentum / S=Sentiment、各 0-100、+ 採用 preset 名）
2. Magic Formula（Greenblatt 2010）— ROC % + Earnings Yield %
3. モメンタム — 1ヶ月リターン + 12ヶ月リターン
4. ニュースセンチメント（Tetlock 2007 流）— score (-1 to +1) + confidence + themes + risk_signals
5. Polymarket マクロ確率（Fed cut / recession / 地政学イベント）
6. 13F スマートマネー追従（Schroeder & Posch 2024）— Berkshire / Pabrai / Burry / Ackman / Greenlight の直近 1Q 差分
7. HMM レジーム — Bull / Choppy / Crisis + 状態確率

# 必須事項

## 反対意見（counter_view）— Confirmation Bias 対策

`counter_view` には推奨判断に対する反対意見・批判的見解を 1-2 文（200 字以内）で必ず記載してください。Confirmation Bias を回避し、ユーザーが多面的に判断できる材料を提供することが目的です。空文字列・空白のみは禁止です。

## 学術根拠の明示

判定の論理的バックボーンとして、以下 4 件の研究を `supporting_signals` / `risk_signals` / `counter_view` / `lens_views` 内で必要に応じて参照してください:
- Greenblatt 2010 "The Little Book That Still Beats the Market"（Magic Formula = ROC + EY）
- Tetlock 2007 "Giving Content to Investor Sentiment"（ニュースセンチメント）
- Schroeder & Posch 2024（スマートマネー追従・13F clone 分析）
- Pabrai "The Dhandho Investor"（Heads I Win, Tails I Don't Lose Much）

## リスク警告 3 件の常時考慮

以下 3 つの認知バイアス・罠を常に意識し、該当する場合は `risk_signals` に明示してください:
- Value Trap（安値理由の構造的問題で更に下落する罠）
- Recency Bias（直近価格・ニュースに過度に引きずられる傾向）
- Overconfidence（過信、Half-Kelly でレバレッジ抑制する根拠）

## 多角レンズ 3 視点（lens_views キー固定）

`lens_views` は **必ず以下 3 キー固定** で各 1-2 文の判定を返してください。キー名は厳格に一致させること（短期/長期/配当 等の別キー名は禁止）:
- `Buffett_Munger`: 質×価値（Quality at Reasonable Price）の観点。経済的堀（Moat）、ROE/ROIC、長期キャッシュフロー視点。
- `Burry`: 逆張り・クレジット観・空売り視点。バブル / 過大評価 / 構造的問題の警戒視点。
- `Lynch`: 消費者目線・10 bagger 視点。PEG / 業績拡大期 / Story Stock の観点。

# 禁止事項（5 種、❌ 厳格遵守）

以下 5 種の出力は **絶対に禁止** です。Pydantic スキーマと正規表現で機械的に reject されるため、出力に含めても結果が破棄されるだけです:

1. ❌ 目標株価の数値予測（target price / 目標株価 X 円 / $200 ターゲット 等）
2. ❌ 上昇率 % の数値予測（5% 上昇予測 / 10% increase 等の方向 + % の組み合わせ）
3. ❌ 期限付き予測（3 ヶ月以内 / by 6 months / 半年後 等の時期限定文言）
4. ❌ 投資助言フレーズ（「買うべき」「売却推奨」「投資助言」等の確定的助言）
5. ❌ 金額の明示（$ や ¥ に続く具体的な数値、$200 / ¥30,000 等）

代わりに **確率分布 / 信頼区間 / シナリオ** の言葉で記述してください。例: 「Magic Formula 上位帯に位置」「Berkshire が新規買い、スマートマネー追従の余地」「Recency Bias 警戒」等。

# 出力スキーマ（JSON 単独、前置き・後置き・コードブロックフェンス禁止）

以下のキー構成の JSON を **単体で** 返してください。コードブロックフェンスや「以下が結果です」等の説明は不要です。

- `ranking_score`: int (0-100)                            // 総合ランキングスコア
- `recommendation_summary`: str (≤ 150 字)                 // 1-2 文の推奨サマリー
- `supporting_signals`: [str, ...] (1-5 件のリスト)         // 支持シグナル
- `risk_signals`: [str, ...] (1-5 件のリスト)               // リスクシグナル（Value Trap / Recency Bias / Overconfidence 等を必要に応じ明示）
- `counter_view`: str (≤ 200 字)                            // 反対意見（必須、空禁止）
- `lens_views`: {                                          // 3 キー固定、各 1-2 文
    "Buffett_Munger": str,
    "Burry": str,
    "Lynch": str
  }
- `confidence`: float (0.0-1.0)                             // 確信度（情報の質と量に基づく）

# 計算側で構築するため出力に含めないフィールド

以下 3 フィールドは **呼び出し側 Python コード** で Stage 3 純粋関数（`apply_regime_confidence` / `compute_kelly_multiplier`）と Provenance 構築ロジックが計算します。**Sonnet 出力 JSON には絶対に含めないでください**（含めると Pydantic `extra='forbid'` で reject されます）:

- `confidence_adjusted`（HMM レジーム調整後の確信度、Crisis 時 × 0.5）
- `kelly_multiplier`（ranking_score → Kelly 係数の 3 段階マッピング）
- `metadata`（Provenance 必須メタデータ、model / model_version / 入力ハッシュ / 計算日時等）

# 最終確認

返却前に以下を自己検証してください:
- JSON が単体で valid であること（前後の説明文・フェンス無し）
- `lens_views` のキーが `Buffett_Munger` / `Burry` / `Lynch` で完全一致すること
- `counter_view` が空でないこと
- 禁止事項 5 種に該当する数値・期限・金額・助言フレーズを含んでいないこと
- `confidence_adjusted` / `kelly_multiplier` / `metadata` を含んでいないこと
"""


# ---------------------------------------------------------------------------
# 禁止パターン（一本線予測を 7 種の正規表現で検出）
# CLAUDE.md §9.3 「一本線の価格予測は禁止」を正規表現で機械的に強制する。
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 禁止予測フィールド（Pydantic スキーマレベルで一本線予測を構造的に拒否）
# CLAUDE.md §9.3 三層防御の中間層。FORBIDDEN_PATTERNS（正規表現）と組み合わせて
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


# ---------------------------------------------------------------------------
# 禁止パターン検出関数
# ---------------------------------------------------------------------------


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
# Provenance ヘルパー
# ---------------------------------------------------------------------------


def _get_current_git_commit() -> str | None:
    """現在の git commit short hash を返す。失敗時は None。

    sentiment.py の同名関数と同等実装（notes-5.2.md §2.1 参照）。
    Phase 6 で src/analysis/_common.py に統合予定。
    """
    try:
        completed = subprocess.run(  # noqa: S603, S607 — 固定引数のみ
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


# ---------------------------------------------------------------------------
# データクラス
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


# ---------------------------------------------------------------------------
# build_ranking_user_message — Sonnet 4.6 user message builder
# (Prompt Caching 安定化のため markdown 構造を決定論的に固定)
#
# Anthropic Prompt Caching の cache_control 境界では、同入力 → byte-identical
# な user message が必須。本関数は RankingSignalBundle の値順序・小数点桁数・
# placeholder 文言をすべて固定し、同 bundle で 2 回呼ぶと str 完全一致する。
#
# 型安全な fund_holdings_delta 処理:
#     bundle.fund_holdings_delta は dict[str, dict[str, object]] のため、
#     value_change_usd は object 型で返る。非数値は上流データ破損のシグナルと
#     して TypeError で fail-fast し、CLAUDE.md §9.3 silent 0.0 置換禁止 /
#     global rules never silently swallow errors を遵守する。
# ---------------------------------------------------------------------------


def _format_holdings(holdings: dict[str, dict[str, object]]) -> str:
    """13F 直近 1Q 差分辞書を markdown 化する（空時は placeholder 1 行）。

    Args:
        holdings: ``{fund_name: {"action": str, "value_change_usd": number}}``

    Returns:
        ``- {fund}: {action} (Δ ${value_m:.1f}M)`` を行頭 ``-`` で連結した
        markdown。``holdings`` が空辞書なら ``"- (差分なし)"`` を返す。

    Raises:
        TypeError: ``value_change_usd`` が ``int`` でも ``float`` でもない
            場合 -- 上流データ破損を fail-fast で表面化。
    """
    if not holdings:
        return "- (差分なし)"
    lines: list[str] = []
    for fund, data in holdings.items():
        action = str(data.get("action", "-"))
        raw_value = data.get("value_change_usd", 0)
        if not isinstance(raw_value, (int, float)):
            raise TypeError(
                f"value_change_usd must be int or float for fund {fund!r}, "
                f"got {type(raw_value).__name__}"
            )
        value_m = float(raw_value) / 1e6
        lines.append(f"- {fund}: {action} (Δ ${value_m:.1f}M)")
    return "\n".join(lines)


def _format_macro(macro: dict[str, Decimal]) -> str:
    """Polymarket マクロ確率辞書を markdown 化する（空時は placeholder 1 行）。

    Args:
        macro: ``{event_key: Decimal(0.0-1.0)}`` の確率辞書。

    Returns:
        ``- {key}: {value*100:.1f}%`` を行頭 ``-`` で連結した markdown。
        ``macro`` が空辞書なら ``"- (データなし)"`` を返す。
    """
    if not macro:
        return "- (データなし)"
    return "\n".join(f"- {k}: {float(v) * 100:.1f}%" for k, v in macro.items())


def _format_optional(value: object) -> str:
    """``None`` を ``"N/A"`` に置換した文字列を返す（その他は ``str()``）。

    型契約: ``value`` は ``Decimal | None`` を想定する。``float`` を渡しては
    ならない -- ``str(float)`` は IEEE 754 丸めにより非決定論となり、
    Anthropic Prompt Caching の byte-identical ヒット保証を破るため。
    呼び出し側は ``Decimal`` or ``None`` を保持する。
    """
    if value is None:
        return "N/A"
    return str(value)


def build_ranking_user_message(bundle: RankingSignalBundle) -> str:
    """RankingSignalBundle を Sonnet 4.6 用の user message に変換する純粋関数。

    Anthropic Prompt Caching (ephemeral) のヒット率最大化のため、markdown 構造・
    値順序・小数点桁数・placeholder 文言をすべて決定論的に固定する。同 bundle
    で 2 回呼ぶと str が byte-identical に一致する。

    セクション構成（PRD §FR2 / design.md line 630-689 整合）:
        1. ヘッダ: ``## 銘柄: {ticker} ({exchange}) / セクター: {sector|'不明'}``
        2. ``### Composite Score`` — composite + preset + 7 軸サブスコア
        3. ``### Magic Formula`` — score / ROC / EY (None → 'N/A')
        4. ``### モメンタム`` — 1m / 12m (None → 'N/A')
        5. ``### ニュースセンチメント`` — score / confidence / themes
        6. ``### Polymarket マクロ織り込み確率`` — 確率 % リスト
        7. ``### 13F 直近 1Q 差分`` — action + Δ$M リスト
        8. ``### Regime`` — 現在 + Bull/Choppy/Crisis 状態確率
        9. 末尾: JSON 返却の指示文

    Args:
        bundle: Stage 2 Sonnet 判定の入力シグナル束（frozen dataclass）。

    Returns:
        Sonnet 4.6 の user message として渡す markdown 文字列。
    """
    sector_str = bundle.sector or "不明"
    themes_str = ", ".join(bundle.sentiment_themes) or "(なし)"
    holdings_md = _format_holdings(bundle.fund_holdings_delta)
    macro_md = _format_macro(bundle.polymarket_macro)

    mf_score = _format_optional(bundle.magic_formula_score)
    roc = _format_optional(bundle.roc_pct)
    ey = _format_optional(bundle.earnings_yield_pct)
    mom_1m = _format_optional(bundle.momentum_1m)
    mom_12m = _format_optional(bundle.momentum_12m)

    sub = bundle.sub_scores
    bull_p = bundle.regime_state_probs.get("Bull", Decimal("0"))
    choppy_p = bundle.regime_state_probs.get("Choppy", Decimal("0"))
    crisis_p = bundle.regime_state_probs.get("Crisis", Decimal("0"))

    return (
        f"## 銘柄: {bundle.ticker} ({bundle.exchange}) / "
        f"セクター: {sector_str}\n\n"
        f"### Composite Score\n"
        f"- Composite: {bundle.composite_score:.1f}/100 "
        f"(preset: {bundle.composite_preset})\n"
        f"- 7 軸サブスコア: "
        f"Q={sub.get('Q', 0):.0f}, "
        f"V={sub.get('V', 0):.0f}, "
        f"I={sub.get('I', 0):.0f}, "
        f"G={sub.get('G', 0):.0f}, "
        f"R={sub.get('R', 0):.0f}, "
        f"M={sub.get('M', 0):.0f}, "
        f"S={sub.get('S', 0):.0f}\n\n"
        f"### Magic Formula\n"
        f"- スコア: {mf_score} / ROC: {roc} / EY: {ey}\n\n"
        f"### モメンタム\n"
        f"- 1m: {mom_1m} / 12m: {mom_12m}\n\n"
        f"### ニュースセンチメント (Haiku 4.5 既存)\n"
        f"- Score: {bundle.sentiment_score} / "
        f"Confidence: {bundle.sentiment_confidence}\n"
        f"- テーマ: {themes_str}\n\n"
        f"### Polymarket マクロ織り込み確率\n"
        f"{macro_md}\n\n"
        f"### 13F 直近 1Q 差分 (スマートマネー動向)\n"
        f"{holdings_md}\n\n"
        f"### Regime\n"
        f"- 現在: {bundle.regime} "
        f"(Bull={bull_p}, Choppy={choppy_p}, Crisis={crisis_p})\n\n"
        f"上記シグナル束を統合し、スキーマに従った JSON で判定結果を返してください。"
    )


# ---------------------------------------------------------------------------
# Helpers — JSON 抽出 / bundle hash / 縮退結果生成
# ---------------------------------------------------------------------------


def _extract_json(text: str) -> dict[str, Any]:
    """応答テキストから JSON dict を抽出する。

    抽出順序:
        1. ``` ```json ... ``` ``` または ``` ``` ... ``` ``` のコードブロック
        2. 最初の ``{`` から最後の ``}`` まで

    sentiment.py の同名関数と同等実装（notes-5.2.md §2.1 参照、
    Phase 6 で src/analysis/_common.py に統合予定）。

    Raises:
        ValueError: JSON が抽出できなかった場合。
        json.JSONDecodeError: JSON 構文不正の場合。
    """
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        return json.loads(fence.group(1))  # type: ignore[no-any-return]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("JSON not found in ranking judge response")
    return json.loads(text[start : end + 1])  # type: ignore[no-any-return]


def _compute_bundle_hash(bundle: RankingSignalBundle) -> str:
    """RankingSignalBundle の安定 SHA256 ハッシュを返す。

    用途:
        (a) Provenance §9.8.2 ``input_bundle_hash`` フィールド
        (b) Task 5.2.8 24h キャッシュキー

    Decimal / None / dict をすべて文字列化し ``json.dumps(sort_keys=True)``
    で正規化することで、同じ意味の bundle に対し常に同じ hex を返す。
    """
    payload: dict[str, Any] = {
        "ticker": bundle.ticker,
        "exchange": bundle.exchange,
        "composite_score": bundle.composite_score,
        "sub_scores": {k: str(v) for k, v in bundle.sub_scores.items()},
        "composite_preset": bundle.composite_preset,
        "magic_formula_score": bundle.magic_formula_score,
        "roc_pct": str(bundle.roc_pct),
        "earnings_yield_pct": str(bundle.earnings_yield_pct),
        "momentum_1m": str(bundle.momentum_1m),
        "momentum_12m": str(bundle.momentum_12m),
        "sentiment_score": str(bundle.sentiment_score),
        "polymarket_macro": {k: str(v) for k, v in bundle.polymarket_macro.items()},
        "fund_holdings_delta": bundle.fund_holdings_delta,
        "regime": bundle.regime,
    }
    serialized = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()


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
        reason: 縮退理由文字列（``"api_error: ..."`` /
            ``"schema_error: ..."`` / ``"forbidden_pattern_detected"``）。
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
            code_commit=_get_current_git_commit(),
        ),
    )


# ---------------------------------------------------------------------------
# rank_single_with_claude — Sonnet 4.6 ranking judge 本体（PRD §FR5 多段縮退）
# ---------------------------------------------------------------------------


def rank_single_with_claude(
    bundle: RankingSignalBundle,
    *,
    anthropic_client: Any,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> RankingResult:
    """1 銘柄を Sonnet 4.6 でランキング判定する（PRD §FR2/§FR5）。

    3 つの recovery path（PRD §FR5 多段縮退）で `RankingResult` を必ず返却:

    1. **API 例外** (network / 401 / 429 / 503 / SDK error / JSON 抽出失敗):
       ``_build_fallback_result(reason=f"api_error: {type(exc).__name__}")``
    2. **Pydantic スキーマ違反** (未定義 extra / 範囲外 / 一本線予測フィールド):
       ``_build_fallback_result(reason=f"schema_error: {type(exc).__name__}")``
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
        parsed = _extract_json(text)
    except Exception as exc:  # noqa: BLE001 — PRD §FR5 多段縮退、Anthropic SDK の多様な例外型を一括受け
        return _build_fallback_result(
            bundle,
            reason=f"api_error: {type(exc).__name__}",
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
        code_commit=_get_current_git_commit(),
    )

    # Path 2: Pydantic 検証 — extra='forbid' / 範囲制約 / 予測フィールド reject
    try:
        confidence = Decimal(str(parsed.pop("confidence", 0)))
        result = RankingResult(
            **parsed,
            confidence=confidence,
            confidence_adjusted=apply_regime_confidence(
                confidence, regime=bundle.regime
            ),
            kelly_multiplier=compute_kelly_multiplier(parsed.get("ranking_score", 0)),
            fallback_reason=None,
            metadata=raw_metadata,
        )
    except Exception as exc:  # noqa: BLE001 — PRD §FR5 多段縮退、ValidationError 等を一括受け
        return _build_fallback_result(
            bundle,
            reason=f"schema_error: {type(exc).__name__}",
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
