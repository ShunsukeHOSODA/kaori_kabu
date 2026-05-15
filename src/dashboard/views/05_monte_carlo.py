"""モンテカルロ確率分布ページ — 1000 通りの未来シミュレーション（素人向け説明付き）。"""

from __future__ import annotations

import streamlit as st

from src.analysis.monte_carlo import (
    percentiles_for_fan_chart,
    render_fan_chart_plotly,
    simulate_gbm_paths,
)
from src.config.settings import settings

st.set_page_config(
    page_title="将来予測（モンテカルロ） — kaori_kabu",
    page_icon="🎲",
    layout="wide",
)

st.title("🎲 将来予測（モンテカルロ確率分布）")
st.caption("ポートフォリオの 1 年後・3 年後の値動きを 1000 通りの未来として描画")

st.markdown(
    """
    > **「絶対に + 100 万円」予測は禁止。1000 通りの未来を確率分布で見る。**

    100 万円が 1 年後にいくらになるか —
    点予測（例: 110 万円）でなく分布（例: 90% 確率で 80 〜 140 万円、悲観 5% で 65 万円）
    として考える習慣を作る。

    **モンテカルロ法** = サイコロ振りを 1000 回繰り返して未来パスを描き、その分布を見る手法。
    値動きは「平均リターン μ」と「ばらつき σ（ボラティリティ）」で表される正規分布から
    ランダム生成される（後述の <span translate="no">GBM</span> モデル）。
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.subheader("シミュレーション設定")
    st.caption("初期資金・期待リターン・リスク・期間を指定")

    initial = st.number_input(
        "初期資金 (JPY)",
        value=1_000_000,
        step=100_000,
    )
    mu = st.slider(
        "年率リターン μ（期待される平均利益率）",
        -0.20,
        0.30,
        0.08,
        0.01,
        help="例: 0.08 = 年 8% で増える前提。米国株インデックスの長期平均は約 7-10%",
    )
    sigma = st.slider(
        "ボラティリティ σ（値動きの激しさ＝年率標準偏差）",
        0.05,
        0.50,
        0.18,
        0.01,
        help="例: 0.18 = 年率 18%。米国株インデックス並み。個別株は 0.30-0.50 が普通",
    )
    horizon = st.selectbox(
        "予測期間",
        [21, 63, 126, 252],
        format_func=lambda d: f"{d} 営業日（約 {d/21:.0f} ヶ月）",
        index=3,
    )
    n_sims = st.slider(
        "シミュレーション回数",
        100,
        10000,
        settings.mc_simulations,
        100,
        help="多いほど精度は上がるが計算が遅くなる。1000 で十分実用的",
    )
    run = st.button("🎲 シミュレーション実行", type="primary")

if run:
    # Phase 5.4.0-A: GBM 計算は src/analysis/monte_carlo.py の純粋関数に委譲。
    paths = simulate_gbm_paths(
        start_price=float(initial),
        mu=mu,
        sigma=sigma,
        days=horizon,
        n_paths=n_sims,
        seed=42,
    )
    percentile_df = percentiles_for_fan_chart(paths)
    fig = render_fan_chart_plotly(percentile_df, ticker="ポートフォリオ全体")
    # 既存 view 固有の y 軸ラベル (JPY 通貨) は上書きで補正。
    fig.update_layout(yaxis_title="ポートフォリオ価値 (JPY)")
    st.plotly_chart(fig, use_container_width=True)

    st.caption(
        "🔍 読み方: 中央線が「最も起こりやすい未来」、青濃い帯が「50% 確率レンジ」、"
        "薄い帯が「90% 確率レンジ」。帯の外側 10% は極端なシナリオ。"
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(
            "中央値（50% の確率でこれより上）",
            f"¥{int(percentile_df['p50'].iloc[-1]):,}",
        )
    with col2:
        st.metric(
            "悲観シナリオ（5% の確率で起こる最悪寄り）",
            f"¥{int(percentile_df['p5'].iloc[-1]):,}",
        )
    with col3:
        st.metric(
            "楽観シナリオ（5% の確率で起こる最良寄り）",
            f"¥{int(percentile_df['p95'].iloc[-1]):,}",
        )
else:
    st.info("左サイドバーでパラメータを設定し「シミュレーション実行」を押してください。")

st.divider()
with st.expander("⚠️ 幾何ブラウン運動（GBM）モデルの限界"):
    st.markdown(
        """
        本シミュレーションは **<span translate="no">GBM</span>（幾何ブラウン運動）** モデルを採用。
        以下の前提があるため、結果は「目安」として扱うこと:

        - **正規分布の前提**: <span translate="no">GBM</span> は値動きが正規分布と仮定するが、
          実際の株価は **ファットテール**（極端な動きが理論より頻繁）を持つ。
          → 5% 以下の極端な暴落は、現実ではもっと頻繁に起こる。
        - **σ・μ の推定誤差**: ボラティリティと期待リターンは過去データから推定するが、
          将来は変動する。低金利時代の σ は利上げ局面で過小評価。
        - **ブラックスワン未対応**: <span translate="no">COVID</span> ショック・リーマン級の
          暴落（1 日 -10% 等）は織り込めない。
        - **緩和策**: 過去の最悪期を含む長期データで σ を計算する。
          可能なら <span translate="no">GARCH</span> や **ジャンプ拡散モデル** に切り替える（Phase 3.3 予定）。
        """,
        unsafe_allow_html=True,
    )
