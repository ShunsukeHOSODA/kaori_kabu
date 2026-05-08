"""EODHD クライアントの単体テスト（モック）と統合テスト（実 API、slow）。

ユニットテストは httpx をモックしてオフライン実行可能。統合テストは
``pytest -m slow`` で明示実行（EODHD クォータを消費するため）。
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
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

        assert len(df) >= 15  # 平日 ~21 日、最低 15 営業日
        assert "close" in df.columns
        assert df["close"].iloc[0] > 0
        assert df.attrs["source"] == "EODHD"
        assert df.attrs["cache_hit"] is False
