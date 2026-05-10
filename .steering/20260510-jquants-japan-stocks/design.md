# 設計 doc — 20260510-jquants-japan-stocks

**目的**: J-Quants Light クライアントを実装し、`portfolio.csv` 内の日本株 (7203 等) の EOD 価格取得を可能にする。これにより `01_home.py` の「最新評価」ボタンで「一部銘柄の取得に失敗」エラーが消え、MVP β 完成に近づく。

**前作業**: `.steering/20260510-13f-dynamic/handoff.md` 完了 → 本セッションで Magic Formula 実機検証 → 01_home 実機検証で 7203.TO 404 検出 → 原因が「EODHD は日本株未サポート」と判明 → J-Quants Light 経路実装へ着手。

**重要前提**:
- CLAUDE.md §5「J-Quants Light = 日本株の正本（JPX 公式、当日データ）」と明記済み
- `.env` に `JQUANTS_REFRESH_TOKEN` / `JQUANTS_PLAN` / `RATE_LIMIT_JQUANTS` 配備済み
- `src/config/settings.py` に対応フィールドあり
- 既契約 1,650 円/月。**契約済みなのに使ってないのは純粋に損**

## 1. スコープ（最小実装）

### 含む
- `src/data/jquants.py` 新規実装（クライアント + 認証フロー + EOD daily_quotes）
- `src/portfolio/holdings.py` の `exchange == "JP"` 経路ディスパッチ追加
- `data/holdings/portfolio.csv` の `7203, TO` → `7203, JP` 正規化
- `01_home.py` の最新評価ロジックで日本株分岐
- TDD 12〜15 ケース

### 含まない（後送り）
- ファンダメンタル `/v1/fins/statements` 統合 → Phase 3.2 で Magic Formula 日本株対応時
- 配当・株主優待 → Phase 3.2
- 投資ユニット数取得 → 不要（保有数は portfolio.csv 管理）
- pagination_key 完全対応 → 1 銘柄 5 年程度なら 1 page で収まるため初期は最小実装

## 2. J-Quants API 仕様

### 認証フロー
```
POST /v1/token/auth_refresh?refreshtoken={refresh_token}
→ {"idToken": "..."}  # 24h 有効
```

### EOD 取得
```
GET /v1/prices/daily_quotes?code={4digit}&from={YYYYMMDD}&to={YYYYMMDD}
Authorization: Bearer {id_token}
→ {"daily_quotes": [...], "pagination_key": "..."}
```

### レスポンス（daily_quotes 1 行抜粋）
```json
{
  "Date": "2025-12-05",
  "Code": "72030",       // 5桁: 4桁証券コード + チェックデジット 0
  "Open": 2900.0,
  "High": 2950.0,
  "Low": 2890.0,
  "Close": 2913.0,
  "Volume": 75083900,
  "AdjustmentClose": 2913.0,
  "AdjustmentVolume": 75083900,
  "AdjustmentFactor": 1.0
}
```

### レート制限
- Light: 60 req/min（`.env` の `RATE_LIMIT_JQUANTS=60` と整合）
- 本クライアントは 1 req/sec 間隔で `_enforce_rate_limit()`

### ティッカー正規化
- API 入力は **4 桁証券コード**（`7203` / `7203.T` / `7203.JP` / `72030` を全て `7203` に正規化）
- レスポンス `Code` は **5 桁** だが、内部表現は 4 桁で統一

## 3. ファイル構造

```
src/data/jquants.py             — クライアント本体（~250 行想定）
tests/unit/data/test_jquants.py — TDD 15 ケース（~300 行）
src/portfolio/holdings.py       — exchange == "JP" 分岐（数行追加）
data/holdings/portfolio.csv     — 7203/TO → 7203/JP 1 行修正
src/dashboard/views/01_home.py  — 最新評価で日本株経路の呼び分け
```

## 4. クラス設計（EODHDClient パターン踏襲）

```python
@dataclass(frozen=True)
class JQuantsClient:
    refresh_token: str
    cache: ParquetCache
    rate_limit_per_min: int = 60
    base_url: str = "https://api.jquants.com"
    http_client: httpx.Client = field(default_factory=httpx.Client)
    _state: dict = field(default_factory=dict)  # id_token + 取得時刻

    def __post_init__(self):
        if not self.refresh_token:
            raise JQuantsConfigError(...)

    def get_eod(
        self,
        code: str,
        *,
        from_date: date,
        to_date: date,
        cache_ttl_sec: int = 86_400,
    ) -> pd.DataFrame: ...

    # 内部
    def _get_id_token(self) -> str: ...           # TTL 23h で再利用
    def _enforce_rate_limit(self) -> None: ...   # 1 req/sec
    def _request(...) -> dict: ...

# 純粋関数
def _normalize_code(code: str) -> str: ...       # 4 桁化
```

## 5. 例外階層

```python
class JQuantsConfigError(Exception): ...    # refresh_token 未設定等
class JQuantsAuthError(Exception): ...      # 401 / refresh_token 期限切れ
class JQuantsAPIError(Exception): ...       # 4xx / 5xx
class JQuantsNotFoundError(Exception): ...  # データ無し
```

## 6. Provenance（CLAUDE.md §9.8 必須）

DataFrame.attrs に必須 6 キー:
- `source = "J-Quants"`
- `fetched_at` = pd.Timestamp UTC
- `endpoint` = "/v1/prices/daily_quotes"
- `params_hash` = SHA256(public_params)
- `cache_hit` = bool
- `cache_age_sec` = int | None

## 7. キャッシュ戦略

- `cache_key = "eod_jp_{code}_{from}_{to}"`（米国 EODHD と衝突しないよう接頭辞 `jp_`）
- TTL: 24h（EOD は日次 1 回更新で足りる）
- `data/cache/JQUANTS/eod_jp_*.parquet`

## 8. TDD テスト計画（15 ケース）

```
TestNormalizeCode (5):
  - 4桁_そのまま
  - .T サフィックス除去
  - .JP サフィックス除去
  - 5桁チェックデジット除去
  - 空文字_ValueError

TestJQuantsClientConfig (1):
  - refresh_token未設定_ConfigError

TestJQuantsAuth (3):
  - auth_refresh_id_token取得
  - id_token_TTL内は再利用
  - 認証失敗_AuthError

TestGetEOD (6):
  - basic_OHLCV取得
  - キャッシュヒット時_API呼ばない
  - Provenance付与
  - 期間指定_from_to
  - 空レスポンス_空DataFrame
  - HTTPエラー_APIError
```

`httpx.MockTransport` でモック → 実機検証は最後にユーザーの refresh_token 更新後。

## 9. holdings.py ディスパッチ

```python
# 米国: EODHDClient.get_eod
# 日本: JQuantsClient.get_eod
# 実装は呼び出し側（01_home._fetch_latest_prices）で分岐
```

## 10. portfolio.csv 修正

```
ticker,exchange,shares,avg_cost_jpy,purchased_at,account_type
AAPL,US,10,25000,2025-01-15,NISA
7203,JP,100,2800,2024-12-01,特定    ← TO → JP に修正
```

## 11. 検証手順

1. `pytest tests/unit/data/test_jquants.py --no-cov -q` → 15 件 PASS
2. `pytest tests/unit/ --no-cov -m unit -q` → 既存 323 + 新規 15 = 338 件 PASS
3. ユーザーが refresh_token 更新後、smoke test:
   ```python
   client = JQuantsClient(refresh_token=settings.jquants_refresh_token, cache=...)
   df = client.get_eod("7203", from_date=date(2025,12,1), to_date=date(2025,12,5))
   assert df["Close"].iloc[-1] > 0
   ```
4. streamlit + playwright で `01_home` の最新評価ボタン → 7203 の評価額表示確認
5. スクショ証跡保存
