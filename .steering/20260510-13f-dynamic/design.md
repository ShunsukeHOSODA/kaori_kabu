# 13F 動的化 設計書

**作業 ID**: `20260510-13f-dynamic`
**起点**: `.steering/20260509-atr-decision-log-handoff/handoff.md` (#4)
**目的**: 静的辞書 `src/data/famous_holdings.py` を **SEC EDGAR 13F-HR の動的データ**に置き換え、`03_thirteen_f.py` を完全実装する。

---

## 1. スコープ（Phase A+B+C 一括）

| Phase | 対象 | 内容 |
|---|---|---|
| **A** | `src/data/sec_edgar.py`（新規） | EDGAR REST API クライアント・XML パーサ・キャッシュ統合 |
| **B** | `src/data/famous_holdings.py`（書換） | EDGAR 由来データから動的に保有関係を導出。フォールバックに静的辞書 |
| **C** | `src/dashboard/views/03_thirteen_f.py`（実装） | プレースホルダー → 実 UI（保有テーブル / Q-over-Q diff / 集中度フィルタ） |

**実装方針**: SEC EDGAR 直叩き（`httpx` + `xml.etree.ElementTree`、外部 13F ライブラリなし）。既存 `eodhd.py` のパターンに完全準拠。

---

## 2. SEC EDGAR API 詳細

### 2.1 認証
- **API キー不要**。ただし `User-Agent` ヘッダで「会社名 + メール」を申告する義務あり（Fair Access Policy）
- 環境変数 `SEC_EDGAR_USER_AGENT`（既に `settings.py` 定義済）に `kaori_kabu personal-research 1usnavf8@gmail.com` 形式で格納
- 未設定時は `EDGARConfigError` で fail-fast

### 2.2 レート制限
- 公式上限: **10 req/sec**（SEC 公表）
- `settings.rate_limit_sec_edgar = 10` 既定
- 実装: 直前リクエスト時刻を記録し、次回呼び出し時に `1/rate` 秒未満なら `time.sleep`
- `httpx.Client` レベルでスレッドセーフ性は不要（Streamlit 単一プロセス前提）

### 2.3 エンドポイント

| 用途 | URL | 備考 |
|---|---|---|
| 提出書類一覧 | `https://data.sec.gov/submissions/CIK{padded10}.json` | 直近 1,000 件まで JSON |
| 過去ファイリング索引 | `https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_no_clean}/index.json` | アクセッション直下 |
| Information Table XML | `https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_no_clean}/{infotable_filename}` | `index.json` から `*.xml` 中で `infotable` を含む名前を抽出 |

`padded10` = 10 桁ゼロ埋め CIK（例: `0001067983`）。
`acc_no_clean` = アクセッション番号からハイフン除去（例: `0000950123-25-009999` → `000095012325009999`）。

### 2.4 13F-HR XML スキーマ（Information Table）

```xml
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable>
    <nameOfIssuer>APPLE INC</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>037833100</cusip>
    <value>15670000</value>           <!-- 単位: 整数 USD（2022Q3 SEC ルール改定後） -->
    <shrsOrPrnAmt>
      <sshPrnamt>905560000</sshPrnamt>  <!-- shares or principal amount -->
      <sshPrnamtType>SH</sshPrnamtType>  <!-- SH or PRN -->
    </shrsOrPrnAmt>
    <putCall>Put</putCall>            <!-- optional -->
    <investmentDiscretion>SOLE</investmentDiscretion>
    <votingAuthority>
      <Sole>905560000</Sole>
      <Shared>0</Shared>
      <None>0</None>
    </votingAuthority>
  </infoTable>
  ...
</informationTable>
```

**注意点**:
- `value` 単位は **2022Q3 以降は整数 USD**、それ以前は **千ドル単位**。`reportDate` 基準で分岐（`>= 2022-09-30` で USD、それ以外は thousands → ×1000）
- CUSIP 9 桁（先頭が銘柄ティッカーと無関係）
- `nameOfIssuer` は会社名で、ティッカー直結ではない（CUSIP → ティッカーの逆引きが必要だが今回は **issuer name + cusip 文字列マッチ**で簡易対応）

---

## 3. アーキテクチャ

### 3.1 ファイル構成

```
src/data/sec_edgar.py            (新規、~350 行想定)
tests/unit/data/test_sec_edgar.py (新規、~250 行想定)
tests/fixtures/sec_edgar/         (新規、合成/抜粋の sample データ)
  ├── berkshire_2025q4_submissions.json
  ├── berkshire_2025q4_index.json
  ├── berkshire_2025q4_infotable.xml
  └── pabrai_2025q4_infotable.xml
```

### 3.2 データフロー

```
get_latest_13f(cik="0001067983")
  ↓
  [1] ParquetCache.get(provider="SEC_EDGAR", key="13f_{cik}_latest", ttl=90d)
       └── HIT → DataFrame 返却（attrs に cache_hit=True 注入済み）
       └── MISS → 続行
  ↓
  [2] GET /submissions/CIK0001067983.json
       └── recent.form 配列から "13F-HR" の最初の要素を抽出
       └── accessionNumber / reportDate / primaryDocument 取得
  ↓
  [3] GET /Archives/edgar/data/{cik}/{acc_no_clean}/index.json
       └── item.name で "infotable" 含むファイル名を抽出
  ↓
  [4] GET /Archives/edgar/data/{cik}/{acc_no_clean}/{infotable.xml}
       └── ET.fromstring() で XML パース
       └── 全 <infoTable> を辞書 → list → DataFrame
  ↓
  [5] attach_provenance(df, source="SEC EDGAR", endpoint=..., params_hash=...)
  ↓
  [6] ParquetCache.set(provider="SEC_EDGAR", key=...)
  ↓
  return df
```

---

## 4. データモデル

### 4.1 DataFrame schema（13F holdings）

| カラム | 型 | 例 |
|---|---|---|
| `cik` | str | `"0001067983"` |
| `report_date` | pd.Timestamp | `2025-12-31` |
| `accession_no` | str | `"0000950123-25-009999"` |
| `name_of_issuer` | str | `"APPLE INC"` |
| `title_of_class` | str | `"COM"` |
| `cusip` | str | `"037833100"` |
| `value_usd` | int | `15_670_000_000`（2022Q3 以降の生値、それ以前は ×1000 補正済み）|
| `shares` | int | `905_560_000` |
| `share_type` | str | `"SH"` or `"PRN"` |
| `put_call` | str \| None | `None` / `"Put"` / `"Call"` |
| `voting_sole` | int | `905_560_000` |
| `voting_shared` | int | `0` |
| `voting_none` | int | `0` |

### 4.2 Provenance attrs（`df.attrs`）

```python
{
    "source": "SEC EDGAR",
    "fetched_at": datetime(2026, 5, 10, 12, 0, 0, tzinfo=UTC),
    "endpoint": "/Archives/edgar/data/1067983/.../infotable.xml",
    "params_hash": "ab12cd34ef567890",  # SHA256(CIK + acc_no)[:16]
    "cache_hit": False,
    "cache_age_sec": None,
}
```

### 4.3 Filing dataclass（補助、メタデータ専用）

```python
@dataclass(frozen=True)
class Filing:
    cik: str
    accession_no: str          # ハイフン入り元形式
    accession_no_clean: str    # ハイフン除去
    form: str                  # "13F-HR"
    filing_date: date
    report_date: date          # 四半期末日
    primary_document: str      # XML ファイル名
```

---

## 5. クラス設計

### 5.1 SECEdgarClient

```python
@dataclass(frozen=True)
class SECEdgarClient:
    user_agent: str                    # 必須、空なら EDGARConfigError
    cache: ParquetCache
    http_client: httpx.Client = field(default_factory=_make_default_http_client)
    rate_limit_per_sec: int = 10
    base_data_url: str = "https://data.sec.gov"
    base_archives_url: str = "https://www.sec.gov"

    def get_latest_13f(self, cik: str, *, cache_ttl_sec: int = 7_776_000) -> pd.DataFrame
    def get_13f_history(self, cik: str, *, limit: int = 4) -> list[pd.DataFrame]
    def list_filings(self, cik: str, *, form: str = "13F-HR", limit: int = 10) -> list[Filing]
    def fetch_information_table(self, cik: str, accession_no: str) -> pd.DataFrame

    # 内部メソッド
    def _get_submissions(self, cik: str) -> dict[str, Any]
    def _get_filing_index(self, cik: str, acc_no_clean: str) -> dict[str, Any]
    def _find_infotable_filename(self, index_json: dict) -> str | None
    def _parse_information_table(self, xml_bytes: bytes, *, report_date: date) -> pd.DataFrame
    def _normalize_cik(self, cik: str) -> str
    def _enforce_rate_limit(self) -> None
    def _request(self, url: str) -> httpx.Response
```

### 5.2 補助関数

```python
def normalize_cik(cik: str) -> str
    # "1067983" / "0001067983" / "CIK0001067983" → "0001067983"

def normalize_accession_no(acc: str) -> tuple[str, str]
    # "0000950123-25-009999" → ("0000950123-25-009999", "000095012325009999")

def parse_information_table(xml_bytes: bytes, *, report_date: date) -> pd.DataFrame
    # 名前空間ストリッピング → ET.iterfind → DataFrame
```

---

## 6. レート制限実装

```python
_last_request_at: float | None = field(default=None, init=False, repr=False)
# frozen dataclass で書き換えるため object.__setattr__ 経由

def _enforce_rate_limit(self) -> None:
    min_interval = 1.0 / self.rate_limit_per_sec  # 0.1 sec @ 10/sec
    if self._last_request_at is not None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
    object.__setattr__(self, "_last_request_at", time.monotonic())
```

---

## 7. エラーハンドリング

| 例外 | 発生条件 |
|---|---|
| `EDGARConfigError` | `user_agent` 空・無効 |
| `EDGARNotFoundError` | submissions JSON で 13F-HR 未提出 / index.json で infotable.xml 不在 |
| `EDGARAPIError` | HTTP 4xx/5xx（メッセージに User-Agent を含めない） |
| `EDGARParseError` | XML パース失敗 / 必須要素欠落 |

`_check_response` 同等のヘルパー実装（API トークンは無いが PII の `user_agent` をエラーに含めない）。

---

## 8. テスト戦略（TDD）

### 8.1 fixture XML（`tests/fixtures/sec_edgar/`）
- 実 SEC データから 5-10 行抜粋した最小 XML（パブリックドメイン）
- 名前空間 `informationtable` 付きと非付きの両方
- value 単位: 2022Q3 以降（USD）と以前（thousands）の両方

### 8.2 テストケース

| ケース | 確認事項 |
|---|---|
| `test_normalize_cik_*` | パディング・プレフィックス除去 |
| `test_normalize_accession_no_*` | ハイフン除去 |
| `test_parse_information_table_basic` | XML → DataFrame カラム正常 |
| `test_parse_information_table_thousands_units` | 旧 value（×1000 補正）|
| `test_parse_information_table_with_options` | put/call フィールド |
| `test_parse_information_table_namespace_handling` | xmlns 付き正常 |
| `test_parse_information_table_invalid_xml` | EDGARParseError |
| `test_get_latest_13f_cache_hit` | キャッシュ経路（HTTP 呼び出しなし）|
| `test_get_latest_13f_cache_miss` | submissions → index → infotable の 3 段呼び出し |
| `test_get_latest_13f_missing_user_agent` | EDGARConfigError |
| `test_get_latest_13f_no_13f_filings` | EDGARNotFoundError |
| `test_rate_limit_enforced` | `time.sleep` 呼び出しモニター |
| `test_provenance_attrs_set` | df.attrs に必須 6 キー |
| `test_provenance_round_trip_via_cache` | キャッシュ越しに保持 |

### 8.3 モック戦略
- `httpx.MockTransport` で URL ごとに固定レスポンス返却
- `tests/fixtures/sec_edgar/*.json` / `*.xml` をロードして bytes 返却
- 時刻 / `time.sleep` は `monkeypatch` で固定

カバレッジ目標: **85%+**（CLAUDE.md §12 / 80%+ ルール超え）

---

## 9. Phase B: famous_holdings.py 動的化

### 9.1 設計方針
- **API は維持**（`get_famous_owners` / `render_owner_badges` / `has_famous_owner`）— 既存テストを壊さない
- 内部実装を「静的辞書」→「EDGAR キャッシュ → 静的辞書フォールバック」に変更
- ファンド CIK → 投資家名のマップを定数化（5 ファンド）

```python
FUND_CIK_TO_INVESTOR = {
    "0001067983": "Buffett",   # Berkshire
    "0001173334": "Pabrai",
    "0001649339": "Burry",     # Scion
    "0001336528": "Ackman",    # Pershing Square
    "0001079114": "Einhorn",   # Greenlight
}
```

### 9.2 動的解決ロジック

```python
def get_famous_owners(ticker: str, exchange: str) -> frozenset[str]:
    # 1. 全 5 ファンドの最新 13F を取得（キャッシュ越しなのでネット呼び出し最小）
    # 2. nameOfIssuer / cusip と ticker をマッチング
    #    - ticker → issuer_name の単純テーブル（米国主要 100 銘柄、ハードコード）
    #    - cusip ベースのマッチが取れれば最優先
    # 3. ヒットしたファンドの投資家名を frozenset で返却
    # 4. EDGAR エラー / cache miss なら静的辞書フォールバック
```

**ティッカー → issuer name マッチング表**: `_KNOWN_TICKER_NAMES` 定数（米国上位 100 銘柄程度、初期投入は手動）。後の Phase で CUSIP master データ統合を検討。

### 9.3 既存テスト互換性
- `tests/unit/data/test_famous_holdings.py` の 全テストは **静的辞書フォールバック経路で同じ結果**を返す
- EDGAR cache が空（テスト環境）= 自動的にフォールバック発動

---

## 10. Phase C: 03_thirteen_f.py UI

### 10.1 ページ構造

```
[サイドバー]
  - ファンド選択（multiselect、5 ファンド）
  - 期間選択（latest / 直近 4 四半期）
  - 集中度フィルタ（≤5 銘柄チェックボックス）
  - 最低保有額フィルタ（USD slider）

[メイン]
  - タブ毎にファンド表示
    - サマリー: 総評価額、銘柄数、上位 5 銘柄円グラフ
    - 保有一覧: DataFrame（issuer / value / shares / weight）
    - 前期比 diff: 新規買い / 増持 / 減持 / 売却
  - 警告 expander（45 日遅延 / Long-only / 等）保持
```

### 10.2 集中度フィルタ
- パブライ Dhandho 哲学: "Few Bets, Big Bets" → ≤5 銘柄ファンドを優先表示
- Burry の小型集中ポートフォリオもこれで強調

### 10.3 Q-over-Q diff 計算
- `df_current.merge(df_previous, on="cusip", how="outer")` で結合
- `value_current - value_previous` の符号で 4 区分:
  - **新規買い**: 前期 NaN, 今期あり
  - **売却**: 前期あり, 今期 NaN
  - **増持**: 両期あり, value_diff > 5%
  - **減持**: 両期あり, value_diff < -5%

---

## 11. キャッシュ戦略

| 用途 | キー | TTL |
|---|---|---|
| Submissions JSON | `submissions_{cik}` | 24h（毎日チェック）|
| Filing index | `index_{cik}_{acc_no_clean}` | 90d（不変）|
| Information Table | `13f_{cik}_{report_date}` | 90d |

**注意**: Submissions JSON / Filing index は DataFrame ではなく dict なので、`eodhd.py` の `_read_fresh_json` パターンを再利用（ParquetCache では包めない）。

---

## 12. 実装順序（1 ファイル毎承認ゲート）

| ステップ | ファイル | TDD 状態 |
|---|---|---|
| 1 | `tests/fixtures/sec_edgar/*.xml`, `*.json` | RED 用 fixture |
| 2 | `tests/unit/data/test_sec_edgar.py` | RED |
| 3 | `src/data/sec_edgar.py` | GREEN |
| 4 | `src/data/famous_holdings.py` 書換 | 既存テスト緑維持 |
| 5 | `tests/unit/data/test_famous_holdings.py` 拡張 | EDGAR 経路カバー追加 |
| 6 | `src/dashboard/views/03_thirteen_f.py` 実装 | 手動検証（screenshot）|
| 7 | `.steering/20260510-13f-dynamic/handoff.md` | 完了引き継ぎ |

各ステップ完了ごとにユーザー承認を取り次に進む。

---

## 13. リスク・未解決事項

| リスク | 緩和策 |
|---|---|
| Burry / Einhorn が 13F-HR ではなく 13F-NT 提出（"Notice"、保有非開示） | `list_filings` で form 種別を確認、NT のみなら `EDGARNotFoundError` |
| CUSIP → ticker 変換が不完全 | Phase 1 は issuer name + ticker ハードコードマップ。CUSIP master は後 phase |
| value 単位の年代分岐ミス | `report_date >= 2022-09-30` で USD、それ以前 thousands と判定（境界テストケース必須） |
| User-Agent 漏洩 | エラーメッセージに含めない、ログレベル INFO 以下に出さない |
| 大型ファンド（Berkshire ~50 銘柄）の XML サイズ | 1 ファイル数 100KB レベル、メモリ問題なし |

---

## 14. 完了基準（Definition of Done）

- [ ] `pytest tests/unit/data/test_sec_edgar.py` 全件 GREEN
- [ ] `pytest tests/unit/data/test_famous_holdings.py` 全件 GREEN（既存 + 新規）
- [ ] `pytest --cov=src/data/sec_edgar.py` で 85%+
- [ ] `ruff check src/data/sec_edgar.py` 警告 0
- [ ] `streamlit run src/dashboard/app.py` で 13F タブが実データ表示（screenshot 取得）
- [ ] `git log` に Phase A / B / C 各 1 コミット（conventional commits）
- [ ] `handoff.md` 作成
