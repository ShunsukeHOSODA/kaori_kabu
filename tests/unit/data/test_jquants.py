"""J-Quants API v2 クライアントの単体テスト。

httpx をモックしてオフライン実行可能。統合テスト（実 API）は
:func:`pytest -m slow` で明示実行（J-Quants Light クォータ 60req/min を消費する）。

学術根拠 / 仕様:
    - J-Quants API v2: https://jpx-jquants.com/spec/migration-v1-v2
    - 認証: x-api-key ヘッダ（永続 API key、idToken ライフサイクル管理不要）
    - daily bars: GET /v2/equities/bars/daily?code=&from=&to=
    - レスポンス: {"data": [...], "pagination_key": "..."}
    - カラム名: O/H/L/C/Vo (短縮) → 本クライアントが Open/High/Low/Close/Volume に展開
    - レート制限: Light プラン 60 req/min

規約:
    - CLAUDE.md §9.1 数値は Decimal 型（OHLCV は float でも OK、UI 直前に Decimal 化）
    - CLAUDE.md §9.2 ParquetCache TTL=24h で日次 1 回取得
    - CLAUDE.md §9.8 Provenance 必須 6 キー（source/fetched_at/endpoint/
      params_hash/cache_hit/cache_age_sec）
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pandas as pd
import pytest


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def mock_daily_bars_response() -> MagicMock:
    """``GET /v2/equities/bars/daily`` レスポンスモック（7203 トヨタ 2 日分）。

    v2 仕様:
        - レスポンスキーは ``"data"``（v1 の ``"daily_quotes"`` から変更）
        - カラム名は短縮 ``O / H / L / C / Vo / Va``
        - ``Code`` は 5 桁（4 桁証券コード + チェックデジット 0）
    """
    response = MagicMock(spec=httpx.Response)
    response.status_code = 200
    response.json.return_value = {
        "data": [
            {
                "Date": "2025-12-01",
                "Code": "72030",
                "O": 2900.0,
                "H": 2950.0,
                "L": 2890.0,
                "C": 2913.0,
                "Vo": 75_083_900,
                "Va": 219_000_000_000,
                "AdjustmentFactor": 1.0,
                "AdjustmentClose": 2913.0,
            },
            {
                "Date": "2025-12-02",
                "Code": "72030",
                "O": 2913.0,
                "H": 2980.0,
                "L": 2905.0,
                "C": 2950.0,
                "Vo": 50_000_000,
                "Va": 147_500_000_000,
                "AdjustmentFactor": 1.0,
                "AdjustmentClose": 2950.0,
            },
        ],
        "pagination_key": None,
    }
    response.raise_for_status.return_value = None
    return response


@pytest.fixture
def mock_http_client(mock_daily_bars_response: MagicMock) -> MagicMock:
    """httpx.Client モック（v2 は API key 認証のみで idToken なし）。"""
    client = MagicMock(spec=httpx.Client)
    client.get.return_value = mock_daily_bars_response
    return client


# ===========================================================================
# TestNormalizeCode（純粋関数: 4 桁証券コード正規化）
# ===========================================================================


@pytest.mark.unit
class TestNormalizeCode:
    """``_normalize_code`` 純粋関数の挙動。

    J-Quants は API 入力に 4 桁証券コードを期待するが、ユーザーの入力
    （portfolio.csv の ``ticker`` 列）は ``7203`` / ``7203.T`` /
    ``7203.JP`` / ``72030`` (5 桁) 等が混在しうる。これらを全て 4 桁に
    正規化する。
    """

    def test_4桁そのまま(self) -> None:
        from data.jquants import _normalize_code

        assert _normalize_code("7203") == "7203"

    def test_T_サフィックス除去(self) -> None:
        from data.jquants import _normalize_code

        assert _normalize_code("7203.T") == "7203"

    def test_JP_サフィックス除去(self) -> None:
        from data.jquants import _normalize_code

        assert _normalize_code("7203.JP") == "7203"

    def test_5桁チェックデジット除去(self) -> None:
        """J-Quants レスポンスの 5 桁 Code（4桁+チェックデジット 0）→ 4 桁。"""
        from data.jquants import _normalize_code

        assert _normalize_code("72030") == "7203"

    def test_空文字_ValueError(self) -> None:
        from data.jquants import _normalize_code

        with pytest.raises(ValueError, match="証券コード"):
            _normalize_code("")


# ===========================================================================
# TestNormalizeV2Columns（純粋関数: v2 短縮カラム → 長名展開）
# ===========================================================================


@pytest.mark.unit
class TestNormalizeV2Columns:
    """``_normalize_v2_columns`` で v2 短縮カラムを長名に展開。

    既存呼び出し側 (01_home.py / 02_screener.py 等) は Open/High/Low/Close/Volume
    のカラム名を期待しているため、本展開で互換性を保つ。
    """

    def test_v2短縮カラム_長名に展開(self) -> None:
        from data.jquants import _normalize_v2_columns

        df = pd.DataFrame(
            {
                "Date": ["2025-12-01"],
                "Code": ["7203"],
                "O": [2900.0],
                "H": [2950.0],
                "L": [2890.0],
                "C": [2913.0],
                "Vo": [75_083_900],
            }
        )
        out = _normalize_v2_columns(df)
        assert {"Open", "High", "Low", "Close", "Volume"} <= set(out.columns)
        assert "O" not in out.columns

    def test_空DataFrame_そのまま返却(self) -> None:
        from data.jquants import _normalize_v2_columns

        out = _normalize_v2_columns(pd.DataFrame())
        assert out.empty


# ===========================================================================
# TestJQuantsClientConfig（設定検証）
# ===========================================================================


@pytest.mark.unit
class TestJQuantsClientConfig:
    """JQuantsClient 初期化時の設定検証。"""

    def test_api_key未設定_ConfigError(self, tmp_path: Path) -> None:
        from data.cache import ParquetCache
        from data.jquants import JQuantsClient, JQuantsConfigError

        with pytest.raises(
            JQuantsConfigError, match="JQUANTS_API_KEY|api_key"
        ):
            JQuantsClient(api_key="", cache=ParquetCache(base_dir=tmp_path))


# ===========================================================================
# TestGetEOD（日次 OHLCV 取得）
# ===========================================================================


@pytest.mark.unit
class TestGetEOD:
    """``get_eod`` E2E 動作確認。"""

    def test_basic_OHLCV取得(
        self, tmp_path: Path, mock_http_client: MagicMock
    ) -> None:
        from data.cache import ParquetCache
        from data.jquants import JQuantsClient

        client = JQuantsClient(
            api_key="dummy_v2_api_key",
            cache=ParquetCache(base_dir=tmp_path),
            http_client=mock_http_client,
            rate_limit_per_min=600,
        )

        df = client.get_eod(
            "7203",
            from_date=date(2025, 12, 1),
            to_date=date(2025, 12, 2),
        )

        # 既存呼び出し側互換の長名カラムが存在
        assert {"Date", "Open", "High", "Low", "Close", "Volume"} <= set(
            df.columns
        )
        assert len(df) == 2
        # ティッカー 4 桁正規化
        assert all(df["Code"].astype(str) == "7203")
        # Close 値の正確性（v2 では C → Close に展開済み）
        assert float(df["Close"].iloc[0]) == 2913.0
        assert float(df["Close"].iloc[1]) == 2950.0

    def test_x_api_key_ヘッダで送信(
        self, tmp_path: Path, mock_http_client: MagicMock
    ) -> None:
        """v2 認証は x-api-key ヘッダ。Authorization Bearer ではない。"""
        from data.cache import ParquetCache
        from data.jquants import JQuantsClient

        client = JQuantsClient(
            api_key="dummy_v2_api_key",
            cache=ParquetCache(base_dir=tmp_path),
            http_client=mock_http_client,
            rate_limit_per_min=600,
        )

        client.get_eod(
            "7203",
            from_date=date(2025, 12, 1),
            to_date=date(2025, 12, 2),
        )

        eod_calls = mock_http_client.get.call_args_list
        assert len(eod_calls) == 1
        headers = eod_calls[0].kwargs.get("headers", {})
        assert headers.get("x-api-key") == "dummy_v2_api_key"
        # idToken / Bearer 認証は使われない
        assert "Authorization" not in headers

    def test_キャッシュヒット時_APIは叩かれない(
        self, tmp_path: Path, mock_http_client: MagicMock
    ) -> None:
        from data._provenance import attach_provenance
        from data.cache import ParquetCache
        from data.jquants import JQuantsClient

        cache = ParquetCache(base_dir=tmp_path)
        cached_df = pd.DataFrame(
            {"Date": ["2025-12-01"], "Code": ["7203"], "Close": [2913.0]}
        )
        attach_provenance(
            cached_df,
            source="J-Quants",
            fetched_at=datetime(2025, 12, 1, tzinfo=timezone.utc),
            endpoint="/v2/equities/bars/daily",
            params_hash="abc",
        )
        cache.set(
            "JQUANTS",
            "eod_jp_7203_2025-12-01_2025-12-01",
            cached_df,
        )

        client = JQuantsClient(
            api_key="dummy_v2_api_key",
            cache=cache,
            http_client=mock_http_client,
            rate_limit_per_min=600,
        )

        df = client.get_eod(
            "7203",
            from_date=date(2025, 12, 1),
            to_date=date(2025, 12, 1),
        )

        mock_http_client.get.assert_not_called()
        assert df.attrs["cache_hit"] is True

    def test_Provenance付与(
        self, tmp_path: Path, mock_http_client: MagicMock
    ) -> None:
        from data._provenance import REQUIRED_PROVENANCE_KEYS
        from data.cache import ParquetCache
        from data.jquants import JQuantsClient

        client = JQuantsClient(
            api_key="dummy_v2_api_key",
            cache=ParquetCache(base_dir=tmp_path),
            http_client=mock_http_client,
            rate_limit_per_min=600,
        )

        df = client.get_eod(
            "7203",
            from_date=date(2025, 12, 1),
            to_date=date(2025, 12, 2),
        )

        for key in REQUIRED_PROVENANCE_KEYS:
            assert key in df.attrs, f"missing provenance key: {key}"
        assert df.attrs["source"] == "J-Quants"
        # v2 エンドポイント
        assert df.attrs["endpoint"].startswith("/v2/equities/bars/daily")
        assert df.attrs["cache_hit"] is False

    def test_期間指定_from_to_API正しいquery(
        self, tmp_path: Path, mock_http_client: MagicMock
    ) -> None:
        from data.cache import ParquetCache
        from data.jquants import JQuantsClient

        client = JQuantsClient(
            api_key="dummy_v2_api_key",
            cache=ParquetCache(base_dir=tmp_path),
            http_client=mock_http_client,
            rate_limit_per_min=600,
        )

        client.get_eod(
            "7203",
            from_date=date(2025, 11, 1),
            to_date=date(2025, 12, 31),
        )

        eod_calls = mock_http_client.get.call_args_list
        assert len(eod_calls) == 1
        params = eod_calls[0].kwargs.get("params", {})
        assert params.get("code") == "7203"
        assert params.get("from") == "2025-11-01"
        assert params.get("to") == "2025-12-31"

    def test_空レスポンス_空DataFrame返却(self, tmp_path: Path) -> None:
        """v2 ``data`` が空配列の場合（休場日のみ等）も DataFrame を返す。"""
        from data.cache import ParquetCache
        from data.jquants import JQuantsClient

        empty_response = MagicMock(spec=httpx.Response)
        empty_response.status_code = 200
        empty_response.json.return_value = {
            "data": [],
            "pagination_key": None,
        }
        empty_response.raise_for_status.return_value = None

        client_mock = MagicMock(spec=httpx.Client)
        client_mock.get.return_value = empty_response

        client = JQuantsClient(
            api_key="dummy_v2_api_key",
            cache=ParquetCache(base_dir=tmp_path),
            http_client=client_mock,
            rate_limit_per_min=600,
        )

        df = client.get_eod(
            "9999",
            from_date=date(2025, 12, 1),
            to_date=date(2025, 12, 1),
        )

        assert df.empty
        assert df.attrs.get("source") == "J-Quants"

    def test_認証エラー_AuthError(self, tmp_path: Path) -> None:
        """API key が無効な場合、JQuantsAuthError を上げる（401 / 403）。"""
        from data.cache import ParquetCache
        from data.jquants import JQuantsAuthError, JQuantsClient

        bad_response = MagicMock(spec=httpx.Response)
        bad_response.status_code = 401
        bad_response.json.return_value = {
            "message": "invalid api key"
        }

        client_mock = MagicMock(spec=httpx.Client)
        client_mock.get.return_value = bad_response

        client = JQuantsClient(
            api_key="invalid_key",
            cache=ParquetCache(base_dir=tmp_path),
            http_client=client_mock,
            rate_limit_per_min=600,
        )

        with pytest.raises(JQuantsAuthError, match="認証失敗|invalid|401"):
            client.get_eod(
                "7203",
                from_date=date(2025, 12, 1),
                to_date=date(2025, 12, 1),
            )

    def test_HTTPエラー_APIError(self, tmp_path: Path) -> None:
        """daily bars が 500 等のサーバエラー時、JQuantsAPIError を上げる。"""
        from data.cache import ParquetCache
        from data.jquants import JQuantsAPIError, JQuantsClient

        error_response = MagicMock(spec=httpx.Response)
        error_response.status_code = 500
        error_response.json.return_value = {"message": "internal server error"}

        client_mock = MagicMock(spec=httpx.Client)
        client_mock.get.return_value = error_response

        client = JQuantsClient(
            api_key="dummy_v2_api_key",
            cache=ParquetCache(base_dir=tmp_path),
            http_client=client_mock,
            rate_limit_per_min=600,
        )

        with pytest.raises(JQuantsAPIError, match="500|internal"):
            client.get_eod(
                "7203",
                from_date=date(2025, 12, 1),
                to_date=date(2025, 12, 1),
            )


# ===========================================================================
# OHLC 変換ヘルパー
# ===========================================================================
#
# J-Quants v2 は OHLC を大文字 (Open/High/Low/Close) で返すが、
# 既存の下流レイヤー（src/strategies/atr_stop.py の calculate_atr,
# src/analysis/risk_metrics.py の compute_portfolio_returns）は EODHD 互換の
# 小文字 (high/low/close) を期待する。本ヘルパー群はその差分を吸収する
# 純粋関数で、リスク指標経路 / ATR 経路の両方で再利用される。


@pytest.mark.unit
class TestExtractCloseSeries:
    """``extract_close_series`` — リスク指標経路用の Close 系列抽出。"""

    def test_基本ケース_Date_Close_からSeries(self) -> None:
        """``Date`` + ``Close`` を持つ DF → ``pd.Series(close, index=Datetime)``。"""
        from data.jquants import extract_close_series

        df = pd.DataFrame(
            {
                "Date": ["2025-12-01", "2025-12-02", "2025-12-03"],
                "Close": [2913.0, 2950.0, 2920.0],
            }
        )
        series = extract_close_series(df, ticker_name="7203")

        assert isinstance(series, pd.Series)
        assert series.name == "7203"
        assert isinstance(series.index, pd.DatetimeIndex)
        assert len(series) == 3
        assert series.iloc[0] == pytest.approx(2913.0)
        assert series.iloc[-1] == pytest.approx(2920.0)
        # dtype は float（risk_metrics の pct_change が float を期待）
        assert series.dtype == float

    def test_空DF_空Series(self) -> None:
        """空 DF → 空 Series（name のみ付与）。"""
        from data.jquants import extract_close_series

        df = pd.DataFrame(columns=["Date", "Close"])
        series = extract_close_series(df, ticker_name="7203")

        assert isinstance(series, pd.Series)
        assert series.name == "7203"
        assert len(series) == 0

    def test_必須カラム欠落_ValueError(self) -> None:
        """``Date`` か ``Close`` のいずれかが欠落 → ``ValueError``。

        下流での silent NaN 伝播を防ぐためフェイルファスト。
        """
        from data.jquants import extract_close_series

        df_no_close = pd.DataFrame({"Date": ["2025-12-01"], "Open": [2900.0]})
        with pytest.raises(ValueError, match="Close|カラム"):
            extract_close_series(df_no_close, ticker_name="7203")

        df_no_date = pd.DataFrame({"Close": [2913.0]})
        with pytest.raises(ValueError, match="Date|カラム"):
            extract_close_series(df_no_date, ticker_name="7203")


@pytest.mark.unit
class TestExtractOhlcLowercase:
    """``extract_ohlc_lowercase`` — ATR 経路用の OHLC 小文字化。"""

    def test_基本ケース_HighLowClose_を小文字化(self) -> None:
        """``High/Low/Close`` → ``high/low/close``。値は不変。"""
        from data.jquants import extract_ohlc_lowercase

        df = pd.DataFrame(
            {
                "Date": ["2025-12-01", "2025-12-02"],
                "Open": [2900.0, 2913.0],
                "High": [2950.0, 2960.0],
                "Low": [2890.0, 2905.0],
                "Close": [2913.0, 2950.0],
                "Volume": [75_000_000, 60_000_000],
            }
        )
        result = extract_ohlc_lowercase(df)

        # ATR 関数が必要とする 3 カラムが小文字で揃う
        assert "high" in result.columns
        assert "low" in result.columns
        assert "close" in result.columns
        # 値は完全一致
        assert result["high"].iloc[0] == pytest.approx(2950.0)
        assert result["low"].iloc[0] == pytest.approx(2890.0)
        assert result["close"].iloc[1] == pytest.approx(2950.0)
        # 行数は不変
        assert len(result) == 2

    def test_必須カラム欠落_ValueError(self) -> None:
        """``High/Low/Close`` のいずれかが欠落 → ``ValueError``（フェイルファスト）。"""
        from data.jquants import extract_ohlc_lowercase

        df = pd.DataFrame(
            {
                "Date": ["2025-12-01"],
                "High": [2950.0],
                "Low": [2890.0],
                # Close が欠落
            }
        )
        with pytest.raises(ValueError, match="Close|カラム"):
            extract_ohlc_lowercase(df)

    def test_既存の小文字カラムがあっても上書きしない(self) -> None:
        """既に ``high/low/close`` が小文字で存在する DF はそのまま返す。

        EODHD（小文字）の DF と J-Quants（大文字）の DF を同じ後続ロジックに
        流せるようにする（idempotent）。
        """
        from data.jquants import extract_ohlc_lowercase

        df = pd.DataFrame(
            {
                "high": [100.0, 105.0],
                "low": [95.0, 98.0],
                "close": [98.0, 103.0],
            }
        )
        result = extract_ohlc_lowercase(df)
        assert result["high"].iloc[0] == pytest.approx(100.0)
        assert result["close"].iloc[1] == pytest.approx(103.0)
        assert len(result) == 2
