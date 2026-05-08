"""Magic Formula スクリーナーページ — Greenblatt のバリュー戦略。

CLAUDE.md §9.3 / §9.4 / §9.8 に準拠:
    - 一本線予測禁止（ランキング合算スコアで提示）
    - シグナル根拠併記（学術的バックボーン引用 + リスク警告）
    - Provenance metadata を ⓘ で開示

データソース:
    - **Demo**: 米国大型株 10 銘柄の合成データ（API キー不要）
    - **EODHD ライブ**: ``settings.eodhd_api_key`` ありで有効。ティッカーを
      指定するとファンダメンタルを取得して Magic Formula を計算する。
      取得結果は TTL 7 日でローカルキャッシュ（CLAUDE.md §9.2）。
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
from src.data.cache import ParquetCache
from src.data.eodhd import EODHDClient

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


# ---------------------------------------------------------------------------
# データソース層
# ---------------------------------------------------------------------------


@st.cache_data
def load_demo_universe() -> pd.DataFrame:
    """米国大型株 10 銘柄のサンプル財務データ（合成）。

    EODHD API キー未設定時のフォールバック。値は教育用の合成データであり
    実際の財務数値ではない。
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


@st.cache_resource
def get_eodhd_client() -> EODHDClient | None:
    """``EODHD_API_KEY`` がある場合のみ EODHDClient を生成。

    Streamlit の :func:`st.cache_resource` で session 中シングルトン化。
    キーが空なら ``None`` を返し、UI 側で Demo にフォールバックさせる。
    """
    if not settings.eodhd_api_key:
        return None
    cache = ParquetCache(base_dir=settings.cache_dir)
    return EODHDClient(api_key=settings.eodhd_api_key, cache=cache)


def fetch_real_universe(
    client: EODHDClient,
    tickers: list[str],
    *,
    exchange: str,
    excluded_sectors: tuple[str, ...],
    min_market_cap_usd: Decimal,
) -> pd.DataFrame:
    """EODHD ライブで指定ティッカーのファンダから DataFrame を構築。

    取得は :meth:`EODHDClient.build_screener_universe` 経由でフィルタ込み。
    """
    return client.build_screener_universe(
        tickers,
        exchange=exchange,
        excluded_sectors=excluded_sectors,
        min_market_cap_usd=min_market_cap_usd,
    )


def parse_tickers(raw: str) -> list[str]:
    """カンマまたは改行区切りのティッカー文字列を正規化。

    重複除去 + 大文字化 + 空白除去。
    """
    parts = [
        p.strip().upper()
        for line in raw.splitlines()
        for p in line.split(",")
    ]
    seen: set[str] = set()
    result: list[str] = []
    for p in parts:
        if p and p not in seen:
            seen.add(p)
            result.append(p)
    return result


# ---------------------------------------------------------------------------
# サイドバー UI
# ---------------------------------------------------------------------------


eodhd_client = get_eodhd_client()
api_available = eodhd_client is not None

with st.sidebar:
    st.subheader("データソース")
    if api_available:
        source_mode = st.radio(
            "モード",
            ["EODHD ライブ", "Demo（合成 10 銘柄）"],
            index=0,
            help="EODHD ライブはファンダ TTL 7 日キャッシュ経由で API 消費を抑制",
        )
    else:
        source_mode = "Demo（合成 10 銘柄）"
        st.warning(
            "⚠️ `EODHD_API_KEY` が未設定のため Demo モードのみ利用可。"
            "実銘柄スクリーニングには `.env` に EODHD_API_KEY を設定してください。"
        )

    st.subheader("パラメータ")
    real_mode = source_mode == "EODHD ライブ"

    exchange = st.selectbox(
        "取引所",
        ["US", "TO"],
        index=0,
        disabled=not real_mode,
        help="US=米国、TO=東証（日本株）",
    )

    if real_mode:
        ticker_text = st.text_area(
            "ティッカー（カンマまたは改行区切り）",
            value="AAPL, MSFT, GOOGL, AMZN, META, NVDA, JNJ, PG, KO, WMT",
            height=120,
        )
        tickers = parse_tickers(ticker_text)
        st.caption(f"対象 {len(tickers)} 銘柄")
    else:
        tickers = []

    min_market_cap = st.number_input(
        "最低時価総額 (USD)",
        value=settings.mf_min_market_cap_usd,
        step=10_000_000,
        disabled=not real_mode,
    )
    excluded = st.multiselect(
        "除外セクター",
        ["Financials", "Utilities", "Energy", "Real Estate"],
        default=settings.excluded_sectors_list,
        disabled=not real_mode,
    )

    top_n = st.slider("上位 N 銘柄", 1, 30, min(settings.mf_top_n, 30))
    run_button = st.button(
        "🚀 スクリーニング実行",
        type="primary",
        disabled=real_mode and len(tickers) == 0,
    )


# ---------------------------------------------------------------------------
# 実行
# ---------------------------------------------------------------------------


if run_button:
    if real_mode and eodhd_client is not None:
        with st.spinner(f"EODHD から {len(tickers)} 銘柄のファンダ取得中..."):
            try:
                df = fetch_real_universe(
                    eodhd_client,
                    tickers,
                    exchange=exchange,
                    excluded_sectors=tuple(excluded),
                    min_market_cap_usd=Decimal(str(min_market_cap)),
                )
            except Exception as exc:  # noqa: BLE001 — UI 側で安全に表示
                st.error(f"❌ 取得失敗: {exc}")
                st.stop()
        if df.empty:
            st.warning(
                "⚠️ フィルタ後に該当銘柄が 0 件。"
                "セクター除外・最低時価総額・ティッカー指定を見直してください。"
            )
            st.stop()
        data_source = f"EODHD live ({exchange})"
        data_period = pd.Timestamp.now(tz="UTC").strftime("fundamentals_as_of_%Y-%m-%d")
        cache_hit_flag: bool | None = None  # 銘柄毎に異なるため要約不能
    else:
        df = load_demo_universe()
        data_source = "demo_fixture_10_us_large_cap"
        data_period = "N/A (synthetic)"
        cache_hit_flag = False

    with st.spinner("Magic Formula 計算中..."):
        result: MagicFormulaResult = screen_magic_formula_with_provenance(
            df,
            n=top_n,
            input_data_source=data_source,
            input_data_period=data_period,
            input_cache_hit=cache_hit_flag,
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
    display_columns = [
        "ticker",
        "magic_formula_score",
        "roc",
        "earnings_yield",
        "roc_rank",
        "ey_rank",
    ]
    if "sector" in result.result.columns:
        display_columns.append("sector")
    if "market_cap" in result.result.columns:
        display_columns.append("market_cap")

    display_df = result.result[display_columns].copy()
    display_df["roc"] = display_df["roc"].apply(
        lambda x: f"{float(x) * 100:.2f}%"
    )
    display_df["earnings_yield"] = display_df["earnings_yield"].apply(
        lambda x: f"{float(x) * 100:.2f}%"
    )
    if "market_cap" in display_df.columns:
        display_df["market_cap"] = display_df["market_cap"].apply(
            lambda x: f"${float(x) / 1e9:,.1f}B" if x is not None else "—"
        )

    rename_map = {
        "ticker": "ティッカー",
        "magic_formula_score": "合算スコア（小↓良）",
        "roc": "ROC",
        "earnings_yield": "EY",
        "roc_rank": "ROC ランク",
        "ey_rank": "EY ランク",
        "sector": "セクター",
        "market_cap": "時価総額",
    }
    display_df = display_df.rename(columns=rename_map)
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    # ───────────────────────────────────────────────
    # リスク警告（CLAUDE.md §9.4 / §9.7）
    # ───────────────────────────────────────────────
    risk_messages = [
        "**過去パフォーマンス ≠ 将来**: 直近 5 年は SP500 にアンダーパフォーム",
        "**Value Trap リスク**: 構造不況業種は永久に割安なまま",
        "**認知バイアス対策**: Confirmation Bias を避け、反対意見も検討すること",
    ]
    if not real_mode:
        risk_messages.insert(0, "**デモデータ**: このページは合成 10 銘柄のサンプルです")
    st.warning("⚠️ **リスク警告**\n\n- " + "\n- ".join(risk_messages))

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
