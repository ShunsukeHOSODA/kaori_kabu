"""Magic Formula スクリーナーページ — Greenblatt のバリュー戦略。

CLAUDE.md §9.3 / §9.4 / §9.8 に準拠:
    - 一本線予測禁止（ランキング合算スコアで提示）
    - シグナル根拠併記（学術的バックボーン引用 + リスク警告）
    - Provenance metadata を ⓘ で開示

実 API ファンダメンタルデータ取得は Phase 2（EODHD ``/fundamentals/``）。
本ページは合成 fixture で Magic Formula UI を完成させる段階。
"""

from __future__ import annotations

from decimal import Decimal

import pandas as pd
import streamlit as st

from src.analysis.magic_formula import (
    MagicFormulaResult,
    screen_magic_formula_with_provenance,
)
from src.config.settings import settings

st.set_page_config(
    page_title="Magic Formula — kaori_kabu", page_icon="📊", layout="wide"
)

st.title("📊 Magic Formula スクリーナー")
st.caption("Joel Greenblatt の ROC + Earnings Yield で割安銘柄を抽出")

st.markdown(
    """
    > **Magic Formula = ROC ランキング + Earnings Yield ランキング**

    良い会社（ROC 高）を安く買う（EY 高）— Buffett 哲学を数式に落としたもの。
    Greenblatt 2010 のバックテストで年率 17% を実証。
    """
)


@st.cache_data
def load_demo_universe() -> pd.DataFrame:
    """米国大型株 10 銘柄のサンプル財務データ（合成）。

    実 API 接続後はこの関数を EODHD ``/fundamentals/`` 取得に置き換える。
    値は教育用の合成データであり実際の財務数値ではない。
    """
    tickers = [
        "AAPL", "MSFT", "GOOGL", "AMZN", "META",
        "NVDA", "JNJ", "PG", "KO", "WMT",
    ]
    ebit = [
        "120000", "100000", "80000", "60000", "50000",
        "30000", "25000", "20000", "15000", "12000",
    ]
    nwc = [
        "50000", "60000", "70000", "40000", "30000",
        "20000", "30000", "10000", "12000", "8000",
    ]
    nfa = [
        "50000", "70000", "80000", "150000", "30000",
        "15000", "30000", "20000", "25000", "60000",
    ]
    ev = [
        "3500000", "3000000", "1900000", "1800000", "1300000",
        "2500000", "400000", "350000", "260000", "450000",
    ]
    return pd.DataFrame(
        {
            "ticker": tickers,
            "ebit": [Decimal(v) for v in ebit],
            "net_working_capital": [Decimal(v) for v in nwc],
            "net_fixed_assets": [Decimal(v) for v in nfa],
            "enterprise_value": [Decimal(v) for v in ev],
        }
    )


with st.sidebar:
    st.subheader("パラメータ")
    market = st.selectbox(
        "市場（Phase 2 で有効化）",
        ["米国 + 日本", "米国のみ", "日本のみ"],
        disabled=True,
    )
    min_market_cap = st.number_input(
        "最低時価総額 (USD、Phase 2)",
        value=settings.mf_min_market_cap_usd,
        step=10_000_000,
        disabled=True,
    )
    excluded = st.multiselect(
        "除外セクター（Phase 2 で有効化）",
        ["Financials", "Utilities", "Energy", "Real Estate"],
        default=settings.excluded_sectors_list,
        disabled=True,
    )
    top_n = st.slider("上位 N 銘柄", 1, 10, min(settings.mf_top_n, 10))
    run_button = st.button("🚀 スクリーニング実行（Demo）", type="primary")
    st.caption(
        "現在は合成データ 10 銘柄でのデモ。"
        "実銘柄スクリーニングは EODHD ファンダ接続後（Phase 2）。"
    )


if run_button:
    df = load_demo_universe()
    with st.spinner("Magic Formula 計算中..."):
        result: MagicFormulaResult = screen_magic_formula_with_provenance(
            df,
            n=top_n,
            input_data_source="demo_fixture_10_us_large_cap",
            input_data_period="N/A (synthetic)",
            input_cache_hit=False,
        )

    st.success(
        f"✅ Top {len(result.result)} 銘柄を抽出 "
        f"({result.metadata.calculated_at.strftime('%Y-%m-%d %H:%M:%S UTC')})"
    )

    # ───────────────────────────────────────────────
    # Provenance 開示（CLAUDE.md §9.8.5）
    # ───────────────────────────────────────────────
    with st.expander("ⓘ 出所追跡情報（Provenance）"):
        st.json(
            {
                "calculation_method": result.metadata.calculation_method,
                "academic_source": result.metadata.academic_source,
                "calculated_at": result.metadata.calculated_at.isoformat(),
                "input_data_source": result.metadata.input_data_source,
                "input_data_period": result.metadata.input_data_period,
                "input_cache_hit": result.metadata.input_cache_hit,
                "code_commit": result.metadata.code_commit,
            }
        )

    # ───────────────────────────────────────────────
    # 結果テーブル
    # ───────────────────────────────────────────────
    display_df = result.result[
        [
            "ticker",
            "magic_formula_score",
            "roc",
            "earnings_yield",
            "roc_rank",
            "ey_rank",
        ]
    ].copy()
    display_df["roc"] = display_df["roc"].apply(
        lambda x: f"{float(x) * 100:.2f}%"
    )
    display_df["earnings_yield"] = display_df["earnings_yield"].apply(
        lambda x: f"{float(x) * 100:.2f}%"
    )
    display_df = display_df.rename(
        columns={
            "ticker": "ティッカー",
            "magic_formula_score": "合算スコア（小↓良）",
            "roc": "ROC",
            "earnings_yield": "EY",
            "roc_rank": "ROC ランク",
            "ey_rank": "EY ランク",
        }
    )
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    # ───────────────────────────────────────────────
    # リスク警告（CLAUDE.md §9.4 / §9.7）
    # ───────────────────────────────────────────────
    st.warning(
        "⚠️ **リスク警告**\n\n"
        "- **過去パフォーマンス ≠ 将来**: 直近 5 年は SP500 にアンダーパフォーム\n"
        "- **Value Trap リスク**: 構造不況業種は永久に割安なまま\n"
        "- **デモデータ**: このページは合成 10 銘柄のサンプルです\n"
        "- **認知バイアス対策**: Confirmation Bias を避け、反対意見も検討すること"
    )

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
