# 持ち越し課題 Issue テンプレ — Phase 6 向け

> Phase 5.5.4 (handoff-session-6 §5.8-5.10) で起票予定の 3 課題。
> `gh` CLI 未インストール環境のため、Markdown テンプレートとして記載。
> 将来 `gh auth login` 後に `gh issue create --title "..." --body-file <section>.md` で一括起票可能。

---

## Issue #1: TRACKED_FUNDS CIK の実機検証

**Label**: `phase-6`, `data-quality`, `13f`
**Priority**: MEDIUM
**Source**: handoff-session-5 §5.1.1 / handoff-session-6 §5.10

### Description

`settings.tracked_funds_cik` に登録した 5 ファンド (Berkshire / Pabrai / Burry /
Ackman / Greenlight) の CIK 番号を SEC EDGAR の `/cgi-bin/browse-edgar?action=getcompany`
で実機検証していない。Phase 5.3 で fixture から 13F XML を読む層は実装したが、
CIK 自体が現実の SEC filings と一致しているかは未確認。

### 検証手順

```bash
# Burry: Scion Asset Management (CIK 0001649339)
curl -sH "User-Agent: kaori_kabu 1usnavf8@gmail.com" \
  "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001649339&type=13F-HR&dateb=&owner=include&count=10" \
  | grep -o "Scion[^<]*" | head -3
```

Ackman / Greenlight も同様に検証。

### 完了条件

- [ ] 5 CIK すべてが現在も active な 13F filer であることを確認
- [ ] CIK 番号と Fund 名の対応を `docs/tracked-funds.md` に記録
- [ ] 不正な CIK があれば `settings.py` の default 値を修正

### 影響範囲

- `src/data/sec_edgar.py` (13F 取得層)
- `src/analysis/signal_aggregator.py` (`fund_holdings_delta_by_fund`)
- 02_screener.py の `extract_holdings_delta("SPY", ...)` 暫定実装

---

## Issue #2: Sonnet ranking cache の LRU purge / 起動時掃除

**Label**: `phase-6`, `cache`, `cleanup`
**Priority**: MEDIUM
**Source**: handoff-session-5 §5.7 / handoff-session-6 §5.9

### Description

`data/cache/sonnet_ranking/*.json` は `(model_version, ticker, signal_bundle_hash)`
ベースで key 生成される。`model_version` がスナップショット更新 (例
`claude-sonnet-4-6-20250514` → `20250901`) で変わるたびに旧 key の cache が残存し、
ディスク容量を圧迫する。Phase 5.5.3 で `_resolved_sonnet_model_version` が動的解決
されるため、この問題は実質発生頻度が上がる。

### 解決案

オプション A (起動時掃除):
```python
def purge_stale_ranking_cache(*, current_model_version: str, max_age_days: int = 30) -> int:
    """current_model_version 以外で max_age_days 古い JSON を削除し件数を返す。"""
```

オプション B (LRU):
- access time-based の lru_cache 風 wrapper を ranking_judge_cache.py に追加
- ファイル数上限 (例 1,000) を超えたら古い順に削除

### 完了条件

- [ ] purge 関数を `src/analysis/ranking_judge_cache.py` に追加
- [ ] 02_screener.py の起動時 (Streamlit page load 1 回目) に purge を呼ぶ
- [ ] テスト: 30 日以上前 + 異なる model_version の JSON が削除されることを確認

### 影響範囲

- `src/analysis/ranking_judge_cache.py`
- `data/cache/sonnet_ranking/*.json`

---

## Issue #3: Prompt Caching ヒット率実測ダッシュボード

**Label**: `phase-6`, `observability`, `cost-tracking`
**Priority**: LOW
**Source**: handoff-session-5 §5.9 / handoff-session-6 §5.8

### Description

Anthropic Prompt Caching の効果 (想定 90% 削減) を実測していない。`rank_with_claude_batch`
の API response にある `usage.input_tokens_cached` を集計してダッシュボード化することで、
コスト最適化の検証ができる。

### 集計指標

| 指標 | 計算式 |
|---|---|
| キャッシュヒット率 | `input_tokens_cached / (input_tokens + input_tokens_cached)` |
| 削減コスト (USD) | `input_tokens_cached * 0.0008 * 0.9` (Sonnet の 90% 割引適用) |
| ヒット率の日次推移 | 日次集計 + 7 日移動平均 |

### 解決案

1. `src/analysis/ranking_judge.py` の `rank_with_claude_batch` で usage を Provenance に保存
   ```python
   metadata.cache_metrics = {
       "input_tokens": ...,
       "input_tokens_cached": ...,
       "cached_ratio": ...,
   }
   ```
2. `data/cache/sonnet_ranking/*.json` から集計する別 view を Streamlit に追加
   (例: `src/dashboard/views/09_observability.py`)
3. Plotly でヒット率推移をグラフ化

### 完了条件

- [ ] `RankingMetadata` に `cache_metrics` フィールドを追加
- [ ] 集計関数 `compute_cache_hit_rate(cache_dir: Path) -> pd.DataFrame` 追加
- [ ] 観測ダッシュボード新規ページで可視化
- [ ] テスト: mock response の usage 値から正しく計算されることを確認

### 影響範囲

- `src/analysis/ranking_judge.py` (Provenance 拡張)
- `src/analysis/ranking_judge_cache.py` (集計関数追加)
- 新規 `src/dashboard/views/09_observability.py`

---

## Issue 起票方法 (将来 gh CLI 導入後)

```bash
brew install gh
gh auth login

# 各 Section を別ファイルに分けて起票
gh issue create --repo ShunsukeHOSODA/kaori_kabu \
  --title "TRACKED_FUNDS CIK の実機検証" \
  --label "phase-6,data-quality,13f" \
  --body "$(sed -n '/^## Issue #1/,/^---$/p' .steering/20260512-claude-ranking-judge/issues-carryover.md)"
```

3 Issue 起票後、本ファイルに発行された Issue 番号を追記し、コード内の
`# TODO(Phase 6):` コメントを `# TODO(#42): TRACKED_FUNDS CIK 検証` 形式で更新する。
