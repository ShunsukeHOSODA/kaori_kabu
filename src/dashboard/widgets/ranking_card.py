"""Claude Sonnet 4.6 ranking TOP N 銘柄詳細カードウィジェット。

Phase 5.4.0-B 新規。``signal_aggregator.RankingSignalBundle`` (Phase 5.3.1) と
``ranking_judge.RankingResult`` (Phase 5.2) を入力に取り、Monte Carlo fan chart
Plotly Figure (Phase 5.4.0-A) を埋め込んだカード UI を構築する純粋描画関数。

CLAUDE.md §9 該当規約:
    §9.3 一本線予測禁止 → Monte Carlo 確率分布 (fan chart) として埋め込み
    §9.4 シグナル根拠併記 + リスク警告併記 →
        ``supporting_signals`` ✅ / ``risk_signals`` ⚠️ チップで両論併記
    §9.5 損切り規律明示 → ``counter_view`` ブロックで反対意見を必ず表示
    §9.7 認知バイアス警告 → Confirmation Bias 対策の counter_view
    §9.8.5 Provenance 開示 → 02_screener.py 側で別 expander、本 widget では不要

Streamlit 関数 (``container``/``markdown``/``tabs``/``plotly_chart``/``warning``)
を使うため戻り値は ``None``。本関数は純粋な描画責務のみ持ち、データ取得・計算は
呼び出し側 (02_screener.py、Phase 5.4.2 で結線) が担う。
"""

from __future__ import annotations

from typing import Final

import plotly.graph_objects as go
import streamlit as st

from analysis.ranking_judge import RankingResult, RankingSignalBundle

# ---------------------------------------------------------------------------
# 定数（色・文言）
# ---------------------------------------------------------------------------

# supporting / risk の HTML 表示色（Streamlit markdown unsafe_allow_html=True で使用）
_SUPPORT_COLOR: Final[str] = "#1f7a3f"  # 緑系
_RISK_COLOR: Final[str] = "#b8341e"  # 赤系

# lens_views の Sonnet 固定 3 キー → タブ表示名マッピング
# キー名は ranking_judge.py L321 の _validate_lens_views_keys で
# Buffett_Munger / Burry / Lynch の 3 キー固定が強制される
_LENS_TAB_LABELS: Final[tuple[tuple[str, str], ...]] = (
    ("Buffett_Munger", "Buffett-Munger"),
    ("Burry", "Burry"),
    ("Lynch", "Lynch"),
)

# CLAUDE.md §9.3 免責文言
_DISCLAIMER: Final[str] = (
    "⚠️ AI 判定は確率分布の参考情報です。最終判断はユーザー自身で。"
)


# ---------------------------------------------------------------------------
# 内部ヘルパー（純粋関数、HTML 文字列生成）
# ---------------------------------------------------------------------------


def _format_chip(text: str, *, emoji: str, color: str) -> str:
    """1 件のシグナルチップ HTML を生成する純粋関数。

    Streamlit ``st.markdown(..., unsafe_allow_html=True)`` で描画する。

    Args:
        text: シグナル本文
        emoji: 先頭絵文字 (✅ or ⚠️)
        color: 文字色 (CSS color value)

    Returns:
        ``<span style=...>絵文字 text</span>`` の HTML 文字列
    """
    return (
        f'<span style="color:{color};font-weight:600;'
        f"background-color:rgba(0,0,0,0.04);padding:2px 8px;"
        f"border-radius:12px;margin-right:6px;display:inline-block;"
        f'margin-bottom:4px;">{emoji} {text}</span>'
    )


def _format_chips_block(signals: tuple[str, ...], *, emoji: str, color: str) -> str:
    """シグナル群を 1 ブロックの HTML 文字列に変換する。"""
    return "".join(_format_chip(s, emoji=emoji, color=color) for s in signals)


# ---------------------------------------------------------------------------
# メイン描画関数
# ---------------------------------------------------------------------------


def render_ranking_card(
    ticker: str,
    ranking_result: RankingResult,
    signal_bundle: RankingSignalBundle,
    mc_figure: go.Figure | None = None,
) -> None:
    """Claude TOP N 銘柄の詳細カードを Streamlit に描画する。

    本関数は戻り値を持たない純粋な描画責務関数。データ取得・計算は呼び出し側
    (``02_screener.py``、Phase 5.4.2 で結線) が担う。

    表示要素 (design.md L1248-1260):
        1. ``st.container(border=True)`` 内に
           大きな ``ranking_score`` 表示 + ``recommendation_summary``
           （blockquote）
        2. ``supporting_signals`` チップ (✅ 緑バッジ)
        3. ``risk_signals`` チップ (⚠️ 赤バッジ)
        4. ``counter_view`` ブロッククォート（反対意見、Confirmation Bias 対策）
        5. ``st.tabs(["Buffett-Munger", "Burry", "Lynch"])`` で
           ``lens_views`` の各レンズ判定
        6. ``mc_figure`` を ``st.plotly_chart(use_container_width=True)`` で埋込
           （None なら ``st.info`` で「未計算」表示）
        7. 末尾に ``st.caption`` で §9.3 免責文言

    ``RankingResult.fallback_reason`` が ``None`` でない場合は
    「⚠️ Claude 判定縮退中 (理由: ...)」を冒頭に表示し、レンズタブ + counter_view
    + supporting/risk チップは描画するが Monte Carlo 埋込はスキップして
    info 表示に倒す（縮退中は判定信頼度が低いため誤誘導を避ける）。

    Args:
        ticker: ティッカー (例 "AAPL", "7203.T")
        ranking_result: ``ranking_judge.rank_with_claude`` / ``batch`` の戻り値要素
        signal_bundle: ``signal_aggregator.build_signal_bundle`` の戻り値
        mc_figure: ``render_fan_chart_plotly`` の戻り値（None 可）
    """
    # st.container(border=True) で外枠を作る。with 文で内側に描画。
    with st.container(border=True):
        # ----------------------------------------------------------------
        # 1. 縮退時の警告 + ヘッダー
        # ----------------------------------------------------------------
        if ranking_result.fallback_reason is not None:
            st.warning(
                f"⚠️ Claude 判定縮退中 (理由: {ranking_result.fallback_reason})"
                "  数式スコアのみで判断中、信頼度は低めです。"
            )

        # 大きな ranking_score 表示。Composite Score も小さく併記して両論明示。
        st.markdown(
            f"### {ticker} — Claude スコア "
            f"{ranking_result.ranking_score:.1f}/100  "
            f"<span style='color:#666;font-size:0.7em;'>"
            f"(Composite {signal_bundle.composite_score:.1f}, "
            f"preset: {signal_bundle.composite_preset})"
            f"</span>",
            unsafe_allow_html=True,
        )

        # ----------------------------------------------------------------
        # 2. recommendation_summary を blockquote で表示
        # ----------------------------------------------------------------
        st.markdown(f"> {ranking_result.recommendation_summary}")

        # ----------------------------------------------------------------
        # 3. supporting_signals チップ (✅ 緑)
        # ----------------------------------------------------------------
        st.markdown("**支持シグナル**")
        st.markdown(
            _format_chips_block(
                ranking_result.supporting_signals,
                emoji="✅",
                color=_SUPPORT_COLOR,
            ),
            unsafe_allow_html=True,
        )

        # ----------------------------------------------------------------
        # 4. risk_signals チップ (⚠️ 赤) — §9.4 リスク警告併記
        # ----------------------------------------------------------------
        st.markdown("**リスクシグナル**")
        st.markdown(
            _format_chips_block(
                ranking_result.risk_signals,
                emoji="⚠️",
                color=_RISK_COLOR,
            ),
            unsafe_allow_html=True,
        )

        # ----------------------------------------------------------------
        # 5. counter_view ブロッククォート — §9.7 Confirmation Bias 対策
        # ----------------------------------------------------------------
        st.markdown("**反対意見 (Confirmation Bias 対策)**")
        st.markdown(f"> 🤔 {ranking_result.counter_view}")

        # ----------------------------------------------------------------
        # 6. lens_views を 3 タブで表示 (Buffett-Munger / Burry / Lynch)
        # ----------------------------------------------------------------
        tab_labels = [label for _, label in _LENS_TAB_LABELS]
        tabs = st.tabs(tab_labels)
        for tab, (lens_key, lens_label) in zip(tabs, _LENS_TAB_LABELS, strict=True):
            with tab:
                lens_text = ranking_result.lens_views.get(lens_key, "(不在)")
                st.markdown(f"**{lens_label} レンズ判定**")
                st.markdown(lens_text)

        # ----------------------------------------------------------------
        # 7. Monte Carlo fan chart 埋込 — §9.3 確率分布表示
        # ----------------------------------------------------------------
        if mc_figure is not None and ranking_result.fallback_reason is None:
            st.plotly_chart(mc_figure, use_container_width=True)
        elif ranking_result.fallback_reason is not None:
            # 縮退中は MC 表示しない（判定信頼度が低いため誤誘導を避ける）
            st.info(
                "Monte Carlo シミュレーション非表示 (Claude 判定縮退中のため)"
            )
        else:
            st.info("Monte Carlo シミュレーション未計算")

        # ----------------------------------------------------------------
        # 8. 免責文言 — §9.3 一本線予測禁止規約の念押し
        # ----------------------------------------------------------------
        st.caption(_DISCLAIMER)
