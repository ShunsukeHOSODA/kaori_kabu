"""yfinance ファンダメンタルラッパー — EODHD と同じ dict shape を返す。

EODHD Fundamentals API ($59.99 単体 or $99.99 ALL-IN-ONE) の代替として、
無料の yfinance を使ってファンダを取得する。EODHD と同じ dict shape に
正規化することで :func:`data.eodhd.extract_magic_formula_row` および
``build_composite_inputs_from_fundamentals`` が無修正で動く。

データ品質: yfinance は Yahoo Finance の非公式 API。米国大型株は十分、
小型株や日本株（東証）は欠損があり得る。商用 SLA は無いので個人利用限定。
日本株のファンダ正本は J-Quants Light を併用するのが望ましい。

キャッシュ規約: TTL 7 日（CLAUDE.md §9.2 ファンダメンタル）、JSON で
``{cache.base_dir}/yfinance/fundamentals_{ticker}_{exchange}.json``。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Final, Protocol

import pandas as pd

from .cache import ParquetCache
from .eodhd import extract_magic_formula_row

logger = logging.getLogger(__name__)

CACHE_PROVIDER: Final[str] = "yfinance"
DEFAULT_FUNDAMENTAL_CACHE_TTL_SEC: Final[int] = 604_800  # 7d (CLAUDE.md §9.2)


class _TickerLike(Protocol):
    """yfinance.Ticker のテスト用 Protocol（必要属性のみ宣言）。"""

    info: dict[str, Any]
    income_stmt: pd.DataFrame
    balance_sheet: pd.DataFrame
    cashflow: pd.DataFrame


# yfinance の row label → EODHD の field 名へのマッピング
INCOME_FIELD_MAP: Final[dict[str, str]] = {
    "Operating Income": "operatingIncome",
    "Total Revenue": "totalRevenue",
    "EBITDA": "ebitda",
    "Gross Profit": "grossProfit",
    "Diluted EPS": "dilutedEps",
}
BALANCE_FIELD_MAP: Final[dict[str, str]] = {
    "Current Assets": "totalCurrentAssets",
    "Current Liabilities": "totalCurrentLiabilities",
    "Net PPE": "propertyPlantEquipment",
    "Property Plant And Equipment Net": "propertyPlantEquipment",
    "Total Assets": "totalAssets",
    "Total Liabilities Net Minority Interest": "totalLiab",
    "Retained Earnings": "retainedEarnings",
}
CASHFLOW_FIELD_MAP: Final[dict[str, str]] = {
    "Cash Flow From Continuing Operating Activities": "totalCashFromOperatingActivities",
    "Operating Cash Flow": "totalCashFromOperatingActivities",
    "Capital Expenditure": "capitalExpenditures",
    "Repurchase Of Capital Stock": "commonStockRepurchased",
}


def _read_fresh_json(path: Path, ttl_sec: int) -> dict[str, Any] | None:
    """JSON ファイルを TTL 内なら読み込み、それ以外は ``None``。

    ``ttl_sec`` が 0 の場合は常に stale（強制再取得）。EODHD と同じ規約。
    """
    if not path.exists() or ttl_sec <= 0:
        return None
    age = datetime.now(timezone.utc).timestamp() - path.stat().st_mtime
    if age > ttl_sec:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _build_symbol(ticker: str, exchange: str) -> str:
    """``ticker`` と ``exchange`` から yfinance シンボル文字列を構築。

    - ``US`` → そのまま (``AAPL``)
    - ``TO`` (東証) → ``.T`` 付与 (``7203`` → ``7203.T``)
    - その他 → ``{ticker}.{exchange}``（yfinance の suffix 規約に従う）
    """
    if exchange == "US":
        return ticker
    if exchange == "TO":
        return f"{ticker}.T"
    return f"{ticker}.{exchange}"


def _yearly_dict_from_df(
    df: pd.DataFrame, field_map: dict[str, str]
) -> dict[str, dict[str, float]]:
    """yfinance DataFrame → EODHD ``yearly`` dict 形式に正規化。

    yfinance の財務 DataFrame は rows=指標名（英語）、columns=決算日
    (``pd.Timestamp``)。これを EODHD の ``{"YYYY-MM-DD": {field: value}}`` 形に。

    Args:
        df: yfinance.Ticker.income_stmt / balance_sheet / cashflow
        field_map: yfinance row label → EODHD field 名

    Returns:
        ``{"2024-09-30": {"operatingIncome": 1.19e11, ...}, ...}``。
        空 DataFrame なら空 dict。NaN は除外。
    """
    if df is None or df.empty:
        return {}

    yearly: dict[str, dict[str, float]] = {}
    for col in df.columns:
        date_str = (
            col.strftime("%Y-%m-%d") if hasattr(col, "strftime") else str(col)
        )
        record: dict[str, float] = {}
        for src_label, dst_field in field_map.items():
            if src_label in df.index:
                value = df.at[src_label, col]
                if pd.notna(value):
                    record[dst_field] = float(value)
        if record:
            yearly[date_str] = record
    return yearly


def _normalize_to_eodhd_shape(
    ticker_obj: _TickerLike, *, ticker: str
) -> dict[str, Any]:
    """yfinance の Ticker インスタンス → EODHD ファンダ dict shape に変換。

    既存の :func:`data.eodhd.extract_magic_formula_row` および
    ``build_composite_inputs_from_fundamentals`` が無修正で動くように
    EODHD の ``General/Highlights/SharesStats/Financials`` 階層を再現する。
    """
    info = ticker_obj.info or {}
    income = _yearly_dict_from_df(ticker_obj.income_stmt, INCOME_FIELD_MAP)
    balance = _yearly_dict_from_df(ticker_obj.balance_sheet, BALANCE_FIELD_MAP)
    cashflow = _yearly_dict_from_df(ticker_obj.cashflow, CASHFLOW_FIELD_MAP)

    # NetDebt = totalDebt - totalCash（どちらかが取れていれば算出）
    total_cash = info.get("totalCash")
    total_debt = info.get("totalDebt")
    net_debt: float | None
    if total_debt is not None or total_cash is not None:
        net_debt = float((total_debt or 0) - (total_cash or 0))
    else:
        net_debt = None

    return {
        "General": {
            "Code": ticker,
            "Name": info.get("longName") or info.get("shortName") or ticker,
            "Sector": info.get("sector") or "",
            "Industry": info.get("industry") or "",
        },
        "Highlights": {
            "MarketCapitalization": info.get("marketCap"),
            "EnterpriseValue": info.get("enterpriseValue"),
            "EBITDA": info.get("ebitda"),
            "PERatio": info.get("trailingPE"),
            "ReturnOnEquityTTM": info.get("returnOnEquity"),
            "ReturnOnAssetsTTM": info.get("returnOnAssets"),
            "ForwardAnnualDividendRate": info.get("dividendRate"),
            "PayoutRatio": info.get("payoutRatio"),
            "QuarterlyEarningsGrowthYOY": info.get("earningsQuarterlyGrowth"),
            "DividendGrowth5Years": info.get("fiveYearAvgDividendYield"),
            "NetDebt": net_debt,
        },
        "SharesStats": {
            "SharesOutstanding": info.get("sharesOutstanding"),
        },
        "Financials": {
            "Income_Statement": {"yearly": income},
            "Balance_Sheet": {"yearly": balance},
            "Cash_Flow": {"yearly": cashflow},
        },
    }


@dataclass(frozen=True)
class YFinanceClient:
    """yfinance ベースのファンダメンタルクライアント。

    ``ticker_factory`` は ``yfinance.Ticker`` 互換のファクトリ。テスト時は
    MagicMock を注入してネットワーク呼び出しを回避する。

    Args:
        cache: Parquet キャッシュ（base_dir のみ利用、JSON で保存）
        ticker_factory: ``Callable[[str], Ticker]``。デフォルトは ``yfinance.Ticker``。
    """

    cache: ParquetCache
    ticker_factory: Callable[[str], _TickerLike]

    def get_fundamentals(
        self,
        ticker: str,
        *,
        exchange: str = "US",
        cache_ttl_sec: int = DEFAULT_FUNDAMENTAL_CACHE_TTL_SEC,
    ) -> dict[str, Any]:
        """yfinance からファンダを取得し EODHD shape dict で返す（7d キャッシュ）。

        Args:
            ticker: ティッカー（``AAPL`` / ``7203``）
            exchange: 取引所コード（``US`` / ``TO``）
            cache_ttl_sec: キャッシュ TTL（デフォルト 7 日）。``0`` で強制再取得。
        """
        cache_path = self._cache_path(ticker, exchange)
        cached = _read_fresh_json(cache_path, cache_ttl_sec)
        if cached is not None:
            return cached

        symbol = _build_symbol(ticker, exchange)
        ticker_obj = self.ticker_factory(symbol)
        payload = _normalize_to_eodhd_shape(ticker_obj, ticker=ticker)

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
        return payload

    def _cache_path(self, ticker: str, exchange: str) -> Path:
        """``{cache.base_dir}/yfinance/fundamentals_{ticker}_{exchange}.json``。"""
        provider_dir = self.cache.base_dir / CACHE_PROVIDER
        return provider_dir / f"fundamentals_{ticker}_{exchange}.json"

    def build_screener_universe(
        self,
        tickers: list[str],
        *,
        exchange: str = "US",
        excluded_sectors: tuple[str, ...] = (),
        min_market_cap_usd: Decimal | None = None,
    ) -> pd.DataFrame:
        """複数銘柄のファンダから Magic Formula 入力 DataFrame を構築。

        :class:`data.eodhd.EODHDClient.build_screener_universe` と同シグネチャ。
        ``data.eodhd.extract_magic_formula_row`` を共有しているため抽出仕様は同一。

        Args:
            tickers: 取得対象のティッカーリスト
            exchange: 取引所コード（デフォルト ``US``）
            excluded_sectors: 除外セクター名タプル
            min_market_cap_usd: 最低時価総額（USD、Decimal）。``None`` なら無し。

        Returns:
            Magic Formula 入力 DataFrame（フィルタ後）。
        """
        rows: list[dict[str, Any]] = []
        excluded_set = set(excluded_sectors)
        for ticker in tickers:
            try:
                fund = self.get_fundamentals(ticker, exchange=exchange)
            except (ValueError, KeyError, OSError) as exc:
                logger.warning("yfinance ファンダ取得失敗: %s (%s)", ticker, exc)
                continue
            row = extract_magic_formula_row(fund, ticker=ticker)
            if row is None:
                continue
            if row.get("sector") in excluded_set:
                continue
            if min_market_cap_usd is not None:
                cap = row.get("market_cap")
                if cap is None or cap < min_market_cap_usd:
                    continue
            rows.append(row)
        return pd.DataFrame(rows)


def make_default_yfinance_client(cache: ParquetCache) -> YFinanceClient:
    """``yfinance.Ticker`` を注入した本番用 YFinanceClient を生成。

    Streamlit セッションシングルトン化は呼び出し側（``@st.cache_resource``）。
    """
    import yfinance as yf  # noqa: PLC0415 — テスト時の lazy import 維持

    return YFinanceClient(cache=cache, ticker_factory=yf.Ticker)
