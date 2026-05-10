"""13F Cloning ページ — 達人投資家の保有銘柄を追跡（素人向け説明付き）。

CLAUDE.md §6 / .steering/20260510-13f-dynamic/design.md §10 に基づき、
SEC EDGAR の 13F-HR から 5 ファンドの最新保有を動的取得して表示する。
"""

from __future__ import annotations

from typing import Final

import pandas as pd
import plotly.express as px
import streamlit as st

from src.config.settings import settings
from src.data.cache import ParquetCache
from src.data.sec_edgar import (
    EDGARAPIError,
    EDGARConfigError,
    EDGARNotFoundError,
    EDGARParseError,
    SECEdgarClient,
)

st.set_page_config(
    page_title="達人追従（13F） — kaori_kabu",
    page_icon="🐋",
    layout="wide",
)

st.title("🐋 達人投資家の保有銘柄追従")
st.markdown(
    "<span translate='no'>Berkshire (Buffett) / Pabrai / Burry / Ackman / Einhorn</span>"
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
FUNDS: Final[dict[str, str]] = {
    "Berkshire Hathaway｜バフェット": "0001067983",
    "Pabrai Investment Funds｜パブライ": "0001173334",
    "Scion Asset Management｜バリー": "0001649339",
    "Pershing Square｜アックマン": "0001336528",
    "Greenlight Capital｜アインホーン": "0001079114",
}

# 集中度フィルタ閾値（design.md §10.2）
SUPER_CONCENTRATED_MAX_HOLDINGS: Final[int] = 5


@st.cache_resource
def _get_edgar_client() -> SECEdgarClient | None:
    """SECEdgarClient のシングルトン。User-Agent 未設定なら None。"""
    if not settings.sec_edgar_user_agent or not settings.sec_edgar_user_agent.strip():
        return None
    try:
        return SECEdgarClient(
            user_agent=settings.sec_edgar_user_agent,
            cache=ParquetCache(base_dir=settings.cache_dir),
        )
    except EDGARConfigError:
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_holdings(cik: str) -> tuple[pd.DataFrame | None, str]:
    """13F 保有データ取得。失敗時 (None, status message)。

    @st.cache_data で同 CIK 1 時間メモ化（ParquetCache の 90 日 TTL の上に
    Streamlit セッション内メモリキャッシュを重ねる）。
    """
    client = _get_edgar_client()
    if client is None:
        return None, (
            "⚠️ `SEC_EDGAR_USER_AGENT` が `.env` に未設定。\n"
            "`SEC_EDGAR_USER_AGENT='YourName your-email@example.com'` を設定してください。"
        )
    try:
        df = client.get_latest_13f(cik)
        return df, ""
    except EDGARNotFoundError:
        return None, (
            "ℹ️ 13F-HR 提出なし。守秘要請（13F-NT）の可能性があります。"
        )
    except (EDGARAPIError, EDGARParseError) as exc:
        return None, f"❌ EDGAR 取得エラー: {type(exc).__name__}: {exc}"


def _render_summary(df: pd.DataFrame) -> None:
    """サマリーメトリクス: 総評価額 / 銘柄数 / レポート期。"""
    total_value = int(df["value_usd"].sum())
    report_date = df["report_date"].iloc[0] if not df.empty else None
    col1, col2, col3 = st.columns(3)
    col1.metric(
        "総評価額",
        (
            f"\\${total_value / 1_000_000_000:,.2f}B"
            if total_value > 0
            else "—"
        ),
        help="13F 報告時点の市場価値（USD）",
    )
    col2.metric("銘柄数", f"{len(df):,}")
    col3.metric(
        "レポート期",
        (
            report_date.strftime("%Y-%m-%d")
            if report_date is not None
            else "—"
        ),
        help="13F-HR の reportDate（保有時点の四半期末）",
    )


def _render_top_pie(df: pd.DataFrame, *, top_n: int = 10) -> None:
    """上位 ``top_n`` 銘柄の保有比率ドーナツチャート。"""
    if df.empty:
        return
    top = (
        df[["name_of_issuer", "value_usd"]]
        .groupby("name_of_issuer", as_index=False)
        .sum()
        .nlargest(top_n, "value_usd")
    )
    fig = px.pie(
        top,
        values="value_usd",
        names="name_of_issuer",
        hole=0.45,
        title=f"上位 {min(top_n, len(top))} 銘柄の保有比率",
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    fig.update_layout(height=440, showlegend=True)
    st.plotly_chart(fig, use_container_width=True)


def _render_holdings_table(df: pd.DataFrame) -> None:
    """全銘柄テーブル（保有比率降順）。"""
    if df.empty:
        st.info("保有銘柄なし。")
        return
    total = int(df["value_usd"].sum())
    display = df.copy()
    display["保有比率%"] = (
        (display["value_usd"] / total * 100).round(2)
        if total > 0
        else 0.0
    )
    display["評価額(B$)"] = (display["value_usd"] / 1_000_000_000).round(3)
    cols = [
        "name_of_issuer",
        "title_of_class",
        "cusip",
        "評価額(B$)",
        "保有比率%",
        "shares",
        "share_type",
        "put_call",
    ]
    st.dataframe(
        display[cols].sort_values("保有比率%", ascending=False),
        use_container_width=True,
        hide_index=True,
    )


def _render_provenance(df: pd.DataFrame) -> None:
    """CLAUDE.md §9.8.5: ⓘ 展開で出所開示。"""
    with st.expander("ⓘ データ Provenance（出所追跡）"):
        attrs = df.attrs
        prov = {
            "source": attrs.get("source", "—"),
            "fetched_at": str(attrs.get("fetched_at", "—")),
            "endpoint": attrs.get("endpoint", "—"),
            "params_hash": attrs.get("params_hash", "—"),
            "cache_hit": attrs.get("cache_hit", "—"),
            "cache_age_sec": attrs.get("cache_age_sec", "—"),
        }
        st.json(prov, expanded=False)


def _render_fund_tab(
    display_name: str,
    cik: str,
    *,
    super_concentrated: bool,
) -> None:
    """1 ファンドのタブコンテンツ。"""
    with st.spinner(f"{display_name} の 13F を取得中…"):
        df, status = _fetch_holdings(cik)

    if df is None:
        st.info(status)
        return

    if super_concentrated and len(df) > SUPER_CONCENTRATED_MAX_HOLDINGS:
        st.caption(
            f"📦 銘柄数 {len(df)} > {SUPER_CONCENTRATED_MAX_HOLDINGS} のため"
            "スーパー集中フィルタで除外。サイドバーでチェックを外すと表示します。"
        )
        return

    _render_summary(df)
    st.divider()
    _render_top_pie(df)
    st.subheader("📋 全保有銘柄")
    _render_holdings_table(df)
    _render_provenance(df)


# ============================================================
# サイドバー
# ============================================================

with st.sidebar:
    st.subheader("追跡対象ファンド")
    st.caption("見たい著名投資家を選択")
    selected = st.multiselect(
        "ファンド選択",
        list(FUNDS.keys()),
        default=list(FUNDS.keys()),
    )
    quarter = st.selectbox(
        "四半期",
        ["最新", "2026Q1", "2025Q4", "2025Q3"],
        help="四半期末から提出義務があるため、最新でも 45 日程度遅れる",
    )
    super_concentrated = st.checkbox(
        "スーパー集中ファンド優先（5 銘柄以下）",
        value=False,
        help="保有銘柄が少ないほど、本気度の高い「ベストアイデア」と判断できる",
    )
    st.divider()
    if _get_edgar_client() is None:
        st.error(
            "⚠️ `SEC_EDGAR_USER_AGENT` 未設定\n\n"
            "`.env` に以下を追加:\n"
            "```\nSEC_EDGAR_USER_AGENT='YourName your-email@example.com'\n```"
        )
    else:
        st.success("✅ SEC EDGAR 接続準備 OK")

# ============================================================
# メインコンテンツ
# ============================================================

if quarter != "最新":
    st.warning(
        f"📅 {quarter} の過去四半期表示は未実装（Phase 後段予定）。"
        " 現在は「最新」のみサポート。"
    )

if not selected:
    st.info("サイドバーで追跡対象ファンドを選択してください。")
else:
    tabs = st.tabs(selected)
    for i, tab in enumerate(tabs):
        with tab:
            display_name = selected[i]
            cik = FUNDS[display_name]
            _render_fund_tab(
                display_name, cik, super_concentrated=super_concentrated
            )

# ============================================================
# フッター: 13F の限界警告
# ============================================================

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
        - **NT 提出**: <span translate="no">Burry / Einhorn</span> 等は守秘要請（<span translate="no">13F-NT</span>）
          を出す四半期があり、その期は保有非開示になる。
        """,
        unsafe_allow_html=True,
    )
