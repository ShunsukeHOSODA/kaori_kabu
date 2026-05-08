"""Parquet TTL キャッシュ（CLAUDE.md §9.2 / §9.8.4）。

API 呼び出しは必ず本キャッシュ経由。レイヤー別 TTL:
    - EOD            = 24h  (CACHE_TTL_EOD)
    - ファンダメンタル = 7d   (CACHE_TTL_FUNDAMENTAL)
    - 13F            = 90d  (CACHE_TTL_13F)
    - ニュース       = 1h   (CACHE_TTL_NEWS)

Provenance metadata (``df.attrs``) は Parquet schema metadata 経由で
ラウンドトリップ保持される（Pandas 1.0+ ``to_parquet(engine="pyarrow")``）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final

import pandas as pd

CACHE_FILE_SUFFIX: Final[str] = ".parquet"
# ファイルシステムで安全でない文字（macOS / Linux / Windows 全環境を考慮）
_UNSAFE_PATH_CHARS: Final[str] = '/:?*<>|"\\'

# pandas は attrs を JSON 経由で Parquet schema metadata に保存するため、
# datetime / Decimal などの非 JSON 型はマーカー付き辞書で文字列化する。
_TYPE_MARKER: Final[str] = "__kabu_type__"


def _serialize_attrs(attrs: dict[str, Any]) -> dict[str, Any]:
    """attrs を JSON 互換に変換（datetime → ISO 8601 文字列）。"""
    out: dict[str, Any] = {}
    for key, value in attrs.items():
        if isinstance(value, datetime):
            out[key] = {_TYPE_MARKER: "datetime", "value": value.isoformat()}
        else:
            out[key] = value
    return out


def _deserialize_attrs(attrs: dict[str, Any]) -> dict[str, Any]:
    """マーカー付き辞書を元の Python オブジェクトに復元。"""
    out: dict[str, Any] = {}
    for key, value in attrs.items():
        if isinstance(value, dict) and value.get(_TYPE_MARKER) == "datetime":
            out[key] = datetime.fromisoformat(value["value"])
        else:
            out[key] = value
    return out


@dataclass(frozen=True)
class ParquetCache:
    """Provider / Key 単位の Parquet キャッシュ。

    ファイル配置:
        ``{base_dir}/{provider}/{safe_key}.parquet``

    Args:
        base_dir: キャッシュルートディレクトリ。なければ自動作成。
    """

    base_dir: Path

    def __post_init__(self) -> None:
        # frozen でも `__post_init__` で外部リソースの初期化は OK
        self.base_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_key(key: str) -> str:
        """ファイルシステム不可文字を ``_`` に置換。"""
        result = key
        for ch in _UNSAFE_PATH_CHARS:
            result = result.replace(ch, "_")
        return result

    def _path(self, provider: str, key: str) -> Path:
        """キャッシュファイルパスを構築（provider 別サブディレクトリ）。"""
        provider_dir = self.base_dir / self._safe_key(provider)
        provider_dir.mkdir(parents=True, exist_ok=True)
        return provider_dir / f"{self._safe_key(key)}{CACHE_FILE_SUFFIX}"

    def is_fresh(self, path: Path, ttl_sec: int) -> bool:
        """ファイルが TTL 内（mtime からの経過秒 <= ttl_sec）か。"""
        if not path.exists():
            return False
        age = datetime.now(timezone.utc).timestamp() - path.stat().st_mtime
        return age <= ttl_sec

    def get(
        self, provider: str, key: str, ttl_sec: int
    ) -> pd.DataFrame | None:
        """キャッシュ取得。存在 + TTL 内なら DataFrame、それ以外は None。

        取得時に ``cache_hit=True`` と ``cache_age_sec`` を attrs に書き込む。
        これによりキャッシュ由来か新規取得かを下流で判別可能。
        """
        path = self._path(provider, key)
        if not self.is_fresh(path, ttl_sec):
            return None
        df = pd.read_parquet(path, engine="pyarrow")
        # serialize 時のマーカー付き辞書を元の型に戻す
        df.attrs = _deserialize_attrs(df.attrs)
        age = int(
            datetime.now(timezone.utc).timestamp() - path.stat().st_mtime
        )
        df.attrs["cache_hit"] = True
        df.attrs["cache_age_sec"] = age
        return df

    def set(self, provider: str, key: str, df: pd.DataFrame) -> Path:
        """キャッシュ書き込み。``df.attrs`` は Parquet schema metadata に保持。

        attrs の datetime / 非 JSON 型はマーカー付き辞書で文字列化してから保存。
        get 時に :func:`_deserialize_attrs` で元の型に復元される。

        Returns:
            書き込み先の Path。
        """
        path = self._path(provider, key)
        # 元の df を破壊しないよう浅いコピーで attrs を差し替え
        out = df.copy(deep=False)
        out.attrs = _serialize_attrs(df.attrs)
        out.to_parquet(path, engine="pyarrow", index=False)
        return path
