"""バックテストページ — vectorbt + walk-forward。"""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="バックテスト — kaori_kabu", page_icon="🔬", layout="wide")

st.title("🔬 バックテスト")
st.caption("vectorbt walk-forward + パラメータ最適化")

with st.sidebar:
    st.subheader("バックテスト設定")
    strategy = st.selectbox(
        "戦略",
        ["Magic Formula", "13F Cloning", "Dividend", "Momentum"],
    )
    start_date = st.date_input("開始日")
    end_date = st.date_input("終了日")
    initial_capital = st.number_input(
        "初期資金 (JPY)",
        value=1_000_000,
        step=100_000,
    )
    walk_forward = st.checkbox("Walk-Forward 検証", value=True)
    run = st.button("🚀 バックテスト実行", type="primary")

st.warning("⚠️ 未実装。vectorbt + QuantStats 統合待ち。")

if run:
    with st.spinner("バックテスト実行中..."):
        st.info("結果ここに表示予定")

st.divider()
with st.expander("📊 表示予定の指標"):
    st.markdown(
        """
        - **CAGR** (年率複利成長率)
        - **Sharpe Ratio** (リスク調整後リターン)
        - **Sortino Ratio** (下方リスク調整)
        - **Calmar Ratio** (Max DD 調整)
        - **Max Drawdown**
        - **Win Rate** / **Profit Factor**
        - **Trade Distribution**
        - **Equity Curve** (vs ベンチマーク)
        - **Monthly Returns Heatmap**
        - **QuantStats Tearsheet** (HTML 出力)
        """
    )
