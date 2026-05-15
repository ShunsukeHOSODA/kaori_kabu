"""Polymarket Gamma API クライアントの単体テスト（CLAUDE.md §9.1 / §9.2 / §9.8）。

設計:
    予測市場（Polymarket）の確率値を取得し、マクロイベント（Fed 利上げ確率
    /景気後退確率/地政学リスク）の市場コンセンサスを LLM ランキング判断の
    入力にする。実取引は行わず参照のみ。

学術根拠:
    Wolfers & Zitzewitz 2004 "Prediction Markets"（予測市場の効率性）
    Manski 2006 "Interpreting the Predictions of Prediction Markets"

カバー範囲:
    - fetch_macro_probabilities: 複数トピック → {topic: Decimal} 取得
    - キャッシュヒット時の API 非呼び出し（CLAUDE.md §9.2 = 6h）
    - TTL 超過時の再 API call
    - 未知トピックの skip + 警告ログ
    - HTTP エラー → ValueError 変換
    - 空 topics → 空 dict
    - Provenance メタデータの記録（CLAUDE.md §9.8.1）
"""

from __future__ import annotations

import logging
import os
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest


def _mock_response(records: list[dict[str, Any]]) -> MagicMock:
    """Polymarket ``/markets`` レスポンスを模倣する MagicMock。"""
    response = MagicMock(spec=httpx.Response)
    response.is_success = True
    response.status_code = 200
    response.json.return_value = records
    return response


@pytest.fixture
def fed_market_response() -> MagicMock:
    return _mock_response(
        [
            {
                "id": "0xfed2026",
                "slug": "fed-rate-cut-2026",
                "question": "Will the Fed cut rates by EOY 2026?",
                "outcomePrices": ["0.62", "0.38"],
                "active": True,
            }
        ]
    )


@pytest.fixture
def recession_market_response() -> MagicMock:
    return _mock_response(
        [
            {
                "id": "0xrec2026",
                "slug": "us-recession-2026",
                "question": "US recession in 2026?",
                "outcomePrices": ["0.28", "0.72"],
                "active": True,
            }
        ]
    )


@pytest.mark.unit
class TestFetchMacroProbabilities:
    """マクロ予測市場から確率辞書を取得。"""

    def test_2件のトピックで_Decimal_dict_を返す(
        self,
        tmp_path: Path,
        fed_market_response: MagicMock,
        recession_market_response: MagicMock,
    ) -> None:
        from data.cache import ParquetCache
        from data.polymarket_client import fetch_macro_probabilities

        http_client = MagicMock(spec=httpx.Client)

        def get_side_effect(url: str, **kwargs: Any) -> MagicMock:
            params = kwargs.get("params", {})
            slug = params.get("slug", "")
            if "fed" in slug:
                return fed_market_response
            if "recession" in slug:
                return recession_market_response
            return _mock_response([])

        http_client.get.side_effect = get_side_effect
        cache = ParquetCache(base_dir=tmp_path)

        result = fetch_macro_probabilities(
            ["fed_rate_cut_2026", "us_recession_2026"],
            http_client=http_client,
            cache=cache,
        )

        assert isinstance(result, dict)
        assert "fed_rate_cut_2026" in result
        assert "us_recession_2026" in result
        # 戻り値は Decimal（CLAUDE.md §9.1）
        assert isinstance(result["fed_rate_cut_2026"], Decimal)
        assert isinstance(result["us_recession_2026"], Decimal)
        assert result["fed_rate_cut_2026"] == Decimal("0.62")
        assert result["us_recession_2026"] == Decimal("0.28")

    def test_キャッシュヒット時は_HTTP_call_されない(
        self, tmp_path: Path, fed_market_response: MagicMock
    ) -> None:
        from data.cache import ParquetCache
        from data.polymarket_client import fetch_macro_probabilities

        http_client = MagicMock(spec=httpx.Client)
        http_client.get.return_value = fed_market_response
        cache = ParquetCache(base_dir=tmp_path)

        # 1 回目: API 叩く
        fetch_macro_probabilities(
            ["fed_rate_cut_2026"], http_client=http_client, cache=cache
        )
        call_count_after_first = http_client.get.call_count

        # 2 回目: キャッシュヒットで API 叩かない
        result2 = fetch_macro_probabilities(
            ["fed_rate_cut_2026"], http_client=http_client, cache=cache
        )

        assert call_count_after_first == 1
        assert http_client.get.call_count == 1  # 増えていない
        assert result2["fed_rate_cut_2026"] == Decimal("0.62")

    def test_TTL超過なら_再_API_call(
        self, tmp_path: Path, fed_market_response: MagicMock
    ) -> None:
        """キャッシュファイル mtime を 7h 前に偽装 → 6h TTL 超過で再取得。"""
        from data.cache import ParquetCache
        from data.polymarket_client import fetch_macro_probabilities

        http_client = MagicMock(spec=httpx.Client)
        http_client.get.return_value = fed_market_response
        cache = ParquetCache(base_dir=tmp_path)

        # 1 回目で書き込み
        fetch_macro_probabilities(
            ["fed_rate_cut_2026"],
            http_client=http_client,
            cache=cache,
            cache_ttl_sec=6 * 3600,
        )
        assert http_client.get.call_count == 1

        # キャッシュファイルの mtime を 7 時間前にする
        provider_dir = tmp_path / "Polymarket"
        for parquet_file in provider_dir.glob("*.parquet"):
            old_time = parquet_file.stat().st_mtime - 7 * 3600
            os.utime(parquet_file, (old_time, old_time))

        # 2 回目: TTL 超過なので再 API call
        fetch_macro_probabilities(
            ["fed_rate_cut_2026"],
            http_client=http_client,
            cache=cache,
            cache_ttl_sec=6 * 3600,
        )

        assert http_client.get.call_count == 2

    def test_未知トピックは_skip_されて警告ログ(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        from data.cache import ParquetCache
        from data.polymarket_client import fetch_macro_probabilities

        http_client = MagicMock(spec=httpx.Client)
        cache = ParquetCache(base_dir=tmp_path)

        with caplog.at_level(logging.WARNING):
            result = fetch_macro_probabilities(
                ["totally_unknown_topic_xyz"],
                http_client=http_client,
                cache=cache,
            )

        assert "totally_unknown_topic_xyz" not in result
        assert result == {}
        # warning ログに未知トピック名が含まれる
        assert any(
            "totally_unknown_topic_xyz" in rec.message for rec in caplog.records
        )
        # API も呼ばれていない
        assert http_client.get.call_count == 0

    def test_HTTP_error_時は_ValueError(self, tmp_path: Path) -> None:
        from data.cache import ParquetCache
        from data.polymarket_client import fetch_macro_probabilities

        http_client = MagicMock(spec=httpx.Client)
        http_client.get.side_effect = httpx.HTTPError("connection refused")
        cache = ParquetCache(base_dir=tmp_path)

        with pytest.raises(ValueError):
            fetch_macro_probabilities(
                ["fed_rate_cut_2026"],
                http_client=http_client,
                cache=cache,
            )

    def test_空_topics_リストは_空_dict_を返す(self, tmp_path: Path) -> None:
        from data.cache import ParquetCache
        from data.polymarket_client import fetch_macro_probabilities

        http_client = MagicMock(spec=httpx.Client)
        cache = ParquetCache(base_dir=tmp_path)

        result = fetch_macro_probabilities(
            [], http_client=http_client, cache=cache
        )

        assert result == {}
        assert http_client.get.call_count == 0

    def test_Provenance_メタデータが_モジュール変数に記録される(
        self, tmp_path: Path, fed_market_response: MagicMock
    ) -> None:
        """戻り値は dict[str, Decimal] のため、Provenance は
        モジュール変数 ``_last_metadata`` で公開する（CLAUDE.md §9.8.1）。"""
        from data import polymarket_client
        from data.cache import ParquetCache
        from data.polymarket_client import fetch_macro_probabilities

        http_client = MagicMock(spec=httpx.Client)
        http_client.get.return_value = fed_market_response
        cache = ParquetCache(base_dir=tmp_path)

        fetch_macro_probabilities(
            ["fed_rate_cut_2026"], http_client=http_client, cache=cache
        )

        meta = polymarket_client._last_metadata
        assert meta["source"] == "Polymarket"
        assert "fetched_at" in meta
        assert meta["endpoint"] == "https://gamma-api.polymarket.com/markets"
        assert "params_hash" in meta
        # cache_hit は False（新規取得）
        assert meta["cache_hit"] is False
