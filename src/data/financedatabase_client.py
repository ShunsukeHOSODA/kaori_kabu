"""FinanceDatabase 経由 日本株ユニバース取得（§4.5、handoff-phase4.md）。

JerBouma/FinanceDatabase（無料、CSV ベース）から TSE 銘柄リストを取得し、
時価総額カテゴリ別にフィルタしてティッカー文字列リストを返す。

設計判断:
    - market_cap は数値ではなく "Mega Cap" / "Large Cap" / "Mid Cap" / "Small Cap" /
      "Micro Cap" / "Nano Cap" の文字列分類
    - TOPIX 公式分類 (Core30 / Large70 / Mid400) と直接対応しないため、
      米国基準分類を流用して TOPIX 近似として提供
    - ティッカー形式は "7203.T" → "7203" に正規化（02_screener の慣習）
    - 外部依存（financedatabase.Equities）は依存性注入で差し替え可能（テスト用）

ユースケース:
    02_screener の JP モード時にハードコード Core30 10 銘柄を脱却し、
    時価総額別ユニバース（large / mid / all）を動的取得する。
"""

from __future__ import annotations

from typing import Callable, Literal, Protocol, runtime_checkable

import pandas as pd

CapFilter = Literal["large", "mid", "all"]
"""ユニバース絞り込みフィルタ。

- "large": Mega + Large Cap（TOPIX Core30~Large70 近似、JP では ~100 銘柄）
- "mid":   Mega + Large + Mid Cap（TOPIX 500 近似、JP では ~350 銘柄）
- "all":   全 TSE 銘柄（~2,950 銘柄、limit で要絞り込み）
"""

_CAP_FILTERS: dict[CapFilter, set[str]] = {
    "large": {"Mega Cap", "Large Cap"},
    "mid": {"Mega Cap", "Large Cap", "Mid Cap"},
    "all": {
        "Mega Cap",
        "Large Cap",
        "Mid Cap",
        "Small Cap",
        "Micro Cap",
        "Nano Cap",
    },
}


@runtime_checkable
class _EquitiesLike(Protocol):
    """FinanceDatabase の Equities インスタンスが満たすべき I/F。"""

    def select(self, **kwargs: object) -> pd.DataFrame: ...


def _default_equities_factory() -> _EquitiesLike:
    """本番用 factory: financedatabase.Equities を返す（lazy import）。"""
    import financedatabase as fd

    return fd.Equities()


def _normalize_symbol(symbol: str) -> str:
    """'7203.T' → '7203'、'72030' → '7203' 等に正規化。"""
    if "." in symbol:
        symbol = symbol.split(".", 1)[0]
    if symbol.isdigit() and len(symbol) == 5 and symbol.endswith("0"):
        symbol = symbol[:4]
    return symbol


def get_jp_universe(
    *,
    cap_filter: CapFilter,
    limit: int = 100,
    equities_factory: Callable[[], _EquitiesLike] | None = None,
) -> list[str]:
    """FinanceDatabase から TSE 銘柄ユニバースをカテゴリ別に取得。

    Args:
        cap_filter: 時価総額フィルタ（"large" / "mid" / "all"）
        limit: 戻り値件数の上限（既定 100）
        equities_factory: 依存性注入用 factory。``None`` のとき本番用
            ``financedatabase.Equities()`` を使う。テスト時はモックを注入。

    Returns:
        4 桁数字のティッカー文字列リスト（例: ``["7203", "6758", ...]``）。
        順序は FinanceDatabase の symbol index 昇順。

    Raises:
        ValueError: cap_filter が不正な場合。
    """
    if cap_filter not in _CAP_FILTERS:
        raise ValueError(
            f"cap_filter must be one of {sorted(_CAP_FILTERS.keys())}, "
            f"got {cap_filter!r}"
        )

    factory = equities_factory or _default_equities_factory
    equities = factory()
    df = equities.select(country="Japan")

    if df.empty:
        return []

    jpx_mask = (
        df["exchange"] == "JPX"
        if "exchange" in df.columns
        else pd.Series([True] * len(df), index=df.index)
    )
    cap_mask = df["market_cap"].isin(_CAP_FILTERS[cap_filter])
    filtered = df[jpx_mask & cap_mask]

    symbols = [_normalize_symbol(str(s)) for s in filtered.index.tolist()]
    return symbols[:limit]
