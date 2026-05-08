"""ニュース取得クライアント (Tavily / Exa) の単体テスト（モック）。

学術根拠:
    Tetlock 2007 "Giving Content to Investor Sentiment"
    Loughran-McDonald 2011 (金融特化センチメント辞書)

設計方針:
    銘柄情報単独ではなく、マクロ + 地政学 (戦争/首脳発言/制裁) + 学術研究までを
    4 系統で束ねて投資判断のコンテキストとする。
    Tavily は速報ニュース、Exa は学術・深い調査向きで使い分ける。
    世界一の投資家（Buffett/Munger/Soros/Druckenmiller/Dalio/Pabrai/Burry/
    Ackman）の視座でレンズを差し込む拡張は ``src/analysis/investor_lenses.py``
    側で別レイヤーとして実装する。

カバー範囲（コア 4 系統）:
    - fetch_ticker_news: Tavily で銘柄ニュース取得
    - fetch_macro_news: Tavily でマクロ経済ニュース
    - fetch_geopolitical_news: Tavily で地政学（戦争・首脳発言・制裁）
    - fetch_research: Exa で学術論文・研究発表
    - gather_market_context: 4 系統を 1 つの MarketContext に束ねる
    - キャッシュ TTL（CLAUDE.md §9.2 = 1 時間）
    - Provenance 付与（CLAUDE.md §9.8）
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import httpx
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# 共通 fixture
# ---------------------------------------------------------------------------


def _tavily_mock_response(records: list[dict[str, Any]]) -> MagicMock:
    """Tavily ``/search`` のレスポンスを模倣する MagicMock を生成。"""
    response = MagicMock(spec=httpx.Response)
    response.is_success = True
    response.status_code = 200
    response.json.return_value = {
        "query": "AAPL earnings",
        "results": records,
    }
    return response


def _exa_mock_response(records: list[dict[str, Any]]) -> MagicMock:
    """Exa ``/search`` のレスポンスを模倣する MagicMock を生成。"""
    response = MagicMock(spec=httpx.Response)
    response.is_success = True
    response.status_code = 200
    response.json.return_value = {
        "results": records,
    }
    return response


@pytest.fixture
def tavily_ticker_response() -> MagicMock:
    return _tavily_mock_response(
        [
            {
                "title": "AAPL beats Q1 estimates",
                "url": "https://example.com/aapl-q1",
                "content": "Apple posted Q1 earnings of $X exceeding estimates...",
                "score": 0.92,
                "published_date": "2026-04-25",
            },
            {
                "title": "Apple AI investment ramps",
                "url": "https://example.com/aapl-ai",
                "content": "Apple announced new AI infrastructure...",
                "score": 0.85,
                "published_date": "2026-05-02",
            },
        ]
    )


@pytest.fixture
def tavily_geopolitical_response() -> MagicMock:
    return _tavily_mock_response(
        [
            {
                "title": "Trump signs executive order on tariffs",
                "url": "https://example.com/trump-tariff",
                "content": "President Trump announced 25% tariff on...",
                "score": 0.95,
                "published_date": "2026-05-08",
            },
        ]
    )


@pytest.fixture
def exa_research_response() -> MagicMock:
    return _exa_mock_response(
        [
            {
                "id": "abc-123",
                "title": "Mean reversion in equity returns: a meta-analysis",
                "url": "https://arxiv.org/abs/xxxx",
                "publishedDate": "2026-03-15",
                "score": 0.88,
                "text": "Abstract: Across 30 studies...",
            }
        ]
    )


# ---------------------------------------------------------------------------
# fetch_ticker_news
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFetchTickerNews:
    """Tavily で銘柄ニュース取得。

    DataFrame カラムは title / snippet / url / published_at / source_provider /
    relevance_score。published_at は tz-aware Timestamp で揃える。
    """

    def test_API1回叩いて_DataFrame返却(
        self, tmp_path: Path, tavily_ticker_response: MagicMock
    ) -> None:
        from data.cache import ParquetCache
        from data.news import NewsClient

        http_client = MagicMock(spec=httpx.Client)
        http_client.post.return_value = tavily_ticker_response

        cache = ParquetCache(base_dir=tmp_path)
        client = NewsClient(
            tavily_api_key="dummy_tavily",
            exa_api_key="dummy_exa",
            cache=cache,
            http_client=http_client,
        )

        df = client.fetch_ticker_news("AAPL", days=30, max_results=5)

        assert http_client.post.call_count == 1
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2
        assert {"title", "snippet", "url", "published_at", "source_provider"} <= set(
            df.columns
        )
        assert all(df["source_provider"] == "Tavily")

    def test_キャッシュヒット時_API呼び出しなし(
        self, tmp_path: Path, tavily_ticker_response: MagicMock
    ) -> None:
        from data.cache import ParquetCache
        from data.news import NewsClient

        http_client = MagicMock(spec=httpx.Client)
        http_client.post.return_value = tavily_ticker_response

        cache = ParquetCache(base_dir=tmp_path)
        client = NewsClient(
            tavily_api_key="dummy",
            exa_api_key="dummy",
            cache=cache,
            http_client=http_client,
        )

        client.fetch_ticker_news("AAPL")
        client.fetch_ticker_news("AAPL")

        # 2 回目はキャッシュヒットで API 呼び出し総数は 1 のまま
        assert http_client.post.call_count == 1

    def test_Provenance_attrs付与(
        self, tmp_path: Path, tavily_ticker_response: MagicMock
    ) -> None:
        """戻り DataFrame の attrs に source / fetched_at / endpoint / cache_hit。"""
        from data.cache import ParquetCache
        from data.news import NewsClient

        http_client = MagicMock(spec=httpx.Client)
        http_client.post.return_value = tavily_ticker_response

        cache = ParquetCache(base_dir=tmp_path)
        client = NewsClient(
            tavily_api_key="dummy",
            exa_api_key="dummy",
            cache=cache,
            http_client=http_client,
        )

        df = client.fetch_ticker_news("AAPL")

        assert df.attrs["source"] == "Tavily"
        assert df.attrs["cache_hit"] is False
        assert "fetched_at" in df.attrs
        assert "/search" in df.attrs["endpoint"]


# ---------------------------------------------------------------------------
# fetch_geopolitical_news
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFetchGeopoliticalNews:
    """戦争・首脳発言・制裁などの地政学ニュース。

    銘柄に直接関係しなくても株式市場全体に影響する情報を取得する。
    例: トランプ大統領の関税発言、ウクライナ情勢、中東情勢、Fed 議長発言。
    """

    def test_首脳発言クエリ_DataFrame返却(
        self, tmp_path: Path, tavily_geopolitical_response: MagicMock
    ) -> None:
        from data.cache import ParquetCache
        from data.news import NewsClient

        http_client = MagicMock(spec=httpx.Client)
        http_client.post.return_value = tavily_geopolitical_response

        cache = ParquetCache(base_dir=tmp_path)
        client = NewsClient(
            tavily_api_key="dummy",
            exa_api_key="dummy",
            cache=cache,
            http_client=http_client,
        )

        df = client.fetch_geopolitical_news("Trump tariff", days=14)

        assert len(df) == 1
        assert df.iloc[0]["title"].startswith("Trump")
        assert df.attrs["source"] == "Tavily"


# ---------------------------------------------------------------------------
# fetch_research (Exa)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFetchResearch:
    """Exa で学術論文・研究発表を取得。

    Tavily よりも深い記事・arxiv・SSRN・公的機関レポート等の取得が得意。
    """

    def test_Exaエンドポイント呼び出し(
        self, tmp_path: Path, exa_research_response: MagicMock
    ) -> None:
        from data.cache import ParquetCache
        from data.news import NewsClient

        http_client = MagicMock(spec=httpx.Client)
        http_client.post.return_value = exa_research_response

        cache = ParquetCache(base_dir=tmp_path)
        client = NewsClient(
            tavily_api_key="dummy",
            exa_api_key="dummy_exa",
            cache=cache,
            http_client=http_client,
        )

        df = client.fetch_research("mean reversion equity")

        assert len(df) == 1
        assert df.iloc[0]["title"].startswith("Mean reversion")
        assert df.attrs["source"] == "Exa"
        # Exa エンドポイントが呼ばれている
        called_url = http_client.post.call_args.args[0]
        assert "exa.ai" in called_url

    def test_既定で直近1年に時間制限_start_published_date付与(
        self, tmp_path: Path, exa_research_response: MagicMock
    ) -> None:
        """古い情報を拾わない方針（CLAUDE.md §9.3）— 既定で 1 年以内に限定。"""
        from data.cache import ParquetCache
        from data.news import NewsClient

        http_client = MagicMock(spec=httpx.Client)
        http_client.post.return_value = exa_research_response

        cache = ParquetCache(base_dir=tmp_path)
        client = NewsClient(
            tavily_api_key="dummy",
            exa_api_key="dummy",
            cache=cache,
            http_client=http_client,
        )
        client.fetch_research("equity factor")

        body = http_client.post.call_args.kwargs["json"]
        assert "start_published_date" in body
        # ISO 8601 (YYYY-MM-DD) 形式
        assert len(body["start_published_date"]) == 10

    def test_include_historical_True_で時間制限を解除(
        self, tmp_path: Path, exa_research_response: MagicMock
    ) -> None:
        """過去ソースが必要な場合（古典論文等）は include_historical=True で解除。"""
        from data.cache import ParquetCache
        from data.news import NewsClient

        http_client = MagicMock(spec=httpx.Client)
        http_client.post.return_value = exa_research_response

        cache = ParquetCache(base_dir=tmp_path)
        client = NewsClient(
            tavily_api_key="dummy",
            exa_api_key="dummy",
            cache=cache,
            http_client=http_client,
        )
        client.fetch_research(
            "Greenblatt Magic Formula 2010", include_historical=True
        )

        body = http_client.post.call_args.kwargs["json"]
        assert "start_published_date" not in body


# ---------------------------------------------------------------------------
# gather_market_context（4 系統統合）
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGatherMarketContext:
    """銘柄 + マクロ + 地政学 + 研究の 4 系統を束ねた MarketContext を返す。

    上位レイヤー（センチメント分析・Decision Log・LLM 判断）から呼ばれる
    エントリーポイント。世界一の投資家レンズ拡張は別 commit で
    ``src/analysis/investor_lenses.py`` 経由で被せる。
    """

    def test_4系統が揃う(
        self,
        tmp_path: Path,
        tavily_ticker_response: MagicMock,
        exa_research_response: MagicMock,
    ) -> None:
        from data.cache import ParquetCache
        from data.news import MarketContext, NewsClient

        http_client = MagicMock(spec=httpx.Client)

        def post_side_effect(url: str, **kwargs: Any) -> MagicMock:
            # Exa は exa.ai、それ以外は Tavily で振り分け
            if "exa.ai" in url:
                return exa_research_response
            return tavily_ticker_response

        http_client.post.side_effect = post_side_effect

        cache = ParquetCache(base_dir=tmp_path)
        client = NewsClient(
            tavily_api_key="dummy",
            exa_api_key="dummy",
            cache=cache,
            http_client=http_client,
        )

        context = client.gather_market_context("AAPL")

        assert isinstance(context, MarketContext)
        # 4 系統すべて DataFrame で揃う
        for df in (
            context.ticker_news,
            context.macro_news,
            context.geopolitical_news,
            context.research,
        ):
            assert isinstance(df, pd.DataFrame)
        assert context.fetched_at.tzinfo is not None
