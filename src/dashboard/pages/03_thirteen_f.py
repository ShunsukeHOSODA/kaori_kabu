"""13F Cloning ページ — トップ投資家の保有銘柄を追跡。"""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="13F Cloning — kaori_kabu", page_icon="🐋", layout="wide")

st.title("🐋 13F Cloning ダッシュボード")
st.caption("Berkshire / Pabrai / Burry / Ackman の最新ポジションを追跡")

st.markdown(
    """
    > **45 日遅延だが情報優位性をタダで借りる戦略**

    機関投資家は SEC に四半期で 13F-HR を提出する義務がある。
    Buffett / Pabrai のような著名投資家のポジションをほぼリアルタイムで追跡できる。

    **Mohnish Pabrai の Dhandho 原則**: heads I win, tails I don't lose much。
    集中バリュー投資が個人投資家の最強戦略。
    """
)

funds = {
    "Berkshire Hathaway (Buffett)": "0001067983",
    "Pabrai Investment Funds": "0001173334",
    "Scion Asset Management (Burry)": "0001649339",
    "Pershing Square (Ackman)": "0001336528",
    "Greenlight Capital (Einhorn)": "0001079114",
}

with st.sidebar:
    st.subheader("追跡対象ファンド")
    selected = st.multiselect("ファンド選択", list(funds.keys()), default=list(funds.keys()))
    quarter = st.selectbox("四半期", ["最新", "2026Q1", "2025Q4", "2025Q3"])
    super_concentrated = st.checkbox("スーパー集中ファンド優先（5 銘柄以下）", value=True)

st.warning("⚠️ 未実装。SEC EDGAR API + XML パース実装待ち。")

if selected:
    tabs = st.tabs([f.split(" (")[0] for f in selected])
    for i, tab in enumerate(tabs):
        with tab:
            st.info(f"{selected[i]} の 13F filings 表示予定")

st.divider()
with st.expander("⚠️ 13F の限界"):
    st.markdown(
        """
        - **45 日遅延**: 四半期末から提出義務、その時点では既に動いている
        - **ロングのみ**: ショートポジション・オプションは含まれない
          （Burry の "Big Short" も 13F では見えない）
        - **マネージャー判断**: ファンド内で誰がどの銘柄を担当しているかは不明
          （Berkshire は Buffett / Munger / Combs / Weschler）
        """
    )
