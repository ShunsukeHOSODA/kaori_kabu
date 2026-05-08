"""Magic Formula スクリーナーページ — Greenblatt のバリュー戦略。"""

from __future__ import annotations

import streamlit as st

from src.config.settings import settings

st.set_page_config(page_title="Magic Formula — kaori_kabu", page_icon="📊", layout="wide")

st.title("📊 Magic Formula スクリーナー")
st.caption("Joel Greenblatt の ROC + Earnings Yield で割安銘柄を抽出")

st.markdown(
    """
    > **Magic Formula = ROC ランキング + Earnings Yield ランキング**

    良い会社（ROC 高）を安く買う（EY 高）— Buffett 哲学を数式に落としたもの。
    Greenblatt 2010 のバックテストで年率 17% を実証。
    """
)

with st.sidebar:
    st.subheader("パラメータ")
    market = st.selectbox("市場", ["米国 + 日本", "米国のみ", "日本のみ"])
    min_market_cap = st.number_input(
        "最低時価総額 (USD)",
        value=settings.mf_min_market_cap_usd,
        step=10_000_000,
    )
    excluded = st.multiselect(
        "除外セクター",
        ["Financials", "Utilities", "Energy", "Real Estate"],
        default=settings.excluded_sectors_list,
    )
    top_n = st.slider("上位 N 銘柄", 10, 100, settings.mf_top_n)
    run_button = st.button("🚀 スクリーニング実行", type="primary")

if run_button:
    st.warning("⚠️ 未実装。`src/analysis/magic_formula.py` でロジック実装予定。")
else:
    st.info("左サイドバーでパラメータを設定し「スクリーニング実行」を押してください。")

st.divider()
with st.expander("📚 Magic Formula について（学習）"):
    st.markdown(
        """
        ### なぜ ROC と Earnings Yield の組み合わせ？

        - **ROC（Return on Capital）= EBIT / (Net WC + Net Fixed Assets)**
          投下資本に対してどれだけ利益を生んだか（資本効率）

        - **Earnings Yield = EBIT / Enterprise Value**
          企業価値に対してどれだけ利益が出ているか（割安度）

        - **組み合わせる理由**: 良い会社は普通高い。両方が高い銘柄は
          「割安に放置されている良い会社」= 逆境にあるが本質的に強い会社

        ### リスク

        - **Value Trap**: 構造不況業種は永久に割安なまま
        - **直近 5 年は SP500 にアンダーパフォーム**: 規律保つことが必要
        - **金融・公益・エネルギー除外**: ROC 計算が異質なため

        ### 学習リソース

        - Greenblatt "The Little Book That Still Beats the Market"
        - Montier 2006 "The Little Book of Behavioral Investing"
        """
    )
