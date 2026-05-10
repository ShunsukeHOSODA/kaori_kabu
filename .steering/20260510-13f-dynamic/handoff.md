# 引き継ぎ doc — 20260510-13f-dynamic 完了 → 次回 UI 実機検証 / 過去四半期 13F

**最終更新**: 2026-05-10
**前作業**: `.steering/20260509-atr-decision-log-handoff/handoff.md` (#4)
**完了範囲**: Phase A + B + C（13F 動的化フル実装）

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
| `src/data/sec_edgar.py` | 22 | 93% |
| `src/data/famous_holdings.py` | 23 (既存 13 + 新規 10) | 85% |
| **全体 unit test** | **306 件 PASS / 0 fail** | — |

未カバー行（sec_edgar.py 13 行）:
- `httpx.HTTPError` キャッチパス（接続エラー時）
- 一部のエッジケースガード（`text=None` 等の防御）
- 設定エラーメッセージ細部

---

## 4. 次回タスク候補（優先度順）

### 4.1 UI 実機検証（最優先、~30 分）
**前提**: `.env` の `SEC_EDGAR_USER_AGENT` 設定済（確認済 = `True`）

**手順**:
```bash
streamlit run src/dashboard/app.py
# → 13F タブを選択
# → 5 ファンドの保有が表示されることを確認
# → screenshot 取得
```

**期待結果**:
- Berkshire / Pabrai / Pershing Square: 保有一覧表示
- Scion (Burry) / Greenlight (Einhorn): 13F-NT の場合は「守秘要請」表示
- ⓘ Provenance で `cache_hit=False`（初回）→ 再表示で `cache_hit=True`
- スーパー集中フィルタ ON で Pabrai のみ表示（≤5 銘柄）

**潜在問題**:
- SEC EDGAR の `Host` ヘッダ自動推論が httpx で動くか（実機で要確認）
- `data.sec.gov` と `www.sec.gov` の switch
- 初回アクセスで 10 req/sec 制限を超過しないか

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
- [x] §12 テスト: pytest 306 件 PASS、新規ファイル 85-93% カバレッジ
