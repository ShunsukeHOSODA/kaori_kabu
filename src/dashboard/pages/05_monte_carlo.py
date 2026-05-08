"""Monte Carlo 確率分布ページ — 1000 パス GBM。"""

from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from src.config.settings import settings

st.set_page_config(page_title="Monte Carlo — kaori_kabu", page_icon="🎲", layout="wide")

st.title("🎲 Monte Carlo 確率分布")
st.caption("ポートフォリオの将来パスを 1000 シミュレーションで分布表示")

st.markdown(
    """
    > **一本線の予測は禁止。1000 通りの未来を確率分布で見る。**

    100 万円が 1 年後にいくらになるか、点予測（例: 110 万円）でなく
    分布（例: 90% 確率で 80〜140 万円）で考える習慣を作る。
    """
)

with st.sidebar:
    st.subheader("シミュレーション設定")
    initial = st.number_input(
        "初期資金 (JPY)",
        value=1_000_000,
        step=100_000,
    )
    mu = st.slider("年率リターン (μ)", -0.20, 0.30, 0.08, 0.01)
    sigma = st.slider("ボラティリティ (σ)", 0.05, 0.50, 0.18, 0.01)
    horizon = st.selectbox(
        "ホライズン",
        [21, 63, 126, 252],
        format_func=lambda d: f"{d} 営業日 (約 {d/21:.0f} ヶ月)",
        index=3,
    )
    n_sims = st.slider("シミュレーション数", 100, 10000, settings.mc_simulations, 100)
    run = st.button("🎲 シミュレーション実行", type="primary")

if run:
    rng = np.random.default_rng(42)
    dt = 1 / 252
    Z = rng.standard_normal((n_sims, horizon))
    drift = (mu - 0.5 * sigma**2) * dt
    diffusion = sigma * np.sqrt(dt) * Z
    log_returns = drift + diffusion
    paths = np.zeros((n_sims, horizon + 1))
    paths[:, 0] = initial
    paths[:, 1:] = initial * np.exp(np.cumsum(log_returns, axis=1))

    percentiles = np.percentile(paths, [5, 25, 50, 75, 95], axis=0)
    days = np.arange(horizon + 1)

    fig = go.Figure()
    fig.add_traces(
        [
            go.Scatter(
                x=days, y=percentiles[4], fill=None, mode="lines",
                line_color="lightblue", name="95%ile (楽観)",
            ),
            go.Scatter(
                x=days, y=percentiles[0], fill="tonexty", mode="lines",
                line_color="lightblue", fillcolor="rgba(0,150,255,0.1)",
                name="5%ile (悲観)",
            ),
            go.Scatter(
                x=days, y=percentiles[3], fill=None, mode="lines",
                line_color="blue", name="75%ile",
            ),
            go.Scatter(
                x=days, y=percentiles[1], fill="tonexty", mode="lines",
                line_color="blue", fillcolor="rgba(0,100,255,0.3)",
                name="25%ile",
            ),
            go.Scatter(
                x=days, y=percentiles[2], mode="lines",
                line=dict(color="darkblue", width=3),
                name="中央値（50%ile）",
            ),
        ]
    )
    fig.update_layout(
        title="Monte Carlo 確率分布（fan chart）",
        xaxis_title="営業日",
        yaxis_title="ポートフォリオ価値 (JPY)",
        height=600,
    )
    st.plotly_chart(fig, use_container_width=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("中央値（50%ile）", f"¥{int(percentiles[2, -1]):,}")
    with col2:
        st.metric("悲観シナリオ（5%ile）", f"¥{int(percentiles[0, -1]):,}")
    with col3:
        st.metric("楽観シナリオ（95%ile）", f"¥{int(percentiles[4, -1]):,}")
else:
    st.info("左サイドバーでパラメータを設定し「シミュレーション実行」を押してください。")

st.divider()
with st.expander("⚠️ GBM の限界"):
    st.markdown(
        """
        - GBM はリターンが正規分布と仮定（実際は **fat tail**）
        - ボラティリティ・相関は過去ヒストリカルから推定（将来変動）
        - **ブラックスワンイベントは織り込めない**（COVID / リーマン級の暴落）
        - リスク削減策: 過去の最悪期を含むデータで σ を計算
        """
    )
