"""データレイヤー Provenance ヘルパー（CLAUDE.md §9.8.1）。

DataFrame メタデータ（source / fetched_at / cache_hit / endpoint / params_hash）を
``pd.DataFrame.attrs`` 辞書で持たせる方式。Pandas 1.0+ 公式機能で
``to_parquet`` 経由のラウンドトリップでは保持されるが、``pd.concat`` や
``groupby`` 後は失われるので、明示的に :func:`propagate_attrs` で伝播する。

カラムには持たせない（30 年日次 = 7,500 行に同じ値を繰り返すのはメモリ非効率）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Final

import pandas as pd

REQUIRED_PROVENANCE_KEYS: Final[frozenset[str]] = frozenset(
    {"source", "fetched_at", "endpoint", "params_hash", "cache_hit"}
)


def attach_provenance(
    df: pd.DataFrame,
    *,
    source: str,
    fetched_at: datetime,
    endpoint: str,
    params_hash: str,
    cache_hit: bool = False,
    cache_age_sec: int | None = None,
) -> pd.DataFrame:
    """DataFrame.attrs に必須メタデータ 6 キーを付与（同オブジェクト返却）。

    Args:
        df: 対象 DataFrame
        source: データ取得元（例: ``EODHD`` / ``J-Quants`` / ``SEC EDGAR``）
        fetched_at: 取得時刻（tz-aware UTC 推奨）
        endpoint: 呼び出した API エンドポイント
        params_hash: リクエストパラメータの SHA256（再現性確認用）
        cache_hit: キャッシュヒットだったか
        cache_age_sec: キャッシュヒット時のキャッシュ年齢（秒）

    Returns:
        df 自身（attrs 変更後）。チェーン記法用。
    """
    df.attrs["source"] = source
    df.attrs["fetched_at"] = fetched_at
    df.attrs["endpoint"] = endpoint
    df.attrs["params_hash"] = params_hash
    df.attrs["cache_hit"] = cache_hit
    df.attrs["cache_age_sec"] = cache_age_sec
    return df


def propagate_attrs(src: pd.DataFrame, dst: pd.DataFrame) -> pd.DataFrame:
    """src の attrs を dst に浅いコピーで伝播（独立辞書）。

    ``pd.concat`` などで attrs が失われた後に明示的に呼ぶ。``dst.attrs`` と
    ``src.attrs`` は独立した辞書になるので、片方の変更は他方に伝わらない。

    Returns:
        dst 自身（チェーン記法用）。
    """
    dst.attrs = dict(src.attrs)
    return dst


def assert_has_provenance(df: pd.DataFrame) -> None:
    """必須メタデータの存在を実行時検証。

    Raises:
        ValueError: 必須キー（source / fetched_at / endpoint / params_hash /
            cache_hit）のいずれかが欠落している場合。
    """
    missing = REQUIRED_PROVENANCE_KEYS - df.attrs.keys()
    if missing:
        raise ValueError(
            f"DataFrame is missing required provenance keys: {sorted(missing)}"
        )


def get_provenance(df: pd.DataFrame) -> dict[str, Any]:
    """DataFrame.attrs を読み取り用に独立辞書としてコピー返却。"""
    return dict(df.attrs)
