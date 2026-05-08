"""EODHD クライアントの単体テスト（モック）と統合テスト（実 API、slow）。

ユニットテストは httpx をモックしてオフライン実行可能。統合テストは
``pytest -m slow`` で明示実行（EODHD クォータを消費するため）。
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pandas as pd
import pytest


@pytest.fixture
def mock_eod_response() -> MagicMock:
    """EODHD ``/eod/{ticker}.{exchange}`` レスポンスのモック。"""
    response = MagicMock(spec=httpx.Response)
    response.json.return_value = [
        {
            "date": "2026-05-08",
            "open": 175.0,
            "high": 178.0,
            "low": 174.0,
            "close": 177.5,
            "adjusted_close": 177.5,
            "volume": 50_000_000,
        },
        {
            "date": "2026-05-09",
            "open": 177.5,
            "high": 180.0,
            "low": 176.0,
            "close": 179.0,
            "adjusted_close": 179.0,
            "volume": 48_000_000,
        },
    ]
    response.raise_for_status.return_value = None
    return response


@pytest.fixture
def mock_http_client(mock_eod_response: MagicMock) -> MagicMock:
    """httpx.Client モック。"""
    client = MagicMock(spec=httpx.Client)
    client.get.return_value = mock_eod_response
    return client


@pytest.mark.unit
class TestEODHDClientCacheHit:
    """キャッシュヒット時は API を叩かない。"""

    def test_キャッシュヒット時_APIは叩かれない(
        self, tmp_path: Path, mock_http_client: MagicMock
    ) -> None:
        from data._provenance import attach_provenance
        from data.cache import ParquetCache
        from data.eodhd import EODHDClient

        cache = ParquetCache(base_dir=tmp_path)
        cached_df = pd.DataFrame(
            {"date": ["2026-05-09"], "close": [177.5]}
        )
        attach_provenance(
            cached_df,
            source="EODHD",
            fetched_at=datetime(2026, 5, 9, tzinfo=timezone.utc),
            endpoint="/eod/AAPL.US",
            params_hash="abc",
        )
        cache.set(
            "EODHD",
            "eod_AAPL.US_2026-05-09_2026-05-09",
            cached_df,
        )

        client = EODHDClient(
            api_key="dummy",
            cache=cache,
            http_client=mock_http_client,
        )
        result = client.get_eod(
            "AAPL",
            from_date=date(2026, 5, 9),
            to_date=date(2026, 5, 9),
        )

        mock_http_client.get.assert_not_called()
        assert len(result) == 1
        assert result["close"].iloc[0] == 177.5
        assert result.attrs["cache_hit"] is True


@pytest.mark.unit
class TestEODHDClientCacheMiss:
    """キャッシュミス時は API を叩いて Provenance 付き DataFrame を返し、
    キャッシュに保存する。"""

    def test_API1回叩いて_DataFrame_と_Provenance_を返す(
        self, tmp_path: Path, mock_http_client: MagicMock
    ) -> None:
        from data.cache import ParquetCache
        from data.eodhd import EODHDClient

        cache = ParquetCache(base_dir=tmp_path)
        client = EODHDClient(
            api_key="dummy",
            cache=cache,
            http_client=mock_http_client,
        )

        result = client.get_eod(
            "AAPL",
            from_date=date(2026, 5, 8),
            to_date=date(2026, 5, 9),
        )

        # API は 1 回呼ばれた
        assert mock_http_client.get.call_count == 1
        # DataFrame の中身
        assert len(result) == 2
        assert "close" in result.columns
        # Provenance 付与
        assert result.attrs["source"] == "EODHD"
        assert result.attrs["endpoint"] == "/eod/AAPL.US"
        assert result.attrs["cache_hit"] is False
        assert "params_hash" in result.attrs

    def test_キャッシュに保存される(
        self, tmp_path: Path, mock_http_client: MagicMock
    ) -> None:
        from data.cache import ParquetCache
        from data.eodhd import EODHDClient

        cache = ParquetCache(base_dir=tmp_path)
        client = EODHDClient(
            api_key="dummy",
            cache=cache,
            http_client=mock_http_client,
        )

        client.get_eod(
            "AAPL",
            from_date=date(2026, 5, 8),
            to_date=date(2026, 5, 9),
        )

        # 同キーで再取得すると API を叩かずキャッシュから返る
        cached = cache.get(
            "EODHD",
            "eod_AAPL.US_2026-05-08_2026-05-09",
            ttl_sec=86400,
        )
        assert cached is not None
        assert len(cached) == 2


@pytest.mark.unit
class TestEODHDClientSecurity:
    """API トークンは params_hash に含めない（再現性 + セキュリティ）。"""

    def test_API_token_はparams_hashに含まれない(
        self, tmp_path: Path, mock_http_client: MagicMock
    ) -> None:
        """別の API トークンでも同じパラメータなら同じ params_hash。"""
        from data.cache import ParquetCache
        from data.eodhd import EODHDClient

        client1 = EODHDClient(
            api_key="KEY_AAA",
            cache=ParquetCache(base_dir=tmp_path / "c1"),
            http_client=mock_http_client,
        )
        client2 = EODHDClient(
            api_key="KEY_BBB",
            cache=ParquetCache(base_dir=tmp_path / "c2"),
            http_client=mock_http_client,
        )

        r1 = client1.get_eod(
            "AAPL", from_date=date(2026, 5, 9), to_date=date(2026, 5, 9)
        )
        r2 = client2.get_eod(
            "AAPL", from_date=date(2026, 5, 9), to_date=date(2026, 5, 9)
        )

        assert r1.attrs["params_hash"] == r2.attrs["params_hash"]


@pytest.fixture
def mock_fundamentals_response() -> MagicMock:
    """EODHD ``/fundamentals/{ticker}.{exchange}`` レスポンスのモック（合成 AAPL）。"""
    response = MagicMock(spec=httpx.Response)
    response.json.return_value = {
        "General": {
            "Code": "AAPL",
            "Type": "Common Stock",
            "Name": "Apple Inc",
            "Sector": "Technology",
            "Industry": "Consumer Electronics",
        },
        "Highlights": {
            "MarketCapitalization": 3_500_000_000_000,
            "EnterpriseValue": 3_600_000_000_000,
            "EBITDA": 130_000_000_000,
        },
        "Financials": {
            "Income_Statement": {
                "yearly": {
                    "2024-09-30": {"operatingIncome": 119_437_000_000},
                    "2023-09-30": {"operatingIncome": 114_301_000_000},
                }
            },
            "Balance_Sheet": {
                "yearly": {
                    "2024-09-30": {
                        "totalCurrentAssets": 152_987_000_000,
                        "totalCurrentLiabilities": 176_392_000_000,
                        "propertyPlantEquipment": 45_680_000_000,
                    },
                    "2023-09-30": {
                        "totalCurrentAssets": 143_566_000_000,
                        "totalCurrentLiabilities": 145_308_000_000,
                        "propertyPlantEquipment": 43_715_000_000,
                    },
                }
            },
        },
    }
    response.raise_for_status.return_value = None
    return response


@pytest.mark.unit
class TestGetFundamentals:
    """get_fundamentals: ファンダメンタルデータの取得 + キャッシュ。"""

    def test_キャッシュミス時_API1回_dict返却(
        self, tmp_path: Path, mock_fundamentals_response: MagicMock
    ) -> None:
        from data.cache import ParquetCache
        from data.eodhd import EODHDClient

        http_client = MagicMock(spec=httpx.Client)
        http_client.get.return_value = mock_fundamentals_response

        cache = ParquetCache(base_dir=tmp_path)
        client = EODHDClient(
            api_key="dummy", cache=cache, http_client=http_client
        )

        result = client.get_fundamentals("AAPL")

        assert http_client.get.call_count == 1
        assert isinstance(result, dict)
        assert result["General"]["Code"] == "AAPL"
        assert result["Highlights"]["EnterpriseValue"] == 3_600_000_000_000


@pytest.mark.unit
class TestExtractMagicFormulaRow:
    """ファンダ dict から Magic Formula 入力行を抽出。"""

    def test_必須フィールドが揃う場合_Decimal_行を返す(
        self, mock_fundamentals_response: MagicMock
    ) -> None:
        from data.eodhd import extract_magic_formula_row

        fundamentals = mock_fundamentals_response.json()
        row = extract_magic_formula_row(fundamentals, ticker="AAPL")

        assert row is not None
        assert row["ticker"] == "AAPL"
        # 最新年（2024-09-30）の値が選ばれる
        assert row["ebit"] == Decimal("119437000000")
        assert row["enterprise_value"] == Decimal("3600000000000")
        # NWC = 流動資産 - 流動負債 = 152,987,000,000 - 176,392,000,000 = -23,405,000,000
        assert row["net_working_capital"] == Decimal("-23405000000")
        assert row["net_fixed_assets"] == Decimal("45680000000")
        assert row["sector"] == "Technology"
        assert row["industry"] == "Consumer Electronics"
        assert row["market_cap"] == Decimal("3500000000000")

    def test_欠損フィールドあれば_None_返す(self) -> None:
        from data.eodhd import extract_magic_formula_row

        # Highlights.EnterpriseValue 欠損
        broken = {
            "General": {"Code": "X", "Sector": "X", "Industry": "X"},
            "Highlights": {"MarketCapitalization": 100},
            "Financials": {
                "Income_Statement": {
                    "yearly": {"2024-12-31": {"operatingIncome": 10}}
                },
                "Balance_Sheet": {
                    "yearly": {
                        "2024-12-31": {
                            "totalCurrentAssets": 50,
                            "totalCurrentLiabilities": 30,
                            "propertyPlantEquipment": 40,
                        }
                    }
                },
            },
        }

        row = extract_magic_formula_row(broken, ticker="X")

        assert row is None


@pytest.mark.unit
class TestBuildScreenerUniverse:
    """複数銘柄を Magic Formula 入力 DataFrame に統合。"""

    def test_3銘柄_統合(
        self, tmp_path: Path, mock_fundamentals_response: MagicMock
    ) -> None:
        from data.cache import ParquetCache
        from data.eodhd import EODHDClient

        http_client = MagicMock(spec=httpx.Client)
        # 3 回呼ばれてもすべて同じレスポンス（テスト簡略化）
        http_client.get.return_value = mock_fundamentals_response

        cache = ParquetCache(base_dir=tmp_path)
        client = EODHDClient(
            api_key="dummy", cache=cache, http_client=http_client
        )

        df = client.build_screener_universe(["AAPL", "MSFT", "GOOGL"])

        assert len(df) == 3
        assert set(df.columns) >= {
            "ticker",
            "ebit",
            "net_working_capital",
            "net_fixed_assets",
            "enterprise_value",
        }
        assert list(df["ticker"]) == ["AAPL", "MSFT", "GOOGL"]


@pytest.mark.unit
class TestEODHDClientErrorHandling:
    """API エラー時に API キーがエラーメッセージに漏洩しない。"""

    def test_HTTP403時_APIキーがエラーメッセージに含まれない(
        self, tmp_path: Path
    ) -> None:
        """403 Forbidden 時のエラーメッセージから api_key の値が漏れない。"""
        from data.cache import ParquetCache
        from data.eodhd import EODHDAPIError, EODHDClient

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.is_success = False
        mock_response.status_code = 403
        mock_response.reason_phrase = "Forbidden"
        mock_response.text = "Access denied"

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response

        cache = ParquetCache(base_dir=tmp_path)
        client = EODHDClient(
            api_key="SECRET_TOKEN_AAA",
            cache=cache,
            http_client=mock_client,
        )

        with pytest.raises(EODHDAPIError) as exc_info:
            client.get_fundamentals("AAPL")

        message = str(exc_info.value)
        # API キーが漏れていないこと
        assert "SECRET_TOKEN_AAA" not in message
        # ステータスコード自体は含まれること（デバッグのため）
        assert "403" in message


@pytest.mark.slow
class TestEODHDClientIntegration:
    """実 API 接続テスト（EODHD クォータ消費。``pytest -m slow`` で実行）。"""

    def test_実API_AAPL_過去30日_EOD取得(self, tmp_path: Path) -> None:
        from data.cache import ParquetCache
        from data.eodhd import EODHDClient

        api_key = os.environ.get("EODHD_API_KEY")
        if not api_key:
            pytest.skip("EODHD_API_KEY not set")

        cache = ParquetCache(base_dir=tmp_path)
        client = EODHDClient(api_key=api_key, cache=cache)

        to_d = date.today()
        from_d = to_d - timedelta(days=30)

        df = client.get_eod("AAPL", from_date=from_d, to_date=to_d)

        assert len(df) >= 15
        assert "close" in df.columns
        assert df["close"].iloc[0] > 0
        assert df.attrs["source"] == "EODHD"
        assert df.attrs["cache_hit"] is False

    def test_実API_AAPL_fundamentals取得_Magic_Formula_行抽出(
        self, tmp_path: Path
    ) -> None:
        from data.cache import ParquetCache
        from data.eodhd import EODHDClient, extract_magic_formula_row

        api_key = os.environ.get("EODHD_API_KEY")
        if not api_key:
            pytest.skip("EODHD_API_KEY not set")

        cache = ParquetCache(base_dir=tmp_path)
        client = EODHDClient(api_key=api_key, cache=cache)

        fund = client.get_fundamentals("AAPL")
        row = extract_magic_formula_row(fund, ticker="AAPL")

        # AAPL は実在の大型株なので必須フィールドが揃うはず
        assert row is not None
        assert row["ticker"] == "AAPL"
        assert row["ebit"] > 0
        assert row["enterprise_value"] > 0
        assert row["net_fixed_assets"] > 0
        assert row["sector"] == "Technology"
