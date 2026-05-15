"""Polymarket Gamma API クライアント（CLAUDE.md §9.1 / §9.2 / §9.8）。

予測市場（Polymarket）の確率値を取得し、マクロイベント（Fed 利上げ確率 /
景気後退確率 / 地政学リスク）の市場コンセンサスを LLM ランキング判断の
入力にする。実取引は行わず参照のみ。

API リファレンス:
    https://gamma-api.polymarket.com/markets
    （Gamma API は public read-only、認証不要、レート制限 60 req/min）

学術根拠:
    Wolfers & Zitzewitz 2004 "Prediction Markets"（予測市場の効率性）
    Manski 2006 "Interpreting the Predictions of Prediction Markets"

キャッシュ:
    TTL = 6h（マクロイベントは数時間単位で価格が動くため EOD よりは短めに）
    パス: ``data/cache/Polymarket/{topic}_{params_hash}.parquet``

Provenance（CLAUDE.md §9.8.1）:
    戻り値が ``dict[str, Decimal]`` のため、内部 DataFrame の attrs ではなく
    モジュール変数 :data:`_last_metadata` 経由で最終取得のメタデータを公開する。
    呼び出し側は直接 ``polymarket_client._last_metadata`` を参照して監査可能。
"""

from __future__ import annotations

import hashlib
import json
import logging
from decimal import Decimal
from pathlib import Path
from typing import Any, Final

import httpx
import pandas as pd

from ._provenance import attach_provenance
from .cache import ParquetCache

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

POLYMARKET_GAMMA_ENDPOINT: Final[str] = "https://gamma-api.polymarket.com/markets"
"""Gamma API ``/markets`` の絶対 URL。Provenance.endpoint としても使う。"""

PROVIDER_NAME: Final[str] = "Polymarket"
"""キャッシュ provider 識別子（``data/cache/Polymarket/`` 配下）。"""

DEFAULT_CACHE_TTL_SEC: Final[int] = 6 * 3600
"""キャッシュ TTL（6 時間）。マクロイベントは数時間単位で価格が動く。"""

DEFAULT_HTTP_TIMEOUT_SEC: Final[float] = 30.0


# topic 名 → Polymarket Gamma API クエリパラメータの対応表。
# 未知 topic はここに存在しないので warning + skip される。
_TOPIC_TO_QUERY: Final[dict[str, dict[str, str]]] = {
    "fed_rate_cut_2026": {
        "category": "macro",
        "slug": "fed-rate-cut-2026",
    },
    "us_recession_2026": {
        "category": "macro",
        "slug": "us-recession-2026",
    },
    "geopolitical_risk": {
        "category": "macro",
        "slug": "geopolitical-2026",
    },
}


# ---------------------------------------------------------------------------
# Provenance 公開用モジュール変数
# ---------------------------------------------------------------------------

_last_metadata: dict[str, Any] = {
    "source": PROVIDER_NAME,
    "fetched_at": None,
    "cache_hit": False,
    "cache_age_sec": None,
    "endpoint": POLYMARKET_GAMMA_ENDPOINT,
    "params_hash": "",
}
"""最終取得の Provenance（CLAUDE.md §9.8.1 の DataFrame.attrs 相当）。

``fetch_macro_probabilities`` 呼び出しの後、呼び出し側はこの辞書を読み取って
ソース・取得時刻・キャッシュヒット状況・パラメータハッシュを監査できる。
複数 topic を 1 回の呼び出しで処理する場合、``params_hash`` は全 topic を
ソートして結合したハッシュとなる（再現性確認用）。
"""


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------


def _params_hash(payload: Any) -> str:
    """リクエストパラメータの SHA256 ハッシュ（先頭 16 文字、再現性確認用）。"""
    serialized = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


def _make_default_http_client() -> httpx.Client:
    """既定の httpx.Client（タイムアウト 30 秒、リダイレクト追従）。"""
    return httpx.Client(
        timeout=DEFAULT_HTTP_TIMEOUT_SEC, follow_redirects=True
    )


def _make_default_cache() -> ParquetCache:
    """既定の Parquet キャッシュ（``data/cache/polymarket/``）。"""
    return ParquetCache(base_dir=Path("data/cache/polymarket"))


def _extract_yes_probability(records: list[dict[str, Any]]) -> Decimal | None:
    """Polymarket Gamma レスポンス（list[market]）から YES 確率を抽出。

    各 market の ``outcomePrices`` は ``["YES_price", "NO_price"]`` の 2 要素
    文字列配列（YES + NO = 1.0）。0 番目を ``Decimal(str(x))`` で変換して返す。

    レスポンスが空配列 / outcomePrices 欠損 / 数値変換失敗の場合は ``None``。
    """
    if not records:
        return None
    market = records[0]
    prices = market.get("outcomePrices")
    if not isinstance(prices, list) or not prices:
        return None
    try:
        return Decimal(str(prices[0]))
    except (ValueError, ArithmeticError, TypeError):
        return None


def _fetch_single_topic(
    *,
    topic: str,
    http_client: httpx.Client,
    cache: ParquetCache,
    cache_ttl_sec: int,
) -> tuple[Decimal | None, bool, int | None]:
    """単一トピックの確率を取得（キャッシュ → API の順）。

    Returns:
        ``(probability, cache_hit, cache_age_sec)``。
        - ``probability`` は取得失敗時 ``None``。
        - ``cache_hit`` はキャッシュヒット時 ``True``。
        - ``cache_age_sec`` はキャッシュヒット時のキャッシュ年齢（秒）。

    Raises:
        ValueError: HTTP エラー等で取得不能の場合。呼び出し側が catch する想定。
    """
    query = _TOPIC_TO_QUERY[topic]
    cache_key = f"{topic}_{_params_hash(query)}"

    # 1) キャッシュ確認
    cached = cache.get(PROVIDER_NAME, cache_key, cache_ttl_sec)
    if cached is not None:
        prob: Decimal | None = None
        if not cached.empty and "probability" in cached.columns:
            try:
                prob = Decimal(str(cached.iloc[0]["probability"]))
            except (ValueError, ArithmeticError, TypeError):
                prob = None
        return prob, True, int(cached.attrs.get("cache_age_sec") or 0)

    # 2) API call
    try:
        response = http_client.get(
            POLYMARKET_GAMMA_ENDPOINT,
            params=query,
            timeout=DEFAULT_HTTP_TIMEOUT_SEC,
        )
    except httpx.HTTPError as err:
        logger.warning(
            "polymarket fetch failed: topic=%s reason=%s", topic, err
        )
        raise ValueError(
            f"Polymarket fetch failed for topic={topic}: {err}"
        ) from err

    if not response.is_success:
        body_preview = (response.text or "")[:200]
        logger.warning(
            "polymarket non-success: topic=%s status=%s body=%s",
            topic,
            response.status_code,
            body_preview,
        )
        raise ValueError(
            f"Polymarket API {response.status_code} for topic={topic}: "
            f"{body_preview}"
        )

    try:
        records = response.json()
    except (ValueError, json.JSONDecodeError) as err:
        logger.warning(
            "polymarket invalid JSON: topic=%s reason=%s", topic, err
        )
        raise ValueError(
            f"Polymarket returned invalid JSON for topic={topic}: {err}"
        ) from err

    if not isinstance(records, list):
        logger.warning(
            "polymarket unexpected schema: topic=%s type=%s",
            topic,
            type(records).__name__,
        )
        raise ValueError(
            f"Polymarket unexpected response schema for topic={topic}"
        )

    probability = _extract_yes_probability(records)
    if probability is None:
        logger.warning(
            "polymarket probability extraction failed: topic=%s", topic
        )

    # 3) キャッシュへ書き込み（Provenance 付き DataFrame として保存）
    df = pd.DataFrame(
        [
            {
                "topic": topic,
                "slug": query.get("slug", ""),
                "probability": (
                    float(probability)
                    if probability is not None
                    else float("nan")
                ),
            }
        ]
    )
    attach_provenance(
        df,
        source=PROVIDER_NAME,
        fetched_at=pd.Timestamp.now(tz="UTC").to_pydatetime(),
        endpoint=POLYMARKET_GAMMA_ENDPOINT,
        params_hash=_params_hash(query),
        cache_hit=False,
    )
    cache.set(PROVIDER_NAME, cache_key, df)
    return probability, False, None


# ---------------------------------------------------------------------------
# 公開 API
# ---------------------------------------------------------------------------


def fetch_macro_probabilities(
    topics: list[str],
    *,
    http_client: httpx.Client | None = None,
    cache: ParquetCache | None = None,
    cache_ttl_sec: int = DEFAULT_CACHE_TTL_SEC,
) -> dict[str, Decimal]:
    """Polymarket Gamma API からマクロ予測市場の確率を取得する。

    各トピックを ``_TOPIC_TO_QUERY`` 経由で Polymarket Gamma ``/markets``
    のクエリに変換し、市場の YES 確率（``outcomePrices[0]``）を ``Decimal``
    で返す。未知トピックは警告ログを残して結果から除外する（silent fail を
    避けつつ、1 件の typo で全体を落とさない方針）。

    キャッシュは ``ParquetCache`` 経由で TTL = 6h（CLAUDE.md §9.2）。
    Provenance は :data:`_last_metadata` モジュール変数に最終取得分が記録される
    （CLAUDE.md §9.8.1、戻り値が ``dict`` のため ``df.attrs`` で持てない）。

    Args:
        topics: 取得対象のトピック識別子のリスト。
            例: ``["fed_rate_cut_2026", "us_recession_2026"]``
        http_client: DI 用 ``httpx.Client``。``None`` なら既定値を生成。
            テスト時に ``MagicMock(spec=httpx.Client)`` を注入する想定。
        cache: Parquet TTL キャッシュ。``None`` なら
            ``data/cache/polymarket/`` を作成。
        cache_ttl_sec: キャッシュ TTL 秒数（既定 6h = ``6 * 3600``）。

    Returns:
        ``{topic: Decimal('0.62'), ...}`` 形式の確率辞書。
        確率抽出に失敗したトピックは含まれない（warning ログのみ）。
        未知トピック・空 ``topics`` リストは空辞書を返す。

    Raises:
        ValueError: 全トピックで HTTP エラー / 想定外スキーマが発生した場合。
            部分的成功時は warning ログのみで成功分を返す。

    Examples:
        >>> from data.polymarket_client import fetch_macro_probabilities
        >>> probs = fetch_macro_probabilities(["fed_rate_cut_2026"])
        >>> probs["fed_rate_cut_2026"]
        Decimal('0.62')
    """
    if not topics:
        return {}

    if http_client is None:
        http_client = _make_default_http_client()
    if cache is None:
        cache = _make_default_cache()

    result: dict[str, Decimal] = {}
    cache_hit_any = False
    cache_age_observed: int | None = None
    errors: list[str] = []

    # トピック群全体の params_hash（再現性確認用）
    combined_hash = _params_hash(sorted(topics))

    for topic in topics:
        if topic not in _TOPIC_TO_QUERY:
            logger.warning(
                "polymarket unknown topic skipped: topic=%s (known=%s)",
                topic,
                sorted(_TOPIC_TO_QUERY.keys()),
            )
            continue

        try:
            probability, cache_hit, cache_age = _fetch_single_topic(
                topic=topic,
                http_client=http_client,
                cache=cache,
                cache_ttl_sec=cache_ttl_sec,
            )
        except ValueError as err:
            errors.append(f"{topic}: {err}")
            continue

        if probability is not None:
            result[topic] = probability
        if cache_hit:
            cache_hit_any = True
            cache_age_observed = cache_age

    # Provenance 更新（モジュール変数経由）
    _last_metadata.update(
        {
            "source": PROVIDER_NAME,
            "fetched_at": pd.Timestamp.now(tz="UTC"),
            "cache_hit": cache_hit_any,
            "cache_age_sec": cache_age_observed,
            "endpoint": POLYMARKET_GAMMA_ENDPOINT,
            "params_hash": combined_hash,
        }
    )

    # 既知トピックを 1 件以上要求していて、かつ全件失敗した場合のみ ValueError
    known_requested = [t for t in topics if t in _TOPIC_TO_QUERY]
    if known_requested and not result and errors:
        raise ValueError(
            "Polymarket fetch failed for all topics: " + " | ".join(errors)
        )

    return result
