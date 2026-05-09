"""13F Cloning ページ — 達人投資家の保有銘柄を追跡（素人向け説明付き）。"""

from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="達人追従（13F） — kaori_kabu",
    page_icon="🐋",
    layout="wide",
)

st.title("🐋 達人投資家の保有銘柄追従")
st.markdown(
    "<span translate='no'>Berkshire (Buffett) / Pabrai / Burry / Ackman</span>"
    " の最新ポジションを追跡",
    unsafe_allow_html=True,
    help=None,
)

st.markdown(
    """
    > **45 日遅れだが、世界トップ投資家のアイデアを「タダ」で覗ける戦略**

    米国では資産 1 億ドル超の機関投資家は四半期ごとに <span translate="no">SEC</span> へ
    「<span translate="no">13F-HR</span>」（保有銘柄リスト）を提出する義務がある。
    これは **完全に公開** されているので、<span translate="no">Buffett</span> や
    <span translate="no">Pabrai</span> のようなプロが何を買って何を売ったかが
    無料で見られる。

    **<span translate="no">Mohnish Pabrai</span> のダンドー原則**:
    *heads I win, tails I don't lose much*（勝てば大きく、負けても小さく）。
    少数銘柄の集中バリュー投資が個人投資家の最強戦略。
    """,
    unsafe_allow_html=True,
)

# 著名ファンド名 → SEC EDGAR の CIK 番号（公開情報）。
# キー（表示名）は Chrome 自動翻訳に勝手に翻訳されないよう、英語＋日本語併記の
# 「混在表記」にして固有名詞を維持しつつ素人にもわかる形にする。
funds = {
    "Berkshire Hathaway｜バフェット": "0001067983",
    "Pabrai Investment Funds｜パブライ": "0001173334",
    "Scion Asset Management｜バリー": "0001649339",
    "Pershing Square｜アックマン": "0001336528",
    "Greenlight Capital｜アインホーン": "0001079114",
}

with st.sidebar:
    st.subheader("追跡対象ファンド")
    st.caption("見たい著名投資家を選択")
    selected = st.multiselect(
        "ファンド選択",
        list(funds.keys()),
        default=list(funds.keys()),
    )
    quarter = st.selectbox(
        "四半期",
        ["最新", "2026Q1", "2025Q4", "2025Q3"],
        help="四半期末から提出義務があるため、最新でも 45 日程度遅れる",
    )
    super_concentrated = st.checkbox(
        "スーパー集中ファンド優先（5 銘柄以下）",
        value=True,
        help="保有銘柄が少ないほど、本気度の高い「ベストアイデア」と判断できる",
    )

st.warning(
    "⚠️ 未実装。SEC EDGAR API からの XML パース実装待ち（Phase 3.2 予定）。",
)

if selected:
    tabs = st.tabs(selected)
    for i, tab in enumerate(tabs):
        with tab:
            st.info(f"{selected[i]} の 13F 提出書類 表示予定")

st.divider()
with st.expander("⚠️ 13F の限界（鵜呑み禁止）"):
    st.markdown(
        """
        <span translate="no">13F</span> は便利だが、以下の制約を理解した上で参考程度に使うこと:

        - **45 日遅れ**: 四半期末から提出義務があるので、最新版でも 1.5 ヶ月以上前のポジション。
          公開時点では既にプロは次の手を打っている可能性大。
        - **買い建て（ロング）のみ**: 空売り・オプション・先物は含まれない。
          <span translate="no">Burry</span> の有名な「<span translate="no">Big Short</span>」も
          <span translate="no">13F</span> では見えなかった。
        - **誰の判断か不明**: ファンド内で誰がどの銘柄を担当しているかは非公開。
          <span translate="no">Berkshire</span> は <span translate="no">Buffett / Munger / Combs / Weschler</span>
          の合議。
        - **米国保有のみ**: <span translate="no">SEC</span> 管轄外（日本株・欧州株）は表示されない。
        """,
        unsafe_allow_html=True,
    )
