"""データレイヤー Provenance ヘルパーの単体テスト（CLAUDE.md §9.8.1）。

df.attrs にメタデータを持たせる方式を採用。Pandas 1.0+ 公式機能で
to_parquet で保持されるが、連結・スライス時の伝播は明示的に必要。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest


@pytest.mark.unit
class TestAttachProvenance:
    """DataFrame.attrs に Provenance metadata を付与する。"""

    def test_必須キー6つが_attrs_に格納される(self) -> None:
        """attach_provenance 後、source / fetched_at / endpoint / params_hash /
        cache_hit / cache_age_sec の 6 キーが揃う。"""
        from data._provenance import attach_provenance

        df = pd.DataFrame({"x": [1, 2, 3]})
        fetched = datetime(2026, 5, 9, 10, 30, tzinfo=timezone.utc)

        out = attach_provenance(
            df,
            source="EODHD",
            fetched_at=fetched,
            endpoint="/api/eod/AAPL.US",
            params_hash="abc123",
            cache_hit=False,
        )

        assert out.attrs["source"] == "EODHD"
        assert out.attrs["fetched_at"] == fetched
        assert out.attrs["endpoint"] == "/api/eod/AAPL.US"
        assert out.attrs["params_hash"] == "abc123"
        assert out.attrs["cache_hit"] is False
        assert out.attrs["cache_age_sec"] is None


@pytest.mark.unit
class TestPropagateAttrs:
    """連結・スライス後に attrs が失われないよう明示的に伝播する。"""

    def test_src_の_attrs_が_dst_にコピーされる(self) -> None:
        from data._provenance import propagate_attrs

        src = pd.DataFrame({"x": [1, 2]})
        src.attrs = {"source": "EODHD", "cache_hit": True}
        dst = pd.DataFrame({"x": [3, 4]})

        propagate_attrs(src, dst)

        assert dst.attrs == {"source": "EODHD", "cache_hit": True}

    def test_伝播後_src変更が_dst_に伝わらない(self) -> None:
        """浅いコピーで attrs 独立保持を保証。"""
        from data._provenance import propagate_attrs

        src = pd.DataFrame({"x": [1]})
        src.attrs = {"source": "EODHD"}
        dst = pd.DataFrame({"x": [2]})

        propagate_attrs(src, dst)
        src.attrs["source"] = "MUTATED"

        assert dst.attrs["source"] == "EODHD"


@pytest.mark.unit
class TestAssertHasProvenance:
    """必須メタデータの存在を実行時検証する（pytest fixture / runtime check 用）。"""

    def test_必須キー揃っていれば例外なし(self) -> None:
        from data._provenance import assert_has_provenance

        df = pd.DataFrame({"x": [1]})
        df.attrs = {
            "source": "EODHD",
            "fetched_at": datetime.now(timezone.utc),
            "endpoint": "/api/eod/AAPL.US",
            "params_hash": "abc123",
            "cache_hit": False,
        }

        # 例外が発生しなければ OK
        assert_has_provenance(df)

    def test_キー不足で_ValueError_発生(self) -> None:
        from data._provenance import assert_has_provenance

        df = pd.DataFrame({"x": [1]})
        df.attrs = {"source": "EODHD"}  # 他のキー欠如

        with pytest.raises(ValueError, match="provenance"):
            assert_has_provenance(df)
