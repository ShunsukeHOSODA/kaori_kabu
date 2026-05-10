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
    compute_qoq_diff,
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

# 四半期選択ラベル — index 0 が最新、N が N 期前（design.md §10.3 / Phase D）
QUARTER_LABELS: Final[tuple[str, ...]] = (
    "最新",
    "1 期前",
    "2 期前",
    "3 期前",
)


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
def _fetch_holdings_history(
    cik: str, *, limit: int = 4
) -> tuple[list[pd.DataFrame] | None, str]:
    """過去 ``limit`` 四半期分の 13F 保有データを新しい順で取得。

    失敗時 ``(None, status message)`` を返す。@st.cache_data で同 (CIK, limit)
    1 時間メモ化（ParquetCache の 90 日 TTL の上に Streamlit セッション内
    メモリキャッシュを重ねる）。
    """
    client = _get_edgar_client()
    if client is None:
        return None, (
            "⚠️ `SEC_EDGAR_USER_AGENT` が `.env` に未設定。\n"
            "`SEC_EDGAR_USER_AGENT='YourName your-email@example.com'` を設定してください。"
        )
    try:
        history = client.get_13f_history(cik, limit=limit)
        return history, ""
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


# 前期比 diff 区分のアイコンマッピング（design.md §10.3）
QOQ_ACTION_ICONS: Final[dict[str, str]] = {
    "新規買い": "🆕",
    "増持": "📈",
    "減持": "📉",
    "売却": "🔚",
    "保持": "🟰",
}
QOQ_ACTIONS_ORDERED: Final[tuple[str, ...]] = (
    "新規買い",
    "増持",
    "減持",
    "売却",
    "保持",
)


def _render_qoq_diff(diff_df: pd.DataFrame, *, key_suffix: str) -> None:
    """前期比 diff の 4 区分メトリクス + テーブル（design.md §10.3）。

    Args:
        diff_df: ``compute_qoq_diff`` の出力 DataFrame
        key_suffix: ``st.multiselect`` の ``key`` を unique にする識別子
            （5 ファンドタブで同じ widget が繰り返されるため必須）
    """
    if diff_df.empty:
        st.info("前期比較データなし。")
        return

    # 区分別カウント表示
    counts = diff_df["action"].value_counts()
    cols = st.columns(len(QOQ_ACTIONS_ORDERED))
    for col, action in zip(cols, QOQ_ACTIONS_ORDERED, strict=False):
        col.metric(
            f"{QOQ_ACTION_ICONS.get(action, '')} {action}",
            f"{int(counts.get(action, 0))} 銘柄",
        )

    st.divider()

    # 区分フィルタ（保持を既定で除外 = 動きのある銘柄に集中）
    selected_actions = st.multiselect(
        "表示する区分",
        list(QOQ_ACTIONS_ORDERED),
        default=["新規買い", "増持", "減持", "売却"],
        help="保持（変化なし）を除外したい時はチェックを外す",
        key=f"qoq_filter_{key_suffix}",
    )

    if not selected_actions:
        st.info("表示する区分を選択してください。")
        return

    filtered = diff_df[diff_df["action"].isin(selected_actions)].copy()
    if filtered.empty:
        st.info("選択された区分に該当する銘柄なし。")
        return

    # 表示用整形（USD → B$/M$ にスケール）
    filtered["change_$M"] = (filtered["change_usd"] / 1_000_000).round(1)
    filtered["value_current_$B"] = (
        filtered["value_current"].fillna(0) / 1_000_000_000
    ).round(3)
    filtered["value_previous_$B"] = (
        filtered["value_previous"].fillna(0) / 1_000_000_000
    ).round(3)

    # change_usd の絶対値降順でソート（変化の大きい銘柄を上に）
    filtered = filtered.assign(
        _abs_change=filtered["change_usd"].abs()
    ).sort_values("_abs_change", ascending=False)

    cols_to_show = [
        "action",
        "name_of_issuer",
        "cusip",
        "value_current_$B",
        "value_previous_$B",
        "change_$M",
    ]
    st.dataframe(
        filtered[cols_to_show],
        use_container_width=True,
        hide_index=True,
    )


def _render_fund_tab(
    display_name: str,
    cik: str,
    *,
    quarter_index: int,
    super_concentrated: bool,
) -> None:
    """1 ファンドのタブコンテンツ — 過去 4 四半期取得 → quarter_index で表示。

    quarter_index=0 が最新。``quarter_index + 1`` 番目を「前期」として
    Q-over-Q diff を計算する（前期がなければ diff サブタブで案内）。
    """
    with st.spinner(f"{display_name} の 13F 履歴を取得中…"):
        history, status = _fetch_holdings_history(cik, limit=4)

    if history is None:
        st.info(status)
        return

    if quarter_index >= len(history):
        st.warning(
            f"📅 {quarter_index + 1} 期前のデータなし"
            f"（取得可能 {len(history)} 期分）。"
        )
        return

    df = history[quarter_index]
    prev_df: pd.DataFrame | None = (
        history[quarter_index + 1]
        if quarter_index + 1 < len(history)
        else None
    )

    if super_concentrated and len(df) > SUPER_CONCENTRATED_MAX_HOLDINGS:
        st.caption(
            f"📦 銘柄数 {len(df)} > {SUPER_CONCENTRATED_MAX_HOLDINGS} のため"
            "スーパー集中フィルタで除外。サイドバーでチェックを外すと表示します。"
        )
        return

    inner_tabs = st.tabs(["📋 保有銘柄", "🔄 前期比 diff"])

    with inner_tabs[0]:
        _render_summary(df)
        st.divider()
        _render_top_pie(df)
        st.subheader("全保有銘柄")
        _render_holdings_table(df)
        _render_provenance(df)

    with inner_tabs[1]:
        if prev_df is None:
            st.info(
                "ℹ️ 前期データがないため diff 計算不可"
                "（取得可能な最古の四半期、または 1 期しか取得できていない）。"
            )
        else:
            cur_date = pd.Timestamp(df["report_date"].iloc[0]).strftime("%Y-%m-%d")
            prev_date = pd.Timestamp(
                prev_df["report_date"].iloc[0]
            ).strftime("%Y-%m-%d")
            st.caption(f"今期: **{cur_date}** ⇄ 前期: **{prev_date}**")
            diff_df = compute_qoq_diff(df, prev_df)
            _render_qoq_diff(diff_df, key_suffix=cik)
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
    quarter_label = st.selectbox(
        "四半期",
        list(QUARTER_LABELS),
        help=(
            "13F は四半期末から 45 日以内に提出義務（最新でも 45 日遅れ）。"
            " 過去 4 期分まで動的取得対応。"
        ),
    )
    quarter_index = QUARTER_LABELS.index(quarter_label)
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

if not selected:
    st.info("サイドバーで追跡対象ファンドを選択してください。")
else:
    tabs = st.tabs(selected)
    for i, tab in enumerate(tabs):
        with tab:
            display_name = selected[i]
            cik = FUNDS[display_name]
            _render_fund_tab(
                display_name,
                cik,
                quarter_index=quarter_index,
                super_concentrated=super_concentrated,
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
