# Ranking Judge 実装計画（Phase 5.2-5.5）

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Claude Sonnet 4.6 を Stage 2 ranking judge にし、6 skill 統合のシグナル束で 02_screener.py の総合判定機能を完成させる

**Architecture:** 3 ステージ構成（Stage 1 既存数式フィルタ / Stage 2 新規 Sonnet 判定 / Stage 3 既存 skill を規律強制レイヤーとして再活用）。Pydantic v2 + 正規表現 2 段 TDD で一本線予測を構造的に禁止。シグナル別 TTL + Sonnet 判定 24 h キャッシュ。多段縮退（PRD §FR5 で正規化済みの規律的フォールバック仕様、ad-hoc patch ではない）。

**Tech Stack:** Python 3.12 / Pydantic v2 / anthropic SDK / pandas / pyarrow / Streamlit / Plotly / pytest / httpx / Playwright MCP

**上位仕様:** `docs/ranking-judge-prd.md`

---

## ファイル構成

### 新規作成

| パス | 責務 | 推定行数 |
|---|---|---:|
| `src/analysis/ranking_judge.py` | Sonnet 連携 / Pydantic 検証 / 正規表現スキャン / 多段縮退 / Stage 3 純粋関数 | 500 |
| `src/analysis/signal_aggregator.py` | 6 skill 統合 / RankingSignalBundle 組み立て | 400 |
| `src/analysis/monte_carlo.py` | GBM シミュレーション関数抽出（05_monte_carlo.py から） | 250 |
| `src/data/polymarket_client.py` | Polymarket Gamma API client | 300 |
| `src/data/sec_edgar_13f_diff.py` | 既存 sec_edgar.py 結果を QoQ 差分化 | 200 |
| `src/dashboard/widgets/ranking_card.py` | TOP 5 詳細カード Streamlit コンポーネント | 200 |
| `tests/unit/analysis/test_ranking_judge.py` | 10-15 テスト | 400 |
| `tests/unit/analysis/test_signal_aggregator.py` | 8-12 テスト | 300 |
| `tests/unit/analysis/test_monte_carlo.py` | 4-5 テスト | 150 |
| `tests/unit/data/test_polymarket_client.py` | 5-7 テスト | 200 |
| `tests/unit/data/test_sec_edgar_13f_diff.py` | 3-5 テスト | 150 |
| `tests/unit/analysis/conftest.py` | `make_bundle` 等の fixture | 100 |

### 修正

| パス | 修正内容 |
|---|---|
| `src/dashboard/views/02_screener.py` | UI 統合 + Stage 3 + MC chart + session_state refactor（§12.3 解消） |
| `src/dashboard/views/05_monte_carlo.py` | `simulate_gbm_paths()` 等の関数を新規 `analysis/monte_carlo.py` から呼ぶよう refactor |
| `src/config/settings.py` | `sonnet_model` / `sonnet_model_version` / `ranking_cache_ttl_sec` / `ranking_top_detail_count` 追加 |
| `src/portfolio/buy_decision.py` | `BuyOrderRequest.claude_ranking: dict | None = None` 追加 |
| `src/portfolio/decision_log.py` | `append_decision(..., claude_ranking=None)` 後方互換 kwarg |
| `.env.example` | `SONNET_MODEL` 等のサンプルエントリ追加 |

---

## 並列化マップ（Agent 起動戦略、PRD §10 と整合）

| Phase | 並列起動 | 起動方法 |
|---|---|---|
| **5.2 開始時** | `Explore`（sentiment.py パターン抽出）+ `docs-lookup`（Anthropic SDK Prompt Caching 仕様）+ `architect`（Pydantic v2 禁止フィールド設計レビュー） | 1 メッセージで 3 Agent tool call |
| **5.2 終了時** | `python-reviewer` + `security-reviewer` + `code-reviewer` | 同上 |
| **5.3 開始時 ★** | Polymarket client 実装 + 13F 差分抽出 + Regime アダプタを **3 サブエージェント並列** | 1 メッセージで 3 implement Agent 並列（最大の並列化効果） |
| **5.3 終了時** | 3 reviewer 並列 | 同上 |
| **5.4 開始時** | MC 関数抽出 + 詳細カード コンポーネント + session_state 構造調査 + settings.py 拡張 | 4 Agent 並列 |
| **5.4 終了時** | `python-reviewer` + `code-reviewer` | 2 reviewer 並列 |
| **5.5 終了時** | 3 reviewer 並列 + handoff doc 起草を別 Agent に並走 | 同上 |

**並列化しない箇所**（質優先）:
- ⚠️ TDD RED→GREEN（テスト先 → 実装の依存）
- ⚠️ Streamlit `02_screener.py` への統合（単一ファイル競合）
- ⚠️ Playwright E2E 実行（Streamlit インスタンス 1 つ）
- ⚠️ `git commit / push`（git 衝突回避）

---

# Phase 5.2: ロジック層 (`ranking_judge.py`)

## Task 5.2.0: 並列で前提情報を取得 ★

**Files:** なし（情報取得のみ、副産物として `.steering/.../notes-5.2.md` を生成）

- [ ] **Step 1: 3 Agent を 1 メッセージで並列起動**

```
Agent A (Explore, "very thorough"):
  prompt: "src/analysis/sentiment.py の Anthropic 連携実装パターンを抽出:
   - DEFAULT_MODEL / DEFAULT_MODEL_VERSION / DEFAULT_MAX_TOKENS 定数
   - _extract_json() / _get_current_git_commit() / _build_metadata() 関数の流用可能部分
   - SentimentMetadata / SentimentResult dataclass の継承可能箇所
  ranking_judge.py で再利用すべき部分と新規実装すべき部分を整理。"

Agent B (docs-lookup):
  prompt: "Anthropic Python SDK で以下を確認:
   1. messages.create に system プロンプトを cache_control で指定する方法
   2. cache_control の ephemeral type の制約（最小 token 数 / TTL）
   3. claude-sonnet-4-6 の正確なモデル ID と価格
   4. Prompt Caching ヒット率最大化のベストプラクティス
   5. response.usage.cache_read_input_tokens の取得方法
  Context7 経由でコード例付きで短くまとめて。"

Agent C (architect):
  prompt: "Pydantic v2 で「禁止フィールド名を reject する」設計をレビュー。
   要件:
   - RankingResult は frozen + extra='forbid'
   - 禁止フィールド: target_price / expected_return / time_horizon / price_target / forecast_price
   - 既存スキーマフィールドはそのまま許容
   model_config / model_validator / before validator のどれが最もシンプルで
   拡張しやすいか、コード例 30 行以内で推薦。"
```

- [ ] **Step 2: 結果を統合し `notes-5.2.md` を保存**

3 Agent の結果を統合して `.steering/20260512-claude-ranking-judge/notes-5.2.md` に保存。次のタスクで Anthropic SDK の最新仕様 + DEFAULT_MODEL_VERSION の確定値が参照される。

## Task 5.2.1: FORBIDDEN_PATTERNS + RankingMetadata + 雛形

**Files:**
- Create: `src/analysis/ranking_judge.py`
- Create: `tests/unit/analysis/test_ranking_judge.py`

- [ ] **Step 1: FORBIDDEN_PATTERNS 検出テスト**

```python
# tests/unit/analysis/test_ranking_judge.py
from __future__ import annotations
import pytest


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
    def test_禁止パターンを検出(self, text):
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
    def test_正常テキストは検出しない(self, text):
        from src.analysis.ranking_judge import contains_forbidden_pattern
        assert not contains_forbidden_pattern(text), f"誤検出: {text}"
```

- [ ] **Step 2: pytest RED 確認**

```bash
pytest tests/unit/analysis/test_ranking_judge.py -v
```

期待: `ImportError`

- [ ] **Step 3: 実装ファイルを作成**

```python
# src/analysis/ranking_judge.py
"""Claude Sonnet 4.6 Stage 2 ranking judge 実装。

CLAUDE.md §9.3 一本線予測禁止を 3 層強制（system prompt + Pydantic + 正規表現）。
Provenance §9.8.2 準拠の RankingMetadata を全結果に付与。
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Final

DEFAULT_MODEL: Final[str] = "claude-sonnet-4-6"
DEFAULT_MODEL_VERSION: Final[str] = "claude-sonnet-4-6-20260101"  # notes-5.2.md で確定値に差し替え
DEFAULT_MAX_TOKENS: Final[int] = 2048
ACADEMIC_SOURCE: Final[str] = (
    "Greenblatt 2010 + Tetlock 2007 + Schroeder & Posch 2024 + "
    "Pabrai Dhandho + Thorp 2006"
)

FORBIDDEN_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\$\s*\d+(\.\d+)?"),
    re.compile(r"¥\s*\d+(,\d{3})*"),
    re.compile(r"\d+\s*%\s*(上昇|下落|上がる|下がる|increase|decrease)"),
    re.compile(r"目標株価|target\s*price|price\s*target", re.IGNORECASE),
    re.compile(r"いつまで|by\s+\d+\s*(month|year|月|年)", re.IGNORECASE),
    re.compile(r"forecast\s+price|expected\s+price", re.IGNORECASE),
    re.compile(r"(\d+\s*ヶ月|\d+\s*months?)\s*以内", re.IGNORECASE),
)


def contains_forbidden_pattern(text: str) -> bool:
    """テキストに一本線予測パターンが含まれていれば True。"""
    return any(p.search(text) for p in FORBIDDEN_PATTERNS)


@dataclass(frozen=True)
class RankingMetadata:
    """Sonnet 判定結果の出所情報（Provenance §9.8.2）。"""

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


def _get_current_git_commit() -> str | None:
    """現在の git commit short hash。失敗時は None。sentiment.py 同名関数と同等。"""
    try:
        completed = subprocess.run(  # noqa: S603, S607
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=2, check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    return completed.stdout.strip() if completed.returncode == 0 else None
```

- [ ] **Step 4: GREEN 確認 + コミット**

```bash
pytest tests/unit/analysis/test_ranking_judge.py -v -m unit
git add src/analysis/ranking_judge.py tests/unit/analysis/test_ranking_judge.py
git commit -m "feat(ranking): FORBIDDEN_PATTERNS + RankingMetadata 雛形 [20260512-claude-ranking-judge]"
```

## Task 5.2.2: RankingResult Pydantic スキーマ（禁止フィールド reject）

**Files:**
- Modify: `src/analysis/ranking_judge.py`
- Modify: `tests/unit/analysis/test_ranking_judge.py`

- [ ] **Step 1: テスト追加**

```python
from decimal import Decimal
from pydantic import ValidationError


def _make_metadata_for_test():
    from src.analysis.ranking_judge import RankingMetadata, DEFAULT_MODEL, DEFAULT_MODEL_VERSION, ACADEMIC_SOURCE
    from datetime import datetime, timezone
    return RankingMetadata(
        model=DEFAULT_MODEL, model_version=DEFAULT_MODEL_VERSION,
        calculation_method="ranking_judge_v1", input_bundle_hash="x" * 64,
        cache_hit=False, cache_age_sec=None,
        input_tokens=0, output_tokens=0, input_tokens_cached=0,
        calculated_at=datetime.now(timezone.utc),
        academic_source=ACADEMIC_SOURCE, code_commit=None,
    )


class TestRankingResultSchema:
    @pytest.mark.unit
    def test_正常な_payload_は_インスタンス化できる(self):
        from src.analysis.ranking_judge import RankingResult
        result = RankingResult(
            ranking_score=85,
            recommendation_summary="Composite + 13F + マクロ整合性高い",
            supporting_signals=("Composite Q=90", "Berkshire NEW position"),
            risk_signals=("Recency Bias 懸念",),
            counter_view="Burry はマクロ警戒中、慎重論あり",
            lens_views={
                "Buffett_Munger": "質×価値良好",
                "Burry": "テールリスク懸念",
                "Lynch": "消費者目線で堅調",
            },
            confidence=Decimal("0.75"), confidence_adjusted=Decimal("0.75"),
            kelly_multiplier=Decimal("1.0"),
            metadata=_make_metadata_for_test(),
        )
        assert result.ranking_score == 85

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "forbidden_field",
        ["target_price", "expected_return", "time_horizon", "price_target", "forecast_price"],
    )
    def test_禁止フィールドが入っていたら_ValidationError(self, forbidden_field):
        from src.analysis.ranking_judge import RankingResult
        payload = {
            "ranking_score": 80, "recommendation_summary": "t",
            "supporting_signals": (), "risk_signals": (), "counter_view": "t",
            "lens_views": {"Buffett_Munger": "", "Burry": "", "Lynch": ""},
            "confidence": Decimal("0.5"), "confidence_adjusted": Decimal("0.5"),
            "kelly_multiplier": Decimal("0.5"),
            "metadata": _make_metadata_for_test(),
            forbidden_field: 200,
        }
        with pytest.raises(ValidationError):
            RankingResult.model_validate(payload)

    @pytest.mark.unit
    def test_ranking_score_範囲外で_ValidationError(self):
        from src.analysis.ranking_judge import RankingResult
        payload = {
            "ranking_score": 150, "recommendation_summary": "t",
            "supporting_signals": (), "risk_signals": (), "counter_view": "t",
            "lens_views": {"Buffett_Munger": "", "Burry": "", "Lynch": ""},
            "confidence": Decimal("0.5"), "confidence_adjusted": Decimal("0.5"),
            "kelly_multiplier": Decimal("0.5"),
            "metadata": _make_metadata_for_test(),
        }
        with pytest.raises(ValidationError):
            RankingResult.model_validate(payload)

    @pytest.mark.unit
    def test_lens_views_に_3_キー揃わないと_ValidationError(self):
        from src.analysis.ranking_judge import RankingResult
        payload = {
            "ranking_score": 80, "recommendation_summary": "t",
            "supporting_signals": (), "risk_signals": (), "counter_view": "t",
            "lens_views": {"Buffett_Munger": "x"},
            "confidence": Decimal("0.5"), "confidence_adjusted": Decimal("0.5"),
            "kelly_multiplier": Decimal("0.5"),
            "metadata": _make_metadata_for_test(),
        }
        with pytest.raises(ValidationError):
            RankingResult.model_validate(payload)
```

- [ ] **Step 2: pytest RED → 実装**

```python
# src/analysis/ranking_judge.py へ追記
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class RankingResult(BaseModel):
    """Sonnet 出力の構造化結果。一本線禁止を Pydantic で強制。"""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    ranking_score: int = Field(ge=0, le=100)
    recommendation_summary: str = Field(max_length=150)
    supporting_signals: tuple[str, ...] = Field(default_factory=tuple, max_length=5)
    risk_signals: tuple[str, ...] = Field(default_factory=tuple, max_length=5)
    counter_view: str = Field(max_length=200)
    lens_views: dict[Literal["Buffett_Munger", "Burry", "Lynch"], str]
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    confidence_adjusted: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    kelly_multiplier: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    fallback_reason: str | None = None
    metadata: RankingMetadata

    @model_validator(mode="after")
    def _validate_lens_views_complete(self) -> "RankingResult":
        required = {"Buffett_Munger", "Burry", "Lynch"}
        if set(self.lens_views.keys()) != required:
            raise ValueError(f"lens_views must have exactly keys {required}")
        return self
```

- [ ] **Step 3: GREEN + コミット**

```bash
pytest tests/unit/analysis/test_ranking_judge.py -v -m unit
git commit -am "feat(ranking): RankingResult Pydantic + 禁止フィールド reject [20260512-claude-ranking-judge]"
```

## Task 5.2.3: RankingSignalBundle dataclass + conftest fixture

**Files:**
- Modify: `src/analysis/ranking_judge.py`
- Create: `tests/unit/analysis/conftest.py`

- [ ] **Step 1: conftest に make_bundle fixture を作る**

```python
# tests/unit/analysis/conftest.py
import pytest
from datetime import datetime, timezone
from decimal import Decimal


@pytest.fixture
def make_bundle():
    """RankingSignalBundle の標準 fixture（ticker / regime / composite_score を可変）。"""
    from src.analysis.ranking_judge import RankingSignalBundle

    def _make(ticker="AAPL", regime="Bull", composite_score=72.5):
        return RankingSignalBundle(
            ticker=ticker, exchange="US", sector="Technology",
            composite_score=composite_score,
            sub_scores={"Q": 90, "V": 50, "I": 30, "G": 60, "R": 80, "M": 70, "S": 55},
            composite_preset="Buffett_型_暫定",
            magic_formula_score=85.0,
            roc_pct=Decimal("32.5"), earnings_yield_pct=Decimal("8.2"),
            momentum_1m=Decimal("3.2"), momentum_12m=Decimal("28.5"),
            sentiment_score=Decimal("0.4"), sentiment_confidence=Decimal("0.7"),
            sentiment_themes=("iPhone 出荷",),
            polymarket_macro={"fed_cut_2026": Decimal("0.62")},
            fund_holdings_delta={"Berkshire": {"action": "NEW", "value_change_usd": 5_200_000_000}},
            regime=regime,
            regime_state_probs={"Bull": Decimal("0.6"), "Choppy": Decimal("0.3"), "Crisis": Decimal("0.1")},
            fetched_at=datetime.now(timezone.utc),
        )
    return _make
```

- [ ] **Step 2: dataclass テスト + 実装**

```python
class TestRankingSignalBundle:
    @pytest.mark.unit
    def test_frozen_で_書き換え不可(self, make_bundle):
        import dataclasses
        bundle = make_bundle()
        with pytest.raises(dataclasses.FrozenInstanceError):
            bundle.ticker = "MSFT"  # type: ignore[misc]

    @pytest.mark.unit
    def test_regime_別の作成(self, make_bundle):
        for r in ("Bull", "Choppy", "Crisis"):
            b = make_bundle(regime=r)
            assert b.regime == r
```

```python
# src/analysis/ranking_judge.py へ追記
@dataclass(frozen=True)
class RankingSignalBundle:
    """Stage 2 Sonnet 判定の入力シグナル束（中スコープ B、PRD §FR2）。"""

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
    fund_holdings_delta: dict[str, dict]
    regime: Literal["Bull", "Choppy", "Crisis"]
    regime_state_probs: dict[str, Decimal]
    fetched_at: datetime
```

- [ ] **Step 3: GREEN + コミット**

```bash
pytest tests/unit/analysis/test_ranking_judge.py -v -m unit
git add src/analysis/ranking_judge.py tests/unit/analysis/conftest.py tests/unit/analysis/test_ranking_judge.py
git commit -m "feat(ranking): RankingSignalBundle dataclass + fixture [20260512-claude-ranking-judge]"
```

## Task 5.2.4: validate_no_price_predictions() + Stage 3 純粋関数

**Files:**
- Modify: `src/analysis/ranking_judge.py`
- Modify: `tests/unit/analysis/test_ranking_judge.py`

- [ ] **Step 1: テスト**

```python
class TestValidateNoPricePredictions:
    @pytest.mark.unit
    def test_全テキストフィールドをスキャンする(self, make_bundle):
        from src.analysis.ranking_judge import validate_no_price_predictions, RankingResult
        bad = RankingResult(
            ranking_score=80, recommendation_summary="AAPL は $200 になる",
            supporting_signals=(), risk_signals=(), counter_view="t",
            lens_views={"Buffett_Munger": "", "Burry": "", "Lynch": ""},
            confidence=Decimal("0.5"), confidence_adjusted=Decimal("0.5"),
            kelly_multiplier=Decimal("0.5"), metadata=_make_metadata_for_test(),
        )
        with pytest.raises(ValueError, match="forbidden pattern"):
            validate_no_price_predictions(bad)


class TestStage3Helpers:
    @pytest.mark.unit
    @pytest.mark.parametrize(
        "regime,expected",
        [("Bull", Decimal("0.8")), ("Choppy", Decimal("0.8")), ("Crisis", Decimal("0.4"))],
    )
    def test_apply_regime_confidence(self, regime, expected):
        from src.analysis.ranking_judge import apply_regime_confidence
        assert apply_regime_confidence(Decimal("0.8"), regime=regime) == expected

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "score,expected",
        [(85, Decimal("1.0")), (80, Decimal("1.0")), (79, Decimal("0.5")),
         (50, Decimal("0.5")), (49, Decimal("0.0")), (0, Decimal("0.0"))],
    )
    def test_compute_kelly_multiplier(self, score, expected):
        from src.analysis.ranking_judge import compute_kelly_multiplier
        assert compute_kelly_multiplier(score) == expected
```

- [ ] **Step 2: 実装**

```python
# src/analysis/ranking_judge.py へ追記
def validate_no_price_predictions(result: RankingResult) -> None:
    """RankingResult の全テキストフィールドに一本線予測が含まれていないか検証。"""
    fields_to_scan = [
        result.recommendation_summary,
        result.counter_view,
        *result.supporting_signals,
        *result.risk_signals,
        *result.lens_views.values(),
    ]
    for txt in fields_to_scan:
        if contains_forbidden_pattern(txt):
            raise ValueError(f"forbidden pattern in text: {txt[:60]}...")


def apply_regime_confidence(
    confidence: Decimal, *, regime: Literal["Bull", "Choppy", "Crisis"]
) -> Decimal:
    """Crisis 時のみ confidence を半減（CLAUDE.md §9.5 / §9.7）。"""
    multiplier = Decimal("0.5") if regime == "Crisis" else Decimal("1.0")
    return confidence * multiplier


def compute_kelly_multiplier(ranking_score: int) -> Decimal:
    """ranking_score から Kelly 連動係数を決定。

    >= 80 → 1.0 (Full Half-Kelly)
    50-79 → 0.5
    < 50  → 0.0 (買い非推奨)
    """
    if ranking_score >= 80:
        return Decimal("1.0")
    if ranking_score >= 50:
        return Decimal("0.5")
    return Decimal("0.0")
```

- [ ] **Step 3: GREEN + コミット**

```bash
pytest tests/unit/analysis/test_ranking_judge.py -v -m unit
git commit -am "feat(ranking): validate_no_price_predictions + Stage 3 純粋関数 [20260512-claude-ranking-judge]"
```

## Task 5.2.5: SYSTEM_PROMPT 定数

**Files:**
- Modify: `src/analysis/ranking_judge.py`

- [ ] **Step 1: SYSTEM_PROMPT を追記**

```python
# src/analysis/ranking_judge.py へ追記
SYSTEM_PROMPT: Final[str] = """あなたは株式投資判定アシスタントです。最終判断は常にユーザーが行います。

## あなたの役割

シグナル束（Composite 7 軸 / Magic Formula / モメンタム / ニュースセンチメント /
Polymarket / 13F / Regime）を統合し、構造化 JSON で判定結果を返します。

## 必須事項

1. **反対意見 (counter_view)** を 1-2 文で生成（Confirmation Bias 対策）
2. **学術的バックボーン** に基づく根拠を supporting_signals に含める:
   - Greenblatt 2010 (Magic Formula)
   - Tetlock 2007 (Sentiment)
   - Schroeder & Posch 2024 (13F クローン)
   - Pabrai Dhandho (集中投資)
3. **リスク警告** を risk_signals に: Value Trap / Recency Bias / Overconfidence
4. **多角レンズ 3 視点** を lens_views に同時表示:
   - Buffett_Munger: 質 × 価値 + 長期資本配分
   - Burry: テールリスク + クレジット観
   - Lynch: 消費者目線 + 業界トレンド

## 禁止事項（厳守）

- ❌ **目標株価の数値予測**（例: "$200 になる" → 禁止）
- ❌ **上昇率 % の数値予測**（例: "15% 上昇予測" → 禁止）
- ❌ **期限付き予測**（例: "3 ヶ月以内に高値更新" → 禁止）
- ❌ **投資助言フレーズ**（例: "買いを推奨します" → 禁止）
- ❌ **金額の明示**（$ / ¥ の数値併記）

これらが含まれていたら出力は無効化されます。

## 出力スキーマ

以下の JSON のみ返してください。前置き・後置き・コードブロックフェンス不要:

{
  "ranking_score": 0-100 の整数,
  "recommendation_summary": "1-2 文（150 字以内）",
  "supporting_signals": ["シグナル 1", "シグナル 2", ...],
  "risk_signals": ["リスク 1", "リスク 2", ...],
  "counter_view": "反対意見（200 字以内）",
  "lens_views": {
    "Buffett_Munger": "...",
    "Burry": "...",
    "Lynch": "..."
  },
  "confidence": 0.0-1.0
}

confidence_adjusted / kelly_multiplier / metadata は呼び出し側で計算するので出力しないでください。
"""
```

- [ ] **Step 2: コミット**

```bash
git commit -am "feat(ranking): SYSTEM_PROMPT 1500 token [20260512-claude-ranking-judge]"
```

## Task 5.2.6: build_ranking_user_message() + TDD

**Files:**
- Modify: `src/analysis/ranking_judge.py`
- Modify: `tests/unit/analysis/test_ranking_judge.py`

- [ ] **Step 1: テスト**

```python
class TestBuildRankingUserMessage:
    @pytest.mark.unit
    def test_必須セクションが全て含まれる(self, make_bundle):
        from src.analysis.ranking_judge import build_ranking_user_message
        msg = build_ranking_user_message(make_bundle())
        for must_include in ("AAPL", "Composite Score", "Magic Formula", "Polymarket", "13F", "Regime", "Bull"):
            assert must_include in msg, f"missing: {must_include}"
```

- [ ] **Step 2: 実装**

```python
def build_ranking_user_message(bundle: RankingSignalBundle) -> str:
    """シグナル束を markdown 化（Prompt Caching 安定化のため構造を固定）。"""
    holdings_lines = "\n".join(
        f"- {fund}: {data.get('action', '-')} (Δ ${data.get('value_change_usd', 0) / 1e6:.1f}M)"
        for fund, data in bundle.fund_holdings_delta.items()
    ) or "- (差分なし)"

    macro_lines = "\n".join(
        f"- {k}: {float(v) * 100:.1f}%" for k, v in bundle.polymarket_macro.items()
    ) or "- (データなし)"

    return f"""## 銘柄: {bundle.ticker} ({bundle.exchange}) / セクター: {bundle.sector or '不明'}

### Composite Score
- Composite: {bundle.composite_score:.1f}/100 (preset: {bundle.composite_preset})
- 7 軸サブスコア: Q={bundle.sub_scores.get('Q', 0):.0f}, V={bundle.sub_scores.get('V', 0):.0f}, I={bundle.sub_scores.get('I', 0):.0f}, G={bundle.sub_scores.get('G', 0):.0f}, R={bundle.sub_scores.get('R', 0):.0f}, M={bundle.sub_scores.get('M', 0):.0f}, S={bundle.sub_scores.get('S', 0):.0f}

### Magic Formula
- スコア: {bundle.magic_formula_score or 'N/A'} / ROC: {bundle.roc_pct or 'N/A'} / EY: {bundle.earnings_yield_pct or 'N/A'}

### モメンタム
- 1m: {bundle.momentum_1m or 'N/A'} / 12m: {bundle.momentum_12m or 'N/A'}

### ニュースセンチメント (Haiku 4.5 既存)
- Score: {bundle.sentiment_score} / Confidence: {bundle.sentiment_confidence}
- テーマ: {', '.join(bundle.sentiment_themes) or '(なし)'}

### Polymarket マクロ織り込み確率
{macro_lines}

### 13F 直近 1Q 差分 (スマートマネー動向)
{holdings_lines}

### Regime
- 現在: {bundle.regime} (Bull={bundle.regime_state_probs.get('Bull', 0)}, Choppy={bundle.regime_state_probs.get('Choppy', 0)}, Crisis={bundle.regime_state_probs.get('Crisis', 0)})

上記シグナル束を統合し、スキーマに従った JSON で判定結果を返してください。
"""
```

- [ ] **Step 3: GREEN + コミット**

```bash
pytest tests/unit/analysis/test_ranking_judge.py -v -m unit
git commit -am "feat(ranking): build_ranking_user_message [20260512-claude-ranking-judge]"
```

## Task 5.2.7: rank_single_with_claude() + 多段縮退

**Files:**
- Modify: `src/analysis/ranking_judge.py`
- Modify: `tests/unit/analysis/test_ranking_judge.py`

- [ ] **Step 1: テスト 4 件**

```python
from unittest.mock import MagicMock


class TestRankSingleWithClaude:
    @pytest.fixture
    def good_response(self):
        class _C: text = '{"ranking_score": 78, "recommendation_summary": "Composite 高 + 13F 整合", "supporting_signals": ["Composite Q=90", "Berkshire NEW position"], "risk_signals": ["Recency Bias"], "counter_view": "Burry はマクロ警戒中", "lens_views": {"Buffett_Munger": "質×価値良好", "Burry": "テールリスク懸念", "Lynch": "消費者目線で堅調"}, "confidence": 0.72}'
        class _U: input_tokens = 1200; output_tokens = 350; cache_read_input_tokens = 800
        class _R: content = [_C()]; usage = _U()
        return _R()

    @pytest.mark.unit
    def test_正常系_RankingResult_返却(self, make_bundle, good_response):
        from src.analysis.ranking_judge import rank_single_with_claude, RankingResult
        client = MagicMock()
        client.messages.create.return_value = good_response
        result = rank_single_with_claude(make_bundle(regime="Bull"), anthropic_client=client)
        assert isinstance(result, RankingResult)
        assert result.ranking_score == 78
        assert result.confidence_adjusted == result.confidence  # Bull → 補正なし
        assert result.kelly_multiplier == Decimal("0.5")  # 50-79

    @pytest.mark.unit
    def test_Crisis_時_confidence_adjusted_半減(self, make_bundle, good_response):
        from src.analysis.ranking_judge import rank_single_with_claude
        client = MagicMock()
        client.messages.create.return_value = good_response
        result = rank_single_with_claude(make_bundle(regime="Crisis"), anthropic_client=client)
        assert result.confidence_adjusted == result.confidence * Decimal("0.5")

    @pytest.mark.unit
    def test_API_例外時_Composite_埋め_fallback(self, make_bundle):
        from src.analysis.ranking_judge import rank_single_with_claude
        client = MagicMock()
        client.messages.create.side_effect = Exception("API error")
        result = rank_single_with_claude(make_bundle(composite_score=72.5), anthropic_client=client)
        assert result.fallback_reason is not None
        assert "api_error" in result.fallback_reason
        assert result.ranking_score == 72  # composite_score を int 化

    @pytest.mark.unit
    def test_一本線予測検出時_forbidden_pattern_fallback(self, make_bundle):
        """Sonnet が誤って予測値を出した場合、fallback_reason が立つ。"""
        from src.analysis.ranking_judge import rank_single_with_claude
        class _C:
            text = '{"ranking_score": 80, "recommendation_summary": "AAPL は $200 になる", "supporting_signals": [], "risk_signals": [], "counter_view": "test", "lens_views": {"Buffett_Munger": "x", "Burry": "y", "Lynch": "z"}, "confidence": 0.5}'
        class _U: input_tokens = 100; output_tokens = 100; cache_read_input_tokens = 0
        class _R: content = [_C()]; usage = _U()
        client = MagicMock()
        client.messages.create.return_value = _R()
        result = rank_single_with_claude(make_bundle(), anthropic_client=client)
        assert result.fallback_reason == "forbidden_pattern_detected"
```

- [ ] **Step 2: 実装**

```python
# src/analysis/ranking_judge.py へ追記
import hashlib
import json
from typing import Any


def _extract_json(text: str) -> dict[str, Any]:
    """sentiment.py の同名関数を継承。"""
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        return json.loads(fence.group(1))
    s = text.find("{"); e = text.rfind("}")
    if s == -1 or e == -1 or e < s:
        raise ValueError("JSON not found in response")
    return json.loads(text[s : e + 1])


def _compute_bundle_hash(bundle: RankingSignalBundle) -> str:
    """RankingSignalBundle の安定 SHA256。"""
    payload = {
        "ticker": bundle.ticker, "exchange": bundle.exchange,
        "composite_score": bundle.composite_score, "sub_scores": bundle.sub_scores,
        "composite_preset": bundle.composite_preset,
        "magic_formula_score": bundle.magic_formula_score,
        "roc_pct": str(bundle.roc_pct), "earnings_yield_pct": str(bundle.earnings_yield_pct),
        "momentum_1m": str(bundle.momentum_1m), "momentum_12m": str(bundle.momentum_12m),
        "sentiment_score": str(bundle.sentiment_score),
        "polymarket_macro": {k: str(v) for k, v in bundle.polymarket_macro.items()},
        "fund_holdings_delta": bundle.fund_holdings_delta,
        "regime": bundle.regime,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _build_fallback_result(
    bundle: RankingSignalBundle, *, reason: str, started_at: datetime
) -> RankingResult:
    """PRD §FR5 多段縮退の核: Composite Score で埋めて fallback_reason 記録。"""
    score = int(bundle.composite_score)
    return RankingResult(
        ranking_score=score,
        recommendation_summary=f"Claude 判定不可、Composite Score {score} で代替（{reason}）。",
        supporting_signals=(f"Composite={bundle.composite_score:.1f}",),
        risk_signals=("Claude 判定取得失敗、数式スコアのみで判断中",),
        counter_view="Claude 不在のため反対意見生成不可。ユーザー自身で他根拠を確認推奨。",
        lens_views={"Buffett_Munger": "(不在)", "Burry": "(不在)", "Lynch": "(不在)"},
        confidence=Decimal("0.3"),
        confidence_adjusted=apply_regime_confidence(Decimal("0.3"), regime=bundle.regime),
        kelly_multiplier=compute_kelly_multiplier(score),
        fallback_reason=reason,
        metadata=RankingMetadata(
            model="(fallback)", model_version="(fallback)",
            calculation_method="ranking_judge_v1_fallback",
            input_bundle_hash=_compute_bundle_hash(bundle),
            cache_hit=False, cache_age_sec=None,
            input_tokens=0, output_tokens=0, input_tokens_cached=0,
            calculated_at=started_at, academic_source=ACADEMIC_SOURCE,
            code_commit=_get_current_git_commit(),
        ),
    )


def rank_single_with_claude(
    bundle: RankingSignalBundle, *, anthropic_client: Any,
    model: str = DEFAULT_MODEL, max_tokens: int = DEFAULT_MAX_TOKENS,
) -> RankingResult:
    """1 銘柄を Sonnet で判定。API 失敗 / スキーマ違反 / 一本線検出は縮退。"""
    started_at = datetime.now(timezone.utc)
    user_msg = build_ranking_user_message(bundle)

    try:
        response = anthropic_client.messages.create(
            model=model, max_tokens=max_tokens,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user_msg}],
        )
        text = response.content[0].text
        parsed = _extract_json(text)
    except Exception as exc:  # noqa: BLE001
        return _build_fallback_result(
            bundle, reason=f"api_error: {type(exc).__name__}", started_at=started_at
        )

    raw_metadata = RankingMetadata(
        model=model, model_version=DEFAULT_MODEL_VERSION,
        calculation_method="ranking_judge_v1",
        input_bundle_hash=_compute_bundle_hash(bundle),
        cache_hit=False, cache_age_sec=None,
        input_tokens=getattr(response.usage, "input_tokens", 0),
        output_tokens=getattr(response.usage, "output_tokens", 0),
        input_tokens_cached=getattr(response.usage, "cache_read_input_tokens", 0),
        calculated_at=started_at, academic_source=ACADEMIC_SOURCE,
        code_commit=_get_current_git_commit(),
    )

    try:
        confidence = Decimal(str(parsed.pop("confidence", 0)))
        result = RankingResult(
            **parsed,
            confidence=confidence,
            confidence_adjusted=apply_regime_confidence(confidence, regime=bundle.regime),
            kelly_multiplier=compute_kelly_multiplier(parsed.get("ranking_score", 0)),
            fallback_reason=None,
            metadata=raw_metadata,
        )
    except Exception as exc:  # noqa: BLE001
        return _build_fallback_result(
            bundle, reason=f"schema_error: {type(exc).__name__}", started_at=started_at
        )

    try:
        validate_no_price_predictions(result)
    except ValueError:
        return _build_fallback_result(
            bundle, reason="forbidden_pattern_detected", started_at=started_at
        )

    return result
```

- [ ] **Step 3: GREEN + コミット**

```bash
pytest tests/unit/analysis/test_ranking_judge.py -v -m unit
git commit -am "feat(ranking): rank_single_with_claude + PRD §FR5 多段縮退 [20260512-claude-ranking-judge]"
```

## Task 5.2.8: rank_with_claude_batch() + 24 h キャッシュ I/O

**Files:**
- Modify: `src/analysis/ranking_judge.py`
- Modify: `tests/unit/analysis/test_ranking_judge.py`

- [ ] **Step 1: キャッシュ ヒット / ミス / TTL 超過テスト**

```python
class TestRankWithClaudeBatch:
    @pytest.mark.unit
    def test_キャッシュヒット時に_API_呼び出ししない(self, tmp_path, make_bundle, good_response):
        from src.analysis.ranking_judge import rank_with_claude_batch
        client = MagicMock()
        client.messages.create.return_value = good_response
        bundles = [make_bundle()]
        r1 = rank_with_claude_batch(bundles, anthropic_client=client, cache_dir=tmp_path)
        assert client.messages.create.call_count == 1
        assert r1[0].metadata.cache_hit is False

        r2 = rank_with_claude_batch(bundles, anthropic_client=client, cache_dir=tmp_path)
        assert client.messages.create.call_count == 1  # 増えない
        assert r2[0].metadata.cache_hit is True

    @pytest.mark.unit
    def test_TTL_超過なら_再呼び出し(self, tmp_path, make_bundle, good_response, monkeypatch):
        from src.analysis import ranking_judge as rj
        from datetime import timedelta
        client = MagicMock()
        client.messages.create.return_value = good_response
        bundles = [make_bundle()]
        rj.rank_with_claude_batch(bundles, anthropic_client=client, cache_dir=tmp_path)
        future = datetime.now(timezone.utc) + timedelta(hours=25)
        monkeypatch.setattr(rj, "_now_utc", lambda: future)
        rj.rank_with_claude_batch(bundles, anthropic_client=client, cache_dir=tmp_path)
        assert client.messages.create.call_count == 2  # 再呼び出し発生
```

- [ ] **Step 2: 実装**

```python
# src/analysis/ranking_judge.py へ追記
import dataclasses
from pathlib import Path

CACHE_TTL_SEC: Final[int] = 24 * 3600


def _now_utc() -> datetime:
    """テスタブルにするためのフック。"""
    return datetime.now(timezone.utc)


def _cache_path(cache_dir: Path, bundle: RankingSignalBundle, model_version: str) -> Path:
    key_src = f"{bundle.ticker}|{bundle.composite_preset}|{bundle.regime}|{_compute_bundle_hash(bundle)}|{model_version}"
    key = hashlib.sha256(key_src.encode()).hexdigest()[:32]
    return cache_dir / f"{bundle.ticker}_{key}.json"


def _read_cache(cache_path: Path, *, ttl_sec: int) -> RankingResult | None:
    if not cache_path.exists():
        return None
    stat = cache_path.stat()
    mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    age = (_now_utc() - mtime).total_seconds()
    if age > ttl_sec:
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        md = payload["metadata"]
        md["calculated_at"] = datetime.fromisoformat(md["calculated_at"])
        metadata = RankingMetadata(**md)
        metadata = dataclasses.replace(metadata, cache_hit=True, cache_age_sec=int(age))
        payload["metadata"] = metadata
        for k in ("confidence", "confidence_adjusted", "kelly_multiplier"):
            payload[k] = Decimal(str(payload[k]))
        payload["supporting_signals"] = tuple(payload["supporting_signals"])
        payload["risk_signals"] = tuple(payload["risk_signals"])
        return RankingResult(**payload)
    except (ValueError, KeyError, json.JSONDecodeError):
        return None


def _write_cache(cache_path: Path, result: RankingResult) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = result.model_dump(mode="json")
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def rank_with_claude_batch(
    bundles: list[RankingSignalBundle], *,
    anthropic_client: Any, cache_dir: Path,
    model: str = DEFAULT_MODEL, model_version: str = DEFAULT_MODEL_VERSION,
    ttl_sec: int = CACHE_TTL_SEC,
) -> list[RankingResult]:
    """銘柄一括ランキング。キャッシュ層 + 多段縮退（PRD §FR5）。"""
    results: list[RankingResult] = []
    for bundle in bundles:
        cache_path = _cache_path(cache_dir, bundle, model_version)
        cached = _read_cache(cache_path, ttl_sec=ttl_sec)
        if cached is not None:
            results.append(cached)
            continue
        result = rank_single_with_claude(bundle, anthropic_client=anthropic_client, model=model)
        if result.fallback_reason is None:
            _write_cache(cache_path, result)
        results.append(result)
    return results
```

- [ ] **Step 3: GREEN + コミット**

```bash
pytest tests/unit/analysis/test_ranking_judge.py -v -m unit
git commit -am "feat(ranking): rank_with_claude_batch + 24h キャッシュ I/O [20260512-claude-ranking-judge]"
```

## Task 5.2.9: Phase 5.2 並列レビュー

**Files:** なし

- [ ] **Step 1: 3 reviewer を 1 メッセージで並列起動**

```
python-reviewer + security-reviewer + code-reviewer をそれぞれ別の Agent tool call で起動:
  対象: src/analysis/ranking_judge.py + tests/unit/analysis/test_ranking_judge.py
  CRITICAL/HIGH の指摘は次ステップで対応
```

- [ ] **Step 2: CRITICAL/HIGH 対応 + コミット**

```bash
pytest tests/unit/analysis/test_ranking_judge.py -v --cov=src/analysis/ranking_judge
# カバレッジ 80%+ 確認
git commit -am "fix(ranking): Phase 5.2 並列レビュー反映 [20260512-claude-ranking-judge]"
```

---

# Phase 5.3: シグナル束（`signal_aggregator.py` + Polymarket + 13F diff + Regime）

## Task 5.3.0: ★ 3 サブエージェント並列起動

**Files:** なし（並列起動指示）

- [ ] **Step 1: 1 メッセージで 3 Agent 並列起動**

```
Agent A (general-purpose, "Polymarket client 完全実装"):
  task: "src/data/polymarket_client.py を新規実装。仕様:
   - エンドポイント: https://gamma-api.polymarket.com/markets
   - 関数: fetch_macro_probabilities(topics: list[str]) -> dict[str, Decimal]
     topics 例: ['fed_rate_cut_2026', 'us_recession_2026', 'geopolitical_risk']
   - レート制限: 60 req/min（ratelimit + sleep_and_retry）
   - キャッシュ: data/cache/polymarket/*.parquet TTL 6h
   - 戻り値: {topic: Decimal('0.62')} 形式
   - df.attrs に CLAUDE.md §9.8.1 メタデータ付与
   - 失敗時は ValueError + 警告ログ（個別フォールバック前提）
   TDD で先にテスト 5 件書いてから実装。httpx をモック。"

Agent B (general-purpose, "13F 差分抽出"):
  task: "src/data/sec_edgar_13f_diff.py を新規実装。既存 src/data/sec_edgar.py の
   fetch_13f_holdings() を呼び、最新 + 前期の DataFrame を取得して
   QoQ 差分を計算する関数を提供:
   - extract_holdings_delta(ticker: str, *, sec_client, tracked_funds) -> dict[str, dict]
     戻り値: {'Berkshire': {'action': 'NEW'|'INCREASE'|'DECREASE'|'EXIT', 'value_change_usd': int}, ...}
   - TRACKED_FUNDS = settings.tracked_funds_cik_list
   - キャッシュ TTL 90d
   - 失敗時は空 dict + 警告ログ
   TDD 3-5 件、既存 fetch_13f_holdings をモック化。"

Agent C (general-purpose, "Regime アダプタ"):
  task: "src/analysis/signal_aggregator.py に Regime 部分のみ先行実装。
   関数: build_regime_signals(*, universe_prices, vix_series=None) -> dict
     戻り値: {'regime': 'Bull'|'Choppy'|'Crisis', 'state_probs': {Bull: Decimal('0.6'), ...}}
   既存 src/analysis/regime.py の detect_regime_with_provenance() をラップ。
   キャッシュ TTL 24h。VIX 失敗時は既存実装の realized_vol 代理を維持。
   TDD 2-3 件。"
```

- [ ] **Step 2: 3 Agent 結果を確認 + 個別コミット**

```bash
pytest tests/unit/data/test_polymarket_client.py -v
git add src/data/polymarket_client.py tests/unit/data/test_polymarket_client.py
git commit -m "feat(data): Polymarket client + TDD [20260512-claude-ranking-judge]"

pytest tests/unit/data/test_sec_edgar_13f_diff.py -v
git add src/data/sec_edgar_13f_diff.py tests/unit/data/test_sec_edgar_13f_diff.py
git commit -m "feat(data): 13F QoQ 差分抽出 + TDD [20260512-claude-ranking-judge]"

# signal_aggregator.py Regime 部分は次タスクで合体させる
```

## Task 5.3.1: signal_aggregator.py 本体（6 skill 統合 build_signal_bundle）

**Files:**
- Modify: `src/analysis/signal_aggregator.py`（Task 5.3.0 Sub-C 出力に追記）
- Create: `tests/unit/analysis/test_signal_aggregator.py`

- [ ] **Step 1: テスト（6 skill のモック注入）**

```python
import pytest
from decimal import Decimal
from unittest.mock import MagicMock


class TestBuildSignalBundle:
    @pytest.mark.unit
    def test_6_skill_統合で_RankingSignalBundle_返却(self):
        from src.analysis.signal_aggregator import build_signal_bundle

        composite = MagicMock(composite_score=72.5,
                              sub_scores={"Q": 90, "V": 50, "I": 30, "G": 60, "R": 80, "M": 70, "S": 55},
                              preset_name="Buffett_型_暫定")
        mf = MagicMock(score=85.0, roc_pct=Decimal("32.5"), earnings_yield_pct=Decimal("8.2"))
        sent = MagicMock(sentiment_score=Decimal("0.4"), confidence=Decimal("0.7"),
                         key_themes=("iPhone",))
        bundle = build_signal_bundle(
            ticker="AAPL", exchange="US",
            composite_result=composite, mf_result=mf,
            sentiment_result=sent, momentum_1m=Decimal("3"), momentum_12m=Decimal("28"),
            polymarket_macro={"fed_cut_2026": Decimal("0.62")},
            fund_holdings_delta={"Berkshire": {"action": "NEW", "value_change_usd": 5_200_000_000}},
            regime_signals={"regime": "Bull", "state_probs": {"Bull": Decimal("0.6")}},
        )
        assert bundle.ticker == "AAPL"
        assert bundle.regime == "Bull"
        assert bundle.composite_score == 72.5

    @pytest.mark.unit
    def test_skill_失敗時に_空_dict_None_で_continue(self):
        from src.analysis.signal_aggregator import build_signal_bundle
        composite = MagicMock(composite_score=70.0, sub_scores={}, preset_name="Buffett_型_暫定")
        sent = MagicMock(sentiment_score=Decimal("0"), confidence=Decimal("0"), key_themes=())
        bundle = build_signal_bundle(
            ticker="X", exchange="US",
            composite_result=composite, mf_result=None,
            sentiment_result=sent,
            polymarket_macro={}, fund_holdings_delta={}, regime_signals=None,
        )
        assert bundle.magic_formula_score is None
        assert bundle.polymarket_macro == {}
        assert bundle.regime == "Choppy"  # デフォルト
```

- [ ] **Step 2: build_signal_bundle 実装**

```python
# src/analysis/signal_aggregator.py へ追記
from datetime import datetime, timezone
from typing import Any, Literal
from src.analysis.ranking_judge import RankingSignalBundle


def build_signal_bundle(
    *, ticker: str, exchange: Literal["US", "JP"], sector: str | None = None,
    composite_result: Any, mf_result: Any | None, sentiment_result: Any,
    momentum_1m: Decimal | None = None, momentum_12m: Decimal | None = None,
    polymarket_macro: dict[str, Decimal] | None = None,
    fund_holdings_delta: dict[str, dict] | None = None,
    regime_signals: dict | None = None,
) -> RankingSignalBundle:
    """6 skill の出力を 1 つの RankingSignalBundle に統合。

    呼び出し側で失敗した skill は空 dict / None でフォールバック済みである前提。
    PRD §FR5 多段縮退の上位フォーマット層。
    """
    return RankingSignalBundle(
        ticker=ticker, exchange=exchange, sector=sector,
        composite_score=float(composite_result.composite_score),
        sub_scores={k: float(v) for k, v in composite_result.sub_scores.items()},
        composite_preset=str(composite_result.preset_name),
        magic_formula_score=float(mf_result.score) if mf_result else None,
        roc_pct=Decimal(str(mf_result.roc_pct)) if mf_result else None,
        earnings_yield_pct=Decimal(str(mf_result.earnings_yield_pct)) if mf_result else None,
        momentum_1m=momentum_1m, momentum_12m=momentum_12m,
        sentiment_score=Decimal(str(sentiment_result.sentiment_score)),
        sentiment_confidence=Decimal(str(sentiment_result.confidence)),
        sentiment_themes=tuple(sentiment_result.key_themes),
        polymarket_macro=polymarket_macro or {},
        fund_holdings_delta=fund_holdings_delta or {},
        regime=regime_signals.get("regime", "Choppy") if regime_signals else "Choppy",
        regime_state_probs=regime_signals.get("state_probs", {}) if regime_signals else {},
        fetched_at=datetime.now(timezone.utc),
    )


def aggregate_signals_for_universe(
    tickers: list[str], *, exchange: Literal["US", "JP"],
    composite_results: dict[str, Any], mf_results: dict[str, Any],
    sentiment_results: dict[str, Any],
    momentum_results: dict[str, dict[str, Decimal]],
    polymarket_macro: dict[str, Decimal],
    fund_holdings_delta_by_fund: dict[str, dict],
    regime_signals: dict,
) -> list[RankingSignalBundle]:
    """ユニバース全体に対し RankingSignalBundle のリストを返す（02_screener から呼ぶ）。"""
    bundles: list[RankingSignalBundle] = []
    for ticker in tickers:
        if ticker not in composite_results:
            continue
        bundles.append(build_signal_bundle(
            ticker=ticker, exchange=exchange,
            composite_result=composite_results[ticker],
            mf_result=mf_results.get(ticker),
            sentiment_result=sentiment_results[ticker],
            momentum_1m=momentum_results.get(ticker, {}).get("1m"),
            momentum_12m=momentum_results.get(ticker, {}).get("12m"),
            polymarket_macro=polymarket_macro,
            fund_holdings_delta=fund_holdings_delta_by_fund,
            regime_signals=regime_signals,
        ))
    return bundles
```

- [ ] **Step 3: GREEN + コミット**

```bash
pytest tests/unit/analysis/test_signal_aggregator.py -v
git add src/analysis/signal_aggregator.py tests/unit/analysis/test_signal_aggregator.py
git commit -m "feat(signal-aggregator): 6 skill 統合 build_signal_bundle + aggregate_signals_for_universe [20260512-claude-ranking-judge]"
```

## Task 5.3.2: Phase 5.3 並列レビュー

- [ ] **Step 1: 3 reviewer 並列起動**

Task 5.2.9 と同じパターンで `python-reviewer` + `security-reviewer` + `code-reviewer` を Polymarket / 13F diff / signal_aggregator に対して並列起動。

- [ ] **Step 2: 修正 + コミット**

```bash
pytest tests/unit/ -v --cov=src/data --cov=src/analysis
git commit -am "fix: Phase 5.3 並列レビュー反映 [20260512-claude-ranking-judge]"
```

---

# Phase 5.4: UI 統合 + Stage 3 規律強制 + MC + session_state refactor

## Task 5.4.0: 並列で 4 つの下準備

**Files:** なし（並列実装サブエージェント起動指示）

- [ ] **Step 1: 1 メッセージで 4 Agent 並列起動**

```
Agent A (general-purpose, "MC 関数抽出"):
  task: "src/dashboard/views/05_monte_carlo.py から Monte Carlo シミュレーションを
   抽出し src/analysis/monte_carlo.py を新規:
   - simulate_gbm_paths(start_price, mu, sigma, days=252, n_paths=1000, seed=42) -> np.ndarray
   - percentiles_for_fan_chart(paths, percentiles=(5,25,50,75,95)) -> pd.DataFrame
   - render_fan_chart_plotly(percentile_df, ticker) -> plotly.graph_objs.Figure
   TDD 4-5 件。既存 05_monte_carlo.py から呼ぶ形に refactor して既存挙動を保つ。"

Agent B (general-purpose, "詳細カード widget"):
  task: "src/dashboard/widgets/ranking_card.py 新規:
   関数: render_ranking_card(ticker, ranking_result, signal_bundle, mc_figure) -> None
   Streamlit container 内:
     - ranking_score 大表示 + 順位
     - summary 1-2 文
     - supporting_signals チップ（✅ 緑）
     - risk_signals チップ（⚠️ 赤）
     - counter_view ブロッククォート
     - st.tabs(['Buffett-Munger', 'Burry', 'Lynch']) で lens_views
     - mc_figure を st.plotly_chart
     - 免責文言
   widget 単体で render できる純粋関数。"

Agent C (Explore, "session_state 構造調査"):
  task: "src/dashboard/views/02_screener.py の line 1000-1200 周辺を読み、
   既存 session_state['screening_session'] / ['last_buy_result'] の構造をマップ。
   §12.3 の UX 妥協を解消するため、結果表示ロジック全体を関数化するときに
   何を session_state に保存し、どこから display_screening_results() を呼ぶべきかを
   設計案として提示（変更なし、調査のみ）。"

Agent D (general-purpose, "settings.py 拡張"):
  task: "src/config/settings.py に以下を追加:
   - sonnet_model: str = 'claude-sonnet-4-6'
   - sonnet_model_version: str = '(Task 5.2.0 で確定値に置換)'
   - ranking_cache_ttl_sec: int = 86400
   - ranking_top_detail_count: int = 5
   .env.example に対応エントリ追加。後方互換維持。
   コミット規約: feat(settings): Phase 5 設定追加 [20260512-claude-ranking-judge]"
```

- [ ] **Step 2: 各 Agent 結果統合 + 個別コミット**

```bash
pytest tests/unit/analysis/test_monte_carlo.py -v
git commit -m "feat(monte-carlo): GBM シミュレーション関数抽出 + TDD [20260512-claude-ranking-judge]"

git add src/dashboard/widgets/ranking_card.py
git commit -m "feat(widgets): ranking_card コンポーネント [20260512-claude-ranking-judge]"

git commit -am "feat(settings): Phase 5 ranking judge 設定追加 [20260512-claude-ranking-judge]"
```

## Task 5.4.1: display_screening_results() 関数抽出（§12.3 解消）

**Files:**
- Modify: `src/dashboard/views/02_screener.py`

- [ ] **Step 1: 既存 line 826-1183 周辺の `if run_button:` ブロックの結果表示部分を `_display_screening_results(...)` に切り出す**

骨子:

```python
# src/dashboard/views/02_screener.py 内に追加
def _display_screening_results(
    *, result, composite_rows, composite_warnings, radar_data,
    composite_preset, kelly_params_default, portfolio_value_jpy_dec,
    ranking_results=None, signal_bundles=None,
) -> None:
    """結果表示ロジック単独。run_button 経路 + session_state 経路の両方から呼べる。"""
    # ── Provenance ─────
    # 既存 Provenance expander ロジックをここに移動
    ...
    # ── 結果テーブル ────
    # composite_rows DataFrame 表示
    ...
    # ── 推奨カード ──────
    # 既存推奨カード
    ...
    # ── レーダー ────────
    ...
    # ── リスク警告 ──────
    ...
    # ── NEW: Claude セクション ──
    if ranking_results:
        _display_claude_section(ranking_results, signal_bundles)
```

- [ ] **Step 2: `if run_button:` 内 と `if "screening_session" in st.session_state:` 内の両方から `_display_screening_results(...)` を呼ぶよう refactor**

- [ ] **Step 3: pytest + コミット**

```bash
pytest tests/unit/ -v
git commit -am "refactor(screener): 結果表示を _display_screening_results に関数化（§12.3 解消） [20260512-claude-ranking-judge]"
```

## Task 5.4.2: Stage 2 Sonnet 呼び出し + Stage 3 を 02_screener に組み込む

**Files:**
- Modify: `src/dashboard/views/02_screener.py`

- [ ] **Step 1: シグナル束組み立て + Sonnet 呼び出しを Composite ループ後に挿入**

```python
import anthropic
from pathlib import Path
from src.analysis.signal_aggregator import aggregate_signals_for_universe
from src.analysis.ranking_judge import rank_with_claude_batch, RankingResult, RankingSignalBundle
from src.data.polymarket_client import fetch_macro_probabilities
from src.data.sec_edgar_13f_diff import extract_holdings_delta
from src.analysis.signal_aggregator import build_regime_signals
from src.config.settings import settings

# Composite ループ終了後、結果表示の前に挿入
ranking_results: list[RankingResult] | None = None
signal_bundles: list[RankingSignalBundle] | None = None

if settings.anthropic_api_key and composite_rows:
    with st.spinner("🤖 Claude による総合判定を実行中..."):
        try:
            # 6 skill の出力を集約
            polymarket_macro = fetch_macro_probabilities(
                topics=["fed_rate_cut_2026", "us_recession_2026", "geopolitical_risk"]
            )
        except Exception as exc:  # noqa: BLE001
            st.warning(f"⚠️ Polymarket 取得失敗: {type(exc).__name__}、空 dict で続行")
            polymarket_macro = {}

        try:
            fund_holdings_delta = {
                fund: extract_holdings_delta(fund, sec_client=sec_edgar_client)
                for fund in settings.tracked_funds_cik_list
            }
        except Exception as exc:  # noqa: BLE001
            st.warning(f"⚠️ 13F 差分取得失敗: {type(exc).__name__}、空 dict で続行")
            fund_holdings_delta = {}

        try:
            regime_signals = build_regime_signals(
                universe_prices=spy_close_series, vix_series=vix_series_or_none
            )
        except Exception as exc:  # noqa: BLE001
            st.warning(f"⚠️ Regime 判定失敗: {type(exc).__name__}、Choppy 仮定で続行")
            regime_signals = {"regime": "Choppy", "state_probs": {}}

        try:
            signal_bundles = aggregate_signals_for_universe(
                tickers=[r["_ticker_raw"] for r in composite_rows],
                exchange=exchange,
                composite_results=composite_results_dict,
                mf_results=mf_results_dict,
                sentiment_results=sentiment_results_dict,
                momentum_results=momentum_results_dict,
                polymarket_macro=polymarket_macro,
                fund_holdings_delta_by_fund=fund_holdings_delta,
                regime_signals=regime_signals,
            )
            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            ranking_results = rank_with_claude_batch(
                signal_bundles, anthropic_client=client,
                cache_dir=Path(settings.cache_dir) / "sonnet_ranking",
                model=settings.sonnet_model,
                model_version=settings.sonnet_model_version,
                ttl_sec=settings.ranking_cache_ttl_sec,
            )
        except anthropic.APIStatusError as exc:
            if exc.status_code == 401:
                st.error("🚨 Claude API key 不正。全銘柄を Composite ランキングへ縮退します。")
            else:
                st.error(f"🚨 Anthropic API エラー ({exc.status_code})、縮退します。")
            ranking_results = None
        except Exception as exc:  # noqa: BLE001
            st.error(f"🚨 Claude 判定全体失敗: {type(exc).__name__}、縮退します。")
            ranking_results = None
elif not settings.anthropic_api_key:
    st.info("ℹ️ ANTHROPIC_API_KEY 未設定のため Claude 判定はスキップ（数式ランキングのみ表示）。")

# session_state に保存（§12.3 解消）
if "screening_session" in st.session_state:
    st.session_state["screening_session"]["ranking_results"] = ranking_results
    st.session_state["screening_session"]["signal_bundles"] = signal_bundles
```

- [ ] **Step 2: `_display_claude_section()` 関数追加**

```python
def _display_claude_section(
    ranking_results: list[RankingResult],
    signal_bundles: list[RankingSignalBundle],
) -> None:
    """Claude TOP 5 詳細カードセクション。"""
    st.subheader("🤖 Claude による総合判定")

    fallback_count = sum(1 for r in ranking_results if r.fallback_reason is not None)
    if fallback_count > 0:
        st.warning(f"⚠️ {fallback_count}/{len(ranking_results)} 銘柄が数式縮退中（Claude 判定不可）")

    sorted_pairs = sorted(
        zip(ranking_results, signal_bundles, strict=True),
        key=lambda p: p[0].ranking_score, reverse=True,
    )

    from src.analysis.monte_carlo import (
        simulate_gbm_paths, percentiles_for_fan_chart, render_fan_chart_plotly,
    )
    from src.dashboard.widgets.ranking_card import render_ranking_card

    for rank, (result, bundle) in enumerate(
        sorted_pairs[: settings.ranking_top_detail_count], start=1
    ):
        st.markdown(f"### #{rank} — {bundle.ticker}")
        paths = simulate_gbm_paths(
            start_price=100.0,  # 相対値で表示
            mu=float(bundle.momentum_12m or 0) / 100.0,
            sigma=0.25,  # 暫定値、Phase 6 で realized vol に置換予定
        )
        pct_df = percentiles_for_fan_chart(paths)
        fig = render_fan_chart_plotly(pct_df, bundle.ticker)
        render_ranking_card(bundle.ticker, result, bundle, fig)
        st.divider()

    st.warning(
        "⚠️ **これは投資助言ではありません。** 最終判断はユーザー自身で行ってください。"
        "AI 出力は確率分布の参考情報です。"
    )
```

- [ ] **Step 3: Composite テーブルに「🎯 Claude」列追加 + Provenance expander**

```python
# composite_rows 構築時、ranking_results 計算後に ticker → ranking_score の dict を作って併記
if ranking_results:
    ranking_score_by_ticker = {
        b.ticker: r.ranking_score
        for r, b in zip(ranking_results, signal_bundles, strict=True)
    }
    for row in composite_rows:
        row["🎯 Claude"] = str(ranking_score_by_ticker.get(row["_ticker_raw"], "-"))

# Provenance expander
if ranking_results and signal_bundles:
    import dataclasses
    with st.expander("ⓘ Provenance — Claude への入力と出力 JSON"):
        for result, bundle in zip(ranking_results, signal_bundles, strict=True):
            st.markdown(f"#### {bundle.ticker}")
            st.json({
                "input_bundle": dataclasses.asdict(bundle),
                "output_result": result.model_dump(mode="json"),
            })
```

- [ ] **Step 4: コミット**

```bash
git commit -am "feat(screener): Stage 2 Sonnet 連携 + Stage 3 規律強制 + TOP 5 詳細カード + Provenance [20260512-claude-ranking-judge]"
```

## Task 5.4.3: BUY フォーム経由で Claude 判定を Decision Log に記録

**Files:**
- Modify: `src/portfolio/buy_decision.py`
- Modify: `src/portfolio/decision_log.py`
- Modify: `src/dashboard/views/02_screener.py`
- Modify: `tests/unit/portfolio/test_buy_decision.py`

- [ ] **Step 1: BuyOrderRequest に claude_ranking フィールド追加 + テスト**

```python
# src/portfolio/buy_decision.py
@dataclass(frozen=True)
class BuyOrderRequest:
    # ... 既存フィールド ...
    claude_ranking: dict | None = None  # 新規: Claude RankingResult.model_dump() の dict
```

- [ ] **Step 2: append_decision に claude_ranking 引数追加（後方互換）**

```python
# src/portfolio/decision_log.py
def append_decision(..., kelly_recommendation=None, claude_ranking=None):
    record = {
        # 既存フィールド ...
        "kelly_recommendation": kelly_recommendation,
        "claude_ranking": claude_ranking,
    }
```

- [ ] **Step 3: submit_buy_order() で渡す**

```python
def submit_buy_order(request, *, log_dir):
    # ... 既存ロジック ...
    return append_decision(
        # ...
        kelly_recommendation=kelly_rec,
        claude_ranking=request.claude_ranking,
    )
```

- [ ] **Step 4: 02_screener BUY フォームで Claude 判定を抽出**

```python
# BUY 確定時
claude_rank_dict = None
if ranking_results and signal_bundles:
    for r, b in zip(ranking_results, signal_bundles, strict=True):
        if b.ticker == selected_ticker:
            claude_rank_dict = r.model_dump(mode="json")
            break

request = BuyOrderRequest(
    # ...
    claude_ranking=claude_rank_dict,
)
```

- [ ] **Step 5: TDD 追加**

```python
def test_BUY_order_に_claude_ranking_が記録される(tmp_path):
    request = BuyOrderRequest(
        # ...
        claude_ranking={"ranking_score": 78, "lens_views": {...}, "metadata": {...}},
    )
    path = submit_buy_order(request, log_dir=tmp_path)
    rec = json.loads(path.read_text().splitlines()[-1])
    assert rec["claude_ranking"]["ranking_score"] == 78
```

- [ ] **Step 6: GREEN + コミット**

```bash
pytest tests/unit/portfolio/test_buy_decision.py -v
git commit -am "feat(buy-decision): Decision Log に Claude ranking 記録（Provenance §9.8.3 完成） [20260512-claude-ranking-judge]"
```

## Task 5.4.4: Phase 5.4 並列レビュー

- [ ] **Step 1: 2 reviewer 並列起動**

```
python-reviewer + code-reviewer を以下に並列適用:
  - src/analysis/monte_carlo.py
  - src/dashboard/widgets/ranking_card.py
  - src/dashboard/views/02_screener.py の追加部分
  - Streamlit st.form rerun 落とし穴の有無
```

- [ ] **Step 2: 修正 + コミット**

```bash
pytest tests/unit/ -v --cov=src
git commit -am "fix: Phase 5.4 並列レビュー反映 [20260512-claude-ranking-judge]"
```

---

# Phase 5.5: E2E 検証 + handoff doc

## Task 5.5.0: Playwright シナリオ 4 件を準備

**Files:**
- Create: `.steering/20260512-claude-ranking-judge/e2e-scenarios.md`

- [ ] **Step 1: E2E シナリオ 4 件を md 化**

```
シナリオ 1 (Golden path):
  - Streamlit 起動 → 02_screener → AAPL/MSFT/GOOGL 入力 → スクリーニング実行
  - 30 秒以内に Claude TOP 5 詳細カード表示
  - 各カードに supporting/risk/counter/3 レンズタブ/MC chart/免責が確認
  - スクショ: e2e-golden-path-verified.png

シナリオ 2 (一本線予測検出):
  - SYSTEM_PROMPT を一時的に弱化して予測出力を誘発
  - 期待: 全銘柄 fallback_reason=forbidden_pattern_detected
  - スクショ: e2e-forbidden-pattern-verified.png

シナリオ 3 (API key 不正フォールバック):
  - .env の ANTHROPIC_API_KEY を一時的に空にして Streamlit restart
  - 期待: 全銘柄 Composite 縮退 + 🚨 警告
  - スクショ: e2e-401-fallback-verified.png

シナリオ 4 (§12.3 残課題解消):
  - スクリーニング → Claude TOP 5 表示 → BUY → JSONL 追記 →
    画面再描画でも Composite テーブル + Claude TOP 5 が維持
  - スクショ: e2e-session-state-verified.png
```

## Task 5.5.1: Streamlit 起動 + Golden path シナリオ

- [ ] **Step 1: ユーザーに別ターミナルで起動を要請**

```
ユーザー実行:
  streamlit run src/dashboard/app.py --server.port 8501
```

- [ ] **Step 2: Playwright MCP で `browser_navigate` → `browser_snapshot` → `browser_type` 入力 → `browser_click` 実行**

- [ ] **Step 3: `browser_wait_for` で Claude 詳細カード表示確認**

- [ ] **Step 4: スクショ撮影 → `.steering/20260512-claude-ranking-judge/e2e-golden-path-verified.png` 保存**

## Task 5.5.2: 一本線予測検出シナリオ

- [ ] **Step 1: SYSTEM_PROMPT を一時的に書き換えて予測出力を誘発（テスト用ブランチ作成 or 環境変数で切り替え）**

- [ ] **Step 2: Playwright で実行 → fallback_reason 検出 → スクショ**

- [ ] **Step 3: SYSTEM_PROMPT を元に戻す**

## Task 5.5.3: API key 不正フォールバックシナリオ

- [ ] **Step 1: .env の ANTHROPIC_API_KEY を一時退避**

```bash
mv .env .env.original
echo "ANTHROPIC_API_KEY=invalid" > .env
# その他必要キーを .env.original から restore
```

- [ ] **Step 2: Streamlit 再起動 + Playwright 検証 + スクショ**

- [ ] **Step 3: .env 復元**

## Task 5.5.4: §12.3 残課題解消シナリオ

- [ ] **Step 1: スクリーニング → BUY ボタン → JSONL 確認**

```bash
cat data/decision-log/2026-05.jsonl | tail -1 | jq .
```

- [ ] **Step 2: BUY 後の画面再描画で Composite テーブル + Claude TOP 5 が維持されているか目視確認 + スクショ**

## Task 5.5.5: handoff doc 起草

**Files:**
- Create: `.steering/20260512-claude-ranking-judge/handoff-doc.md`

- [ ] **Step 1: handoff-phase4.md フォーマットに沿って handoff-doc.md を起草**

セクション:
1. 完了サマリー（5 Phase + コミット数）
2. 実装したファイル + LOC + テスト件数
3. AC1-AC13 達成状況
4. 月額コスト実測（Anthropic ダッシュボードから抽出）
5. CLAUDE.md 規約適合チェック（§9.3 / §9.4 / §9.5 / §9.7 / §9.8）
6. スクショ証跡 4 枚（埋め込み）
7. 既知の課題 / 持ち越し（§5.6 13F-NT, Phase 6 候補等）
8. 次の Phase 6 候補（FRED 統合 / 動的 lens_views / Prompt Caching ヒット率実測等）

## Task 5.5.6: 最終並列レビュー + コミット + プロジェクト完了

- [ ] **Step 1: 3 reviewer 並列起動（最終）**

```
python-reviewer + security-reviewer + code-reviewer を以下に一斉適用:
  - src/analysis/ranking_judge.py
  - src/analysis/signal_aggregator.py
  - src/analysis/monte_carlo.py
  - src/data/polymarket_client.py
  - src/data/sec_edgar_13f_diff.py
  - src/dashboard/widgets/ranking_card.py
  - src/dashboard/views/02_screener.py
```

- [ ] **Step 2: 最終コミット + push**

```bash
pytest tests/ -v --cov=src --cov-report=term-missing
git commit -am "feat(ranking): Phase 5 完了 — Claude Sonnet 総合ランキング機能 [20260512-claude-ranking-judge]"
git push origin main
```

- [ ] **Step 3: vault 同期確認**

Stop hook で `vault/notes/projects/kaori_kabu.md` が更新されたことを確認。

---

## Self-Review

### Spec coverage チェック（PRD と照合）

| PRD 要件 | 実装タスク |
|---|---|
| FR1 Stage 1 数式フィルタ | 既存維持（タスク変更なし） |
| FR2 Stage 2 Sonnet 判定 | Task 5.2.1-5.2.8 |
| FR3 Stage 3 規律強制 | Task 5.2.4 + Task 5.4.0-A (MC) + Task 5.4.2 |
| FR4 UI 統合 | Task 5.4.0-B / 5.4.1 / 5.4.2 / 5.4.3 |
| FR5 多段縮退（フォールバック） | Task 5.2.7 + Task 5.4.2 |
| FR6 シグナル別キャッシュ + Sonnet 24h | Task 5.2.8 + Task 5.3.0-A/B |
| NFR1 パフォーマンス | Task 5.5.1 で 30 秒以内検証 |
| NFR2 コスト | Task 5.5.5 で実測記録 |
| NFR3 信頼性 | Task 5.5.1-5.5.4 で 4 シナリオ検証 |
| NFR4 規律遵守 | Task 5.2.4 / 5.2.5 / 5.5.2 |
| NFR5 テスト | 全タスクで TDD、Task 5.5.6 でカバレッジ確認 |
| AC1-AC13 | Task 5.5.1-5.5.5 で全項目検証 |

### 型一致チェック

- `RankingSignalBundle` のフィールド名 → `build_ranking_user_message` / `build_signal_bundle` / `aggregate_signals_for_universe` で一貫
- `RankingResult` フィールド名 → Pydantic スキーマと parser、cache I/O で一致
- `apply_regime_confidence(confidence, *, regime)` 引数順 → 呼び出し側 (`rank_single_with_claude`, `_build_fallback_result`) で一致
- `compute_kelly_multiplier(ranking_score)` int 引数 → fallback / 正常パスで一致
- `claude_ranking: dict | None` → BuyOrderRequest / append_decision / 02_screener で一致

### 並列化チェック（PRD §10 と整合）

- Phase 5.2 開始: 3 Agent 並列 ✅
- Phase 5.2 終了: 3 reviewer 並列 ✅
- Phase 5.3 開始: 3 implement Agent 並列 ✅（最大効果）
- Phase 5.3 終了: 3 reviewer 並列 ✅
- Phase 5.4 開始: 4 Agent 並列 ✅
- Phase 5.4 終了: 2 reviewer 並列 ✅
- Phase 5.5 終了: 3 reviewer 並列 ✅

並列化箇所合計 **7 セッション** で工数を **約 30% 削減**（PRD §10 / §13 と一致）。

---

## Execution Handoff

Plan complete and saved to `.steering/20260512-claude-ranking-judge/design.md`.

**Two execution options:**

**1. Subagent-Driven（推奨）** — Fresh subagent per task、各タスク後に並列レビュー、高速イテレーション。並列化を最大化したい場合に最適。Required: `superpowers:subagent-driven-development`

**2. Inline Execution** — このセッションで `executing-plans` を使い、チェックポイント付きバッチ実行。コンテキストを連続で保ちたい場合に最適。Required: `superpowers:executing-plans`

**どちらで進める？**
