# 引き継ぎ — ATR Decision Log 連携 完了 → 次は 13F 動的化 / 7203.TO 404

> **作成日**: 2026-05-09
> **対象**: 次回作業開始時の最初の参照ドキュメント
> **本セッション最終コミット**: `a24a076`
> **GitHub**: https://github.com/ShunsukeHOSODA/kaori_kabu (Private, SSH 認証)

---

## 1. 本セッションで完了した内容

### A. ATR Decision Log 連携 (#5) — `a24a076`

ATR トレーリングストップ条件が breach / near に到達した瞬間、自動で `data/decision-log/{YYYY-MM}.jsonl` に追記する仕組みを実装。CLAUDE.md §9.5 / §9.8.3 Provenance 規約準拠。

**ユーザー確定の設計判断**:

- action = `"HOLD"` + rationale で「売却検討」を明示（既存スキーマ維持、AI 自動売買誤読を回避）
- 重複防止 = 月内 (ticker, alert_status) 初回のみ。状態遷移時は再記録、safe は記録対象外

**新規ファイル**:

| ファイル | 役割 |
|---|---|
| `src/portfolio/atr_alert_logger.py` | should_log_alert / log_atr_alert 純関数（USD は usdjpy 換算、原通貨情報は trigger.metadata に保存） |
| `src/analysis/_provenance.py` | get_current_git_commit 共通ヘルパー（regime.py / risk_metrics.py の `_get_current_git_commit` 重複を止めるための新規モジュール。既存 2 ファイルの統合は別 PR） |
| `tests/unit/portfolio/test_atr_alert_logger.py` | 12 ケース（should_log_alert 6 + log_atr_alert 6） |
| `.steering/20260509-atr-decision-log-bridge/design.md` | 設計ドキュメント |

**修正**:

| ファイル | 変更 |
|---|---|
| `src/dashboard/views/01_home.py` | atr_alerts ループ後に decision-log 自動追記ブロック追加（+24 行）。UI には書かない（規律 = 静かに残す） |

### B. テスト

- **270 → 282 件 GREEN**（slow 除く、coverage 除外）
- 新規内訳: should_log_alert 6 件 + log_atr_alert 6 件 = **12 件**

### C. 実機検証 (Playwright + 目視)

ホーム + サンプル portfolio.csv (AAPL/US + 7203/TO) で:

- AAPL 評価: **439,980 円**、含み益 **+189,980 円 (+75.99%)**
- ATR トレーリングストップ: 🟢 **全銘柄が安全圏**（AAPL のみ評価成功）
- → AAPL は safe → **JSONL 作成されない**（重複防止規約・safe 除外規約の正しい挙動を確認）
- → breach/near のポジティブ動作は単体テスト 12 件で完全網羅
- スクリーンショット: `atr-decision-log-bridge-verified.png`（コミット済）

### D. 学んだこと（再発防止メモ）

#### `src/` 内パッケージ間 import は **相対 import** を使う

- pytest は `pythonpath = ["src"]` で src を sys.path に入れる → `from portfolio.X import` で動く
- Streamlit は src を sys.path に入れない → `from src.portfolio.X import` が必要
- 両方で動かすには **相対 import** (`from .decision_log import`) が正解
- `src/portfolio/valuation.py:14` に既に前例あり (`from .holdings import`)
- 今回 1 度ハマった (ModuleNotFoundError: No module named 'portfolio') → 修正済

---

## 2. 残タスク（優先順位付き）

### 🟡 優先 1: 13F Cloning 動的化 (#4)

- `src/data/sec_edgar.py` の XML パーサ実装
- `src/data/famous_holdings.py` の静的辞書を SEC EDGAR からの動的取得に置換
- 13F-HR の四半期更新追従
- 規模: 大（context ~80-100k 想定）→ **フレッシュセッション推奨**

### ⚪ 副次: 7203.TO の EODHD 404 (#6)

- EODHD で `7203.TO` が 404 Not Found
- 東証は `.T` / `.JP` / `.TSE` のいずれかを要求している可能性
- 確認すべき: portfolio.csv の `exchange` 列、`Holding.ticker` 組み立てロジック、EODHDClient.get_eod の exchange パラメータ仕様
- 日本株は J-Quants 経由に分岐させる選択肢もあり
- 規模: 小（context ~20-30k 想定）

### 🟢 共通化候補（CLAUDE.md §9.8 / 別 PR）

- `regime.py::_get_current_git_commit` / `risk_metrics.py::_get_current_git_commit` を `_provenance.py::get_current_git_commit` に統合
- 既存 2 ファイルのテスト・呼び出し側修正必要（軽め）

---

## 3. セッション開始時の自動アクション

```bash
cd /Users/kaori/Desktop/kaori_kabu

# 1. git 状況把握
git log --oneline -10
git status --short

# 2. テスト緑チェック
export PATH="$HOME/.local/bin:$PATH"
uv run pytest --no-cov -m "not slow" -q | tail -3
# 期待値: 282 passed, 3 deselected

# 3. 残タスクの再確認
cat .steering/20260509-atr-decision-log-handoff/handoff.md
```

ユーザーへの最初の問いかけ（候補）:
> 「前回 ATR Decision Log 連携が完成 + 視覚検証 + 1 commit 済。残タスクは
> 🟡 #4 13F 動的化（規模大、フレッシュセッション推奨）/ ⚪ #6 7203.TO 404（規模小）。**どれから着手？**」

---

## 4. 動作確認済みコマンド

```bash
# テスト全体（slow 除く）
uv run pytest --no-cov -m "not slow" -q

# 特定モジュール
uv run pytest --no-cov -m "not slow" -q tests/unit/portfolio/test_atr_alert_logger.py

# Streamlit 起動 / 停止
uv run streamlit run src/dashboard/app.py --server.port 8520 --server.headless true
lsof -iTCP:8520 -sTCP:LISTEN
kill $(lsof -tiTCP:8520 -sTCP:LISTEN)
```

---

## 5. 既知の限界・注意（追記）

### portfolio.csv サンプル状態

- `data/holdings/portfolio.csv` は前セッションのサンプル (AAPL/US + 7203/TO)
- `.gitignore` の `data/holdings/` で除外 → git には上がらない
- 7203.TO は EODHD 404 で評価対象外（#6 で対応予定）

### Decision Log 動作シナリオ

- AAPL が breach/near になれば自動で `data/decision-log/2026-05.jsonl` に書かれる
- 同月に同 status が既存なら **重複しない**（重複防止 OK）
- safe は **記録対象外**（イベントとして意味がない）
- USD 通貨は usdjpy_fallback (現在 150) で JPY 換算、原通貨情報は trigger.metadata に保存

### `_provenance.py` の責務分離

- 新規モジュールは `get_current_git_commit` を本ヘルパーから import する方針
- 既存 `regime.py::_get_current_git_commit` / `risk_metrics.py::_get_current_git_commit` は後方互換のため残置
- 統合 PR はリファクタタスクとして単独で管理

### ECC 自動メモリ

- `.omc/project-memory.json` に M がある場合、ECC が自動更新したもの
- コミットには含めない（毎セッション同じ）

### 視覚検証スクリーンショット

- 前セッションの `atr-usd-fix-verified.png` / `risk-metrics-panel-verified.png` は untracked のまま残置
- 本セッション分 `atr-decision-log-bridge-verified.png` は `a24a076` でコミット済

---

## 6. 主要ファイルマップ（本セッション追加分）

```
src/portfolio/atr_alert_logger.py                          — ★ 新規 should_log_alert / log_atr_alert
src/analysis/_provenance.py                                — ★ 新規 get_current_git_commit 共通ヘルパー
src/dashboard/views/01_home.py                             — Edit atr_alerts ループ後に logger 呼び出し追加（+24 行）

tests/unit/portfolio/test_atr_alert_logger.py              — ★ 新規 12 ケース

.steering/20260509-atr-decision-log-bridge/design.md       — ★ 新規 設計ドキュメント
atr-decision-log-bridge-verified.png                       — 視覚検証 screenshot (commit 済)
```

---

## 7. 次セッション最初の操作（推奨）

1. このファイル `.steering/20260509-atr-decision-log-handoff/handoff.md` を読む
2. `git status` + `git log --oneline -10` で現状確認（最新は `a24a076`、handoff doc commit 後はその次）
3. テスト緑チェック (`pytest -m "not slow" -q | tail -3` で 282 passed 確認)
4. ユーザーに「優先 🟡 #4 13F 動的化（フレッシュセッション推奨）/ ⚪ #6 7203.TO 404 — どれから着手？」と聞く

---

## 8. アーキテクチャ判断ログ

### 同パッケージ内 import の正解 = 相対 import

- pytest と Streamlit でモジュール解決パスが異なるため、`from package.X import` も `from src.package.X import` も片方しか動かない
- 相対 import (`from .X import`) なら両方動く
- 既存 `valuation.py:14` の `from .holdings import` が前例

### `_provenance.py` を本タスクで作った理由

- 当初 design.md 「Out of Scope」だったが、3 度目の `_get_current_git_commit` 実装になることが判明
- DRY 原則優先で **新規モジュール 1 ファイル追加のみで** 共通化（既存 2 ファイルのリファクタは別 PR）
- 結果: 既存テスト無影響、新規モジュールは `home.py` 経由でのみ使われる
