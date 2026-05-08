"""マクロウォッチャーページ — Polymarket + FRED + HMM レジーム。"""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="マクロ — kaori_kabu", page_icon="🌍", layout="wide")

st.title("🌍 マクロウォッチャー")
st.caption("Polymarket 予測市場 + FRED 経済指標 + HMM レジーム")

tab1, tab2, tab3 = st.tabs(["🎯 Polymarket", "📈 FRED マクロ", "🚦 HMM レジーム"])

with tab1:
    st.subheader("Polymarket 予測市場")
    st.markdown(
        """
        実資金で取引されている市場の織り込み確率を取得。
        Fed 利上げ・選挙・景気後退・地政学リスク。
        """
    )
    st.warning("⚠️ 未実装。`src/data/polymarket.py` 実装待ち。")

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Fed 次回利下げ確率", "-- %", delta=None)
        st.metric("米景気後退確率（2026）", "-- %", delta=None)
    with col2:
        st.metric("大統領選 候補A", "-- %")
        st.metric("大統領選 候補B", "-- %")

with tab2:
    st.subheader("FRED マクロ指標")
    st.warning("⚠️ 未実装。`src/data/fred.py` 実装待ち。")

    indicators = [
        "10 年国債利回り (DGS10)",
        "失業率 (UNRATE)",
        "CPI Year-over-Year (CPIAUCSL)",
        "Fed Funds Rate (FEDFUNDS)",
        "VIX (VIXCLS)",
        "日銀政策金利",
    ]
    for ind in indicators:
        st.write(f"- {ind}: 取得予定")

with tab3:
    st.subheader("🚦 HMM レジーム検出")
    st.markdown("市場の状態を Bull / Choppy / Crisis の 3 段階で自動判定")
    st.warning("⚠️ 未実装。`src/analysis/regime_hmm.py` 実装待ち。")

    st.markdown("### 現在のレジーム: **🟢 Bull** （仮）")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Bull 確率", "-- %")
    with col2:
        st.metric("Choppy 確率", "-- %")
    with col3:
        st.metric("Crisis 確率", "-- %")
