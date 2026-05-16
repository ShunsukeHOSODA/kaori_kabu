"""Sonnet ranking judge の 24h ディスクキャッシュ層 (PRD §FR6)。

:mod:`analysis.ranking_judge` から切り出した永続化ヘルパー群。元ファイルが
1,020 行に肥大化した Phase 6 第 2 弾 refactor の成果物で、キャッシュ I/O と
バッチ判定だけを集約する。元ファイル末尾で re-export しているため、外部
コードは ``from analysis.ranking_judge import rank_with_claude_batch`` でも
``from analysis.ranking_judge_cache import rank_with_claude_batch`` でも
等価にアクセスできる（ただしテストで ``_now_utc`` を ``monkeypatch.setattr``
する場合は本モジュールを直接対象にする必要がある — 循環 import 対策の都合）。

責務:
    - キャッシュキー算出 (:func:`_cache_path`)
    - JSON 読み出しと TTL 判定 (:func:`_read_cache`)
    - JSON 書き込み (:func:`_write_cache`)
    - 銘柄一括判定 + キャッシュ層 (:func:`rank_with_claude_batch`)
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Final

from pydantic import ValidationError

from .anthropic_types import AnthropicLike
from .ranking_judge import (
    DEFAULT_MODEL,
    DEFAULT_MODEL_VERSION,
    RankingMetadata,
    RankingResult,
    RankingSignalBundle,
    _compute_bundle_hash,
    rank_single_with_claude,
)

logger = logging.getLogger(__name__)

# PRD §FR6: Sonnet ranking judge 結果の 24h キャッシュ TTL（秒）。
# mtime からの経過秒がこれを超えるとキャッシュ無効化、再判定が発生する。
CACHE_TTL_SEC: Final[int] = 24 * 3600


def _now_utc() -> datetime:
    """現在時刻 (UTC) を返すテスト可能フック。

    :func:`_read_cache` の TTL 判定で参照される。テストでは
    ``monkeypatch.setattr(rjc, "_now_utc", lambda: future)`` で将来時刻を
    注入し、キャッシュ TTL 超過を再現する。**`rj._now_utc` の monkeypatch
    は効かないため、必ず本モジュール（``ranking_judge_cache``）を patch
    対象にすること** — Python の名前解決上、``_read_cache`` 内のグローバル
    ``_now_utc`` ルックアップは本モジュールの binding を見るため。
    """
    return datetime.now(UTC)


def _cache_path(
    cache_dir: Path,
    bundle: RankingSignalBundle,
    model_version: str,
) -> Path:
    """キャッシュファイルパスを bundle + model_version の SHA256 で決定論的に生成する。

    キャッシュキー成分:
        - ``ticker`` / ``composite_preset`` / ``regime``: 人間可読の判別子
        - ``_compute_bundle_hash(bundle)``: 入力シグナル束 SHA256（§9.8.4 input_bundle_hash と同一）
        - ``model_version``: モデル変更時に旧キャッシュを無効化

    ファイル名は ``{ticker}_{key[:32]}.json``（ticker prefix でディスク走査時の可視性確保）。
    """
    key_src = (
        f"{bundle.ticker}|{bundle.composite_preset}|{bundle.regime}|"
        f"{_compute_bundle_hash(bundle)}|{model_version}"
    )
    key = hashlib.sha256(key_src.encode()).hexdigest()[:32]
    return cache_dir / f"{bundle.ticker}_{key}.json"


def _read_cache(cache_path: Path, *, ttl_sec: int) -> RankingResult | None:
    """キャッシュファイルから :class:`RankingResult` を復元する。

    ヒット条件: ファイル存在 + mtime からの経過秒 <= ``ttl_sec``。
    復元時は ``metadata.cache_hit=True`` / ``cache_age_sec=int(age)`` で上書き。

    Returns:
        - 復元成功時: :class:`RankingResult`
        - ファイル不在 / TTL 超過 / JSON 不正 / スキーマ不整合: ``None``

    Note:
        ``validate_no_price_predictions`` は書き込み時点で検証済みのため
        再実行しない（キャッシュ済 = 安全と見做す）。
    """
    if not cache_path.exists():
        return None
    stat = cache_path.stat()
    mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
    age = (_now_utc() - mtime).total_seconds()
    if age > ttl_sec:
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        md_dict = payload.pop("metadata")
        md_dict["calculated_at"] = datetime.fromisoformat(md_dict["calculated_at"])
        metadata = RankingMetadata(**md_dict)
        metadata = replace(metadata, cache_hit=True, cache_age_sec=int(age))
        # JSON 永続化で失われる Pydantic 側の型を復元
        for k in ("confidence", "confidence_adjusted", "kelly_multiplier"):
            payload[k] = Decimal(str(payload[k]))
        payload["supporting_signals"] = tuple(payload["supporting_signals"])
        payload["risk_signals"] = tuple(payload["risk_signals"])
        return RankingResult(**payload, metadata=metadata)
    except (ValueError, KeyError, TypeError, json.JSONDecodeError, ValidationError) as exc:
        # code-review MEDIUM 対策: 破損キャッシュは miss 扱いで再生成するが、
        # silent failure を避けるため WARN ログを残す（ディスク破損 / スキーマ
        # 変更 / シリアライズバグの早期発見に利用）。
        logger.warning(
            "ranking cache 破損のため miss 扱い: path=%s error=%s",
            cache_path,
            type(exc).__name__,
        )
        return None


def _write_cache(cache_path: Path, result: RankingResult) -> None:
    """:class:`RankingResult` を JSON でディスクに永続化する。

    ``metadata`` は ``@dataclass`` で Pydantic から見ると arbitrary type のため、
    ``dataclasses.asdict`` で dict 化してから合成する。``datetime`` は ISO 8601
    string に明示変換し、json.dumps の ``default=str`` 救済に依存しない。
    """
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = result.model_dump(mode="json", exclude={"metadata"})
    md_dict = asdict(result.metadata)
    md_dict["calculated_at"] = result.metadata.calculated_at.isoformat()
    payload["metadata"] = md_dict
    # code-review MEDIUM 対策: ``default=str`` は型ずれを隠す救済機構として
    # 機能してしまうので削除。``Decimal`` は ``model_dump(mode='json')``、
    # ``datetime`` は明示 ``isoformat()`` で予め変換済みであり、未知の非
    # 直列化型が混入した場合は ``TypeError`` を発生させて早期検出する。
    cache_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def rank_with_claude_batch(
    bundles: list[RankingSignalBundle],
    *,
    anthropic_client: AnthropicLike,
    cache_dir: Path,
    model: str = DEFAULT_MODEL,
    model_version: str = DEFAULT_MODEL_VERSION,
    ttl_sec: int = CACHE_TTL_SEC,
) -> list[RankingResult]:
    """銘柄一括ランキング判定 — PRD §FR6 24h キャッシュ層 + §FR5 多段縮退付き。

    各 bundle について:
        1. ``_cache_path`` でキャッシュキーを算出
        2. ``_read_cache`` でヒット判定（ヒット時はそのまま結果に追加）
        3. ミス時は ``rank_single_with_claude`` を呼び出して判定
        4. ``fallback_reason is None`` の場合のみ ``_write_cache`` で永続化
           （PRD §FR5 多段縮退結果は一時的失敗扱い、次回呼び出しで再試行）

    Args:
        bundles: ランキング対象のシグナル束（順序保持）。
        anthropic_client: Anthropic SDK クライアント（messages.create を持つ）。
        cache_dir: キャッシュ JSON の保存先ディレクトリ（不在時は自動作成）。
        model: モデル名（既定: ``DEFAULT_MODEL``）。
        model_version: モデルバージョン（キャッシュキー成分にも使用、既定: ``DEFAULT_MODEL_VERSION``）。
        ttl_sec: キャッシュ TTL 秒数（既定: ``CACHE_TTL_SEC`` = 24h）。

    Returns:
        :class:`RankingResult` の list（入力 bundles と順序対応）。
    """
    results: list[RankingResult] = []
    for bundle in bundles:
        cache_path = _cache_path(cache_dir, bundle, model_version)
        cached = _read_cache(cache_path, ttl_sec=ttl_sec)
        if cached is not None:
            results.append(cached)
            continue
        result = rank_single_with_claude(
            bundle, anthropic_client=anthropic_client, model=model
        )
        if result.fallback_reason is None:
            _write_cache(cache_path, result)
        results.append(result)
    return results
