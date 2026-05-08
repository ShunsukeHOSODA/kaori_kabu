"""ParquetCache の単体テスト（CLAUDE.md §9.2 / §9.8.4）。

API 呼び出しは必ず本キャッシュ経由。EOD = 24h, ファンダ = 7d, 13F = 90d 等の
TTL を呼び出し側が指定。df.attrs（Provenance metadata）は Parquet schema
metadata 経由で保持される。
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest


@pytest.mark.unit
class TestParquetCacheBasic:
    """Parquet ベースの TTL キャッシュの基本動作。"""

    def test_set_then_get_は同一データを返す(self, tmp_path: Path) -> None:
        """書き込んだ DataFrame が読み出せる。"""
        from data.cache import ParquetCache

        cache = ParquetCache(base_dir=tmp_path)
        df = pd.DataFrame({"price": [100.0, 200.0], "volume": [1000, 2000]})

        cache.set(provider="EODHD", key="AAPL_2026-05-09", df=df)
        retrieved = cache.get(
            provider="EODHD", key="AAPL_2026-05-09", ttl_sec=3600
        )

        assert retrieved is not None
        pd.testing.assert_frame_equal(
            retrieved.reset_index(drop=True),
            df.reset_index(drop=True),
        )

    def test_未存在キーは_None(self, tmp_path: Path) -> None:
        """存在しないキャッシュは None。"""
        from data.cache import ParquetCache

        cache = ParquetCache(base_dir=tmp_path)

        result = cache.get(provider="EODHD", key="MISSING", ttl_sec=3600)

        assert result is None

    def test_TTL超過は_None(self, tmp_path: Path) -> None:
        """TTL を超えたキャッシュは None。"""
        from data.cache import ParquetCache

        cache = ParquetCache(base_dir=tmp_path)
        df = pd.DataFrame({"x": [1]})
        cache.set(provider="EODHD", key="OLD", df=df)

        # mtime と now に差を作る
        time.sleep(0.05)
        result = cache.get(provider="EODHD", key="OLD", ttl_sec=0)

        assert result is None


@pytest.mark.unit
class TestParquetCacheProvenance:
    """Provenance metadata の Parquet ラウンドトリップ保持。"""

    def test_attrs_がラウンドトリップで保持される(self, tmp_path: Path) -> None:
        """attach_provenance した DataFrame を保存→読込しても attrs が残る。"""
        from data._provenance import attach_provenance
        from data.cache import ParquetCache

        cache = ParquetCache(base_dir=tmp_path)
        df = pd.DataFrame({"x": [1, 2]})
        attach_provenance(
            df,
            source="EODHD",
            fetched_at=datetime(2026, 5, 9, tzinfo=timezone.utc),
            endpoint="/api/eod/AAPL.US",
            params_hash="abc123",
        )

        cache.set(provider="EODHD", key="AAPL", df=df)
        retrieved = cache.get(provider="EODHD", key="AAPL", ttl_sec=3600)

        assert retrieved is not None
        assert retrieved.attrs["source"] == "EODHD"
        assert retrieved.attrs["endpoint"] == "/api/eod/AAPL.US"
        assert retrieved.attrs["params_hash"] == "abc123"

    def test_get時にcache_hit_True_age付きに更新(self, tmp_path: Path) -> None:
        """get で取り出した DataFrame は cache_hit=True と cache_age_sec を持つ。"""
        from data._provenance import attach_provenance
        from data.cache import ParquetCache

        cache = ParquetCache(base_dir=tmp_path)
        df = pd.DataFrame({"x": [1]})
        attach_provenance(
            df,
            source="EODHD",
            fetched_at=datetime(2026, 5, 9, tzinfo=timezone.utc),
            endpoint="/api",
            params_hash="x",
            cache_hit=False,  # 初回取得は False
        )
        cache.set(provider="EODHD", key="A", df=df)

        time.sleep(0.05)  # cache_age_sec が確実に >= 0 になるように
        retrieved = cache.get(provider="EODHD", key="A", ttl_sec=3600)

        assert retrieved is not None
        assert retrieved.attrs["cache_hit"] is True
        assert retrieved.attrs["cache_age_sec"] is not None
        assert retrieved.attrs["cache_age_sec"] >= 0


@pytest.mark.unit
class TestParquetCachePathSafety:
    """キャッシュキーがファイルシステム安全に変換される。"""

    def test_スラッシュを含むキーが安全変換される(self, tmp_path: Path) -> None:
        """ticker に / を含む（例: BRK/B）でも保存・取得できる。"""
        from data.cache import ParquetCache

        cache = ParquetCache(base_dir=tmp_path)
        df = pd.DataFrame({"x": [1]})

        cache.set(provider="EODHD", key="BRK/B_2026-05-09", df=df)
        retrieved = cache.get(
            provider="EODHD", key="BRK/B_2026-05-09", ttl_sec=3600
        )

        assert retrieved is not None
