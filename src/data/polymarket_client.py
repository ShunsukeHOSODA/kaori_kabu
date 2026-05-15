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
    戻り値は :class:`MacroProbabilities` (dict[str, Decimal] サブクラス) で、
    ``.provenance`` 属性に取得時メタデータを保持する。呼び出し側は通常の
    dict と同じ ``result[topic]`` でアクセスでき、監査時は ``result.provenance``
    でソース・取得時刻・キャッシュヒット状況を取り出せる。Phase 5.3 review
    でモジュールグローバル mutable 設計の問題が 3 reviewer 一致で指摘された
    ため、Session 5 で戻り値同梱に再設計（スレッドセーフ・呼び出し対応）。
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

PROVIDER_NAME: Final[str] = "polymarket"
"""キャッシュ provider 識別子（``data/cache/polymarket/`` 配下）。

Phase 5.3 review (C-L-1) で ``_make_default_cache`` が ``data/cache/polymarket``
を base_dir に指定する一方で ``PROVIDER_NAME = "Polymarket"`` を渡すことで
``data/cache/polymarket/Polymarket/`` という意図しないネストが発生する問題が
指摘されたため小文字に統一した。"""

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
# Provenance 同梱戻り値（dict サブクラス、スレッドセーフ）
# ---------------------------------------------------------------------------


class MacroProbabilities(dict[str, Decimal]):
    """確率辞書 + Provenance 属性を持つ拡張 dict。

    Phase 5.3 review で「モジュールグローバル mutable な ``_last_metadata`` は
    スレッドセーフでなく、Streamlit の並行リクエストで監査性が崩れる」と
    3 reviewer 一致で指摘されたため (P-CRIT-1 / C-H-2 / S-M-2)、Session 5 で
    戻り値同梱型に再設計。

    呼び出し側は通常の ``dict[str, Decimal]`` として使えるため後方互換性が
    保たれる (``result[topic]`` / ``len(result)`` / iteration すべて従来通り)。
    監査時は ``result.provenance`` で取得時メタデータを取り出せる。

    Attributes:
        provenance: ソース・取得時刻・キャッシュヒット状況・params_hash 等の
            CLAUDE.md §9.8.1 必須メタデータ。
    """

    __slots__ = ("provenance",)

    def __init__(
        self,
        data: dict[str, Decimal] | None = None,
        *,
        provenance: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(data or {})
        self.provenance: dict[str, Any] = provenance or {}


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------


def _params_hash(payload: Any) -> str:
    """リクエストパラメータの SHA256 ハッシュ（先頭 16 文字、再現性確認用）。

    ``default=str`` は使用しない (Phase 5.3 review C-M-1 / handoff §2.5 の
    「型ずれ隠蔽機構」教訓に整合)。``payload`` が JSON シリアライズ不能な
    型を含む場合は ``TypeError`` を raise させて早期検出する。
    """
    serialized = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


def _make_default_http_client() -> httpx.Client:
    """既定の httpx.Client（タイムアウト 30 秒、リダイレクト追従なし）。

    Phase 5.3 review (S-L-1) で「``POLYMARKET_GAMMA_ENDPOINT`` は固定 URL の
    ため follow_redirects は不要かつ 169.254 系メタデータエンドポイントへの
    リダイレクト誘導リスクがある」と指摘されたため最小権限原則に従い無効化。
    """
    return httpx.Client(
        timeout=DEFAULT_HTTP_TIMEOUT_SEC, follow_redirects=False
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
        # Phase 5.3 review (P-M-1) 対策: 失敗値 (None) はキャッシュしない。
        # ``float("nan")`` で書き込むと次回 ``Decimal(str(nan))`` が
        # InvalidOperation を起こすため、書き込み自体をスキップして次回
        # API リトライを許容する (PRD §FR5 多段縮退の精神)。
        return None, False, None

    # 3) キャッシュへ書き込み（Provenance 付き DataFrame として保存、成功時のみ）
    df = pd.DataFrame(
        [
            {
                "topic": topic,
                "slug": query.get("slug", ""),
                "probability": float(probability),
            }
        ]
    )
    attach_provenance(
        df,
        source=PROVIDER_NAME,
        fetched_at=pd.Timestamp.now(tz="UTC"),
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
) -> MacroProbabilities:
    """Polymarket Gamma API からマクロ予測市場の確率を取得する。

    各トピックを ``_TOPIC_TO_QUERY`` 経由で Polymarket Gamma ``/markets``
    のクエリに変換し、市場の YES 確率（``outcomePrices[0]``）を ``Decimal``
    で返す。未知トピックは警告ログを残して結果から除外する（silent fail を
    避けつつ、1 件の typo で全体を落とさない方針）。

    キャッシュは ``ParquetCache`` 経由で TTL = 6h（CLAUDE.md §9.2）。
    Provenance は戻り値の ``.provenance`` 属性に同梱される
    （CLAUDE.md §9.8.1、Phase 5.3 review で「グローバル mutable な
    ``_last_metadata`` はスレッドセーフでない」と 3 reviewer 一致で指摘
    されたため Session 5 で再設計）。

    Args:
        topics: 取得対象のトピック識別子のリスト。
            例: ``["fed_rate_cut_2026", "us_recession_2026"]``
        http_client: DI 用 ``httpx.Client``。``None`` なら既定値を生成。
            テスト時に ``MagicMock(spec=httpx.Client)`` を注入する想定。
        cache: Parquet TTL キャッシュ。``None`` なら
            ``data/cache/polymarket/`` を作成。
        cache_ttl_sec: キャッシュ TTL 秒数（既定 6h = ``6 * 3600``）。

    Returns:
        :class:`MacroProbabilities` (``dict[str, Decimal]`` サブクラス) で
        ``result[topic] == Decimal('0.62')`` の通常 dict アクセスに加え
        ``result.provenance`` で取得メタデータを参照できる。確率抽出に
        失敗したトピックは含まれない (warning ログのみ)。

    Raises:
        ValueError: 全トピックで HTTP エラー / 想定外スキーマが発生した場合。
            部分的成功時は warning ログのみで成功分を返す。

    Examples:
        >>> from data.polymarket_client import fetch_macro_probabilities
        >>> probs = fetch_macro_probabilities(["fed_rate_cut_2026"])
        >>> probs["fed_rate_cut_2026"]
        Decimal('0.62')
        >>> probs.provenance["source"]
        'polymarket'
    """
    if not topics:
        return MacroProbabilities(
            provenance={
                "source": PROVIDER_NAME,
                "fetched_at": pd.Timestamp.now(tz="UTC"),
                "cache_hit": False,
                "cache_age_sec": None,
                "endpoint": POLYMARKET_GAMMA_ENDPOINT,
                "params_hash": "",
            }
        )

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

    provenance = {
        "source": PROVIDER_NAME,
        "fetched_at": pd.Timestamp.now(tz="UTC"),
        "cache_hit": cache_hit_any,
        "cache_age_sec": cache_age_observed,
        "endpoint": POLYMARKET_GAMMA_ENDPOINT,
        "params_hash": combined_hash,
    }

    # 既知トピックを 1 件以上要求していて、かつ全件失敗した場合のみ ValueError
    known_requested = [t for t in topics if t in _TOPIC_TO_QUERY]
    if known_requested and not result and errors:
        raise ValueError(
            "Polymarket fetch failed for all topics: " + " | ".join(errors)
        )

    return MacroProbabilities(result, provenance=provenance)
