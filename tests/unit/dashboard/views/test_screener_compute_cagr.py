"""_compute_cagr_from_yearly の単体テスト（Phase 6.1 P-HIGH-1 解消）。

CLAUDE.md §9.1 「金額は常に Decimal 型」遵守の検証。
``float`` を経由しない Decimal-only 計算 (``Decimal.ln`` + ``Decimal.exp``) で
``ratio ** (1/N) - 1`` が等価な精度で得られることを確認する。
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.dashboard.views._screener_compute import _compute_cagr_from_yearly


@pytest.mark.unit
class TestComputeCagrFromYearly:
    """CAGR 計算の Decimal-only 実装検証。"""

    def test_5年で2倍_CAGRは約148パーセント(self) -> None:
        """成長率 = 2^(1/5) - 1 ≈ 0.148698 → Decimal で同精度。"""
        yearly = {
            "2020-12-31": {"revenue": Decimal("100")},
            "2021-12-31": {"revenue": Decimal("120")},
            "2022-12-31": {"revenue": Decimal("140")},
            "2023-12-31": {"revenue": Decimal("160")},
            "2024-12-31": {"revenue": Decimal("180")},
            "2025-12-31": {"revenue": Decimal("200")},
        }
        result = _compute_cagr_from_yearly(yearly, "revenue", years=5)
        assert result is not None
        assert isinstance(result, Decimal)
        # 2^(1/5) - 1 = 0.148698354997...
        expected = Decimal("0.148698")
        assert abs(result - expected) < Decimal("0.000001")

    def test_空dictはNone(self) -> None:
        assert _compute_cagr_from_yearly({}, "revenue", years=5) is None

    def test_履歴不足はNone(self) -> None:
        """5 年 CAGR を計算するには 6 件必要。3 件のみなら None。"""
        yearly = {
            "2023-12-31": {"revenue": Decimal("100")},
            "2024-12-31": {"revenue": Decimal("120")},
            "2025-12-31": {"revenue": Decimal("140")},
        }
        assert _compute_cagr_from_yearly(yearly, "revenue", years=5) is None

    def test_過去値がゼロはNone(self) -> None:
        yearly = {
            "2020-12-31": {"revenue": Decimal("0")},
            "2021-12-31": {"revenue": Decimal("120")},
            "2022-12-31": {"revenue": Decimal("140")},
            "2023-12-31": {"revenue": Decimal("160")},
            "2024-12-31": {"revenue": Decimal("180")},
            "2025-12-31": {"revenue": Decimal("200")},
        }
        assert _compute_cagr_from_yearly(yearly, "revenue", years=5) is None

    def test_最新値がゼロはNone(self) -> None:
        yearly = {
            "2020-12-31": {"revenue": Decimal("100")},
            "2021-12-31": {"revenue": Decimal("120")},
            "2022-12-31": {"revenue": Decimal("140")},
            "2023-12-31": {"revenue": Decimal("160")},
            "2024-12-31": {"revenue": Decimal("180")},
            "2025-12-31": {"revenue": Decimal("0")},
        }
        assert _compute_cagr_from_yearly(yearly, "revenue", years=5) is None

    def test_負の値はNone(self) -> None:
        yearly = {
            "2020-12-31": {"revenue": Decimal("-100")},
            "2021-12-31": {"revenue": Decimal("120")},
            "2022-12-31": {"revenue": Decimal("140")},
            "2023-12-31": {"revenue": Decimal("160")},
            "2024-12-31": {"revenue": Decimal("180")},
            "2025-12-31": {"revenue": Decimal("200")},
        }
        assert _compute_cagr_from_yearly(yearly, "revenue", years=5) is None

    def test_フィールド欠損はNone(self) -> None:
        yearly = {
            "2020-12-31": {"other": Decimal("100")},
            "2021-12-31": {"revenue": Decimal("120")},
            "2022-12-31": {"revenue": Decimal("140")},
            "2023-12-31": {"revenue": Decimal("160")},
            "2024-12-31": {"revenue": Decimal("180")},
            "2025-12-31": {"revenue": Decimal("200")},
        }
        assert _compute_cagr_from_yearly(yearly, "revenue", years=5) is None

    def test_3年CAGRも計算可能(self) -> None:
        """``years`` パラメータの汎用性を確認。"""
        yearly = {
            "2022-12-31": {"revenue": Decimal("100")},
            "2023-12-31": {"revenue": Decimal("110")},
            "2024-12-31": {"revenue": Decimal("121")},
            "2025-12-31": {"revenue": Decimal("133.1")},
        }
        result = _compute_cagr_from_yearly(yearly, "revenue", years=3)
        assert result is not None
        # 1.331^(1/3) - 1 = 0.1（10% 厳密）
        assert abs(result - Decimal("0.1")) < Decimal("0.000001")

    def test_戻り値は6桁にquantizeされる(self) -> None:
        """``quantize(Decimal("0.000001"))`` で 6 桁固定。"""
        yearly = {
            "2020-12-31": {"revenue": Decimal("100")},
            "2021-12-31": {"revenue": Decimal("120")},
            "2022-12-31": {"revenue": Decimal("140")},
            "2023-12-31": {"revenue": Decimal("160")},
            "2024-12-31": {"revenue": Decimal("180")},
            "2025-12-31": {"revenue": Decimal("200")},
        }
        result = _compute_cagr_from_yearly(yearly, "revenue", years=5)
        assert result is not None
        # 小数点以下 6 桁
        assert result.as_tuple().exponent == -6
