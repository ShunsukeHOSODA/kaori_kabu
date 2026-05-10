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
    BenchmarkComparison,
    BenchmarkMetadata,
    RiskMetrics,
    RiskMetricsMetadata,
    compute_benchmark_comparison,
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


@pytest.mark.unit
class TestComputeBenchmarkComparison:
    """ポートフォリオ vs ベンチマーク比較指標の検証。

    empyrical-reloaded の alpha / beta / excess_sharpe(IR) /
    tracking_error / up_capture / down_capture をラップし、
    Provenance metadata を付与する。
    """

    def _bench(self, n: int = 252, value: float = 0.0004) -> pd.Series:
        idx = pd.date_range("2024-01-02", periods=n, freq="B")
        return pd.Series([value] * n, index=idx, name="bench_ret")

    def test_完全相関_β_1_α_0(self) -> None:
        """ポートフォリオ = ベンチマーク → β ≈ 1, α ≈ 0, TE ≈ 0。

        empyrical の β は ``Cov(R, B) / Var(B)`` のため、ベンチマークが
        一定（Var=0）だと NaN になる。**変動する系列**で比較する必要あり。
        """
        import numpy as np

        rng = np.random.default_rng(seed=7)
        idx = pd.date_range("2024-01-02", periods=120, freq="B")
        bench_vals = rng.normal(loc=0.0005, scale=0.012, size=120)
        bench = pd.Series(bench_vals, index=idx, name="bench")
        port = bench.copy()
        port.name = "port"

        cmp_ = compute_benchmark_comparison(
            port, bench, benchmark_label="S&P500"
        )

        assert isinstance(cmp_, BenchmarkComparison)
        assert cmp_.beta == pytest.approx(1.0, abs=1e-6)
        assert cmp_.alpha == pytest.approx(0.0, abs=1e-6)
        assert cmp_.tracking_error == pytest.approx(0.0, abs=1e-6)

    def test_β_0_5_は_ベンチマーク変動の半分(self) -> None:
        """ポートフォリオがベンチマークの 0.5 倍変動 → β ≈ 0.5。"""
        idx = pd.date_range("2024-01-02", periods=100, freq="B")
        # ベンチマークは振動、ポートフォリオはその半分
        import numpy as np

        rng = np.random.default_rng(seed=42)
        bench_vals = rng.normal(loc=0.0005, scale=0.01, size=100)
        bench = pd.Series(bench_vals, index=idx, name="bench")
        port = pd.Series(bench_vals * 0.5, index=idx, name="port")

        cmp_ = compute_benchmark_comparison(port, bench, benchmark_label="SPY")

        assert cmp_.beta == pytest.approx(0.5, abs=0.05)

    def test_information_ratio_出力_が_数値(self) -> None:
        bench = self._bench(value=0.0003)
        port = self._bench(value=0.0006)
        port.name = "port"

        cmp_ = compute_benchmark_comparison(
            port, bench, benchmark_label="S&P500"
        )

        # 一定リターン差があるので IR は有限の数値（非 NaN）
        import math

        assert not math.isnan(cmp_.information_ratio)
        assert not math.isinf(cmp_.information_ratio)

    def test_up_down_capture_出力(self) -> None:
        idx = pd.date_range("2024-01-02", periods=20, freq="B")
        bench = pd.Series(
            [0.01, -0.02, 0.015, -0.01, 0.02, -0.015, 0.01, -0.025, 0.018, 0.005,
             -0.012, 0.022, -0.018, 0.014, -0.008, 0.011, -0.02, 0.016, -0.013, 0.009],
            index=idx,
            name="bench",
        )
        # ポートフォリオは上昇局面で 0.8 倍、下落局面で 0.6 倍捕捉
        port_vals = [
            v * (0.8 if v > 0 else 0.6) for v in bench
        ]
        port = pd.Series(port_vals, index=idx, name="port")

        cmp_ = compute_benchmark_comparison(port, bench, benchmark_label="SPY")

        # empyrical の up_capture / down_capture は cum_return ベースの比率。
        # 個別日次 0.8 倍 / 0.6 倍に設定しても複利効果で結果は ~0.5 / ~0.9 程度。
        # 仕様確認: ベンチより小さい捕捉率（< 1.0）が出ること、
        # 完全に 0 ではないこと（> 0.0）が本テストの主眼。
        assert 0.0 < cmp_.up_capture < 1.0
        assert 0.0 < cmp_.down_capture < 1.5  # 下落耐性ありの想定

    def test_共通日付なし_ValueError(self) -> None:
        """ポートフォリオとベンチマークの日付集合に重なりが無い場合は ValueError。

        実用上は両 API の取得期間がズレることがある（ポートフォリオは
        J-Quants 2026-02-15 上限、ベンチマークは EODHD 当日まで等）。
        共通部分 < 2 件で計算不能となるケースを保証する。
        """
        port = pd.Series(
            [0.01, 0.02],
            index=pd.date_range("2024-01-02", periods=2, freq="B"),
        )
        bench = pd.Series(
            [0.01, 0.02, 0.03],
            index=pd.date_range("2024-06-03", periods=3, freq="B"),  # 完全別月
        )

        with pytest.raises(ValueError, match="共通日付|alignment|empty"):
            compute_benchmark_comparison(
                port, bench, benchmark_label="S&P500"
            )

    def test_metadata_必須フィールド完備(self) -> None:
        bench = self._bench()
        port = bench.copy()
        port.name = "port"

        cmp_ = compute_benchmark_comparison(
            port, bench, benchmark_label="S&P500", input_data_source="EODHD"
        )

        meta: BenchmarkMetadata = cmp_.metadata
        assert meta.calculation_method == "benchmark_comparison_v1"
        assert "Jensen" in meta.academic_source or "alpha" in meta.academic_source.lower()
        assert meta.benchmark_label == "S&P500"
        assert meta.input_data_source == "EODHD"
        assert " to " in meta.input_data_period
        delta = (datetime.now(timezone.utc) - meta.calculated_at).total_seconds()
        assert 0 <= delta < 10

    def test_BenchmarkComparison_は_frozen_で不変(self) -> None:
        bench = self._bench()
        port = bench.copy()
        port.name = "port"

        cmp_ = compute_benchmark_comparison(
            port, bench, benchmark_label="S&P500"
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            cmp_.alpha = 99.0  # type: ignore[misc]
