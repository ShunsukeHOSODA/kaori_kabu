"""Sonnet 4.6 ``model_version`` の動的解決 (Phase 5.5.3 / handoff §5.7)。

``settings.sonnet_model_version`` は ``"claude-sonnet-4-6"`` (model と同値) の
接頭辞として動作する。Anthropic Prompt Caching の cache key は model_version 文字列
の bit-equal 比較なので、日付付きスナップショット ID
(``claude-sonnet-4-6-20250514`` 等) を起動時に取得しておくと、

    - API 側のモデル更新で振る舞いが変わっても古い cache key で続行できる
    - 異なる日付スナップショット間で cache key を分離できる

の 2 つの利点がある。

``.env`` で ``SONNET_MODEL_VERSION`` を override すれば本リゾルバはスキップされ、
override 値が cache key としてそのまま使われる (CLAUDE.md §9.8 Provenance)。

依存方向:
    src.analysis._sonnet_model_resolver
        → anthropic SDK (lazy import 不要、引数で client を受け取るため)
    呼び出し元: src.dashboard.views._screener_compute (Phase 5.5.3 連携)
"""

from __future__ import annotations

import logging
from typing import Final

from src.analysis.anthropic_types import AnthropicLike

logger = logging.getLogger(__name__)

DEFAULT_PREFIX: Final[str] = "claude-sonnet-4-6"


def resolve_sonnet_model_version(
    anthropic_client: AnthropicLike | None,
    *,
    prefix: str = DEFAULT_PREFIX,
    fallback: str | None = None,
) -> str:
    """``anthropic.models.list()`` から prefix 一致の最新日付付き ID を返す。

    Anthropic API のモデル一覧から ``prefix-YYYYMMDD`` 形式の最新スナップショットを
    辞書順降順 (= 日付降順) で選ぶ。Anthropic は日付サフィックスを YYYYMMDD 固定で
    付与するので文字列ソートで安全に最新が選べる。

    Args:
        anthropic_client: ``anthropic.Anthropic`` クライアント or ``None``。
            ``None`` のときは ``fallback`` (or ``prefix``) をそのまま返す。
        prefix: モデル ID 接頭辞。既定 ``"claude-sonnet-4-6"``。
        fallback: API 呼び出し失敗 / 該当なしのとき返す ID。
            ``None`` のときは ``prefix`` を返す。

    Returns:
        日付付き ID (例 ``"claude-sonnet-4-6-20250514"``) または fallback。

    Note:
        例外は logger.warning でログするのみで再 raise しない。UI ループで
        本関数を呼んでも縮退して動作継続する設計 (PRD §FR5 多段縮退)。
    """
    if anthropic_client is None:
        return fallback if fallback is not None else prefix
    try:
        models = anthropic_client.models.list()
        # ``prefix-YYYYMMDD`` パターンを優先、辞書順降順 = 日付降順で latest を選ぶ
        candidates = sorted(
            [
                model.id
                for model in models.data
                if model.id.startswith(prefix + "-")
                and len(model.id) > len(prefix) + 1
            ],
            reverse=True,
        )
        if candidates:
            logger.info(
                "Sonnet model version resolved: %s (prefix=%s)",
                candidates[0],
                prefix,
            )
            return candidates[0]
        logger.warning(
            "No date-suffixed model found for prefix %s, using fallback",
            prefix,
        )
    except Exception as exc:  # noqa: BLE001 — UI ループ向けに広く捕捉
        logger.warning(
            "Failed to resolve Sonnet model version (%s): %s",
            type(exc).__name__,
            exc,
        )
    return fallback if fallback is not None else prefix
