# Ranking Judge — Claude Sonnet 4.6 総合ランキング判定器 PRD

| 項目 | 値 |
|---|---|
| ドキュメント種別 | Product Requirements Document（PRD） |
| ステアリング ID | `20260512-claude-ranking-judge` |
| 起草日 | 2026-05-12 |
| 起草者 | かおりん + Claude Opus 4.7 |
| 上位 PRD | `docs/product-requirements.md`（MVP #1 Magic Formula スクリーナーの拡張） |
| 関連 handoff | `.steering/20260512-claude-ranking-judge/handoff-prompt.md` |
| ステータス | Phase 5.1 設計中 |

---

## 1. プロブレム

現状の `02_screener.py` は **数式（Magic Formula + Composite 7 軸）のみ** で銘柄評価している。一方でプロジェクトには以下 6 個のプロジェクト固有 skill / 既存実装が独立して存在するが、ランキング判定には統合されていない:

| 既存資産 | 現状 | ランキングへの貢献 |
|---|---|---|
| `magic-formula-screener` | ✅ Stage 1 で活用済み | ✅ |
| `polymarket-macro-watcher` | SKILL.md のみ、実装コード未存在 | ❌ |
| `13f-cloning-tracker` | `sec_edgar.py` + `views/03_thirteen_f.py` 存在 | ❌（dashboard 表示のみ、ランキング未経由） |
| `regime-detection` | `src/analysis/regime.py` 存在 | ❌（home view 表示のみ、ランキング未経由） |
| `kelly-position-sizer` | BUY フォームで活用済み | △（暫定値ハードコード、ranking_score 連動なし） |
| `monte-carlo-projection` | `views/05_monte_carlo.py` 存在 | ❌（独立タブ、ランキング未経由） |

加えて、Claude Haiku 4.5 はニュースセンチメント定量化のみで、**ランキング判断には参加していない**。結果として:

1. ユーザー期待「数ある銘柄から総合判断してほしい」と実装に乖離
2. 認知バイアス対策（Confirmation / Recency / Overconfidence）が UI レベルで欠落
3. Provenance §9.8 が Composite には適用済みだが、AI 判定が未経由
4. CLAUDE.md §9.3「一本線予測禁止」の規律が AI 出力で強制されていない（現在は人間判断頼み）

---

## 2. ゴール

数式フィルタ後の上位銘柄に対し、**Claude Sonnet 4.6 が 6 skill 統合のシグナル束を AI 判定** し、構造化 JSON で多角的根拠を返す。Stage 3 で既存の規律強制レイヤー（Regime / Kelly / Monte Carlo）と連動させ、**素人でも規律と統計でトップ投資家に近づく** プロジェクトミッションを完成させる。

### 2.1 中核ゴール

- ✅ シグナル束を Sonnet 4.6 で総合判定（中スコープ B: Composite + MF + モメンタム + センチメント + Polymarket + 13F + Regime）
- ✅ 多角レンズ視点を同時表示（Buffett_Munger / Burry / Lynch の固定 3 個）
- ✅ Stage 3 規律強制（Crisis 時 confidence 補正 / Kelly multiplier / MC fan chart）
- ✅ 一本線予測の構造的禁止（system prompt + Pydantic + 正規表現 TDD の 3 層）
- ✅ Provenance §9.8 — 全シグナル + Claude 判定理由 + キャッシュ状況を JSON 化

### 2.2 副次ゴール

- §12.3 残課題（BUY 確定後にテーブル消える UX 問題）を `session_state` refactor で同時解消
- 6 skill 全部の「最適配置」— `kelly-position-sizer` を ranking_score 連動、`monte-carlo-projection` を TOP 5 詳細カードに統合
- 月額運用コストを約 4,950 円に維持（EODHD 4,500 + Anthropic 450）

---

## 3. 非ゴール

| 非ゴール | 理由 |
|---|---|
| ❌ 目標株価予測 | CLAUDE.md §9.3 一本線禁止、TDD で構造的に reject |
| ❌ 期限付き予測（「3 ヶ月以内に $X」等） | 同上、Pydantic スキーマで `time_horizon` フィールド禁止 |
| ❌ 投資助言サービス化 | 完全個人ローカル、金商法対象外を厳守 |
| ❌ リアルタイム高頻度判定 | 月 4 回程度の運用想定、低頻度バッチで十分 |
| ❌ FRED マクロ統合 | 中スコープ B には含めず、Phase 6 候補 |
| ❌ 自動売買 | 最終判断は常にユーザー、UI で承認ゲート維持 |

---

## 4. ペルソナとユーザーシナリオ

### 4.1 ペルソナ — かおりん

- トヨタ自動車 生産技術 / UPR チーフ（育休中）
- 投資は副業探索、専任ではない
- 60 点 MVP 思考、即決型
- 「数ある銘柄から総合判断してほしい」と発話済（2026-05-12）

### 4.2 ユーザーシナリオ

```
かおりん: 02_screener を開く
    ↓
Stage 1: MF スクリーニング実行（既存）
    ↓ ~5 秒
銘柄候補 5 個（MF_TOP_N=5）が Composite テーブルに表示
    ↓
Stage 2: 🤖 Claude 総合判定（新規、自動発火）
    ├─ 進捗バー: "5/5 銘柄を判定中..."
    └─ ~30 秒（Prompt Caching ヒット時 ~10 秒）
    ↓
結果:
  - Composite テーブルに「🎯 Claude」列追加（ranking_score 0-100）
  - TOP 5 詳細カード:
    * 1-2 文の根拠サマリ
    * supporting_signals チップ
    * risk_signals 赤チップ
    * counter_view（反対意見）ブロッククォート
    * Buffett_Munger / Burry / Lynch の 3 レンズタブ
    * Monte Carlo 1000 パス fan chart（§9.3 一本線禁止の視覚化）
  - 免責: 「これは投資助言ではありません」
    ↓
かおりん が BUY ボタン → Decision Log に Kelly + Claude 判定の全 Provenance 記録
    ↓
テーブル + カードは session_state 永続化で BUY 後も維持（§12.3 解消）
```

---

## 5. 機能要件

### FR1: Stage 1 — 数式フィルタ（既存維持）

`magic-formula-screener` 経由で MF_TOP_N 銘柄を抽出。ユニバースは US / JP 切替可能（既存 §4.5 動的取得を踏襲）。

### FR2: Stage 2 — Sonnet 4.6 Ranking Judge

| 入力 | シグナル束 `RankingSignalBundle` |
|---|---|
| **Composite** | sub_scores (Q/V/I/G/R/M/S 各 0-100) + composite_score + preset_name |
| **Magic Formula** | magic_formula_score + ROC% + EY% |
| **モメンタム** | 1m return + 12m return |
| **ニュースセンチメント** | 既存 Haiku 出力（score + confidence + themes + risk_signals） |
| **Polymarket** | macro probability dict（Fed cut / recession / 地政学） |
| **13F** | 直近 1Q の Berkshire/Pabrai/Burry/Ackman/Greenlight の差分 |
| **Regime** | Bull / Choppy / Crisis + 状態確率 |
| **属性** | ticker / exchange (US/JP) / sector / market |

| 出力 | `RankingResult`（Pydantic 検証） |
|---|---|
| `ranking_score` | 0-100（int） |
| `recommendation_summary` | 1-2 文（150 字以内） |
| `supporting_signals` | `tuple[str, ...]`（最大 5 件） |
| `risk_signals` | `tuple[str, ...]`（最大 5 件） |
| `counter_view` | 反対意見テキスト（200 字以内、Confirmation Bias 対策） |
| `lens_views` | `{"Buffett_Munger": str, "Burry": str, "Lynch": str}` 固定 3 個 |
| `confidence` | 0.0-1.0（Decimal） |
| `confidence_adjusted` | Regime 補正後（Crisis → ×0.5） |
| `kelly_multiplier` | ranking_score → Kelly 係数 |
| `metadata` | RankingMetadata（Provenance §9.8.2 準拠） |

**禁止フィールド**（Pydantic で reject）: `target_price`, `expected_return`, `time_horizon`, `price_target`, `forecast_price`

### FR3: Stage 3 — 規律強制レイヤー

| ロジック | 内容 |
|---|---|
| **Regime × confidence** | レジーム判定が Crisis → `confidence_adjusted = confidence × 0.5` を強制 |
| **kelly-position-sizer 連動** | `kelly_multiplier`: ranking_score ≥80 → 1.0（Full Half-Kelly）/ 50-79 → 0.5 / <50 → 0.0（買い非推奨警告） |
| **monte-carlo-projection** | TOP 5 各銘柄で 1000 パス GBM シミュレーション、5/25/50/75/95 パーセンタイル fan chart を詳細カードに併記 |

### FR4: UI 統合（`02_screener.py`）

- Composite テーブルに「🎯 Claude」列追加（ranking_score でソート可能）
- ranking_score 上位 5 銘柄に **詳細カード**:
  - サマリ（1-2 文）
  - supporting_signals チップ（緑）
  - risk_signals チップ（赤）
  - counter_view ブロッククォート
  - 3 レンズタブ（`st.tabs`）
  - **Monte Carlo fan chart**（Plotly）
- 「ⓘ Provenance」expander: 入力 `RankingSignalBundle` + 出力 `RankingResult` の JSON 全開示
- **免責必須**: 「これは投資助言ではありません。最終判断はユーザー自身で。AI 出力は確率分布の参考情報です」を Claude 結果直下
- **session_state refactor**（§12.3 残課題同時解決）: `display_screening_results()` 関数化、計算結果を `session_state["screening_session"]` に永続化、BUY 後も全表示維持

### FR5: 多段フォールバック

| 失敗パターン | 挙動 | UI 表示 |
|---|---|---|
| 個別銘柄 API エラー | その銘柄のみ `ranking_score = composite_score`, `lens_views = None`, `fallback_reason = "api_error"` | ⚠️ N/M 銘柄が数式埋め |
| API key 不正（401） | 全銘柄数式ランキング | 🚨 Claude 判定を取得できません（API key 確認） |
| Anthropic 障害（503） | 全銘柄数式ランキング | 🚨 Anthropic 障害中、数式ランキングへ |
| レート制限（429） | 取れた分まで Sonnet 判定 | ⚠️ N/M 銘柄のみ Claude 判定 |

### FR6: キャッシュ（シグナル別 TTL + Sonnet 24h）

| 層 | TTL | キャッシュキー |
|---|---|---|
| ファンダ | 7 d | `ticker + date` |
| Polymarket | 6 h | `endpoint + params_hash` |
| 13F | 90 d | `cik + quarter` |
| ニュースセンチメント | 1 h | `ticker + lens_set + query_hash` |
| Regime | 24 h | `universe + lookback` |
| **Sonnet 判定** | **24 h** | `sha256(ticker + preset + regime + bundle_hash + model_version)` |

`data/cache/sonnet_ranking/` 配下に `parquet` で保存、pyarrow schema metadata に `kabu_source / kabu_fetched_at / kabu_endpoint / kabu_params_hash` を埋め込む（CLAUDE.md §9.8.4 準拠）。

---

## 6. 非機能要件

### NFR1: パフォーマンス

| 指標 | 目標 |
|---|---|
| Stage 1 数式フィルタ | < 5 秒（既存維持） |
| Stage 2 Sonnet 判定（5 銘柄） | < 30 秒（Prompt Caching ヒット時 < 10 秒） |
| Stage 3 規律強制 + UI 描画 | < 3 秒 |
| キャッシュヒット時の全体 | < 2 秒 |

### NFR2: コスト

| 項目 | 月額 |
|---|---|
| EODHD EOD+Intraday Extended | 4,500 円 |
| Anthropic Sonnet 4.6（月 4 回 × 5 銘柄、Prompt Caching 90% 削減想定） | 約 80 円 |
| Anthropic Sonnet 4.6（月 4 回 × 30 銘柄、上限ケース） | 約 450 円 |
| Polymarket Gamma API | 0 円（無料・認証不要） |
| **月額合計** | **約 4,580 〜 4,950 円** |

開発時の Sonnet 試験呼び出しコスト: **約 $5-10**（Phase 5.2-5.5 で 100-200 回程度）

### NFR3: 信頼性

- フォールバック動作 100%（個別 / 全体 / レート制限の 3 ケースで E2E 検証）
- API key 漏洩防止（`.env` のみ、エラーメッセージに含めない）
- セッション間で `session_state` の永続化（BUY 後もテーブル維持）

### NFR4: 規律遵守

- CLAUDE.md §9.3 一本線予測禁止 — system prompt + Pydantic + 正規表現 TDD の 3 層強制
- CLAUDE.md §9.5 損切り規律 — ATR ストップは既存維持、Sonnet は売却条件に介入しない
- CLAUDE.md §9.7 認知バイアス警告 — counter_view + Overconfidence 警告（Crisis 時 confidence × 0.5）
- CLAUDE.md §9.8 Provenance — シグナル束 + Claude 出力 + キャッシュ状況を全 Decision Log 記録

### NFR5: テスト

- TDD カバレッジ 80%+（pytest --cov）
- Phase 5.2: ranking_judge.py 単体テスト 10-15 件
- Phase 5.3: signal_aggregator + Polymarket / 13F / Regime 統合テスト 8-12 件
- Phase 5.4: UI 統合テスト（Streamlit form 挙動 + session_state）3-5 件
- Phase 5.5: Playwright E2E 全フロー検証

---

## 7. データモデル

### 7.1 RankingSignalBundle（Stage 2 入力）

```python
@dataclass(frozen=True)
class RankingSignalBundle:
    ticker: str
    exchange: Literal["US", "JP"]
    sector: str | None
    composite_score: float
    sub_scores: dict[str, float]  # Q/V/I/G/R/M/S 各 0-100
    composite_preset: str  # "Buffett_型_暫定" 等
    magic_formula_score: float | None
    roc_pct: Decimal | None
    earnings_yield_pct: Decimal | None
    momentum_1m: Decimal | None
    momentum_12m: Decimal | None
    sentiment_score: Decimal  # 既存 Haiku 出力
    sentiment_confidence: Decimal
    sentiment_themes: tuple[str, ...]
    polymarket_macro: dict[str, Decimal]  # {"fed_cut_2026": 0.62, "recession_2026": 0.30}
    fund_holdings_delta: dict[str, dict]  # {"Berkshire": {"action":"NEW", "value_change_usd": ...}, ...}
    regime: Literal["Bull", "Choppy", "Crisis"]
    regime_state_probs: dict[str, Decimal]
    fetched_at: datetime
```

### 7.2 RankingResult（Stage 2 出力、Pydantic）

```python
class RankingResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")  # 禁止フィールド reject の核

    ranking_score: int = Field(ge=0, le=100)
    recommendation_summary: str = Field(max_length=150)
    supporting_signals: tuple[str, ...] = Field(max_length=5)
    risk_signals: tuple[str, ...] = Field(max_length=5)
    counter_view: str = Field(max_length=200)
    lens_views: dict[Literal["Buffett_Munger", "Burry", "Lynch"], str]
    confidence: Decimal = Field(ge=0, le=1)
    confidence_adjusted: Decimal = Field(ge=0, le=1)
    kelly_multiplier: Decimal = Field(ge=0, le=1)
    fallback_reason: str | None = None  # 個別失敗時のみ非 None
    metadata: RankingMetadata
```

### 7.3 RankingMetadata（Provenance §9.8.2）

```python
@dataclass(frozen=True)
class RankingMetadata:
    model: str  # "claude-sonnet-4-6"
    model_version: str  # "claude-sonnet-4-6-20260101" 等
    calculation_method: str  # "ranking_judge_v1"
    input_bundle_hash: str  # SHA256 of bundle dict
    cache_hit: bool
    cache_age_sec: int | None
    input_tokens: int
    output_tokens: int
    input_tokens_cached: int  # Prompt Caching ヒット token 数
    calculated_at: datetime
    academic_source: str  # 引用学術文献
    code_commit: str | None
```

---

## 8. Sonnet プロンプト設計

### 8.1 SYSTEM_PROMPT（Prompt Caching 対象、~1500 token）

要素:

1. **役割定義**: 「あなたは株式投資判定アシスタントです。最終判断は常にユーザーが行います」
2. **必須事項**:
   - 反対意見（counter_view）を必ず生成
   - 学術的バックボーンに基づく根拠（supporting_signals）
   - リスク警告（risk_signals）— Value Trap / Recency Bias / Overconfidence 等
   - 多角レンズ 3 視点（Buffett_Munger / Burry / Lynch）の同時表示
3. **禁止事項**:
   - ❌ 目標株価の数値予測
   - ❌ 上昇率 % の数値予測
   - ❌ 期限付き予測（「3 ヶ月以内に」等）
   - ❌ 投資助言フレーズ（「買いを推奨します」など）
4. **出力スキーマ JSON**（厳密 schema）

### 8.2 USER_MESSAGE（Prompt Caching 非対象）

シグナル束 dict を構造化 markdown で展開:

```markdown
## 銘柄: {ticker} ({exchange})

### Composite Score
- Composite: {composite_score}/100 (preset: {preset_name})
- 7 軸サブスコア: Q={Q}, V={V}, I={I}, G={G}, R={R}, M={M}, S={S}

### Magic Formula
- スコア: {mf_score} / ROC: {roc}% / EY: {ey}%

### モメンタム
- 1m: {momentum_1m}% / 12m: {momentum_12m}%

### ニュースセンチメント（既存 Haiku 4.5 出力）
- Score: {sent_score} / Confidence: {sent_conf}
- テーマ: {sent_themes}

### Polymarket マクロ織り込み確率
- Fed 利下げ 2026: {fed_cut_prob}%
- 景気後退 2026: {recession_prob}%
- 地政学リスク: {geo_prob}%

### 13F 直近 1Q 差分（スマートマネー動向）
- Berkshire: {action} ({value_change_usd})
- Pabrai: ...
- Burry: ...
- Ackman: ...

### Regime
- 現在: {regime} (Bull={p_bull}, Choppy={p_choppy}, Crisis={p_crisis})

上記シグナル束を統合し、スキーマに従った JSON で判定結果を返してください。
```

---

## 9. TDD 計画（FORBIDDEN_PATTERNS 検証の核）

```python
# tests/unit/analysis/test_ranking_judge.py

FORBIDDEN_PATTERNS = [
    r"\$\s*\d+(\.\d+)?",                          # $200
    r"¥\s*\d+(,\d{3})*",                          # ¥30,000
    r"\d+\s*%\s*(上昇|下落|上がる|下がる|increase|decrease)",
    r"目標株価|target\s*price|price\s*target",
    r"いつまで|by\s+\d+\s*(month|year|月|年)",
    r"forecast\s+price|expected\s+price",
    r"(\d+\s*ヶ月|\d+\s*months?)\s*以内",
]

class TestRankingJudgeOutputValidation:
    def test_出力に一本線予測が含まれない_全テキストフィールド(self):
        # 各銘柄の summary/supporting/risk/counter/lens_views 全部をスキャン
        ...

    def test_pydantic_スキーマで禁止フィールドを reject(self):
        bad_json = {"target_price": 200, "ranking_score": 80, ...}
        with pytest.raises(ValidationError):
            RankingResult.model_validate(bad_json)

    def test_Crisis_レジーム時に_confidence_adjusted_が半減(self):
        bundle = make_bundle(regime="Crisis")
        result = apply_regime_confidence(result, bundle)
        assert result.confidence_adjusted == result.confidence * Decimal("0.5")

    def test_ranking_score_別の_kelly_multiplier(self):
        assert compute_kelly_multiplier(85) == Decimal("1.0")
        assert compute_kelly_multiplier(65) == Decimal("0.5")
        assert compute_kelly_multiplier(40) == Decimal("0.0")
```

---

## 10. 並列化戦略（時間短縮、質を落とさず）

サブエージェントを **積極的に並列起動** して工数を 28% 短縮する。CLAUDE.md「並列タスク実行」原則と AGENTS.md「ALWAYS use parallel Task execution for independent operations」に準拠。

### 10.1 Phase 別 並列化マップ

| Phase | 並列起動するエージェント / タスク | 直列工数 | 並列化後 | 削減 |
|---|---|---:|---:|---:|
| **5.2 ロジック層** | ① `Explore` で既存 sentiment.py パターン抽出<br>② `docs-lookup` で Anthropic SDK + Prompt Caching 仕様取得<br>③ `architect` で Pydantic スキーマ設計レビュー | 6 h | 4.5 h | -25% |
| **5.3 シグナル束** | ① Polymarket client 新規実装（独立サブエージェント）<br>② 13F 差分抽出（既存 sec_edgar.py + 03_thirteen_f.py から関数化、独立サブエージェント）<br>③ Regime アダプタ（既存 regime.py を bundle dict 整形、独立サブエージェント） | 7 h | 4.5 h | -36% |
| **5.4 UI** | ① `session_state` refactor 下準備（display_screening_results 関数抽出）<br>② Stage 3 規律強制（Kelly multiplier / Regime 補正、純粋関数）<br>③ MC fan chart 関数（既存 05_monte_carlo.py から抽出）<br>④ 詳細カード レイアウト テンプレート | 7 h | 5 h | -29% |
| **5.5 E2E** | ① `python-reviewer` + `security-reviewer` + `code-reviewer` を **同時起動**<br>② Playwright スクリプト準備 + テストデータ準備並列 | 5 h | 3.5 h | -30% |
| **計** | | **25 h** | **17.5 h** | **-30%** |

※ 5.1 残（PRD + design.md）は直列依存のため 1.5 h 維持。

### 10.2 並列化の実行ルール

1. **1 メッセージで複数 Agent tool call** — CLAUDE.md「並列タスク実行」原則に従う
2. **インターフェース先決め** — `RankingSignalBundle` dataclass を Phase 5.1 / 5.2 早期で確定 → 5.2 と 5.3 が独立化
3. **コードレビュー並列** — 各 Phase 完了時に 3 reviewer 同時起動、修正を 1 回に集約
4. **Streamlit ファイル統合は最後に直列** — `02_screener.py` は単一ファイルで競合するため、関数抽出 → メインスレッドで統合
5. **失敗時は直列に降格** — サブエージェント結果が想定外の場合、メインスレッドで書き直し（質を落とさない）

### 10.3 並列化しない箇所（質優先）

- ⚠️ Phase 5.1 PRD / design.md は **直列**（コンテキスト一貫性）
- ⚠️ Sonnet プロンプト調整 / TDD RED→GREEN サイクルは **直列**（テスト → 実装の依存）
- ⚠️ Playwright E2E は **直列**（Streamlit インスタンス 1 つ）
- ⚠️ コミット / push は **直列**（git 衝突回避）

---

## 11. 受け入れ基準（Acceptance Criteria）

Phase 5 完了の判定:

- [ ] AC1: `02_screener.py` で MF_TOP_N=5 を実行すると 30 秒以内に Sonnet 判定結果が表示される
- [ ] AC2: 詳細カードに supporting / risk / counter_view / 3 レンズタブ / MC fan chart / 免責が全て表示されている
- [ ] AC3: 出力 JSON に `target_price` / `expected_return` / `time_horizon` フィールドが含まれていない（Pydantic で reject）
- [ ] AC4: 出力テキストに「$200 になる」「3 ヶ月以内に上昇」等の一本線予測が含まれていない（FORBIDDEN_PATTERNS で TDD 検証）
- [ ] AC5: Regime=Crisis のテストデータで `confidence_adjusted = confidence × 0.5` が成立
- [ ] AC6: ranking_score 別の Kelly multiplier が `≥80→1.0 / 50-79→0.5 / <50→0.0` で動作
- [ ] AC7: API key 不正時に全銘柄数式ランキング + 🚨 UI 警告が出る
- [ ] AC8: 個別銘柄 timeout 時に該当銘柄のみ Composite 埋め + ⚠️ UI 警告が出る
- [ ] AC9: Sonnet 判定結果が 24 h キャッシュされ、同一入力で再実行が API 呼び出しせず復元
- [ ] AC10: BUY ボタン押下後も Composite テーブル + 詳細カードが session_state で維持される（§12.3 解消）
- [ ] AC11: Decision Log JSONL に Claude `ranking_score / lens_views / metadata` が記録される
- [ ] AC12: TDD カバレッジ 80%+、ruff F/E/W ゼロ
- [ ] AC13: 月額運用コスト < 5,000 円（試算ベース）

---

## 12. リスクと緩和策

| リスク | 影響 | 緩和策 |
|---|---|---|
| Sonnet プロンプトが「一本線予測」を出してしまう | CLAUDE.md §9.3 違反 | system prompt + Pydantic + 正規表現 TDD の 3 層強制 |
| Polymarket API が停止 / スキーマ変更 | シグナル束の一部欠落 | 個別フォールバック（その銘柄のみ Composite 埋め）+ シグナル別キャッシュで延命 |
| Sonnet 出力 JSON 構造ブレ | パース失敗 | Pydantic + `_extract_json` パターン（既存 sentiment.py 流用）+ リトライ 1 回 |
| Sonnet コスト想定超過 | 月額予算オーバー | Prompt Caching 90% 削減 + 24 h キャッシュ + MF_TOP_N=5 デフォルト |
| Streamlit `st.form` rerun 挙動で UI 壊れる（§12.3 既知） | BUY 後にテーブル消失再発 | session_state refactor で display_screening_results 関数化 |
| サブエージェント並列化で出力が断片化 | 統合コスト増 | インターフェース先決め（RankingSignalBundle 定義）+ メインスレッド統合ゲート |
| 13F-NT (守秘要請) 銘柄の扱い | UI で混乱（既知 §5.6） | Phase 5.3 で `is_confidential` フラグ付与、UI で「⚠️ 守秘要請中」表示 |

---

## 13. 工数試算と Phase 分割

### 13.1 工数試算

| Phase | 直列工数 | 並列化後 |
|---|---:|---:|
| 5.1 残（PRD + design.md） | 1.5 h | 1.5 h |
| 5.2 ロジック層 | 6.0 h | 4.5 h |
| 5.3 シグナル束（Polymarket 新規含む） | 7.0 h | 4.5 h |
| 5.4 UI + Stage 3 + MC + refactor | 7.0 h | 5.0 h |
| 5.5 E2E + handoff | 5.0 h | 3.5 h |
| **純作業計** | **26.5 h** | **19.0 h** |

### 13.2 実時間（オーバーヘッド込み）

```
19.0 h × 1.05 (GateGuard) × 1.15 (バッファ) + 1.25 (新セッション × 5) = 約 24 h
```

### 13.3 セッション / カレンダー

| 観点 | 値 |
|---|---|
| 1 セッション目安 | 2.0-2.5 h（コンテキスト 300k rot ライン尊重） |
| 推定セッション数 | 約 10 セッション |
| 1 日 1 セッション運用 | 約 10 日（1.5 週間） |
| 1 日 2 セッション運用 | 約 5 日（1 週間） |

育休中の現実的ペースは **1 日 1 セッション → 約 10 日で完成**。

### 13.4 マイルストーン

```
[Day 1] PRD レビュー + design.md 起草 + レビュー       … 5.1 完了
[Day 2] Phase 5.2 ロジック層（dataclass + Pydantic + TDD RED）
[Day 3] Phase 5.2 完成（実装 GREEN + フォールバック）
[Day 4] Phase 5.3（Polymarket / 13F / Regime 並列）
[Day 5] Phase 5.3 仕上げ（signal_aggregator + キャッシュ）
[Day 6] Phase 5.4（session_state refactor + Stage 3）
[Day 7] Phase 5.4 仕上げ（UI 詳細カード + MC + 免責）
[Day 8] Phase 5.5（Playwright E2E）
[Day 9] Phase 5.5（リワーク + handoff doc）
[Day 10] 最終コミット + push + プロジェクト完了
```

---

## 14. 関連ドキュメント / 出典

- `CLAUDE.md` §1（プロジェクト概要）/ §6（出力先固定）/ §9.3（一本線禁止）/ §9.4（学術根拠）/ §9.5（損切り規律）/ §9.7（認知バイアス）/ §9.8（Provenance）
- `docs/product-requirements.md` MVP #1 Magic Formula スクリーナー（本 PRD の上位）
- `docs/long-term-investment-architecture.md` Composite 7 軸の理論的背景
- `docs/cost-budget.md` 月額コスト試算
- `.steering/20260510-jquants-japan-stocks/handoff-phase4.md` §11 / §12（前 phase 完了内容、§12.3 残課題）
- `.steering/20260512-claude-ranking-judge/handoff-prompt.md` 引き継ぎプロンプト本体
- `.claude/skills/polymarket-macro-watcher/SKILL.md`
- `.claude/skills/13f-cloning-tracker/SKILL.md`
- `.claude/skills/regime-detection/SKILL.md`
- `.claude/skills/kelly-position-sizer/SKILL.md`
- `.claude/skills/monte-carlo-projection/SKILL.md`
- `.claude/skills/magic-formula-screener/SKILL.md`

### 学術根拠（Sonnet system prompt で引用、§9.4 準拠）

- Greenblatt 2010 "The Little Book That Still Beats the Market"（Magic Formula）
- Tetlock 2007 "Giving Content to Investor Sentiment"（センチメント分析）
- Loughran-McDonald 2011（金融特化センチメント辞書）
- Schroeder & Posch 2024（13F クローン戦略の実証）
- Pabrai "The Dhandho Investor"（集中投資、Few Bets / Big Bets / Infrequent Bets）
- Thorp 2006 "The Kelly Criterion in Blackjack, Sports Betting, and the Stock Market"（Half-Kelly）

---

**PRD 終わり** — 次は `.steering/20260512-claude-ranking-judge/design.md`（実装計画）を起草する。
