"""Streamlit 再利用可能 UI コンポーネント（CLAUDE.md §9.4 / §9.8.5）。

純粋関数（``format_*``）と Streamlit レンダラー（``render_*``）を分離。
純粋関数は単体テスト対象、レンダラーは Streamlit ランタイムが必要なため
スモークテスト + 目視確認とする。
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pandas as pd

if TYPE_CHECKING:
    from analysis.sentiment import SentimentResult
    from data.news import MarketContext

# ---------------------------------------------------------------------------
# センチメント分類
# ---------------------------------------------------------------------------

_BULL_THRESHOLD = Decimal("0.3")
_BEAR_THRESHOLD = Decimal("-0.3")

_EMOJI_BY_LABEL: dict[str, str] = {
    "bull": "🟢",
    "neutral": "🟡",
    "bear": "🔴",
}

_JP_LABEL_BY_LABEL: dict[str, str] = {
    "bull": "強気",
    "neutral": "中立",
    "bear": "弱気",
}

# 投資家レンズ名 → 表示ラベル（日本語ニックネーム）
LENS_LABELS: dict[str, str] = {
    "Buffett_Munger": "Buffett-Munger（質×価値）",
    "Soros": "Soros（リフレクシビティ）",
    "Druckenmiller": "Druckenmiller（流動性）",
    "Dalio": "Dalio（覇権・負債）",
    "Pabrai": "Pabrai（クローニング）",
    "Burry": "Burry（テールリスク）",
    "Ackman": "Ackman（ガバナンス）",
    "Lynch": "Lynch（消費者目線）",
}


def _classify(score: Decimal) -> str:
    """スコアを bull / neutral / bear に分類。"""
    if score >= _BULL_THRESHOLD:
        return "bull"
    if score <= _BEAR_THRESHOLD:
        return "bear"
    return "neutral"


def format_sentiment_emoji(score: Decimal) -> str:
    """センチメントスコアを信号灯絵文字に変換（🟢/🟡/🔴）。"""
    return _EMOJI_BY_LABEL[_classify(score)]


def format_sentiment_label(score: Decimal) -> str:
    """センチメントスコアを日本語ラベルに変換（強気/中立/弱気）。"""
    return _JP_LABEL_BY_LABEL[_classify(score)]


def format_lenses_applied(lenses: tuple[str, ...]) -> str:
    """レンズ名タプル → ` / ` 区切りの表示用文字列。空なら ``—``。"""
    if not lenses:
        return "—"
    return " / ".join(LENS_LABELS.get(n, n) for n in lenses)


# ---------------------------------------------------------------------------
# Streamlit レンダラー（テスト対象外）
# ---------------------------------------------------------------------------


def render_sentiment_badge(
    sentiment_result: SentimentResult,
    *,
    label_prefix: str = "",
) -> None:
    """センチメントの信号灯バッジを 1 行で描画。

    Streamlit ランタイム必須。テスト対象外。
    """
    import streamlit as st  # noqa: PLC0415 — UI 専用 lazy import

    score = sentiment_result.sentiment_score
    emoji = format_sentiment_emoji(score)
    label = format_sentiment_label(score)
    confidence = sentiment_result.confidence

    st.markdown(
        f"{label_prefix}**センチメント**: {emoji} {label} "
        f"(score `{score}` / confidence `{confidence}`)"
    )


def render_news_tab(
    *,
    ticker: str,
    market_context: MarketContext | None,
    sentiment_result: SentimentResult,
    lenses_applied: tuple[str, ...] = (),
) -> None:
    """銘柄ごとのニュースタブをレンダリング。

    呼び出し側は ``st.expander`` 内で本関数を呼ぶことを推奨。
    Streamlit ランタイム必須。テスト対象外。

    Args:
        ticker: 銘柄シンボル
        market_context: NewsClient.gather_market_context の結果。
            ``None`` ならソース URL セクションをスキップ。
        sentiment_result: analyze_sentiment の結果
        lenses_applied: 適用した投資家レンズ名タプル
    """
    import streamlit as st  # noqa: PLC0415

    st.markdown(f"### 📰 {ticker} ニュース & センチメント分析")

    render_sentiment_badge(sentiment_result)

    if sentiment_result.summary:
        st.markdown(f"**要約**: {sentiment_result.summary}")

    if sentiment_result.key_themes:
        st.markdown("**主要テーマ**:")
        for theme in sentiment_result.key_themes:
            st.markdown(f"- {theme}")

    if sentiment_result.risk_signals:
        st.warning(
            "⚠️ **リスクシグナル**\n\n- "
            + "\n- ".join(sentiment_result.risk_signals)
        )

    if lenses_applied:
        st.caption(f"適用レンズ: {format_lenses_applied(lenses_applied)}")

    # ソース URL リスト
    if market_context is not None:
        all_news = pd.concat(
            [
                market_context.ticker_news,
                market_context.macro_news,
                market_context.geopolitical_news,
                market_context.research,
            ],
            ignore_index=True,
        )
        if len(all_news) > 0 and "url" in all_news.columns:
            st.markdown("**ソース** (上位 5 件):")
            for _, row in all_news.head(5).iterrows():
                title = str(row.get("title", "")).strip()
                url = str(row.get("url", "")).strip()
                if url and url != "nan":
                    st.markdown(f"- [{title or url}]({url})")

    # Provenance（CLAUDE.md §9.8.5 必須）
    with st.expander("ⓘ 出所追跡情報"):
        md = sentiment_result.metadata
        info: dict[str, Any] = {
            "model_version": md.model_version,
            "calculation_method": md.calculation_method,
            "input_news_count": md.input_news_count,
            "academic_source": md.academic_source,
            "calculated_at": md.calculated_at.isoformat(),
            "code_commit": md.code_commit,
            "lenses_applied": list(lenses_applied),
        }
        st.json(info)


# ---------------------------------------------------------------------------
# Composite Score 7 軸レーダーチャート（Phase 3.1b）
# ---------------------------------------------------------------------------

_AXIS_LABELS: tuple[tuple[str, str], ...] = (
    ("Q", "Quality"),
    ("V", "Value"),
    ("I", "Income"),
    ("G", "Growth"),
    ("R", "Risk"),
    ("M", "Momentum"),
    ("S", "Sentiment"),
)


def composite_radar_chart(
    *,
    ticker: str,
    sub_scores: dict[str, float],
) -> Any:
    """7 軸 Composite Score を Plotly Scatterpolar でレーダー描画。

    Args:
        ticker: 銘柄表示名（タイトルに反映）
        sub_scores: 軸記号 → 0-100 スコア dict（``Q``/``V``/``I``/``G``/``R``/``M``/``S``）。
            欠損キーは 0.0 で補完（Phase 3.1a 互換）。

    Returns:
        :class:`plotly.graph_objects.Figure`。Streamlit 側で
        ``st.plotly_chart(fig)`` として描画する。
    """
    import plotly.graph_objects as go  # noqa: PLC0415 — UI モジュール起動コスト軽減

    theta = [label for _key, label in _AXIS_LABELS]
    r = [float(sub_scores.get(key, 0.0)) for key, _label in _AXIS_LABELS]

    # 閉じたポリゴンにするため最初の値を末尾に追加
    theta_closed = theta + [theta[0]]
    r_closed = r + [r[0]]

    fig = go.Figure(
        data=go.Scatterpolar(
            r=r_closed,
            theta=theta_closed,
            fill="toself",
            name=ticker,
            line=dict(color="#4F8DFF"),
            fillcolor="rgba(79, 141, 255, 0.25)",
        )
    )
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100], tick0=0, dtick=20),
        ),
        showlegend=False,
        title=dict(text=f"{ticker} — Composite Score 7 軸"),
        margin=dict(l=40, r=40, t=60, b=40),
        height=380,
    )
    return fig
