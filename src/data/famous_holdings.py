"""達人投資家の保有銘柄解決（SEC EDGAR 動的 + 静的辞書フォールバック）。

CLAUDE.md §6 / .steering/20260510-13f-dynamic/design.md §9 に基づき、
:mod:`data.sec_edgar` の 13F-HR キャッシュから動的に保有関係を導出する。
キャッシュが空 / フェッチ失敗時は静的辞書にフォールバックする。

参照元:
    - 直近四半期 13F-HR (SEC EDGAR)
    - 静的辞書: 公知保有銘柄（Berkshire / Pabrai / Burry / Ackman）

注意:
    - 各達人の保有は四半期で大きく変動する
    - スコアリングや売買判断には使わず、UI バッジの**心理的安心材料**としてのみ使用
"""

from __future__ import annotations

import logging
from typing import Final

from .cache import ParquetCache
from .sec_edgar import CACHE_PROVIDER, DEFAULT_CACHE_TTL_SEC

logger = logging.getLogger(__name__)

# (ticker, exchange) → frozenset of investor names
# 動的解決が空のときフォールバックとして使う。手動メンテ。
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


# 追跡対象 4 ファンド: CIK → 投資家名
FUND_CIK_TO_INVESTOR: Final[dict[str, str]] = {
    "0001067983": "Buffett",  # Berkshire Hathaway
    "0001173334": "Pabrai",   # Pabrai Investment Funds
    "0001649339": "Burry",    # Scion Asset Management
    "0001336528": "Ackman",   # Pershing Square Capital
}


# ティッカー → SEC 13F の nameOfIssuer 検索キー（大文字、部分一致用）。
# 13F の name_of_issuer は SEC 表記（"APPLE INC"）でティッカーと直結しないため、
# 既知ティッカーから issuer 名キーワードを引く。
TICKER_TO_ISSUER_NAME: Final[dict[str, str]] = {
    "AAPL": "APPLE",
    "BAC": "BANK OF AMERICA",
    "AXP": "AMERICAN EXPRESS",
    "KO": "COCA COLA",
    "OXY": "OCCIDENTAL",
    "CVX": "CHEVRON",
    "MCO": "MOODYS",
    "KHC": "KRAFT HEINZ",
    "DVA": "DAVITA",
    "VRSN": "VERISIGN",
    "MU": "MICRON",
    "RAIN": "RAIN",
    "JD": "JD COM",
    "BABA": "ALIBABA",
    "CMG": "CHIPOTLE",
    "RBI": "RESTAURANT BRANDS",
    "HLT": "HILTON",
    "UBER": "UBER",
    "GOOGL": "ALPHABET",
}


_INVESTOR_BADGES: Final[dict[str, str]] = {
    "Buffett": "🐋 バフェット保有",
    "Pabrai": "🐋 パブライ保有",
    "Burry": "🐋 バーリ保有",
    "Ackman": "🐋 アックマン保有",
}


def _get_default_cache() -> ParquetCache | None:
    """設定から ParquetCache を遅延構築。

    settings 読み込みに失敗した場合（テスト環境等）は ``None`` を返し、
    呼び出し側で静的辞書フォールバックさせる。
    """
    try:
        from config.settings import settings

        return ParquetCache(base_dir=settings.cache_dir)
    except Exception as exc:  # noqa: BLE001
        logger.debug("could not init default cache: %s", exc)
        return None


def _resolve_from_edgar_cache(
    ticker: str,
    exchange: str,
    *,
    cache: ParquetCache | None = None,
) -> frozenset[str]:
    """SEC EDGAR 13F キャッシュから動的に保有関係を解決。

    Args:
        ticker: 大文字正規化済みティッカー
        exchange: 大文字正規化済み取引所コード
        cache: ParquetCache 注入（None なら settings から構築）

    Returns:
        該当達人名 frozenset。以下の場合は空集合（静的フォールバックを促す）:
            - 非 US 銘柄
            - TICKER_TO_ISSUER_NAME に登録なし
            - cache 取得不能 / 全ファンド cache miss / issuer name 一致なし
    """
    if exchange != "US":
        return frozenset()
    issuer_name = TICKER_TO_ISSUER_NAME.get(ticker)
    if not issuer_name:
        return frozenset()

    if cache is None:
        cache = _get_default_cache()
    if cache is None:
        return frozenset()

    owners: set[str] = set()
    for cik, investor in FUND_CIK_TO_INVESTOR.items():
        try:
            df = cache.get(
                CACHE_PROVIDER, f"13f_{cik}_latest", DEFAULT_CACHE_TTL_SEC
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("edgar cache read failed for %s: %s", cik, exc)
            continue
        if df is None or df.empty:
            continue
        if "name_of_issuer" not in df.columns:
            continue
        # 大文字部分一致（SEC 表記揺れ吸収）
        match_mask = df["name_of_issuer"].str.upper().str.contains(
            issuer_name, regex=False, na=False
        )
        if match_mask.any():
            owners.add(investor)
    return frozenset(owners)


def get_famous_owners(
    ticker: str,
    exchange: str,
    *,
    cache: ParquetCache | None = None,
) -> frozenset[str]:
    """指定銘柄を保有している達人名集合を返す。

    動的解決（SEC EDGAR cache）を先に試み、ヒットすればそれを返す。
    cache 空 / 不明銘柄 → 静的辞書フォールバック。

    Args:
        ticker: 銘柄シンボル（大文字小文字どちらでも）
        exchange: 取引所コード（``US`` / ``TO`` 等）
        cache: ParquetCache 注入用（テスト時のみ。本番は settings から自動）

    Returns:
        ``frozenset`` of investor names。例: ``frozenset({"Buffett"})``。
        未保有時は空集合。
    """
    ticker_norm = ticker.upper()
    exchange_norm = exchange.upper()

    dynamic = _resolve_from_edgar_cache(
        ticker_norm, exchange_norm, cache=cache
    )
    if dynamic:
        return dynamic
    return FAMOUS_HOLDINGS.get((ticker_norm, exchange_norm), frozenset())


def render_owner_badges(owners: frozenset[str]) -> str:
    """達人名集合 → 表示用バッジ文字列（複数なら空白区切り）。

    Args:
        owners: ``get_famous_owners`` の戻り値

    Returns:
        例 ``"🐋 バフェット保有 🐋 パブライ保有"``。空集合なら空文字列。
    """
    return " ".join(
        _INVESTOR_BADGES.get(name, name) for name in sorted(owners)
    )


def has_famous_owner(
    ticker: str,
    exchange: str,
    *,
    cache: ParquetCache | None = None,
) -> bool:
    """指定銘柄を達人が誰か保有しているか（バッジ表示判定の高速版）。"""
    return bool(get_famous_owners(ticker, exchange, cache=cache))
