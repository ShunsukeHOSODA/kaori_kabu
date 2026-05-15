"""Monte Carlo GBM シミュレーション関数の単体テスト。

Phase 5.4.0-A: ``src/dashboard/views/05_monte_carlo.py`` から抽出された
``src/analysis/monte_carlo.py`` の純粋関数に対する TDD 5 件。

CLAUDE.md §9.3 「予測」表示ルール準拠:
    - 一本線価格予測禁止
    - 必ず確率分布 (5/25/50/75/95 パーセンタイル) で表示

Phase 5.4.2 で Claude TOP 5 銘柄詳細カード内の個別 fan chart に再利用される
ため、UI レイヤーから独立した純粋関数として設計され、Streamlit dependency
を一切持たない。
"""

from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import pytest

from src.analysis.monte_carlo import (
    percentiles_for_fan_chart,
    render_fan_chart_plotly,
    simulate_gbm_paths,
)


@pytest.mark.unit
def test_simulate_gbm_paths_shape() -> None:
    """戻り値 ndarray の shape が (n_paths, days + 1) であること。"""
    n_paths = 500
    days = 252
    paths = simulate_gbm_paths(
        start_price=100.0,
        mu=0.08,
        sigma=0.18,
        days=days,
        n_paths=n_paths,
        seed=42,
    )
    assert paths.shape == (n_paths, days + 1)


@pytest.mark.unit
def test_simulate_gbm_paths_deterministic() -> None:
    """同一 seed なら結果が完全一致 (np.allclose) すること。

    Decision Log の再現性 (CLAUDE.md §9.8) のため決定論性は必須。
    """
    paths1 = simulate_gbm_paths(
        start_price=100.0,
        mu=0.08,
        sigma=0.18,
        days=252,
        n_paths=1000,
        seed=42,
    )
    paths2 = simulate_gbm_paths(
        start_price=100.0,
        mu=0.08,
        sigma=0.18,
        days=252,
        n_paths=1000,
        seed=42,
    )
    assert np.allclose(paths1, paths2)


@pytest.mark.unit
def test_simulate_gbm_paths_starts_at_start_price() -> None:
    """全パスの column 0 (= day 0) が start_price と一致すること。"""
    start_price = 1_000_000.0
    paths = simulate_gbm_paths(
        start_price=start_price,
        mu=0.08,
        sigma=0.18,
        days=126,
        n_paths=500,
        seed=7,
    )
    assert np.all(paths[:, 0] == start_price)


@pytest.mark.unit
def test_percentiles_for_fan_chart_columns() -> None:
    """戻り DataFrame の columns に p5/p25/p50/p75/p95 が全て含まれること。"""
    paths = simulate_gbm_paths(
        start_price=100.0,
        mu=0.08,
        sigma=0.18,
        days=63,
        n_paths=200,
        seed=42,
    )
    df = percentiles_for_fan_chart(paths)
    for col in ("p5", "p25", "p50", "p75", "p95"):
        assert col in df.columns, f"missing column: {col}"
    assert len(df) == 64  # days + 1


@pytest.mark.unit
def test_render_fan_chart_plotly_has_5_traces() -> None:
    """戻り Figure.data に 5 traces (p5/p25/p50/p75/p95) が含まれること。"""
    paths = simulate_gbm_paths(
        start_price=100.0,
        mu=0.08,
        sigma=0.18,
        days=21,
        n_paths=100,
        seed=42,
    )
    df = percentiles_for_fan_chart(paths)
    fig = render_fan_chart_plotly(df, ticker="AAPL")
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 5
