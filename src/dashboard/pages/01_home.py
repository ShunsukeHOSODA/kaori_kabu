"""ホームページ — 保有銘柄サマリー + リスク信号灯。"""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="ホーム — kaori_kabu", page_icon="🏠", layout="wide")

st.title("🏠 ホーム — 保有銘柄サマリー")
st.caption("当日の評価額・含み益損・リスク指標を一画面で確認")

st.warning("⚠️ 未実装。`data/holdings/portfolio.csv` 読み込み + リスク計算ロジック実装待ち。")

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("ポートフォリオ評価額", "¥ -- ", delta=None)
with col2:
    st.metric("含み益損", "¥ -- ", delta=None)
with col3:
    st.metric("Sharpe Ratio", "-- ", delta=None)

st.divider()
st.subheader("🚦 マーケットレジーム")
st.info("HMM レジーム検出（Bull / Choppy / Crisis）信号灯を表示予定")

st.subheader("📊 保有銘柄")
st.info("`data/holdings/portfolio.csv` から読み込み、ATR トレーリングストップ抵触銘柄を強調表示予定")
