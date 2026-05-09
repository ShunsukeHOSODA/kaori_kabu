"""analysis.risk_metrics の単体テスト。

CLAUDE.md §5 / §9.8（Provenance）/ Phase 3.2 に準拠。
empyrical-reloaded ラッパー + provenance metadata の正しさを保証する。
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pandas as pd
import pytest

from analysis.risk_metrics import (
    RiskMetrics,
    RiskMetricsMetadata,
    compute_portfolio_returns,
    compute_risk_metrics,
)


@pytest.mark.unit
class TestComputePortfolioReturns:
    """ウェイト付きポートフォリオ daily returns の検証。"""

    def test_単一銘柄_ウェイト_1_でリターンが各銘柄一致(self) -> None:
        idx = pd.date_range("2025-01-01", periods=5, freq="B")
        prices = pd.Series([100.0, 101.0, 102.0, 100.0, 105.0], index=idx)

        result = compute_portfolio_returns(
            {"AAPL": prices},
            {"AAPL": Decimal("1.0")},
        )

        # pct_change で先頭 1 行 NaN dropped → 4 行残る
        assert len(result) == 4
        assert result.iloc[0] == pytest.approx(0.01)
        assert result.iloc[1] == pytest.approx(102.0 / 101.0 - 1.0)
        assert result.iloc[2] == pytest.approx(100.0 / 102.0 - 1.0)
        assert result.iloc[3] == pytest.approx(105.0 / 100.0 - 1.0)

    def test_2銘柄_等ウェイト_でリターンの加重平均(self) -> None:
        idx = pd.date_range("2025-01-01", periods=3, freq="B")
        a = pd.Series([100.0, 110.0, 121.0], index=idx)  # +10% / +10%
        b = pd.Series([100.0, 90.0, 81.0], index=idx)    # -10% / -10%

        result = compute_portfolio_returns(
            {"A": a, "B": b},
            {"A": Decimal("0.5"), "B": Decimal("0.5")},
        )

        # 等ウェイトで daily portfolio return = 0.5 * 0.10 + 0.5 * (-0.10) = 0.0
        assert result.iloc[0] == pytest.approx(0.0, abs=1e-9)
        assert result.iloc[1] == pytest.approx(0.0, abs=1e-9)

    def test_ウェイト合計が_1_でないと_ValueError(self) -> None:
        idx = pd.date_range("2025-01-01", periods=3, freq="B")
        prices = pd.Series([100.0, 101.0, 102.0], index=idx)

        with pytest.raises(ValueError, match="weights must sum"):
            compute_portfolio_returns(
                {"AAPL": prices},
                {"AAPL": Decimal("0.5")},
            )

    def test_ティッカー集合不一致で_ValueError(self) -> None:
        idx = pd.date_range("2025-01-01", periods=3, freq="B")
        prices = pd.Series([100.0, 101.0, 102.0], index=idx)

        with pytest.raises(ValueError, match="ticker sets"):
            compute_portfolio_returns(
                {"AAPL": prices},
                {"AAPL": Decimal("0.5"), "MSFT": Decimal("0.5")},
            )

    def test_空_dict_で_ValueError(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            compute_portfolio_returns({}, {})


@pytest.mark.unit
class TestComputeRiskMetrics:
    """empyrical 結果の格納と provenance 必須フィールドの保証。"""

    def _stable_returns(self, value: float = 0.0005, n: int = 252) -> pd.Series:
        """日次一定リターン（既定: ~0.05%/日 = 年率 ~13%）。"""
        idx = pd.date_range("2024-01-02", periods=n, freq="B")
        return pd.Series([value] * n, index=idx, name="port_ret")

    def test_主要フィールドが妥当な範囲で計算される(self) -> None:
        returns = self._stable_returns()

        metrics = compute_risk_metrics(returns, input_data_source="EODHD")

        assert isinstance(metrics, RiskMetrics)
        # 一定リターンなので Max DD = 0、ボラ ≈ 0
        assert metrics.max_drawdown == pytest.approx(0.0, abs=1e-9)
        assert metrics.annualized_volatility == pytest.approx(0.0, abs=1e-9)
        # 年率 ~13% が出るはず（empyrical の compounding 計算）
        assert 0.10 < metrics.annualized_return < 0.16

    def test_metadata_必須フィールドが完備されている(self) -> None:
        returns = self._stable_returns()

        metrics = compute_risk_metrics(returns, input_data_source="EODHD")

        meta: RiskMetricsMetadata = metrics.metadata
        assert meta.calculation_method == "risk_metrics_v1"
        assert "Sharpe" in meta.academic_source
        assert "Sortino" in meta.academic_source
        assert "VaR" in meta.academic_source
        assert meta.input_data_source == "EODHD"
        assert meta.var_confidence == 0.05
        assert meta.risk_free_rate == 0.0
        assert " to " in meta.input_data_period
        # calculated_at は近過去（10 秒以内）
        delta = (datetime.now(timezone.utc) - meta.calculated_at).total_seconds()
        assert 0 <= delta < 10

    def test_returns_が_2_観測未満で_ValueError(self) -> None:
        idx = pd.date_range("2025-01-01", periods=1, freq="B")
        returns = pd.Series([0.01], index=idx)

        with pytest.raises(ValueError, match=r"≥ 2"):
            compute_risk_metrics(returns)

    def test_max_drawdown_は_常に_0_以下(self) -> None:
        # 山あり谷ありの非自明リターン
        idx = pd.date_range("2024-01-02", periods=10, freq="B")
        returns = pd.Series(
            [0.05, -0.10, -0.05, 0.03, 0.02, 0.01, -0.08, 0.04, 0.05, 0.02],
            index=idx,
        )

        metrics = compute_risk_metrics(returns)

        assert metrics.max_drawdown <= 0  # empyrical 仕様

    def test_VaR_と_CVaR_は_常に_0_以下_かつ_CVaR_le_VaR(self) -> None:
        idx = pd.date_range("2024-01-02", periods=20, freq="B")
        returns = pd.Series(
            [0.01, -0.02, 0.015, -0.025, 0.005, -0.01, 0.02, -0.03, 0.01, -0.015,
             0.012, -0.008, 0.018, -0.022, 0.006, -0.014, 0.024, -0.028, 0.011, -0.017],
            index=idx,
        )

        metrics = compute_risk_metrics(returns, var_confidence=0.05)

        assert metrics.var_95 <= 0
        assert metrics.cvar_95 <= 0
        # CVaR ≤ VaR（テールはより悪い損失）
        assert metrics.cvar_95 <= metrics.var_95

    def test_var_confidence_を_変更可能(self) -> None:
        returns = self._stable_returns(value=0.001, n=100)

        metrics_5 = compute_risk_metrics(returns, var_confidence=0.05)
        metrics_1 = compute_risk_metrics(returns, var_confidence=0.01)

        assert metrics_5.metadata.var_confidence == 0.05
        assert metrics_1.metadata.var_confidence == 0.01

    def test_RiskMetrics_は_frozen_で不変(self) -> None:
        returns = self._stable_returns()
        metrics = compute_risk_metrics(returns)

        with pytest.raises(Exception):  # FrozenInstanceError
            metrics.sharpe = 99.0  # type: ignore[misc]
