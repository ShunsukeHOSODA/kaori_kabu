# ruff: noqa: RUF002
# 理由: docstring 内の GBM 数式に Black-Scholes 標準記法の
# ギリシャ文字 (mu, sigma) を残すため。RUF002 (ambiguous unicode in docstring)
# を file-level で無効化。
"""Monte Carlo GBM シミュレーション (純粋関数層)。

Phase 5.4.0-A: ``src/dashboard/views/05_monte_carlo.py`` に直書きされていた
幾何ブラウン運動 (GBM) 計算ロジックを再利用可能な純粋関数として切り出し。

設計方針:
    - **Streamlit dependency を持ち込まない**。pure ``numpy`` / ``pandas`` /
      ``plotly`` のみで構成し、ダッシュボード以外の用途 (Decision Log の事後
      検証、Claude TOP 5 詳細カード内の個別 fan chart 等) でも再利用可能にする。
    - **決定論性必須** (CLAUDE.md §9.8 Provenance)。``np.random.default_rng(seed)``
      で seed を明示し、同一入力なら同一出力を保証する。
    - **一本線予測の禁止** (CLAUDE.md §9.3)。ファンチャートは必ず
      5/25/50/75/95 percentile 帯で描画する。

学術的バックボーン:
    Geometric Brownian Motion (Black-Scholes 1973):
        dS_t = μ S_t dt + σ S_t dW_t
    離散化:
        log_return_t = (μ - 0.5 σ²) dt + σ √dt · Z_t,  Z_t ~ N(0, 1)
        S_t = S_0 · exp(cumsum(log_return))
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

# 1 年あたりの営業日数 (米国・日本市場の概数)。
# GBM の離散化単位 dt = 1 / TRADING_DAYS_PER_YEAR。
TRADING_DAYS_PER_YEAR: int = 252

# fan chart で描画する percentile の標準セット。
# 必ず 5 段 (悲観 - 25%帯 - 中央値 - 75%帯 - 楽観) を出す。
DEFAULT_PERCENTILES: tuple[int, ...] = (5, 25, 50, 75, 95)


def simulate_gbm_paths(
    start_price: float,
    mu: float,
    sigma: float,
    days: int = 252,
    n_paths: int = 1000,
    seed: int = 42,
) -> np.ndarray:
    """幾何ブラウン運動 (GBM) で価格パスを生成する。

    Args:
        start_price: 初期価格 (例: JPY 建てなら 1_000_000、USD 株価なら 150.0)。
        mu: 年率期待リターン (例: 0.08 = 年 8%)。
        sigma: 年率ボラティリティ (例: 0.18 = 年率 18%)。
        days: 予測日数 (営業日)。デフォルト 252 営業日 (約 1 年)。
        n_paths: 生成するシミュレーションパス数。デフォルト 1000。
        seed: 乱数 seed。決定論的再現のため必須。

    Returns:
        shape ``(n_paths, days + 1)`` の ``np.ndarray``。
        column 0 は全て ``start_price`` (= day 0)。
        column 1..days は GBM で生成された価格。

    Notes:
        ``np.random.default_rng(seed)`` を使用するため、同一 ``seed`` で
        呼び出した場合の結果は完全に一致する (Decision Log 検証要件)。
    """
    rng = np.random.default_rng(seed)
    dt = 1.0 / TRADING_DAYS_PER_YEAR
    # 標準正規乱数 Z ~ N(0, 1) を (n_paths, days) で一括生成。
    z = rng.standard_normal((n_paths, days))
    # GBM 離散化: log_return = drift + diffusion。
    drift = (mu - 0.5 * sigma**2) * dt
    diffusion = sigma * np.sqrt(dt) * z
    log_returns = drift + diffusion
    # cumsum で累積対数リターンを取り、exp で価格に戻す。
    paths = np.zeros((n_paths, days + 1))
    paths[:, 0] = start_price
    paths[:, 1:] = start_price * np.exp(np.cumsum(log_returns, axis=1))
    return paths


def percentiles_for_fan_chart(
    paths: np.ndarray,
    percentiles: tuple[int, ...] = DEFAULT_PERCENTILES,
) -> pd.DataFrame:
    """価格パス配列から各日のパーセンタイル系列を計算して DataFrame で返す。

    Args:
        paths: ``simulate_gbm_paths`` が返す shape ``(n_paths, days + 1)``
            の ndarray。
        percentiles: 計算するパーセンタイル値のタプル。
            デフォルト ``(5, 25, 50, 75, 95)`` で 5 段ファンチャート用。

    Returns:
        index = day (``0..days``)、columns = ``[f"p{p}" for p in percentiles]``
        の ``pd.DataFrame``。各セルは該当 day における該当 percentile の価格。

    Notes:
        column 命名は ``p{percentile}`` 形式で統一 (例: ``p5``, ``p50``, ``p95``)。
        UI 側で ``percentile_df["p50"].iloc[-1]`` のようにアクセス可能。
    """
    # np.percentile は axis=0 (パス方向) で計算 → shape (n_percentiles, days + 1)。
    values = np.percentile(paths, list(percentiles), axis=0)
    # 各 percentile を column として持つ DataFrame に変換。
    # values.T は shape (days + 1, n_percentiles) になり、行が day、列が percentile。
    return pd.DataFrame(
        values.T,
        columns=[f"p{p}" for p in percentiles],
    )


def render_fan_chart_plotly(
    percentile_df: pd.DataFrame,
    ticker: str,
) -> go.Figure:
    """ファンチャート (5 段 percentile 帯) を Plotly Figure で返す。

    Args:
        percentile_df: ``percentiles_for_fan_chart`` の戻り値。
            columns に ``p5`` / ``p25`` / ``p50`` / ``p75`` / ``p95`` を必須で含む。
        ticker: チャートタイトルに埋め込む銘柄識別子
            (例: ``"AAPL"`` / ``"ポートフォリオ全体"``)。

    Returns:
        5 traces を持つ ``plotly.graph_objects.Figure``。
            - trace 0: p95 楽観帯 (lightblue 線)
            - trace 1: p5 悲観帯 (lightblue 線、fill=tonexty で 90% 確率帯描画)
            - trace 2: p75 (blue 線)
            - trace 3: p25 (blue 線、fill=tonexty で 50% 確率帯描画)
            - trace 4: p50 中央値 (darkblue、width=3)

    Notes:
        既存 ``05_monte_carlo.py`` L90-124 の見た目を保持。
        title は ``"モンテカルロ確率分布: {ticker}"`` 形式。
    """
    days = percentile_df.index
    fig = go.Figure()
    fig.add_traces(
        [
            # 楽観帯の上端 (p95) — fill なし、後段の p5 で tonexty 用に置く。
            go.Scatter(
                x=days,
                y=percentile_df["p95"],
                fill=None,
                mode="lines",
                line_color="lightblue",
                name="95%ile (楽観)",
            ),
            # 悲観帯の下端 (p5) — 直前 trace との間 (= p5〜p95) を薄青で塗る。
            go.Scatter(
                x=days,
                y=percentile_df["p5"],
                fill="tonexty",
                mode="lines",
                line_color="lightblue",
                fillcolor="rgba(0,150,255,0.1)",
                name="5%ile (悲観)",
            ),
            # 50% 確率帯の上端 (p75) — fill なし、後段の p25 で tonexty 用に置く。
            go.Scatter(
                x=days,
                y=percentile_df["p75"],
                fill=None,
                mode="lines",
                line_color="blue",
                name="75%ile",
            ),
            # 50% 確率帯の下端 (p25) — 直前 trace との間 (= p25〜p75) を濃青で塗る。
            go.Scatter(
                x=days,
                y=percentile_df["p25"],
                fill="tonexty",
                mode="lines",
                line_color="blue",
                fillcolor="rgba(0,100,255,0.3)",
                name="25%ile",
            ),
            # 中央値 (p50) — 一本太線で「最も起こりやすい未来」を強調。
            go.Scatter(
                x=days,
                y=percentile_df["p50"],
                mode="lines",
                line={"color": "darkblue", "width": 3},
                name="中央値 (50%ile)",
            ),
        ]
    )
    fig.update_layout(
        title=f"モンテカルロ確率分布: {ticker}",
        xaxis_title="経過営業日",
        yaxis_title="価格",
        height=600,
    )
    return fig
