"""世界一の投資家レンズ（Phase 2 拡張、CLAUDE.md §5）。

NewsClient の汎用 4 系統だけでは取りこぼす「投資家固有の視座」を、
クエリテンプレート化したレンズとして 8 つ提供する。
``apply_lenses(client, ticker, lenses=(...))`` で展開し、
:class:`MarketContext` の補強情報として使う。

8 レンズの選定理由:
    - **Buffett_Munger**: 経営者の質 / モート / 長期資本効率（質×価値）
    - **Soros**: 市場心理とマクロのリフレクシビティ
    - **Druckenmiller**: 流動性サイクル（Fed BS / 財政赤字）
    - **Dalio**: 覇権サイクル / 負債サイクル / 生産性
    - **Pabrai**: スーパー投資家のクローニング（発信フォロー）
    - **Burry**: テールリスク / クレジット市場 / シャドーバンキング
    - **Ackman**: アクティビズム / ガバナンス / 規制動向
    - **Lynch**: 消費者目線 / 製品観察 / 業界トレンド

各レンズはクエリテンプレートに ``{ticker}`` プレースホルダを含み、
``apply_lenses`` 内で ticker で展開される。

設計方針:
    - レンズはあくまでクエリ拡張層。実取得は :class:`NewsClient` に委譲。
    - 出力 DataFrame は ``lens_name`` / ``lens_query`` 列付きで、
      後段の SentimentAnalyzer や Decision Log で「どのレンズ由来か」を
      復元可能にする（Provenance 規約 CLAUDE.md §9.8）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal, Protocol

import pandas as pd

# ---------------------------------------------------------------------------
# 型
# ---------------------------------------------------------------------------

FetchCategory = Literal["geopolitical", "research"]


class _NewsClientProtocol(Protocol):
    """``apply_lenses`` が要求する NewsClient の最小インターフェース。"""

    def fetch_geopolitical_news(
        self, topic: str, **kwargs: object
    ) -> pd.DataFrame: ...

    def fetch_research(
        self, query: str, **kwargs: object
    ) -> pd.DataFrame: ...


@dataclass(frozen=True)
class InvestorLens:
    """単一投資家視座のレンズ定義。

    Attributes:
        name: レンズ名（``INVESTOR_LENSES`` キーと一致）
        rationale: 採用理由（日本語、Provenance 出力用）
        fetch_category: ``"geopolitical"`` で Tavily news、``"research"`` で
            Exa neural search を呼ぶ
        queries: クエリテンプレート（``{ticker}`` プレースホルダ可）
    """

    name: str
    rationale: str
    fetch_category: FetchCategory
    queries: tuple[str, ...]


# ---------------------------------------------------------------------------
# レンズカタログ
# ---------------------------------------------------------------------------


INVESTOR_LENSES: Final[dict[str, InvestorLens]] = {
    "Buffett_Munger": InvestorLens(
        name="Buffett_Munger",
        rationale="経営者の質 / モート（経済堀）/ 長期資本配分",
        fetch_category="geopolitical",
        queries=(
            "{ticker} CEO leadership management integrity",
            "{ticker} competitive moat economic advantage durability",
            "{ticker} share buyback dividend capital allocation long-term",
        ),
    ),
    "Soros": InvestorLens(
        name="Soros",
        rationale="市場心理とマクロのリフレクシビティ（自己強化）",
        fetch_category="geopolitical",
        queries=(
            "currency crisis emerging market positioning sentiment",
            "Fed policy market expectations reflexivity feedback loop",
            "political economic feedback narrative central bank reaction",
        ),
    ),
    "Druckenmiller": InvestorLens(
        name="Druckenmiller",
        rationale="流動性サイクル / Fed バランスシート / 財政赤字",
        fetch_category="geopolitical",
        queries=(
            "Federal Reserve balance sheet liquidity tightening QT",
            "fiscal deficit Treasury issuance debt ceiling impact",
            "M2 money supply liquidity equity market correlation",
        ),
    ),
    "Dalio": InvestorLens(
        name="Dalio",
        rationale="覇権サイクル / 負債サイクル / 生産性（All Weather）",
        fetch_category="geopolitical",
        queries=(
            "US China hegemony decoupling reserve currency dollar",
            "sovereign debt cycle credit market stress refinancing",
            "productivity demographics AI technology long wave",
        ),
    ),
    "Pabrai": InvestorLens(
        name="Pabrai",
        rationale="スーパー投資家のクローニング（発信フォロー）",
        fetch_category="geopolitical",
        queries=(
            "Warren Buffett Berkshire latest move position",
            "Mohnish Pabrai recent interview holdings concentration",
            "Michael Burry Twitter warning comment market",
        ),
    ),
    "Burry": InvestorLens(
        name="Burry",
        rationale="テールリスク / クレジットスプレッド / シャドーバンキング",
        fetch_category="geopolitical",
        queries=(
            "credit default swap spread widening high yield",
            "shadow banking liquidity stress repo market funding",
            "{ticker} debt covenant credit risk balance sheet leverage",
        ),
    ),
    "Ackman": InvestorLens(
        name="Ackman",
        rationale="アクティビズム / ガバナンス / 規制動向",
        fetch_category="geopolitical",
        queries=(
            "{ticker} board of directors governance shareholder activism",
            "{ticker} SEC regulatory action FTC antitrust investigation",
            "{ticker} ESG proxy advisor recommendation",
        ),
    ),
    "Lynch": InvestorLens(
        name="Lynch",
        rationale="消費者目線 / 製品観察 / 業界トレンド（10-bagger）",
        fetch_category="research",
        queries=(
            "{ticker} consumer adoption product launch market share",
            "{ticker} industry trend total addressable market growth",
            "{ticker} brand loyalty customer satisfaction NPS survey",
        ),
    ),
}


# ---------------------------------------------------------------------------
# 適用関数
# ---------------------------------------------------------------------------


_OUTPUT_COLUMNS: tuple[str, ...] = (
    "title",
    "snippet",
    "url",
    "published_at",
    "source_provider",
    "relevance_score",
    "lens_name",
    "lens_query",
)


def apply_lenses(
    client: _NewsClientProtocol,
    *,
    ticker: str,
    lenses: tuple[str, ...],
) -> pd.DataFrame:
    """指定レンズのクエリを展開して NewsClient で取得し DataFrame に統合。

    各レンズの ``queries`` を ``ticker`` で展開し、``fetch_category`` に応じて
    Tavily 地政学検索または Exa research 検索を呼ぶ。
    結果には ``lens_name`` / ``lens_query`` 列を付与し、後段で「なぜこの記事を
    取りに行ったか」を復元可能にする（Provenance 規約 CLAUDE.md §9.8）。

    Args:
        client: NewsClient 互換オブジェクト（``fetch_geopolitical_news`` /
            ``fetch_research`` を持つ）
        ticker: クエリの ``{ticker}`` プレースホルダで使う銘柄名
        lenses: 適用するレンズ名タプル（:data:`INVESTOR_LENSES` のキー）

    Returns:
        統合 DataFrame。空でも ``_OUTPUT_COLUMNS`` を保持。
    """
    frames: list[pd.DataFrame] = []
    for lens_name in lenses:
        lens = INVESTOR_LENSES[lens_name]
        for template in lens.queries:
            query = template.format(ticker=ticker)
            if lens.fetch_category == "research":
                df = client.fetch_research(query)
            else:
                df = client.fetch_geopolitical_news(query)
            tagged = df.copy()
            tagged["lens_name"] = lens_name
            tagged["lens_query"] = query
            frames.append(tagged)

    if not frames:
        return pd.DataFrame(columns=list(_OUTPUT_COLUMNS))

    combined = pd.concat(frames, ignore_index=True)
    # 不足カラムは空で揃える（fetch 結果が薄いケースの安全策）
    for col in _OUTPUT_COLUMNS:
        if col not in combined.columns:
            combined[col] = pd.Series(dtype="object")
    return combined
