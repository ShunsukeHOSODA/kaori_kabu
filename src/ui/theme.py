"""Streamlit カスタムテーマ — Dark luxury + Editorial（CLAUDE.md §1）。

各ダッシュボードページ冒頭で :func:`apply_theme` を呼び出すと、
カスタム CSS をページに injection してデザイントークンを統一する。

デザインガイドライン:
    - 数字は tabular-nums で揃え、フィナンシャル UI らしさを出す
    - カードはホバーで微妙にリフト（depth = 信頼感）
    - アクセントカラーはセマンティック使用に限定（強気=緑、弱気=赤、警告=黄）
    - 余白大胆 + タイポ階層強化で素人っぽさを排除
"""

from __future__ import annotations

import streamlit as st

# CSS injection 本体。:root にデザイントークンを定義し、Streamlit 各
# 要素のセレクタにカスタム指定を当てる。
_CUSTOM_CSS: str = """
<style>
:root {
    --color-emerald: #10b981;
    --color-emerald-soft: #34d399;
    --color-amber: #f59e0b;
    --color-ruby: #ef4444;
    --color-bg-deep: #0a0e1a;
    --color-surface: #141b2d;
    --color-surface-hover: #1a2238;
    --color-border: rgba(255, 255, 255, 0.08);
    --color-border-strong: rgba(255, 255, 255, 0.16);
    --color-text-muted: rgba(231, 234, 243, 0.55);

    --space-section: clamp(2rem, 1rem + 3vw, 4rem);
    --radius-card: 14px;
    --shadow-card: 0 1px 2px rgba(0, 0, 0, 0.2),
                   0 4px 12px rgba(0, 0, 0, 0.15);
    --shadow-card-hover: 0 8px 24px rgba(16, 185, 129, 0.10),
                         0 2px 6px rgba(0, 0, 0, 0.30);

    --duration-fast: 150ms;
    --duration-normal: 250ms;
    --ease-out-expo: cubic-bezier(0.16, 1, 0.3, 1);
}

/* ===== タイポ階層 ===== */
.stApp h1 {
    font-weight: 700 !important;
    letter-spacing: -0.025em !important;
    font-size: clamp(2rem, 1.5rem + 1.5vw, 2.75rem) !important;
    background: linear-gradient(135deg, #ffffff 0%, #a8b2d1 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin-bottom: 0.5rem !important;
}
.stApp h2 {
    font-weight: 600 !important;
    letter-spacing: -0.015em !important;
    margin-top: var(--space-section) !important;
}
.stApp h3 {
    font-weight: 600 !important;
    letter-spacing: -0.01em !important;
}

/* ===== 数字は等幅で揃える（フィナンシャル UI 標準）===== */
[data-testid="stMetricValue"],
[data-testid="stMetricDelta"],
[data-testid="stDataFrame"],
.stDataFrame td,
code {
    font-variant-numeric: tabular-nums !important;
    font-feature-settings: "tnum" 1 !important;
}

[data-testid="stMetricValue"] {
    font-weight: 700 !important;
}

/* ===== カード（st.container border=True）===== */
[data-testid="stVerticalBlockBorderWrapper"] {
    background: var(--color-surface) !important;
    border: 1px solid var(--color-border) !important;
    border-radius: var(--radius-card) !important;
    box-shadow: var(--shadow-card) !important;
    transition: transform var(--duration-fast) var(--ease-out-expo),
                box-shadow var(--duration-fast) var(--ease-out-expo),
                border-color var(--duration-fast) var(--ease-out-expo) !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:hover {
    transform: translateY(-2px);
    border-color: var(--color-border-strong) !important;
    box-shadow: var(--shadow-card-hover) !important;
}

/* ===== サイドバー ===== */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #080c17 0%, #0d1322 100%) !important;
    border-right: 1px solid var(--color-border) !important;
}
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
    background: none !important;
    -webkit-text-fill-color: initial !important;
    color: #ffffff !important;
}

/* ===== ボタン ===== */
.stButton > button {
    border-radius: 10px !important;
    font-weight: 600 !important;
    letter-spacing: 0.01em !important;
    transition: transform var(--duration-fast) var(--ease-out-expo),
                box-shadow var(--duration-fast) var(--ease-out-expo) !important;
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, var(--color-emerald), var(--color-emerald-soft)) !important;
    border: none !important;
    color: #0a0e1a !important;
}
.stButton > button[kind="primary"]:hover:not(:disabled) {
    transform: translateY(-1px);
    box-shadow: 0 8px 24px rgba(16, 185, 129, 0.35) !important;
}
.stButton > button[kind="primary"]:disabled {
    opacity: 0.5 !important;
}

/* ===== expander ===== */
[data-testid="stExpander"] {
    border: 1px solid var(--color-border) !important;
    border-radius: var(--radius-card) !important;
    background: rgba(255, 255, 255, 0.015) !important;
}
[data-testid="stExpander"] summary {
    font-weight: 500 !important;
}

/* ===== テーブル ===== */
[data-testid="stDataFrame"] {
    border-radius: var(--radius-card) !important;
    overflow: hidden !important;
    border: 1px solid var(--color-border) !important;
}

/* ===== キャプション ===== */
[data-testid="stCaptionContainer"],
.stCaption {
    color: var(--color-text-muted) !important;
    font-style: normal !important;
}

/* ===== divider ===== */
hr {
    border: none !important;
    border-top: 1px solid var(--color-border) !important;
    margin: var(--space-section) 0 !important;
}

/* ===== alert ===== */
[data-testid="stAlert"] {
    border-radius: var(--radius-card) !important;
    border-left-width: 3px !important;
}

/* ===== success ===== */
[data-baseweb="notification"][kind="positive"] {
    background: rgba(16, 185, 129, 0.10) !important;
    border-color: var(--color-emerald) !important;
}

/* ===== progress ===== */
[data-testid="stProgress"] > div > div > div > div {
    background: linear-gradient(90deg, var(--color-emerald), var(--color-emerald-soft)) !important;
}

/* ===== Markdown link ===== */
.stMarkdown a {
    color: var(--color-emerald-soft) !important;
    text-decoration: none !important;
    border-bottom: 1px solid rgba(52, 211, 153, 0.3);
    transition: border-color var(--duration-fast) var(--ease-out-expo);
}
.stMarkdown a:hover {
    border-bottom-color: var(--color-emerald-soft);
}

/* ===== ブロック引用 ===== */
.stMarkdown blockquote {
    border-left: 3px solid var(--color-emerald) !important;
    background: rgba(16, 185, 129, 0.05);
    padding: 0.75rem 1rem !important;
    border-radius: 0 8px 8px 0;
}
</style>
"""


def apply_theme() -> None:
    """ページ冒頭で呼び出してカスタム CSS を injection。

    ``st.set_page_config`` の直後に呼ぶこと。
    """
    st.markdown(_CUSTOM_CSS, unsafe_allow_html=True)


def render_page_header(
    *,
    title: str,
    subtitle: str | None = None,
    icon: str = "",
) -> None:
    """統一ヘッダーを描画。

    アイコン + タイトル + サブタイトルの 3 行構成で全ページ共通の
    視覚的階層を作る。
    """
    if icon:
        st.markdown(
            f'<div style="font-size: 2.5rem; line-height: 1; margin-bottom: '
            f'0.25rem;">{icon}</div>',
            unsafe_allow_html=True,
        )
    st.title(title)
    if subtitle:
        st.caption(subtitle)
