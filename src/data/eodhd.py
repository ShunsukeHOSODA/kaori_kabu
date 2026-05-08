"""EODHD All World API クライアント（CLAUDE.md §9.2 / §9.8.4）。

EODHD All World サブスクリプション ($19.99/月) で米国 + 60+ 取引所 + 日本株
EOD データを取得。:class:`ParquetCache` 経由で API 呼び出しを最小化、
Provenance metadata を自動付与する。

API リファレンス:
    https://eodhd.com/financial-apis/api-for-historical-data-and-volumes/

レート制限:
    100,000 calls/day（All World プラン）、約 1,000 calls/min。
    EOD はキャッシュ TTL = 24h で 1 銘柄当たり 1 call/day に抑える。
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

import httpx
import pandas as pd

from ._provenance import attach_provenance
from .cache import ParquetCache

logger = logging.getLogger(__name__)

EODHD_BASE_URL = "https://eodhd.com/api"
CACHE_PROVIDER = "EODHD"
DEFAULT_CACHE_TTL_SEC = 86_400  # 24h


class EODHDAPIError(Exception):
    """EODHD API エラー。API キーを含まない安全なメッセージのみ。

    ``httpx.Response.raise_for_status()`` は URL（``api_token=`` を含む）を
    エラーメッセージに含めるため、ログ・例外トレースに API キーが漏洩する。
    本例外はステータスコードと endpoint パスのみを露出させる。
    """


def _check_response(response: httpx.Response, *, endpoint: str) -> None:
    """response が success でない場合、API キーを含まない例外を raise。

    Args:
        response: httpx の Response
        endpoint: エンドポイントパス（例: ``/eod/AAPL.US``）。
            URL 全体ではないので api_token は含まれない。

    Raises:
        EODHDAPIError: ``response.is_success`` が False の場合
    """
    if response.is_success:
        return
    body_preview = (response.text or "")[:200]
    raise EODHDAPIError(
        f"EODHD API {response.status_code} {response.reason_phrase} "
        f"for {endpoint}: {body_preview}"
    )


def _params_hash(params: dict[str, Any]) -> str:
    """リクエストパラメータの SHA256 ハッシュ（先頭 16 文字、再現性確認用）。

    api_token はセキュリティと再現性の観点から呼び出し側で除外すること。
    同じデータでもキーが違うとハッシュが変わり、再現性検証が破綻する。
    """
    serialized = json.dumps(params, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


def _make_default_http_client() -> httpx.Client:
    """既定の httpx.Client（タイムアウト 30 秒、リダイレクト追従）。"""
    return httpx.Client(timeout=30.0, follow_redirects=True)


@dataclass(frozen=True)
class EODHDClient:
    """EODHD All World API クライアント。

    Args:
        api_key: EODHD API トークン（``.env`` の ``EODHD_API_KEY``）
        cache: Parquet TTL キャッシュ
        http_client: httpx.Client インスタンス（テスト時はモック注入）
        base_url: API ベース URL
    """

    api_key: str
    cache: ParquetCache
    http_client: httpx.Client = field(default_factory=_make_default_http_client)
    base_url: str = EODHD_BASE_URL

    def get_eod(
        self,
        ticker: str,
        *,
        from_date: date,
        to_date: date,
        exchange: str = "US",
        cache_ttl_sec: int = DEFAULT_CACHE_TTL_SEC,
    ) -> pd.DataFrame:
        """EOD OHLCV データ取得（キャッシュ経由）。

        Args:
            ticker: ティッカーシンボル（例: ``AAPL``、``7203``）
            from_date: 取得開始日
            to_date: 取得終了日（inclusive）
            exchange: 取引所コード（デフォルト ``US``、東証は ``TO``）
            cache_ttl_sec: キャッシュ TTL（デフォルト 24h）

        Returns:
            OHLCV DataFrame（カラム: ``date``, ``open``, ``high``, ``low``,
            ``close``, ``adjusted_close``, ``volume``）+ Provenance attrs。
        """
        symbol = f"{ticker}.{exchange}"
        cache_key = (
            f"eod_{symbol}_{from_date.isoformat()}_{to_date.isoformat()}"
        )

        cached = self.cache.get(CACHE_PROVIDER, cache_key, cache_ttl_sec)
        if cached is not None:
            return cached

        endpoint = f"/eod/{symbol}"
        public_params: dict[str, Any] = {
            "fmt": "json",
            "from": from_date.isoformat(),
            "to": to_date.isoformat(),
        }
        # api_token は params_hash 計算対象外（セキュリティ + 再現性）
        request_params = {**public_params, "api_token": self.api_key}
        response = self.http_client.get(
            f"{self.base_url}{endpoint}",
            params=request_params,
        )
        _check_response(response, endpoint=endpoint)
        records = response.json()
        df = pd.DataFrame(records)

        # date 列を pd.Timestamp に統一（型安定性）
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])

        attach_provenance(
            df,
            source="EODHD",
            fetched_at=datetime.now(timezone.utc),
            endpoint=endpoint,
            params_hash=_params_hash(public_params),
            cache_hit=False,
        )

        self.cache.set(CACHE_PROVIDER, cache_key, df)
        return df

    def get_fundamentals(
        self, ticker: str, *, exchange: str = "US"
    ) -> dict[str, Any]:
        """ファンダメンタルデータ取得（生 JSON dict）。

        EODHD ``/fundamentals/{ticker}.{exchange}`` を呼び、深いネスト構造の
        dict をそのまま返す。Magic Formula 入力に必要なフィールド抽出は
        :func:`extract_magic_formula_row` を使う。

        Note:
            現状はキャッシュなし。ファンダは月次更新が一般的なので、
            上位レイヤーで明示的にキャッシュ管理する想定。
        """
        symbol = f"{ticker}.{exchange}"
        endpoint = f"/fundamentals/{symbol}"
        response = self.http_client.get(
            f"{self.base_url}{endpoint}",
            params={"api_token": self.api_key},
        )
        _check_response(response, endpoint=endpoint)
        return response.json()

    def build_screener_universe(
        self,
        tickers: list[str],
        *,
        exchange: str = "US",
    ) -> pd.DataFrame:
        """複数銘柄のファンダから Magic Formula 入力 DataFrame を構築。

        各銘柄の :meth:`get_fundamentals` を順次呼び出し、必要フィールドが
        揃う行だけ集める。欠損・取得失敗銘柄はスキップされる。

        Args:
            tickers: 取得対象のティッカーリスト
            exchange: 取引所コード（デフォルト ``US``）

        Returns:
            ``ticker``/``ebit``/``net_working_capital``/``net_fixed_assets``/
            ``enterprise_value``/``market_cap``/``sector``/``industry``
            カラムを持つ DataFrame。
        """
        rows: list[dict[str, Any]] = []
        for ticker in tickers:
            try:
                fund = self.get_fundamentals(ticker, exchange=exchange)
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("fundamentals 取得失敗: %s (%s)", ticker, exc)
                continue
            row = extract_magic_formula_row(fund, ticker=ticker)
            if row is not None:
                rows.append(row)
        return pd.DataFrame(rows)


def extract_magic_formula_row(
    fundamentals: dict[str, Any], *, ticker: str
) -> dict[str, Any] | None:
    """EODHD fundamentals レスポンスから Magic Formula 入力 1 行を抽出。

    必要フィールド:
        - ``Financials.Income_Statement.yearly.{latest}.operatingIncome`` → EBIT
        - ``Financials.Balance_Sheet.yearly.{latest}.totalCurrentAssets``
        - ``Financials.Balance_Sheet.yearly.{latest}.totalCurrentLiabilities``
        - ``Financials.Balance_Sheet.yearly.{latest}.propertyPlantEquipment`` → NFA
        - ``Highlights.EnterpriseValue``

    Args:
        fundamentals: EODHD ``/fundamentals/`` レスポンス dict
        ticker: ティッカーシンボル

    Returns:
        必須フィールドが揃う場合は ``dict``、欠損があれば ``None``。
    """
    try:
        general = fundamentals.get("General", {})
        highlights = fundamentals.get("Highlights", {})
        financials = fundamentals.get("Financials", {})
        income_yearly = financials.get("Income_Statement", {}).get("yearly", {})
        balance_yearly = financials.get("Balance_Sheet", {}).get("yearly", {})

        if not income_yearly or not balance_yearly:
            return None

        # ISO 8601 文字列キー（YYYY-MM-DD）の最大が最新財務年度
        latest_income = income_yearly[max(income_yearly.keys())]
        latest_balance = balance_yearly[max(balance_yearly.keys())]

        ebit_raw = latest_income.get("operatingIncome")
        ev_raw = highlights.get("EnterpriseValue")
        market_cap_raw = highlights.get("MarketCapitalization")
        ca_raw = latest_balance.get("totalCurrentAssets")
        cl_raw = latest_balance.get("totalCurrentLiabilities")
        ppe_raw = latest_balance.get("propertyPlantEquipment")

        if None in (ebit_raw, ev_raw, ca_raw, cl_raw, ppe_raw):
            return None

        return {
            "ticker": ticker,
            "ebit": Decimal(str(ebit_raw)),
            "net_working_capital": (
                Decimal(str(ca_raw)) - Decimal(str(cl_raw))
            ),
            "net_fixed_assets": Decimal(str(ppe_raw)),
            "enterprise_value": Decimal(str(ev_raw)),
            "market_cap": (
                Decimal(str(market_cap_raw)) if market_cap_raw else None
            ),
            "sector": general.get("Sector", ""),
            "industry": general.get("Industry", ""),
        }
    except (KeyError, TypeError, ValueError):
        return None
