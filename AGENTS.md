# AGENTS.md — kaori_kabu エージェント運用

> グローバル `~/.claude/AGENTS.md` を継承。このファイルにはプロジェクト固有の運用のみ記述。

## このプロジェクト固有のエージェント

### `kabu-analyst`（独自エージェント）

`.claude/agents/kabu-analyst.md` に定義。データ取得 + 分析を統合する。

**起動条件**:
- 「銘柄分析して」「○○の Magic Formula スコア出して」「ポートフォリオの Sharpe 計算」等
- バックテスト実行 + 結果解釈
- 13F filings の差分分析

**できること**:
- OpenBB SDK + EODHD + J-Quants からのデータ取得
- pandas-ta でテクニカル指標計算
- vectorbt でバックテスト
- QuantStats でリスク指標生成
- Riskfolio-Lib でポートフォリオ最適化
- 結果を Streamlit ダッシュボードに渡せる形式で返す

## 即時起動

| トリガー | エージェント |
|---|---|
| 銘柄分析リクエスト | `kabu-analyst`（独自） |
| 複雑な機能要求 | `planner` agent / `/superpowers:writing-plans` |
| バグ修正・新機能 | `tdd-guide` agent / `/superpowers:test-driven-development` |
| Python コード変更直後 | `python-reviewer` agent（必須） |
| アーキテクチャ判断 | `architect` agent |
| API キー / セキュリティ感応コード | `security-reviewer` agent（必須） |
| OpenBB / pandas / vectorbt API 仕様 | `docs-lookup` agent (Context7) |
| 曖昧な要件 | `/superpowers:brainstorming` |
| コードベース横断調査 | `Explore` agent（並列） |
| パフォーマンス問題 | `performance-optimizer` agent |

## 言語別レビュアー

このプロジェクトは Python 中心。

| 言語 | エージェント |
|---|---|
| Python | `python-reviewer`（必須） |
| HTML/CSS（Streamlit カスタム） | `typescript-reviewer`（軽く） |
| SQL（DuckDB / SQLite 利用時） | `database-reviewer` |

## 並列実行（必須運用）

独立タスクは **1 メッセージに複数 Agent tool call** を並べて同時起動。

### 典型パターン（株運用）

```
Agent 1 (Explore): src/data/ で EODHD クライアント実装を発見
Agent 2 (Explore): src/analysis/ で Magic Formula 関連コード発見
Agent 3 (docs-lookup): OpenBB SDK の最新 API 仕様取得
↓
Agent 4 (kabu-analyst): 実際のデータでロジック検証
Agent 5 (python-reviewer): 型ヒント・PEP 8 確認
Agent 6 (security-reviewer): API キー漏洩リスク確認
```

`/superpowers:dispatching-parallel-agents` を活用。

## モデル選定

| タスク | モデル |
|---|---|
| メインの開発作業 | Sonnet 4.6（デフォルト） |
| 戦略アルゴリズム設計判断 | Opus 4.5（`/multi-plan` で起動） |
| 軽量・頻繁呼び出し（review 等） | Haiku 4.5（自動選択） |
| 数値計算検証（クロスモデル） | Codex（`codex:rescue` agent） |

## 株運用プロジェクト特有のエージェント運用ルール

### データ取得タスク
- 必ず `kabu-analyst` 経由で OpenBB SDK を叩く（直接 EODHD/J-Quants API を叩かない）
- キャッシュチェック必須（`data/cache/{provider}/`）
- レート制限を守る（rate-limit デコレータ実装）

### バックテスト
- look-ahead bias 防止のため walk-forward を必ず採用
- vectorbt の `Portfolio.from_orders` でシミュレーション
- 結果は QuantStats `qs.reports.html()` で出力

### 13F filings 取得
- SEC EDGAR の User-Agent ヘッダ必須（メアド明記）
- 過剰呼び出し禁止（10 req/秒）
- 取得済みデータは 90 日キャッシュ

### 戦略コード変更
- 変更前後でバックテスト結果（Sharpe / Max DD）を比較
- 改悪なら自動で revert 提案
- 重要パラメータ変更時は ADR 作成（`docs/ADR/`）

### 保有銘柄データ操作
- `data/holdings/portfolio.csv` 編集前に必ずバックアップ
- 売買履歴は append-only（過去データ書き換え禁止）

## チェックリスト（新機能実装の典型フロー）

- [ ] `Explore` agent で既存コード発見（並列で複数起動）
- [ ] `architect` agent で設計レビュー
- [ ] `tdd-guide` agent でテスト先行（pytest）
- [ ] 実装
- [ ] バックテストで Sharpe / Max DD 確認
- [ ] `python-reviewer` + `code-reviewer` で品質確認
- [ ] `security-reviewer` で API キー漏洩リスク確認
- [ ] `superpowers:verification-before-completion` で完了前検証
