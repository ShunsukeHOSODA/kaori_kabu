# Phase 5 引き継ぎプロンプト — Claude Sonnet を Ranking Judge にする総合ランキング

**生成日**: 2026-05-12
**前 handoff**: `.steering/20260510-jquants-japan-stocks/handoff-phase4.md` (Phase 4 完了 + Session 3)
**新ステアリング ID**: `20260512-claude-ranking-judge`

---

## 使い方

次セッション開始時に `/clear` してから、下記「引き継ぎプロンプト本体」を 1 メッセージで投げる。承認後に Phase 5.1 設計（brainstorming）から着手。

---

## 引き継ぎプロンプト本体（コピペ用）

```
Phase 5 着手: Claude Sonnet を Ranking Judge にする総合ランキング機能を実装したい。

【プロジェクト方針（厳守、Claude プロンプトの制約にも組み込む）】
- 完全に個人専用ローカル（金商法対象外、サーバ公開しない）
- 投資助言サービスではない（自己責任で売買判断、Claude 出力に必ず免責表示）
- AI 予測は確率分布として表示、一本線の価格予測は禁止（CLAUDE.md §9.3）
- 学術的バックボーン引用 + リスク警告併記（§9.4）
- Provenance §9.8.3 で全入力シグナル + Claude 判定理由を JSON 化して再現可能に

【課題認識】
現状の 02_screener ランキングは Magic Formula + Composite 7 軸（数式加重合算）のみ。
Claude Haiku はニュースセンチメント定量化だけで、ランキング判断には参加していない。
Polymarket / 13F 差分 / EODHD ニュース / FRED マクロが分離した skill のまま統合されておらず、
「数ある銘柄から総合判断」というユーザー期待と実装に乖離がある。

【理想像】
入力ユニバース（US: S&P500 等 / JP: FinanceDatabase 経由 TSE 銘柄、§4.5 で実装済）から
以下の 2 段階で「数ある銘柄から最適な株を判定」する:

【Stage 1】数式フィルタ（コスト抑制）
- Magic Formula + Composite 7 軸で 100-500 銘柄 → 上位 K (= 20-30 銘柄) に絞る
- ここまでは現行ロジックを再利用

【Stage 2】Claude Sonnet 4.6 による精密判定
- 各銘柄について以下のシグナル束を Sonnet に渡す:
  * Composite サブスコア（Q/V/I/G/R/M/S 各 0-100）
  * Magic Formula スコア + ROC + EY
  * 直近 1m/12m モメンタム
  * Tavily/Exa ニュース 4 系統 + Claude Haiku センチメント（既存）
  * Polymarket マクロ確率（Fed 利上げ / 景気後退 / 地政学）
  * 13F 直近 1Q 差分（Berkshire / Pabrai / Burry / Ackman 等の保有変化）
  * FRED マクロ（VIX / 利回り曲線 / クレジットスプレッド）
  * HMM レジーム判定（Bull / Choppy / Crisis）
  * セクター + 市場（US / JP）
- Sonnet が銘柄ごとに以下の JSON を返す:
  {
    "ranking_score": 0-100,
    "recommendation_summary": "1-2 文の根拠",
    "supporting_signals": ["Composite Q 高", "Polymarket Fed 利下げ確率上昇", ...],
    "risk_signals": ["Recency Bias 警告", "Value Trap 懸念", ...],
    "counter_view": "反対意見（Confirmation Bias 対策）",
    "lens_views": {
      "Buffett_Munger": "...",
      "Burry": "...",
      "Lynch": "..."
    },
    "confidence": 0-1
  }
- 「目標株価」「上昇率予測」「いつまでにいくらになる」は禁止プロンプトで縛る
  → 出力スキーマに含めない、system prompt で明示的に禁止
- レジーム = Crisis のとき confidence を強制的に下げる（規律トレーニング）

【UI 統合】
- 02_screener 結果テーブルに「Claude スコア」「Claude 推奨度」列追加
- 上位 5 銘柄に Claude 詳細カード（recommendation_summary + supporting_signals +
  risk_signals + counter_view + lens_views）を併記
- 既存 Magic Formula / Composite テーブルは残す（透明性のため）
- 「ⓘ Provenance」expander で Claude への入力 dict と出力 dict を全開示
- 免責: 「これは投資助言ではありません。最終判断はユーザー自身で。AI 出力は
  確率分布の参考情報です」を Claude 結果直下に必須表示

【事前読み込み】
- .steering/20260510-jquants-japan-stocks/handoff-phase4.md §12（Session 3 完了内容）
- .steering/20260512-claude-ranking-judge/handoff-prompt.md（本プロンプト元ファイル）
- CLAUDE.md §9.3 / §9.4 / §9.7 / §9.8（一本線禁止 / 根拠併記 / バイアス対策 / Provenance）
- docs/long-term-investment-architecture.md（既存 Composite 7 軸設計）
- docs/product-requirements.md（MVP 機能 #1 = Magic Formula スクリーナー）
- src/dashboard/views/02_screener.py 現状実装（特に Composite 計算ループ line 1029-1113）
- src/analysis/composite.py（7 軸スコア定義）
- src/analysis/sentiment.py（既存 Claude Haiku 連携、入出力スキーマ参考）
- .claude/skills/polymarket-macro-watcher/SKILL.md
- .claude/skills/13f-cloning-tracker/SKILL.md
- .claude/skills/regime-detection/SKILL.md
- src/config/settings.py（ANTHROPIC_API_KEY 既存設定）

【実装方針（フェーズ分け）】
Phase 5.1: 設計（半日）
  1. /superpowers:brainstorming で要件詰める:
     - Sonnet 4.6 vs Haiku 4.5 のコスト/品質トレードオフ
     - 上位 K = 20 / 30 のどちらが ROI 高いか
     - シグナル束の入力 token サイズ見積もり
     - キャッシュ戦略（同銘柄 + 同シグナルなら 24h キャッシュ）
     - 失敗時 graceful degradation（Claude 落ちたら数式ランキングにフォールバック）
  2. /prp-prd で PRD 起こす → docs/ranking-judge-prd.md
  3. /superpowers:writing-plans で実装計画 →
     .steering/20260512-claude-ranking-judge/design.md

Phase 5.2: ロジック層（1 日）
  4. src/analysis/ranking_judge.py 新規:
     - RankingSignalBundle (frozen dataclass): 全シグナルを 1 銘柄ぶん束ねる
     - RankingResult (frozen dataclass): Sonnet 出力の Pydantic 検証付き
     - rank_with_claude(bundles, *, anthropic_client, ...) -> list[RankingResult]
     - system prompt で「一本線予測禁止 / 投資助言ではない / 学術根拠引用必須」を明示
     - 失敗時は数式ランキングにフォールバック
  5. TDD: tests/unit/analysis/test_ranking_judge.py で
     - 入力スキーマ検証
     - Sonnet モックでの出力 schema 検証
     - 一本線予測（"AAPL は $200 になる" 等）が出力に含まれないこと
     - confidence × レジーム の規律ロジック検証

Phase 5.3: シグナル束組み立て（半日）
  6. src/analysis/signal_aggregator.py 新規:
     - 既存 Composite / Magic Formula / Polymarket / 13F / FRED / HMM スキルを呼び出し
     - 1 銘柄あたり RankingSignalBundle を構築
     - キャッシュ TTL: 24h（ファンダ）/ 1h（センチメント）/ 6h（Polymarket）

Phase 5.4: UI 統合（半日）
  7. 02_screener.py:
     - Stage 1 数式フィルタ後に上位 K を取得
     - Stage 2 Claude 判定（progress bar + キャッシュ表示）
     - 結果テーブルに Claude 列追加 + 上位 5 銘柄詳細カード
     - Provenance expander
     - 免責文言の必須表示

Phase 5.5: E2E 検証（半日）
  8. Playwright で全フロー検証:
     - 入力 5-10 銘柄 → Claude スコアが返る
     - 詳細カードに lens_views / risk_signals / counter_view が表示
     - Provenance expander に全シグナル束と Claude 出力 dict が見える
     - 免責が表示されている
     - 一本線予測が出ていないことを目視確認
  9. スクショ証跡 .steering/20260512-claude-ranking-judge/ に保存

【コミット規約】
feat(ranking): Claude Sonnet 総合ランキング Stage X [20260512-claude-ranking-judge]
- 各フェーズで個別コミット（5.1 設計 / 5.2 ロジック / 5.3 シグナル / 5.4 UI / 5.5 E2E）

【特記事項】
- Anthropic API のキーは既に ANTHROPIC_API_KEY で設定済（settings.py 経由）
- Claude モデルは Sonnet 4.6 (claude-sonnet-4-6) を使う（コーディングではなく判定タスクなので Opus は過剰）
- 入力 token サイズが大きい場合は Prompt Caching で抑制
- 失敗・例外時は静かに数式ランキングにフォールバックして UI 警告

承認後に Phase 5.1 設計から着手。まず brainstorming で要件詰めてから PRD へ。
```

---

## 設計判断のポイント（参考）

| ポイント | 理由 |
|---|---|
| **2 段階フィルタ** | 全ユニバース（数千銘柄）を Sonnet に投げると 1 回 $5-10 → 数式で 20-30 銘柄に絞ってから Sonnet |
| **一本線予測禁止の縛り** | 出力スキーマに「目標株価」「予測上昇率」を含めない + system prompt で明示禁止 + TDD で出力検証 |
| **レジーム連動** | Crisis 判定時に confidence を強制的に下げる → 規律トレーニング（CLAUDE.md §9.5 損切り規律 / §9.7 Overconfidence 対策） |
| **多角レンズ** | lens_views で Buffett-Munger / Burry / Lynch の異なる視点を **同時表示** → Confirmation Bias 対策 |
| **graceful degradation** | Claude 落ちたら数式ランキングにフォールバック（個人ローカルだからこそ可用性確保） |
| **Phase 分割** | 1 セッションで全実装は無理。5.1 設計 → 5.2 ロジック → 5.3 シグナル → 5.4 UI → 5.5 E2E の 5 フェーズ、各半日〜1 日 |

---

## 補足: Sonnet 4.6 を選んだ理由

- **コスト**: Opus 4.6/4.7 は判定タスクに過剰、Sonnet 4.6 で十分（コーディングではなく構造化判定）
- **品質**: 30 銘柄 × 入力 5,000 token × 出力 1,500 token 程度なら Sonnet で精度十分
- **Prompt Caching**: 共通の system prompt + 投資家レンズ定義はキャッシュ可能 → コスト 50-90% 削減
- **モデル ID**: `claude-sonnet-4-6`（CLAUDE.md グローバル設定の最新世代）

---

## 想定コスト試算（参考、月次）

- 月 4 回ランキング実行 × 30 銘柄 × Sonnet 4.6
- 入力: 5,000 token × 30 銘柄 = 150,000 token / 回
- 出力: 1,500 token × 30 銘柄 = 45,000 token / 回
- Sonnet 4.6 価格: $3/MTok input、$15/MTok output（Prompt Caching で input 90% OFF）
- 1 回コスト: ($3 × 0.15 × 0.1) + ($15 × 0.045) = $0.05 + $0.68 = **約 $0.73 / 回**
- 月 4 回: **約 $3 / 月（約 450 円）**

→ EODHD $30 / 月 + Anthropic $3 / 月 = **約 4,950 円 / 月** に収まる。
