"""マクロ経済ページ — 予測市場 + 経済指標 + 市場レジーム検出（素人向け説明付き）。"""

from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="マクロ経済 — kaori_kabu",
    page_icon="🌍",
    layout="wide",
)

st.title("🌍 マクロ経済ウォッチャー")
st.caption(
    "予測市場（Polymarket） + 経済指標（FRED） + 市場レジーム判定（HMM）",
)

tab1, tab2, tab3 = st.tabs(
    ["🎯 予測市場", "📈 経済指標", "🚦 市場レジーム"],
)

with tab1:
    st.subheader("🎯 予測市場（実資金で取引される確率）")
    st.markdown(
        """
        **<span translate="no">Polymarket</span>** は実資金で「将来の出来事の発生確率」を
        取引するプラットフォーム。市場参加者の集合知が <span translate="no">FOMC</span>
        利下げ・選挙・景気後退・地政学リスクの確率として可視化される。

        **使い方**: 自分のシナリオ予想と市場の織り込みを比べて「ズレ」を見つける。
        例えば自分が「Fed は利下げする」と思っているのに市場の確率が 30% なら、
        逆張り余地があるかも。
        """,
        unsafe_allow_html=True,
    )
    st.warning("⚠️ 未実装。`src/data/polymarket.py` 実装待ち（Phase 3.4 予定）。")

    col1, col2 = st.columns(2)
    with col1:
        st.metric(
            "Fed 次回利下げ確率",
            "-- %",
            delta=None,
            help="米連邦準備制度理事会の次回会合での利下げ確率",
        )
        st.metric(
            "米景気後退確率（2026）",
            "-- %",
            delta=None,
            help="2026 年中に米国がリセッション入りする確率",
        )
    with col2:
        st.metric("大統領選 候補A", "-- %")
        st.metric("大統領選 候補B", "-- %")

with tab2:
    st.subheader("📈 経済指標（FRED 連邦準備制度データ）")
    st.markdown(
        "FRED（米セントルイス連邦準備銀行）の公式データから、"
        "金融市場に効く主要マクロ指標を取得。",
    )
    st.warning("⚠️ 未実装。`src/data/fred.py` 実装待ち（Phase 3.4 予定）。")

    indicators = [
        ("10 年米国債利回り", "DGS10",
         "長期金利の代表値。上昇＝株式の割引率上昇＝株安要因"),
        ("米国失業率", "UNRATE",
         "上昇＝景気悪化、Fed 利下げ圧力。低水準維持＝賃金インフレ警戒"),
        ("米CPI（消費者物価指数 前年比）", "CPIAUCSL",
         "インフレ率。Fed 目標は 2%。2% 大幅超過＝利上げ継続"),
        ("Fed Funds Rate（米政策金利）", "FEDFUNDS",
         "金融政策の主役指標。下落局面＝株式上昇追い風"),
        ("VIX（恐怖指数）", "VIXCLS",
         "S&P 500 オプションが示す予想変動率。20 超で警戒、30 超でパニック"),
        ("日銀政策金利", "JP_POLICY_RATE",
         "日本円・東証株価に直結。マイナス金利解除以降の上昇局面に注目"),
    ]
    for name, code, desc in indicators:
        st.markdown(
            f"- **{name}** (<span translate='no'>{code}</span>): {desc}",
            unsafe_allow_html=True,
        )

with tab3:
    st.subheader("🚦 市場レジーム検出（HMM）")
    st.markdown(
        """
        **市場レジーム** = 相場の「気分・温度感」のこと。
        **<span translate="no">HMM</span>（隠れマルコフモデル）** という統計手法で
        過去の値動きから自動判定する。

        - 🟢 **強気（<span translate="no">Bull</span>）**: 上昇トレンド + 低ボラ。新規買いに有利
        - 🟡 **横ばい（<span translate="no">Choppy</span>）**: 方向感なし + 中ボラ。様子見が無難
        - 🔴 **暴落・危機（<span translate="no">Crisis</span>）**: 下落 + 高ボラ。新規買い控え + 損切り厳格化

        **使い方**: 🔴 の時は新規買いを控え、🟢 の時に積極買い。
        感情ではなく統計で「今は買い時か」を判断する。
        """,
        unsafe_allow_html=True,
    )
    st.warning("⚠️ 未実装。`src/analysis/regime_hmm.py` 実装待ち（Phase 3.4 予定）。")

    st.markdown("### 現在のレジーム: **🟢 強気（仮表示）**")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("🟢 強気の確率", "-- %")
    with col2:
        st.metric("🟡 横ばいの確率", "-- %")
    with col3:
        st.metric("🔴 暴落・危機の確率", "-- %")
