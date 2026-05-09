"""バックテストページ — 戦略の過去検証（素人向け説明付き）。"""

from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="過去検証（バックテスト） — kaori_kabu",
    page_icon="🔬",
    layout="wide",
)

st.title("🔬 戦略の過去検証（バックテスト）")
st.caption(
    "「もし当時この戦略を続けていたら、いくら儲かったか？」を過去データで計算",
)

st.markdown(
    """
    > **新しい戦略は、過去 10 年以上で検証してから本番投入。**

    例えば「割安株を毎月 10 銘柄買って 1 年保有を繰り返す」戦略を、
    2010 〜 2025 年の実データで動かすと、年率何 % で資産が増えたかが分かる。
    過去で勝てない戦略は、未来でも勝てない可能性が高い。
    """,
)

with st.sidebar:
    st.subheader("バックテスト設定")
    st.caption("検証する戦略・期間・初期資金を指定")

    strategy = st.selectbox(
        "戦略",
        [
            "割安株（マジックフォーミュラ）",
            "達人追従（13F クローニング）",
            "高配当再投資",
            "勢い（モメンタム）",
        ],
        help=(
            "検証したい投資ルール。Magic Formula = 割安銘柄、"
            "13F = 著名投資家追従、配当 = 配当再投資、勢い = 直近上昇銘柄"
        ),
    )
    start_date = st.date_input("開始日")
    end_date = st.date_input("終了日")
    initial_capital = st.number_input(
        "初期資金 (JPY)",
        value=1_000_000,
        step=100_000,
    )
    walk_forward = st.checkbox(
        "Walk-Forward 検証",
        value=True,
        help=(
            "過去データで最適化したパラメータで「未知の」次期間を検証。"
            "過去フィット（カーブフィッティング）を防ぐ"
        ),
    )
    run = st.button("🚀 バックテスト実行", type="primary")

st.warning(
    "⚠️ 未実装。vectorbt + QuantStats 統合待ち（Phase 3.3 予定）。",
)

if run:
    with st.spinner("バックテスト実行中..."):
        st.info("結果ここに表示予定")

st.divider()
with st.expander("📊 表示予定の指標（素人向け説明）"):
    st.markdown(
        """
        | 指標 | 何の指標？ | 良い目安 |
        |---|---|---|
        | <span translate="no">**CAGR**</span> | 年率複利成長率（年平均何 % で増えたか） | 8% 以上で良好（米国株インデックス並み） |
        | <span translate="no">**Sharpe Ratio**</span> | リスク 1 単位あたりリターン（リスク対比の儲け） | 1.0 以上で優秀、2.0 以上で超優秀 |
        | <span translate="no">**Sortino Ratio**</span> | 下落リスクだけで調整した儲け（上ブレは無視） | <span translate="no">Sharpe</span> より厳しい指標、1.0 以上目標 |
        | <span translate="no">**Calmar Ratio**</span> | 最大下落幅（後述）あたりリターン | 1.0 以上で良好 |
        | <span translate="no">**Max Drawdown**</span> | 過去最大の含み損率（資産がピークから何 % 下がったか） | -20% 以内が許容、-50% 超は危険 |
        | <span translate="no">**Win Rate**</span> | 勝ちトレード率（何 % が利益で終わるか） | 50% 以上が望ましいが低くても可（後述） |
        | <span translate="no">**Profit Factor**</span> | 総利益 ÷ 総損失（1 超で利益） | 1.5 以上で健全、2.0 以上で優秀 |
        | <span translate="no">**Trade Distribution**</span> | トレード損益の分布（外れ値の有無） | 一握りの大勝ちに依存しすぎていないか |
        | <span translate="no">**Equity Curve**</span> | 資産推移グラフ（ベンチマーク <span translate="no">vs</span> 戦略） | 右肩上がりで <span translate="no">S&P 500</span> を上回るか |
        | <span translate="no">**Monthly Returns Heatmap**</span> | 月別リターンの色分けマップ | 季節性・特定月の落ち込みを可視化 |
        | <span translate="no">**QuantStats Tearsheet**</span> | 上記を 1 枚にまとめた <span translate="no">HTML</span> レポート | 戦略の全体像を 1 ページで把握 |
        """,
        unsafe_allow_html=True,
    )

with st.expander("⚠️ バックテストの罠（鵜呑み禁止）"):
    st.markdown(
        """
        - **過去フィット（カーブフィッティング）**: 過去で勝てるパラメータを探しすぎると、
          未来では機能しない。<span translate="no">Walk-Forward</span> 検証で抑制。
        - **生存者バイアス**: 倒産した銘柄が除外されたデータで検証すると、実態より良い結果に。
        - **取引コスト未考慮**: 手数料・スプレッド・スリッページを引かないと過大評価。
        - **環境変化**: 過去 10 年が金利低下局面だった場合、利上げ局面では結果が変わる。
        """,
        unsafe_allow_html=True,
    )
