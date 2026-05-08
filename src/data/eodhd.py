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
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

import httpx
import pandas as pd

from data._provenance import attach_provenance
from data.cache import ParquetCache

EODHD_BASE_URL = "https://eodhd.com/api"
CACHE_PROVIDER = "EODHD"
DEFAULT_CACHE_TTL_SEC = 86_400  # 24h


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
        response.raise_for_status()
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
