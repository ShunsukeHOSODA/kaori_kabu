"""analysis._adapters の単体テスト (Phase 5.4.0-D)。

Phase 5.3.2 で導入された :class:`MagicFormulaResultProtocol` に対し、
既存 :class:`MagicFormulaResult` (DataFrame ベース) を per-ticker view に
変換する adapter の挙動を検証する。

検証内容:
    - dict のキーが ticker になる
    - ``magic_formula_score`` が ``score`` 属性に保持される
    - ``roc`` (比率) が ``roc_pct`` (%) に変換される
    - ``earnings_yield`` (比率) が ``earnings_yield_pct`` (%) に変換される
    - 戻り値の view が MagicFormulaResultProtocol を duck typing で満たす
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd
import pytest

from analysis._adapters import (
    MagicFormulaPerTickerView,
    magic_formula_result_to_per_ticker_dict,
)
from analysis.magic_formula import MagicFormulaMetadata, MagicFormulaResult


@pytest.fixture
def sample_mf_result() -> MagicFormulaResult:
    """3 銘柄分の MagicFormulaResult サンプル fixture。"""
    df = pd.DataFrame(
        {
            "ticker": ["AAPL", "MSFT", "GOOG"],
            "magic_formula_score": [2, 4, 6],
            "roc": [Decimal("0.28"), Decimal("0.22"), Decimal("0.18")],
            "earnings_yield": [Decimal("0.15"), Decimal("0.12"), Decimal("0.10")],
            "roc_rank": [1, 2, 3],
            "ey_rank": [1, 2, 3],
        }
    )
    metadata = MagicFormulaMetadata(
        calculation_method="magic_formula_v1",
        academic_source="Greenblatt 2010 Ch.5",
        calculated_at=datetime(2026, 5, 15, tzinfo=UTC),
    )
    return MagicFormulaResult(result=df, metadata=metadata)


@pytest.mark.unit
class TestMagicFormulaAdapter:
    """:func:`magic_formula_result_to_per_ticker_dict` の挙動検証。"""

    def test_adapter_returns_dict_indexed_by_ticker(
        self, sample_mf_result: MagicFormulaResult
    ) -> None:
        """変換後の dict のキーが ticker 一覧と一致する。"""
        out = magic_formula_result_to_per_ticker_dict(sample_mf_result)
        assert set(out.keys()) == {"AAPL", "MSFT", "GOOG"}

    def test_adapter_preserves_magic_formula_score(
        self, sample_mf_result: MagicFormulaResult
    ) -> None:
        """``magic_formula_score`` が ``score`` 属性に float で保持される。"""
        out = magic_formula_result_to_per_ticker_dict(sample_mf_result)
        assert out["AAPL"].score == 2.0
        assert out["GOOG"].score == 6.0

    def test_adapter_converts_roc_to_percent_decimal(
        self, sample_mf_result: MagicFormulaResult
    ) -> None:
        """比率 ``roc`` が % 表記の Decimal に変換される (0.28 → 28.00)。"""
        out = magic_formula_result_to_per_ticker_dict(sample_mf_result)
        assert out["AAPL"].roc_pct == Decimal("28.00")
        assert out["MSFT"].roc_pct == Decimal("22.00")

    def test_adapter_converts_ey_to_percent_decimal(
        self, sample_mf_result: MagicFormulaResult
    ) -> None:
        """比率 ``earnings_yield`` が % 表記の Decimal に変換される。"""
        out = magic_formula_result_to_per_ticker_dict(sample_mf_result)
        assert out["AAPL"].earnings_yield_pct == Decimal("15.00")
        assert out["GOOG"].earnings_yield_pct == Decimal("10.00")

    def test_view_satisfies_magic_formula_protocol(
        self, sample_mf_result: MagicFormulaResult
    ) -> None:
        """duck typing で MagicFormulaResultProtocol の 3 属性を全て持つ確認。"""
        out = magic_formula_result_to_per_ticker_dict(sample_mf_result)
        view = out["AAPL"]
        assert isinstance(view, MagicFormulaPerTickerView)
        assert hasattr(view, "score")
        assert hasattr(view, "roc_pct")
        assert hasattr(view, "earnings_yield_pct")
        assert isinstance(view.roc_pct, Decimal)
        assert isinstance(view.earnings_yield_pct, Decimal)
