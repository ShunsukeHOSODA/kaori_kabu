"""達人投資家の保有銘柄静的辞書（Phase 3.2 で SEC EDGAR 13F 動的化予定）。

要件 .steering/20260509-ui-5tab-redesign/ §3 反対意見 2 に基づき、おすすめ銘柄
カードに「🐋 バフェット保有」等のバッジを表示するためのソース。

Phase 3.1 段階では手動メンテの静的辞書から始める。Phase 3.2 で
src/data/sec_edgar.py の 13F-HR XML パーサ実装後に動的取得に切替。

参照元:
    - 2026Q1 13F-HR (Berkshire Hathaway, Pabrai Investment Funds 等)
    - 公式 IR / 各種ニュースソース（Berkshire の主要保有銘柄は公知）

注意:
    - 各達人の保有は四半期で大きく変動する。本辞書は「過去 4 四半期で継続的に
      保有されている主要銘柄」を保守的に列挙したもの
    - スコアリングや売買判断には使わず、UI バッジの**心理的安心材料**としてのみ使用
"""

from __future__ import annotations

from typing import Final

# (ticker, exchange) → frozenset of investor names
# 拡張は手動メンテ。Phase 3.2 で SEC EDGAR から動的取得に置換
FAMOUS_HOLDINGS: Final[dict[tuple[str, str], frozenset[str]]] = {
    # Berkshire Hathaway (Buffett)
    ("AAPL", "US"): frozenset({"Buffett"}),
    ("BAC", "US"): frozenset({"Buffett"}),
    ("AXP", "US"): frozenset({"Buffett"}),
    ("KO", "US"): frozenset({"Buffett"}),
    ("OXY", "US"): frozenset({"Buffett"}),
    ("CVX", "US"): frozenset({"Buffett"}),
    ("MCO", "US"): frozenset({"Buffett"}),
    ("KHC", "US"): frozenset({"Buffett"}),
    ("DVA", "US"): frozenset({"Buffett"}),
    ("VRSN", "US"): frozenset({"Buffett"}),
    # Pabrai Investment Funds（スーパー集中、5-10 銘柄）
    ("RAIN", "US"): frozenset({"Pabrai"}),
    ("MU", "US"): frozenset({"Pabrai"}),
    # Burry (Scion Asset Management) — 注: 高頻度で入れ替わる
    ("JD", "US"): frozenset({"Burry"}),
    ("BABA", "US"): frozenset({"Burry"}),
    # Pershing Square (Ackman)
    ("CMG", "US"): frozenset({"Ackman"}),
    ("RBI", "US"): frozenset({"Ackman"}),
    ("HLT", "US"): frozenset({"Ackman"}),
    ("UBER", "US"): frozenset({"Ackman"}),
    ("GOOGL", "US"): frozenset({"Ackman"}),
}


_INVESTOR_BADGES: Final[dict[str, str]] = {
    "Buffett": "🐋 バフェット保有",
    "Pabrai": "🐋 パブライ保有",
    "Burry": "🐋 バーリ保有",
    "Ackman": "🐋 アックマン保有",
}


def get_famous_owners(ticker: str, exchange: str) -> frozenset[str]:
    """指定銘柄を保有している達人名集合を返す。未保有時は空集合。

    Args:
        ticker: 銘柄シンボル（大文字小文字どちらでも）
        exchange: 取引所コード（``US`` / ``TO`` 等）

    Returns:
        ``frozenset`` of investor names（``"Buffett"``, ``"Pabrai"``, ...）。
    """
    return FAMOUS_HOLDINGS.get((ticker.upper(), exchange.upper()), frozenset())


def render_owner_badges(owners: frozenset[str]) -> str:
    """達人名集合 → 表示用バッジ文字列（複数なら空白区切り）。

    Args:
        owners: ``get_famous_owners`` の戻り値

    Returns:
        例 ``"🐋 バフェット保有 🐋 パブライ保有"``。空集合なら空文字列。
    """
    return " ".join(_INVESTOR_BADGES.get(name, name) for name in sorted(owners))


def has_famous_owner(ticker: str, exchange: str) -> bool:
    """指定銘柄を達人が誰か保有しているか（バッジ表示判定の高速版）。"""
    return bool(get_famous_owners(ticker, exchange))
