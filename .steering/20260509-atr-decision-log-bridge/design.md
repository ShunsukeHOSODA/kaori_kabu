# ATR Decision Log 連携（#5）

> **作成日**: 2026-05-09
> **規模**: 中（context ~50-70k）
> **方針**: TDD で純関数を先に固め、UI 統合は最後に薄く差し込む

---

## 1. 目的

ATR トレーリングストップ条件が `breach` / `near` に到達した時点で `data/decision-log/{YYYY-MM}.jsonl` に**自動追記**し、CLAUDE.md §9.5 と §9.8.3 Provenance 規約を満たす。

---

## 2. ユーザー確定の設計判断

- **action フィールド** = `"HOLD"`（既存スキーマ維持）+ rationale で状況記述
- **重複防止** = 月内 `(ticker, status)` 初回のみ。状態遷移時は再記録、`safe` は記録対象外

---

## 3. 既存資産（拡張せず利用）

| ファイル | 役割 |
|---|---|
| `src/portfolio/decision_log.py::append_decision` | JSONL 1 行追記 |
| `src/portfolio/decision_log.py::read_decisions` | 月次ログ読込（重複検出に再利用） |
| `src/dashboard/widgets/atr_alert.py::AtrAlert` | frozen dataclass 入力 |
| `src/portfolio/holdings.py::Holding` | shares / exchange / avg_cost_jpy 入力 |

---

## 4. JSONL レコード仕様（実例）

```json
{
  "timestamp": "2026-05-09T05:30:00+00:00",
  "action": "HOLD",
  "ticker": "AAPL",
  "shares": "10",
  "price_jpy": "44245",
  "rationale": "ATR トレーリングストップ条件抵触（基準 \\$277、現在 \\$280）→ 売却検討",
  "trigger": {
    "skill": "atr-trailing-stop",
    "metadata": {
      "alert_status": "breach",
      "atr_period": 14,
      "atr_multiplier": "2.5",
      "lookback": 20,
      "stop_price_original": "277.00",
      "current_price_original": "280.00",
      "currency_original": "USD",
      "usdjpy_rate_applied": "158.00"
    }
  },
  "stop_loss_atr_jpy": "43766",
  "code_commit": "9bb59d8",
  "news_context": null
}
```

---

## 5. 実装ファイル

### 5.1 新規: `src/portfolio/atr_alert_logger.py`

```python
def should_log_alert(*, alert, log_dir, year_month) -> bool: ...
def log_atr_alert(*, alert, holding, log_dir, usdjpy_rate, code_commit) -> Path | None: ...
```

- USD は `usdjpy_rate` で JPY 換算、JPY はそのまま
- `safe` は早期 return → JSONL 作成すらしない
- 内部で `read_decisions` を呼んで重複チェック

### 5.2 Edit: `src/dashboard/views/01_home.py`

`atr_alerts` ループの後、breach/near のみ logger を呼ぶ。UI には記録した旨を表示しない（規律 = 静かに残す）。

---

## 6. TDD タスク分解

### T1: `should_log_alert` 6 ケース

| # | ケース | 期待 |
|---|---|---|
| 1 | ログファイル無し | True |
| 2 | 月内 (ticker, 同 status) 既存 | False |
| 3 | 月内 (ticker, 別 status) | True |
| 4 | 別月 (ticker, 同 status) | True |
| 5 | 既存レコードが他 skill | True |
| 6 | status="safe" | False |

### T2: `log_atr_alert` 6 ケース

| # | ケース | 期待 |
|---|---|---|
| 1 | breach + JPY | 1 行追加、price=JPY のまま |
| 2 | breach + USD | price_jpy/stop_loss_atr_jpy が usdjpy 換算 |
| 3 | trigger.metadata 完全（atr_period/multiplier/currency_original 等） | 全フィールド一致 |
| 4 | 重複（既存有り） | None 返し JSONL 不変 |
| 5 | safe | None 返し JSONL 作成しない |
| 6 | code_commit | top-level のみ伝播 |

### T3: home view 統合

視覚検証のみ。

---

## 7. 規模見積

| 項目 | 行数 | テスト |
|---|---|---|
| `atr_alert_logger.py` | ~100 | - |
| `tests/unit/portfolio/test_atr_alert_logger.py` | ~250 | 12 ケース |
| `views/01_home.py` 編集 | ~15 | - |
| **合計** | **~365 行** | **270 → 282** |

---

## 8. 完了条件

- [ ] T1 / T2 全テスト緑
- [ ] `pytest -m "not slow" -q` で 282 passed
- [ ] Streamlit 起動して breach 状態で JSONL に 1 行追加を目視確認
- [ ] 同セッションで複数回評価しても JSONL がダブらない
- [ ] git commit `feat(decision-log): ATR breach/near 自動記録 [20260509-atr-decision-log-bridge]`

---

## 9. 非対象（Out of Scope）

- BUY 時の Decision Log 記録（別タスク）
- 為替動的取得（Phase 2 別タスク）
- Decision Log 集計・可視化（別 Phase）
- USD 以外の通貨（現状 portfolio に無し）
- `_get_current_git_commit` 共通モジュール化（YAGNI、別 PR）
