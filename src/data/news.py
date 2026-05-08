"""ニュース取得クライアント（Tavily / Exa）— CLAUDE.md §9.2 / §9.8 準拠。

設計:
    - **Tavily**: 速報・銘柄・マクロ・地政学（戦争 / 首脳発言 / 制裁 / 選挙）
      ニュースに強い ``/search`` エンドポイント。``topic="news"`` + ``days``
      指定で時間制約付き検索。
    - **Exa**: 学術論文・arxiv・SSRN・公的機関レポートなど深い調査向けの
      neural search。``contents.text`` で全文も取得可能。

世界一の投資家視座の拡張は ``src/analysis/investor_lenses.py``（次コミット）
で別レイヤーとして提供する。本モジュールはニュース取得の基盤を成す。

学術根拠:
    Tetlock 2007 "Giving Content to Investor Sentiment"
    Loughran-McDonald 2011 (金融特化センチメント辞書)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Final

import httpx
import pandas as pd

from ._provenance import attach_provenance
from .cache import ParquetCache

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

TAVILY_BASE_URL: Final[str] = "https://api.tavily.com"
EXA_BASE_URL: Final[str] = "https://api.exa.ai"
TAVILY_PROVIDER: Final[str] = "Tavily"
EXA_PROVIDER: Final[str] = "Exa"

DEFAULT_NEWS_TTL_SEC: Final[int] = 3_600  # 1h（CLAUDE.md §9.2）
DEFAULT_TICKER_DAYS: Final[int] = 30
DEFAULT_MACRO_DAYS: Final[int] = 7
DEFAULT_GEOPOLITICAL_DAYS: Final[int] = 14
DEFAULT_MAX_RESULTS: Final[int] = 10
DEFAULT_RESEARCH_RESULTS: Final[int] = 5
DEFAULT_RESEARCH_RECENCY_DAYS: Final[int] = 365
"""Exa 研究検索の既定 recency 窓（過去 1 年）。

『古い情報を拾わない』方針（CLAUDE.md §9.3）に基づき、研究も既定で
直近 1 年に制限する。長期バックテスト用に過去 30 年論文を取りたい
場合は :meth:`NewsClient.fetch_research` の ``include_historical=True``
で recency 制限を無効化できる。
"""

# 既定マクロクエリ — Fed / インフレ / 雇用統計を一括カバー
DEFAULT_MACRO_QUERY: Final[str] = (
    "Federal Reserve FOMC interest rate inflation CPI employment"
)
# 既定地政学クエリ — トランプ関税・ウクライナ・中東・対中関係
DEFAULT_GEOPOLITICAL_QUERY: Final[str] = (
    "Trump tariff China sanctions Ukraine war Middle East geopolitics"
)


class NewsAPIError(Exception):
    """ニュース API のエラー。API キーをメッセージに含めない。"""


# ---------------------------------------------------------------------------
# データクラス
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MarketContext:
    """銘柄 + マクロ + 地政学 + 研究の 4 系統を束ねたコンテキスト。

    上位レイヤー（センチメント分析・Decision Log・LLM 判断）から呼ばれる
    エントリーポイント。各 DataFrame は :class:`NewsClient` の単一系統メソッド
    と同じスキーマを持つ。
    """

    ticker: str
    ticker_news: pd.DataFrame
    macro_news: pd.DataFrame
    geopolitical_news: pd.DataFrame
    research: pd.DataFrame
    fetched_at: datetime


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------


def _params_hash(params: dict[str, Any]) -> str:
    """リクエストパラメータの SHA256（先頭 16 文字）。再現性確認用。"""
    serialized = json.dumps(params, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


def _make_default_http_client() -> httpx.Client:
    """既定の httpx.Client（タイムアウト 30 秒、リダイレクト追従）。"""
    return httpx.Client(timeout=30.0, follow_redirects=True)


def _check_response(response: httpx.Response, *, endpoint: str) -> None:
    """API キーを含まない安全なエラー化。"""
    if response.is_success:
        return
    body_preview = (response.text or "")[:200]
    raise NewsAPIError(
        f"News API {response.status_code} {response.reason_phrase} "
        f"for {endpoint}: {body_preview}"
    )


def _to_utc_timestamp(value: str | None) -> pd.Timestamp | None:
    """日付文字列を tz-aware UTC ``Timestamp`` に正規化。"""
    if not value:
        return None
    try:
        ts = pd.Timestamp(value)
    except (ValueError, TypeError):
        return None
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return ts


def _normalize_tavily_results(records: list[dict[str, Any]]) -> pd.DataFrame:
    """Tavily ``results`` 配列 → 統一スキーマ DataFrame。

    Tavily の各レコードは ``title``/``url``/``content``/``score``/
    ``published_date`` を含む。
    """
    rows = [
        {
            "title": r.get("title", ""),
            "snippet": r.get("content", ""),
            "url": r.get("url", ""),
            "published_at": _to_utc_timestamp(r.get("published_date")),
            "source_provider": TAVILY_PROVIDER,
            "relevance_score": float(r.get("score") or 0.0),
        }
        for r in records
    ]
    return pd.DataFrame(rows)


def _normalize_exa_results(records: list[dict[str, Any]]) -> pd.DataFrame:
    """Exa ``results`` 配列 → 統一スキーマ DataFrame。

    Exa の各レコードは ``title``/``url``/``text``/``publishedDate``/``score``
    を含む（``contents.text=True`` 時のみ ``text``）。
    """
    rows = [
        {
            "title": r.get("title", ""),
            "snippet": r.get("text", "") or r.get("summary", ""),
            "url": r.get("url", ""),
            "published_at": _to_utc_timestamp(r.get("publishedDate")),
            "source_provider": EXA_PROVIDER,
            "relevance_score": float(r.get("score") or 0.0),
        }
        for r in records
    ]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# クライアント本体
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NewsClient:
    """Tavily + Exa 統合ニュース取得クライアント。

    キャッシュ TTL は 1 時間（CLAUDE.md §9.2）。同一クエリ + 同一日時の重複
    取得を防ぎ、Tavily の 1000 req/月無料枠を保護する。

    Args:
        tavily_api_key: Tavily API key（``.env`` の ``TAVILY_API_KEY``）
        exa_api_key: Exa API key（``.env`` の ``EXA_API_KEY``）
        cache: Parquet TTL キャッシュ（既存 :class:`ParquetCache` を流用）
        http_client: httpx.Client（テスト時はモック注入）
    """

    tavily_api_key: str
    exa_api_key: str
    cache: ParquetCache
    http_client: httpx.Client = field(default_factory=_make_default_http_client)
    tavily_base_url: str = TAVILY_BASE_URL
    exa_base_url: str = EXA_BASE_URL

    # ----- Tavily 系 ------------------------------------------------------

    def fetch_ticker_news(
        self,
        ticker: str,
        *,
        days: int = DEFAULT_TICKER_DAYS,
        max_results: int = DEFAULT_MAX_RESULTS,
        cache_ttl_sec: int = DEFAULT_NEWS_TTL_SEC,
    ) -> pd.DataFrame:
        """銘柄ニュース取得（決算・指標・経営発表）。"""
        return self._tavily_search(
            query=f"{ticker} stock earnings news",
            cache_key_prefix=f"ticker_{ticker}",
            days=days,
            max_results=max_results,
            cache_ttl_sec=cache_ttl_sec,
        )

    def fetch_macro_news(
        self,
        topic: str = DEFAULT_MACRO_QUERY,
        *,
        days: int = DEFAULT_MACRO_DAYS,
        max_results: int = DEFAULT_MAX_RESULTS,
        cache_ttl_sec: int = DEFAULT_NEWS_TTL_SEC,
    ) -> pd.DataFrame:
        """マクロ経済ニュース（FOMC / CPI / 雇用統計 / 中央銀行）。"""
        return self._tavily_search(
            query=topic,
            cache_key_prefix=f"macro_{topic[:30]}",
            days=days,
            max_results=max_results,
            cache_ttl_sec=cache_ttl_sec,
        )

    def fetch_geopolitical_news(
        self,
        topic: str = DEFAULT_GEOPOLITICAL_QUERY,
        *,
        days: int = DEFAULT_GEOPOLITICAL_DAYS,
        max_results: int = DEFAULT_MAX_RESULTS,
        cache_ttl_sec: int = DEFAULT_NEWS_TTL_SEC,
    ) -> pd.DataFrame:
        """地政学ニュース（戦争 / 首脳発言 / 制裁 / 選挙 / 関税）。

        株式に直接関係しなくても市場全体に影響する情報を取得。
        例: トランプ大統領の関税発言、ウクライナ情勢、中東情勢、対中規制。
        """
        return self._tavily_search(
            query=topic,
            cache_key_prefix=f"geo_{topic[:30]}",
            days=days,
            max_results=max_results,
            cache_ttl_sec=cache_ttl_sec,
        )

    # ----- Exa 系 --------------------------------------------------------

    def fetch_research(
        self,
        query: str,
        *,
        max_results: int = DEFAULT_RESEARCH_RESULTS,
        cache_ttl_sec: int = DEFAULT_NEWS_TTL_SEC,
        recency_days: int = DEFAULT_RESEARCH_RECENCY_DAYS,
        include_historical: bool = False,
    ) -> pd.DataFrame:
        """学術論文・研究発表・公的機関レポート（Exa neural search）。

        既定で過去 ``recency_days`` 日（= 1 年）以内の論文に限定する。
        長期バックテストや古典論文を引きたい場合は ``include_historical=True``
        で recency 制限を無効化する（CLAUDE.md §9.3 古い情報を拾わない方針 +
        過去ソース必要時の例外）。
        """
        effective_recency = None if include_historical else recency_days
        return self._exa_search(
            query=query,
            num_results=max_results,
            cache_ttl_sec=cache_ttl_sec,
            recency_days=effective_recency,
        )

    # ----- 統合 ----------------------------------------------------------

    def gather_market_context(
        self,
        ticker: str,
        *,
        macro_query: str = DEFAULT_MACRO_QUERY,
        geopolitical_query: str = DEFAULT_GEOPOLITICAL_QUERY,
        research_query: str | None = None,
    ) -> MarketContext:
        """4 系統を束ねた :class:`MarketContext` を返す。

        投資判断のコンテキスト取得エントリーポイント。
        Buffett / Soros / Burry / Dalio 等の世界一投資家レンズによる
        クエリ拡張は ``src/analysis/investor_lenses.py`` 経由で被せる。
        """
        if research_query is None:
            research_query = (
                f"{ticker} valuation factor analysis academic research"
            )
        return MarketContext(
            ticker=ticker,
            ticker_news=self.fetch_ticker_news(ticker),
            macro_news=self.fetch_macro_news(macro_query),
            geopolitical_news=self.fetch_geopolitical_news(geopolitical_query),
            research=self.fetch_research(research_query),
            fetched_at=datetime.now(timezone.utc),
        )

    # ----- 内部ヘルパー --------------------------------------------------

    def _tavily_search(
        self,
        *,
        query: str,
        cache_key_prefix: str,
        days: int,
        max_results: int,
        cache_ttl_sec: int,
    ) -> pd.DataFrame:
        """Tavily ``/search`` 呼び出し（キャッシュ + Provenance）。"""
        public_params: dict[str, Any] = {
            "query": query,
            "search_depth": "basic",
            "topic": "news",
            "days": days,
            "max_results": max_results,
        }
        cache_key = f"{cache_key_prefix}_{_params_hash(public_params)}"

        cached = self.cache.get(TAVILY_PROVIDER, cache_key, cache_ttl_sec)
        if cached is not None:
            return cached

        endpoint = "/search"
        body = {**public_params, "api_key": self.tavily_api_key}
        response = self.http_client.post(
            f"{self.tavily_base_url}{endpoint}", json=body
        )
        _check_response(response, endpoint=endpoint)
        records = response.json().get("results", [])
        df = _normalize_tavily_results(records)
        attach_provenance(
            df,
            source=TAVILY_PROVIDER,
            fetched_at=datetime.now(timezone.utc),
            endpoint=endpoint,
            params_hash=_params_hash(public_params),
            cache_hit=False,
        )
        self.cache.set(TAVILY_PROVIDER, cache_key, df)
        return df

    def _exa_search(
        self,
        *,
        query: str,
        num_results: int,
        cache_ttl_sec: int,
        recency_days: int | None = None,
    ) -> pd.DataFrame:
        """Exa ``/search`` 呼び出し（キャッシュ + Provenance）。

        ``recency_days`` が指定されると ``start_published_date`` を計算して
        body に含める（古い記事を拾わないための時間制約）。``None`` なら
        無制限（過去 30 年の古典論文等を引きたい場合）。
        """
        public_params: dict[str, Any] = {
            "query": query,
            "num_results": num_results,
            "type": "neural",
        }
        if recency_days is not None:
            start_date = (
                datetime.now(timezone.utc) - timedelta(days=recency_days)
            ).date().isoformat()
            public_params["start_published_date"] = start_date
        cache_key = f"research_{_params_hash(public_params)}"

        cached = self.cache.get(EXA_PROVIDER, cache_key, cache_ttl_sec)
        if cached is not None:
            return cached

        endpoint = "/search"
        body = {
            **public_params,
            "contents": {"text": True},
        }
        response = self.http_client.post(
            f"{self.exa_base_url}{endpoint}",
            json=body,
            headers={"x-api-key": self.exa_api_key},
        )
        _check_response(response, endpoint=endpoint)
        records = response.json().get("results", [])
        df = _normalize_exa_results(records)
        attach_provenance(
            df,
            source=EXA_PROVIDER,
            fetched_at=datetime.now(timezone.utc),
            endpoint=endpoint,
            params_hash=_params_hash(public_params),
            cache_hit=False,
        )
        self.cache.set(EXA_PROVIDER, cache_key, df)
        return df
