# 引き継ぎ doc — 20260510-13f-dynamic 完了 → 次回 過去四半期 13F / MVP 実装

**最終更新**: 2026-05-10（実機検証 + Donnelley 数値命名バグ fix 後）
**前作業**: `.steering/20260509-atr-decision-log-handoff/handoff.md` (#4)
**完了範囲**: Phase A + B + C（13F 動的化フル実装）+ **実機検証 + Donnelley fix**

---

## 1. 完了サマリー

### コミット履歴
| コミット | 内容 |
|---|---|
| `51a62ff` | Phase A: SEC EDGAR 13F-HR REST API クライアント (sec_edgar.py) |
| `5a20085` | Phase B: famous_holdings.py 動的解決 + 静的フォールバック |
| `ea5c4f1` | Phase C: 03_thirteen_f.py UI 実装 |

### Phase A: `src/data/sec_edgar.py` (新規)
- `SECEdgarClient` (httpx + xml.etree.ElementTree、frozen dataclass)
- 公開 API: `get_latest_13f(cik) → DataFrame`
- 内部 3 段フロー: submissions → filing index → infoTable XML
- 例外階層: `EDGARConfigError` / `EDGARNotFoundError` / `EDGARAPIError` / `EDGARParseError`
- 純粋関数: `normalize_cik` / `normalize_accession_no` / `parse_information_table`
- 2022Q3 SEC ルール改定対応 (`value` 単位境界 = `report_date >= 2022-09-30`)
- User-Agent 必須（PII 漏洩防止: エラーに含めない）
- 10 req/sec レート制限
- Provenance attrs 自動付与（CLAUDE.md §9.8）
- ParquetCache 統合（TTL 90 日）

**テスト**: 22 件 / カバレッジ 93%

### Phase B: `src/data/famous_holdings.py` (動的化)
- 後方互換 100%（既存 13 テストすべて緑、API シグネチャ維持 + `cache=` keyword-only 追加）
- 4 ファンド（Berkshire/Pabrai/Burry/Ackman）の CIK → 投資家名マップ
- 19 銘柄の TICKER → SEC issuer name 検索キー
- 動的解決優先 → 静的辞書フォールバック
- `_resolve_from_edgar_cache()`: 非 US / 不明銘柄 / cache miss → frozenset() で静的経路へ

**テスト**: 23 件（既存 13 + 新規 10）/ カバレッジ 85%

### Phase C: `src/dashboard/views/03_thirteen_f.py` (実 UI)
- プレースホルダー → 実データ表示（96 → 308 行）
- サマリーメトリクス + 上位 10 銘柄ドーナツチャート + 全銘柄テーブル
- スーパー集中ファンド (≤5 銘柄) フィルタ
- ⓘ Provenance 展開（出所開示）
- User-Agent 未設定時の親切なエラー表示
- @st.cache_resource (client) + @st.cache_data ttl=3600 (holdings) で 2 段キャッシュ

---

## 2. 設計判断記録

### 採用
| 判断 | 理由 |
|---|---|
| `requests` ではなく `httpx` | 既存 codebase 規約（eodhd.py / yfinance.py）と整合 |
| `xml.etree.ElementTree` | 標準ライブラリ、外部依存なし |
| frozen dataclass + `_state: dict` | 不変性 + レート制限のための最小可変状態 |
| issuer name **部分一致** | CUSIP master データ統合は次フェーズ送り |
| 4 投資家縛り（Einhorn 除外） | 既存テスト `test_全達人名が既知の_4_人` 互換性 |
| 静的辞書を保持 | テスト環境（cache 空）で fall-through、後方互換 |

### 後送り
- 過去四半期選択（quarter selectbox の「最新」以外）→ Phase 後段で `_find_filing_at_quarter()` 追加
- CUSIP master データ統合（FinanceDatabase 連携）
- Q-over-Q diff（前期比 新規/売却/増持/減持）
- 13F-HR/A（修正提出）の自動マージ

---

## 3. テストカバレッジサマリー

| ファイル | テスト件数 | カバレッジ |
|---|---|---|
| `src/data/sec_edgar.py` | 22 + 5 (Donnelley fix) = **27** | 93% |
| `src/data/famous_holdings.py` | 23 (既存 13 + 新規 10) | 85% |
| **全体 unit test** | **311 件 PASS / 0 fail**（306 + Donnelley 5 件） | — |

未カバー行（sec_edgar.py 13 行）:
- `httpx.HTTPError` キャッチパス（接続エラー時）
- 一部のエッジケースガード（`text=None` 等の防御）
- 設定エラーメッセージ細部

---

## 4. 次回タスク候補（優先度順）

### 4.1 UI 実機検証 ✅ 完了（2026-05-10、Step B + A 併用）

**Step B: smoke test (Python REPL)** — `/tmp/smoke_13f.py`（一時 scratch、非コミット）
- ✅ Berkshire の最新 13F-HR を取得（2025-12-31、110 銘柄）
- ✅ Provenance attrs（source/fetched_at/endpoint/params_hash/cache_hit/cache_age_sec）全付与
- ✅ 2 回目で `cache_hit=True`、ParquetCache 動作確認
- ⚠️ **発見されたバグ**: Berkshire Q4 2025 提出の InfoTable XML が
    Donnelley 採番の数値ファイル名 (`50240.xml`) で、`_find_infotable_filename`
    の `"infotable" 部分一致` だけだと取りこぼす → §8 で fix

**Step A: UI 実機検証 (streamlit + playwright MCP)**
- 起動: `uv run streamlit run src/dashboard/views/03_thirteen_f.py`（5 タブ
  redesign の制約により app.py 経由ではナビ非表示。view 単独起動が低侵襲）
- ✅ Berkshire タブ: 総評価額 **$274.16B** / 銘柄数 **110** /
  レポート期 **2025-12-31** / 上位 10 銘柄ドーナツチャート
  （Apple 25.6% / AMEX 23.2% / BAC 11.8% / Coca Cola 11.6% / Chevron 8.2%...）
- ✅ Pabrai タブ: 「ℹ️ 13F-HR 提出なし。守秘要請（13F-NT）の可能性があります。」
  フォールバックメッセージ正常表示
- ✅ スーパー集中フィルタ動作: Berkshire 110 → 「📦 銘柄数 110 > 5 のため
  スーパー集中フィルタで除外」、ON/OFF 切替で再表示
- ✅ ⓘ Provenance 展開で全 6 メタデータ JSON 表示:
  ```json
  {
    "source": "SEC EDGAR",
    "fetched_at": "2026-05-10 12:39:42.825713+00:00",
    "endpoint": "/Archives/edgar/data/1067983/000119312526054580/50240.xml",
    "params_hash": "66a7bd4c37290c54",
    "cache_hit": true,
    "cache_age_sec": 73
  }
  ```
  → endpoint の末尾 `50240.xml` が Donnelley 数値命名で動的解決された証跡

**スクリーンショット証跡**:
- `.playwright-mcp/13f-berkshire-verified.png`（Berkshire メイン画面）
- `.playwright-mcp/13f-provenance-verified.png`（Provenance JSON 展開）

**潜在問題（消化済）**:
- ✅ httpx の `Host` ヘッダ自動推論 — 問題なし（実機で submissions/Archives 両方成功）
- ✅ `data.sec.gov` ↔ `www.sec.gov` switch — `_get_submissions` / `_get_filing_index`
  の URL 組み立てで正しく振り分け
- ✅ 10 req/sec 制限 — 5 ファンド × 3 段呼び出し = 最大 15 req でも制限内、
  `_enforce_rate_limit` で間隔保証

### 4.2 過去四半期 13F 表示（~2 時間）
- `SECEdgarClient.get_13f_history(cik, limit=4)` メソッド追加
- 03_thirteen_f.py の quarter selectbox を実装に接続
- 前期比 diff 計算（design.md §10.3）

### 4.3 Phase 3.3 候補
- Magic Formula スクリーナー実装（`docs/product-requirements.md` MVP #1）
- Half-Kelly ポジションサイザー（MVP #4）
- Monte Carlo 確率分布チャート（MVP #3）

---

## 5. 既知の課題

### 5.1 7203.TO 404（前回引き継ぎから残存）
EODHD で `7203.TO` (トヨタ自動車 東京) が 404。原因調査未着手。

### 5.2 CUSIP マスタ未統合
現在の動的解決は `TICKER_TO_ISSUER_NAME` ハードコード 19 銘柄のみ。13F の CUSIP を Yahoo / FinanceDatabase の CUSIP master に逆引きする経路を追加すれば、ハードコード不要になる。

### 5.3 RUF002 警告
日本語 docstring の全角括弧 / × 記号で ruff RUF002 が大量警告。既存 codebase 全体（eodhd.py 等）で同じ状態。**プロジェクト規約として許容**だが、`pyproject.toml` で `RUF002, RUF003` を ignore に追加すれば消せる。

---

## 6. ファイル変更サマリー

| ファイル | 変更内容 |
|---|---|
| `src/data/sec_edgar.py` | **新規** 456 行 |
| `src/data/famous_holdings.py` | **書換** 88 → 218 行 |
| `src/dashboard/views/03_thirteen_f.py` | **書換** 96 → 308 行 |
| `tests/unit/data/test_sec_edgar.py` | **新規** 462 行 (22 件) |
| `tests/unit/data/test_famous_holdings.py` | **追加** 95 → 260 行 (+10 件) |
| `tests/fixtures/sec_edgar/*.{json,xml}` | **新規** 5 ファイル |
| `.steering/20260510-13f-dynamic/design.md` | **新規** 396 行 |
| `.steering/20260510-13f-dynamic/handoff.md` | **新規** (本ファイル) |

合計: 8 ファイル新規 / 3 ファイル書換、コミット 3 件、insertions ~2,000 行

---

## 7. CLAUDE.md 規約適合チェック

- [x] §6 出力先固定: `.steering/20260510-13f-dynamic/{design,handoff}.md`
- [x] §7 1 ファイル毎承認ゲート: Phase A → B → C 順次承認
- [x] §9.1 Decimal: 金額は int (USD)、比率は小数 → UI で % 化
- [x] §9.2 キャッシュ: `data/cache/SEC_EDGAR/13f_{cik}_latest.parquet`、TTL 90 日
- [x] §9.8 Provenance: source / fetched_at / endpoint / params_hash / cache_hit / cache_age_sec を全 DataFrame に付与
- [x] §11 安全装置: API キー埋め込みなし、User-Agent は `.env` のみ、PII 漏洩防止
- [x] §12 テスト: pytest **311 件 PASS**、新規ファイル 85-93% カバレッジ

---

## 8. Donnelley 数値命名 fix（実機検証で発見・修正）

### 8.1 症状

Step B (smoke test) で Berkshire の最新 13F-HR 取得が
`EDGARNotFoundError: InfoTable XML not found for 0001067983/000119312526054580`
で失敗。

### 8.2 ルート原因

`SECEdgarClient._find_infotable_filename` が `"infotable" in name.lower()` の
**部分一致** だけで XML を探していたが、Berkshire Q4 2025 の提出代理人
（Donnelley Financial）は **数値ファイル名 `50240.xml`** を採番していた。

実機の filing index 内訳:
```
0001193125-26-054580-index-headers.html
0001193125-26-054580-index.html
0001193125-26-054580.txt
50240.xml          ← InfoTable（"infotable" 文字列なし）
primary_doc.xml    ← 表紙
```

### 8.3 修正（`src/data/sec_edgar.py:413-462`）

`_find_infotable_filename` を **2 段判別** に拡張:

1. **Step 1**: `"infotable"` 部分一致（明示命名 = `form13fInfoTable.xml` 等）
2. **Step 2**: フォールバック — `primary_doc.xml` / `*-index.*` /
   `*-headers.*` を除外した残り `.xml`（13F-HR は通常 InfoTable と表紙の
   2 ファイルのみなので、表紙を除けば InfoTable）

Step 2 で誤って表紙を選んだ場合、`parse_information_table` の
ルート要素チェック（`informationTable` 必須）が `EDGARParseError` を
上げるため、サイレント失敗にはならない。

### 8.4 追加した unit test（5 件）

`tests/unit/data/test_sec_edgar.py` に `TestFindInfoTableFilename` クラスを追加:

| テスト名 | カバー内容 |
|---|---|
| `test_Step1_infotable部分一致が最優先` | 明示命名と Step 2 候補が併存しても Step 1 優先 |
| `test_Step2_Donnelley数値命名_primary_doc除外` | 実機 Berkshire 2026 Q4 と同形 |
| `test_Step2_index_headers系XMLは除外` | `*-index.xml` / `*-headers.xml` の誤検知防止 |
| `test_該当なし_None返却` | 該当 XML がない場合 |
| `test_directory欠損_None返却` | index_json が空・directory 欠損 |

### 8.5 検証

- `pytest tests/unit/data/test_sec_edgar.py --no-cov -m unit -q` → **27 件 PASS**
- `/tmp/smoke_13f.py` 実行 → Berkshire 110 銘柄取得成功、cache_hit ラウンドトリップ OK
- streamlit + playwright 実機検証 → §4.1 完了報告どおり全機能動作

### 8.6 後送り（次回検討）

- 13F-NT (守秘要請) を明示的に検出して UI 表示を分岐（現在は `EDGARNotFoundError`
  で「13F-HR 提出なし」と一括表示。`form == "13F-NT"` を `_find_latest_13fhr` で
  判定して別メッセージ「現四半期は守秘要請中」を出すと UX 向上）
- Pabrai が現在 13F-NT 状態の理由調査（AUM が $100M を割って提出義務消滅した
  可能性。CIK 確認 / 過去四半期で 13F-HR 取得テスト）
