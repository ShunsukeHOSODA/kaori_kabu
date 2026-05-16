"""Magic Formula スクリーニング 1 回分の状態スナップショット。

Phase 5.5.1 (handoff-session-6 §2.6) で導入。``_display_screening_results`` が
受け取っていた 11 引数（P-M-2 / C-M-2 の 2 reviewer 一致指摘）を 1 つの
:class:`ScreeningSession` (frozen dataclass) に集約する。

``run_button`` 経路で計算し ``st.session_state["screening_session"]`` に格納する。
BUY フォーム / ``_display_screening_results`` / 結果テーブル再描画は本オブジェクトを
受け取って動く。dataclass は frozen + slots でメモリ効率と immutability を確保
（CLAUDE.md §9 / python-patterns）。

依存方向:
    src.dashboard.views._screener_session
        → src.analysis.magic_formula, ranking_judge, sentiment
        → src.strategies.kelly

session_state 互換性:
    Streamlit は in-memory なので pickling 不要。frozen dataclass を直接格納でき、
    BUY フォーム経路で ``st.session_state["screening_session"]`` から取り出して
    そのままフィールドアクセス可能。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from src.analysis.magic_formula import MagicFormulaResult
from src.analysis.ranking_judge import RankingResult, RankingSignalBundle
from src.analysis.sentiment import SentimentResult
from src.data.news import MarketContext
from src.strategies.kelly import KellyParams

# 推奨カード 1 銘柄分の解析結果タプル。
# Phase 2: (rank, ticker, magic_formula_row_dict, analysis_tuple | None)
# analysis_tuple = (MarketContext, SentimentResult, pd.DataFrame) | None
RecommendationAnalysis = tuple[
    int,
    str,
    dict[str, Any],
    tuple[MarketContext, SentimentResult, Any] | None,
]

# ---------------------------------------------------------------------------
# 描画・計算双方が参照する共有定数 (Phase 5.5.6 C-HIGH-1 解消)
# ---------------------------------------------------------------------------
# 推奨根拠カードに自動分析する銘柄数（待ち時間を許容、視界に収まる粒度のベスト）。
# _screener_compute (Phase 2 分析計算) と _screener_display (サブヘッダ表示) +
# 02_screener.py (サイドバー UI のヘルプ文言) の 3 箇所から参照される共通定数。
TOP_PICKS_FOR_NEWS: int = 5
DEFAULT_NEWS_LENSES: tuple[str, ...] = ("Buffett_Munger", "Burry")


@dataclass(frozen=True, slots=True)
class ScreeningSession:
    """Magic Formula スクリーニング 1 回分の全状態。

    ``run_button`` 経路の compute フェーズが構築し、描画 helper と BUY フォームの
    両経路で再利用する。frozen のため計算後の状態改変を構造的に禁止する
    （CLAUDE.md §9 immutability）。

    Attributes:
        result: Magic Formula 計算結果（テーブル + Provenance metadata）。
        composite_rows: 7 軸 Composite Score テーブル行（dataframe 化前の dict）。
            BUY フォームは ``_ticker_raw`` キーで lookup する。
        composite_warnings: 警告 expander 用 (ticker, warnings) リスト。
        radar_data: 7 軸レーダーチャート用 (ticker, score, sub_scores) リスト。
        analyses: 推奨根拠カード分析結果（Tavily/Exa + Claude Haiku）。
            ``enable_news_cards == False`` のとき ``None``。
        ranking_results: Sonnet 4.6 ranking judge の結果リスト。Sonnet 縮退時 ``None``。
        signal_bundles: Sonnet 入力シグナル束。``ranking_results`` と同順序・同長。
        composite_preset: 現在の投資スタイルプリセット (``"Buffett_型_暫定"`` 等)。
        real_mode: ``True`` = EODHD ライブ、``False`` = Demo 合成 10 銘柄。
        enable_news_cards: 推奨根拠カードを描画するか。
        enable_composite: Composite Score テーブルを描画するか。
        exchange: サイドバーで選択された取引所 (``"US"`` or ``"TO"``)。
        kelly_params_default: BUY フォーム既定値の Kelly パラメータ。
        portfolio_value_jpy_dec: BUY フォーム既定値のポートフォリオ評価額。
        calculated_at_iso: ``result.metadata.calculated_at`` の ISO 8601 文字列。
            ``ScreenerTrigger.screener_run_at`` に渡すため事前に文字列化済み。
        code_commit: 計算時の git short hash（Provenance §9.8.2）。
    """

    # ── 計算結果（描画 helper が参照） ──────────────────────────────
    result: MagicFormulaResult
    composite_rows: list[dict[str, Any]]
    composite_warnings: list[tuple[str, list[Any]]]
    radar_data: list[tuple[str, float, dict[str, float]]]
    analyses: list[RecommendationAnalysis] | None
    ranking_results: list[RankingResult] | None
    signal_bundles: list[RankingSignalBundle] | None

    # ── 制御フラグ（描画分岐 + 縮退判定で参照） ─────────────────────
    composite_preset: str
    real_mode: bool
    enable_news_cards: bool
    enable_composite: bool
    exchange: str

    # ── BUY フォーム経路で参照する追加状態 ─────────────────────────
    kelly_params_default: KellyParams
    portfolio_value_jpy_dec: Decimal
    calculated_at_iso: str
    code_commit: str | None
