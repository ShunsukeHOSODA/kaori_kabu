"""J-Quants API v2 クライアント（CLAUDE.md §5 / §9.2 / §9.8）。

J-Quants Light サブスクリプション (1,650 円/月) で日本株 (TSE) の EOD
（Daily Bars）データを取得。:class:`ParquetCache` 経由で API 呼び出しを
最小化、Provenance metadata を自動付与する。

API リファレンス:
    https://jpx-jquants.com/spec/migration-v1-v2
    GET https://api.jquants.com/v2/equities/bars/daily
        ヘッダ: x-api-key: {API_KEY}
        パラメータ: code, from, to, pagination_key

レート制限:
    Light プラン 60 req/min。本実装は 1 req/sec の間隔で
    :meth:`_enforce_rate_limit` が制限を保証。

設計判断:
    - **EODHD は日本株未サポート** であることが本セッションで判明
      （`TO` exchange は Toronto、`TSE/JP` は EODHD に exchange 自体が存在せず）。
      CLAUDE.md §5 「J-Quants Light = 日本株の正本」と整合。
    - **2025-12-22 以降 v2 必須**: 永続 API key 認証 (x-api-key ヘッダ)。
      v1 の refresh_token → idToken 24h ライフサイクルは廃止。
    - v2 はカラム名が短縮 (Open→O, High→H, Low→L, Close→C, Volume→Vo)
      されるが、本クライアントは下流互換のため Open/High/Low/Close/Volume
      に展開して返す（既存呼び出し側の影響最小化）。
    - 4 桁証券コードに正規化してから API に渡す
      （J-Quants 入力は 4 桁、レスポンス Code は 5 桁チェックデジット付き）。
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Final

import httpx
import pandas as pd

from ._provenance import attach_provenance
from .cache import ParquetCache

logger = logging.getLogger(__name__)

JQUANTS_BASE_URL: Final[str] = "https://api.jquants.com"
CACHE_PROVIDER: Final[str] = "JQUANTS"
DEFAULT_CACHE_TTL_SEC: Final[int] = 86_400  # 24h（EOD は日次更新で十分）
DEFAULT_RATE_LIMIT_PER_MIN: Final[int] = 60  # Light プラン

# v2 短縮カラム → 既存呼び出し側互換の長名へのマッピング
V2_COLUMN_RENAME: Final[dict[str, str]] = {
    "O": "Open",
    "H": "High",
    "L": "Low",
    "C": "Close",
    "Vo": "Volume",
    "Va": "TurnoverValue",
}


# ============================================================
# 例外
# ============================================================


class JQuantsConfigError(Exception):
    """設定エラー（API key 未設定等）。"""


class JQuantsAuthError(Exception):
    """認証エラー（401 / API key 無効等）。

    API key は J-Quants Web (jpx-jquants.com) ダッシュボードから再発行可能。
    """


class JQuantsAPIError(Exception):
    """J-Quants HTTP エラー（4xx / 5xx）。

    例外メッセージには API key を絶対に含めない
    （ログ・スタックトレース漏洩対策）。
    """


# ============================================================
# 純粋関数
# ============================================================


_CODE_PATTERN: Final[re.Pattern[str]] = re.compile(r"^(\d{4})\d?$")


def _normalize_code(code: str) -> str:
    """ティッカー文字列を 4 桁証券コードに正規化。

    受け付けるパターン:
        - ``"7203"``    → ``"7203"``
        - ``"7203.T"``  → ``"7203"`` (Yahoo Finance 表記)
        - ``"7203.JP"`` → ``"7203"`` (本プロジェクト表記)
        - ``"72030"``   → ``"7203"`` (J-Quants レスポンスの 5 桁、末尾チェックデジット 0)

    Raises:
        ValueError: 4 桁証券コードを抽出できない場合（空文字 / 形式不正）。
    """
    if not code:
        raise ValueError("証券コードが空です")
    bare = code.split(".")[0]
    match = _CODE_PATTERN.match(bare)
    if not match:
        raise ValueError(f"証券コードの形式が不正: {code!r}")
    return match.group(1)


def _params_hash(params: dict[str, Any]) -> str:
    """リクエストパラメータの SHA256 short hash（再現性確認用）。"""
    canonical = json.dumps(params, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _normalize_v2_columns(df: pd.DataFrame) -> pd.DataFrame:
    """v2 短縮カラム名を既存互換の長名に展開。

    ``O/H/L/C/Vo/Va`` を ``Open/High/Low/Close/Volume/TurnoverValue`` に
    リネーム。既存カラムが既に長名（v1 互換 / 一部移行期データ）なら
    そのまま保持。
    """
    if df.empty:
        return df
    rename_map = {
        old: new for old, new in V2_COLUMN_RENAME.items()
        if old in df.columns and new not in df.columns
    }
    if rename_map:
        df = df.rename(columns=rename_map)
    return df


# ============================================================
# クライアント
# ============================================================


@dataclass(frozen=True)
class JQuantsClient:
    """J-Quants API v2 クライアント。

    frozen=True で不変性を保ちつつ、``_state: dict`` でレート制限の
    last_request_ts だけ可変にする（EODHDClient / SECEdgarClient と同パターン）。
    v1 と異なり id_token のライフサイクル管理は不要（API key 永続）。

    Args:
        api_key: J-Quants v2 ダッシュボードで発行した永続 API key
        cache: ParquetCache インスタンス
        rate_limit_per_min: 1 分あたりの最大リクエスト数（Light=60）
        base_url: API ベース URL（テスト時のオーバライド用）
        http_client: httpx.Client インスタンス（テスト時のモック注入用）
        _state: 内部状態（last_request_ts のみ）
    """

    api_key: str
    cache: ParquetCache
    rate_limit_per_min: int = DEFAULT_RATE_LIMIT_PER_MIN
    base_url: str = JQUANTS_BASE_URL
    http_client: httpx.Client = field(default_factory=httpx.Client)
    _state: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.api_key:
            raise JQuantsConfigError(
                "JQUANTS_API_KEY が未設定。.env で設定してください。"
                " 取得元: https://jpx-jquants.com/ ダッシュボード"
            )

    # ----- レート制限 ---------------------------------------------------

    def _enforce_rate_limit(self) -> None:
        """連続リクエスト間隔を ``60/rate_limit_per_min`` 秒以上空ける。"""
        if self.rate_limit_per_min <= 0:
            return
        min_interval_sec = 60.0 / self.rate_limit_per_min
        last_ts: float | None = self._state.get("last_request_ts")
        if last_ts is not None:
            elapsed = time.monotonic() - last_ts
            if elapsed < min_interval_sec:
                time.sleep(min_interval_sec - elapsed)
        self._state["last_request_ts"] = time.monotonic()

    # ----- 公開 API -----------------------------------------------------

    def get_eod(
        self,
        code: str,
        *,
        from_date: date,
        to_date: date,
        cache_ttl_sec: int = DEFAULT_CACHE_TTL_SEC,
    ) -> pd.DataFrame:
        """日次 OHLCV データ取得（J-Quants v2 daily bars）。

        Args:
            code: 証券コード（``"7203"`` / ``"7203.T"`` / ``"7203.JP"`` / ``"72030"``
                を全て 4 桁に正規化）
            from_date: 取得開始日
            to_date: 取得終了日（inclusive）
            cache_ttl_sec: キャッシュ TTL（デフォルト 24h）

        Returns:
            OHLCV DataFrame（カラム: ``Date`` / ``Code`` / ``Open`` / ``High`` /
            ``Low`` / ``Close`` / ``Volume`` ...）+ Provenance attrs。
            v2 の短縮カラム名 ``O/H/L/C/Vo`` は内部で長名に展開される。
            データが存在しない場合は空 DataFrame に Provenance attrs のみ付与。

        Raises:
            JQuantsAuthError: API key 無効
            JQuantsAPIError: 4xx / 5xx HTTP エラー
            ValueError: code の形式不正
        """
        normalized = _normalize_code(code)
        from_str = from_date.isoformat()
        to_str = to_date.isoformat()
        cache_key = f"eod_jp_{normalized}_{from_str}_{to_str}"

        cached = self.cache.get(CACHE_PROVIDER, cache_key, cache_ttl_sec)
        if cached is not None:
            return cached

        self._enforce_rate_limit()

        endpoint = "/v2/equities/bars/daily"
        public_params: dict[str, Any] = {
            "code": normalized,
            "from": from_str,
            "to": to_str,
        }
        try:
            response = self.http_client.get(
                f"{self.base_url}{endpoint}",
                params=public_params,
                headers={"x-api-key": self.api_key},
                timeout=30.0,
            )
        except httpx.HTTPError as exc:
            raise JQuantsAPIError(
                f"v2 daily bars 接続失敗: {type(exc).__name__}"
            ) from exc

        if response.status_code == 401 or response.status_code == 403:
            payload = _safe_json(response)
            msg = payload.get("message", "")
            raise JQuantsAuthError(
                f"v2 認証失敗 (status={response.status_code}): {msg}"
            )

        if response.status_code != 200:
            payload = _safe_json(response)
            msg = payload.get("message", "")
            raise JQuantsAPIError(
                f"v2 daily bars failed (status={response.status_code}): {msg}"
            )

        body = _safe_json(response)
        # v2 はレスポンスキー "data" に統一
        rows = body.get("data", []) or []
        df = pd.DataFrame(rows)

        # 短縮カラム名 → 長名展開
        df = _normalize_v2_columns(df)

        # Code を 4 桁に正規化
        if "Code" in df.columns and not df.empty:
            df["Code"] = df["Code"].astype(str).map(_normalize_code)

        attach_provenance(
            df,
            source="J-Quants",
            fetched_at=datetime.now(timezone.utc),
            endpoint=endpoint,
            params_hash=_params_hash(public_params),
            cache_hit=False,
        )

        self.cache.set(CACHE_PROVIDER, cache_key, df)
        return df


# ============================================================
# OHLC 変換ヘルパー（公開純粋関数）
# ============================================================
#
# J-Quants v2 は OHLC を大文字 (Open/High/Low/Close) で返すが、
# 既存の下流レイヤー（atr_stop.calculate_atr,
# risk_metrics.compute_portfolio_returns）は EODHD 互換の小文字
# (high/low/close) を期待する。本ヘルパー群はその差分を吸収する純粋関数。
# 01_home.py のリスク指標経路 / ATR 経路の両方から呼ばれる。


def extract_close_series(df: pd.DataFrame, *, ticker_name: str) -> pd.Series:
    """J-Quants の OHLC DF から Close 系列を抽出（リスク指標経路用）。

    Args:
        df: ``Date`` (str ISO 8601) と ``Close`` (float) カラムを持つ DF。
            ``get_eod`` の戻り値をそのまま渡せる。
        ticker_name: 出力 Series の ``name`` 属性（risk_metrics の銘柄識別用）。

    Returns:
        ``pd.Series(close_float, index=DatetimeIndex, name=ticker_name, dtype=float)``。
        空 DF の場合は空 Series を name 付きで返す。

    Raises:
        ValueError: ``Date`` か ``Close`` カラムが欠落している場合（フェイルファスト）。
    """
    if df.empty:
        return pd.Series([], name=ticker_name, dtype=float)
    if "Date" not in df.columns:
        raise ValueError("DF に Date カラムが存在しません")
    if "Close" not in df.columns:
        raise ValueError("DF に Close カラムが存在しません")
    return pd.Series(
        df["Close"].astype(float).values,
        index=pd.to_datetime(df["Date"]),
        name=ticker_name,
    )


def extract_ohlc_lowercase(df: pd.DataFrame) -> pd.DataFrame:
    """J-Quants の OHLC DF を小文字 ``high/low/close`` に揃える（ATR 経路用）。

    既に小文字カラムが存在する場合は idempotent（EODHD DF をそのまま流せる）。
    値は完全に保持、行数も不変。``atr_stop.calculate_atr`` が要求する
    最低 3 カラム ``high``, ``low``, ``close`` のみ保証。

    Args:
        df: J-Quants の OHLC DF（大文字）または EODHD の OHLC DF（小文字）。

    Returns:
        ``high`` / ``low`` / ``close`` カラムを持つ DF（その他のカラムは保持）。

    Raises:
        ValueError: ``High/Low/Close`` のいずれかが両ケースで欠落の場合。
    """
    rename_map: dict[str, str] = {}
    for upper, lower in (("High", "high"), ("Low", "low"), ("Close", "close")):
        if upper in df.columns and lower not in df.columns:
            rename_map[upper] = lower

    result = df.rename(columns=rename_map) if rename_map else df.copy()

    missing = [c for c in ("high", "low", "close") if c not in result.columns]
    if missing:
        raise ValueError(
            f"OHLC DF に必須カラムが不足: {missing}"
            " (High/Low/Close または high/low/close のいずれか必要)"
        )
    return result


# ============================================================
# ヘルパー
# ============================================================


def _safe_json(response: httpx.Response) -> dict[str, Any]:
    """``response.json()`` を安全に呼ぶ（パース失敗時は空 dict）。"""
    try:
        result = response.json()
        return result if isinstance(result, dict) else {}
    except (ValueError, json.JSONDecodeError):
        return {}
