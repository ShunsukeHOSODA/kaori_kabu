"""_screener_display.py の format helper 単体テスト（Phase 6.1 P-MEDIUM-1 解消）。

CLAUDE.md §9.1 「金額は常に Decimal 型」遵守の検証。
``_format_decimal_pct`` と ``_format_market_cap_usd_billion`` が
``float`` を経由せず Decimal で計算することを確認する。
"""

from __future__ import annotations

from decimal import Decimal

import pandas as pd
import pytest

from src.dashboard.views._screener_display import (
    _format_decimal_pct,
    _format_market_cap_usd_billion,
)


@pytest.mark.unit
class TestFormatDecimalPct:
    """ROC / Earnings Yield 等の比率を百分率文字列に整形。"""

    def test_Decimal入力_2桁表示(self) -> None:
        assert _format_decimal_pct(Decimal("0.123456")) == "12.35%"

    def test_整数入力(self) -> None:
        assert _format_decimal_pct(Decimal("0.25")) == "25.00%"

    def test_ゼロ(self) -> None:
        assert _format_decimal_pct(Decimal("0")) == "0.00%"

    def test_負の値(self) -> None:
        assert _format_decimal_pct(Decimal("-0.05")) == "-5.00%"

    def test_None入力はダッシュ(self) -> None:
        assert _format_decimal_pct(None) == "—"

    def test_NaN入力はダッシュ(self) -> None:
        assert _format_decimal_pct(float("nan")) == "—"

    def test_inf入力はダッシュ(self) -> None:
        """Phase 6.1 review (python-r HIGH): float('inf') はガード対象。"""
        assert _format_decimal_pct(float("inf")) == "—"

    def test_負のinf入力もダッシュ(self) -> None:
        assert _format_decimal_pct(float("-inf")) == "—"

    def test_pandas_NA入力はダッシュ(self) -> None:
        """Phase 6.1 review (python-r HIGH): pd.NA はガード対象。"""
        assert _format_decimal_pct(pd.NA) == "—"

    def test_Decimal_NaN入力はダッシュ(self) -> None:
        """Phase 6.1 review (2 視点一致 MEDIUM): Decimal('NaN') はガード対象。"""
        assert _format_decimal_pct(Decimal("NaN")) == "—"

    def test_Decimal_inf入力はダッシュ(self) -> None:
        assert _format_decimal_pct(Decimal("Infinity")) == "—"

    def test_float入力もDecimal経由で処理(self) -> None:
        """float が混入してもエラーにならず Decimal 経由で処理。"""
        # 0.1 は float では誤差があるが Decimal(str(0.1)) で正規化
        assert _format_decimal_pct(0.1) == "10.00%"


@pytest.mark.unit
class TestFormatMarketCapUsdBillion:
    """時価総額 (USD) を ``$NNN.NB`` 形式に整形。"""

    def test_3490B_アップル相当(self) -> None:
        """Apple ~$3.49T = 3,490,000,000,000 → $3,490.0B"""
        assert (
            _format_market_cap_usd_billion(Decimal("3490000000000"))
            == "$3,490.0B"
        )

    def test_1点5B_小型株(self) -> None:
        assert _format_market_cap_usd_billion(Decimal("1500000000")) == "$1.5B"

    def test_None入力はダッシュ(self) -> None:
        assert _format_market_cap_usd_billion(None) == "—"

    def test_NaN入力はダッシュ(self) -> None:
        assert _format_market_cap_usd_billion(float("nan")) == "—"

    def test_inf入力はダッシュ(self) -> None:
        """Phase 6.1 review (python-r HIGH): float('inf') はガード対象。"""
        assert _format_market_cap_usd_billion(float("inf")) == "—"

    def test_pandas_NA入力はダッシュ(self) -> None:
        """Phase 6.1 review (python-r HIGH): pd.NA はガード対象。"""
        assert _format_market_cap_usd_billion(pd.NA) == "—"

    def test_Decimal_NaN入力はダッシュ(self) -> None:
        """Phase 6.1 review (2 視点一致 MEDIUM): Decimal('NaN') はガード対象。"""
        assert _format_market_cap_usd_billion(Decimal("NaN")) == "—"

    def test_ゼロ(self) -> None:
        assert _format_market_cap_usd_billion(Decimal("0")) == "$0.0B"

    def test_float入力もDecimal経由で処理(self) -> None:
        """float が混入してもエラーにならず Decimal 経由で処理。"""
        assert _format_market_cap_usd_billion(2.5e9) == "$2.5B"
