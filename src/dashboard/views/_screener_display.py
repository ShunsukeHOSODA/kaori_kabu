"""Magic Formula スクリーナー描画 helper（Phase 5.5.0 で 02_screener.py から切り出し）。

handoff-session-6 §5.1 / Phase 5.4.4 C-H-2 指摘の解消:
    02_screener.py が 1857 行 (800 budget の 2.3x) に膨張していたため、
    純粋な描画関数を本モジュールに移動し、02_screener.py は
    サイドバー UI + 制御フロー + BUY フォーム + 学習 expander に集中する。

責務分離:
    - 本モジュール: 計算済みデータの描画専用 (副作用は st.* 呼び出しのみ)
    - ``_screener_compute.py``: run_button 経路の計算ロジック
    - ``02_screener.py``: ページエントリ + サイドバー UI + 制御フロー + BUY フォーム

呼び出し規約 (Phase 5.5.1 で ScreeningSession 化):
    すべての描画は :func:`render_screening_results` に 1 つの
    :class:`ScreeningSession` を渡すだけで完結する。内部 helper は
    private (_display_*) で本モジュール外部からは呼ばない。
"""

from __future__ import annotations

import dataclasses
import json
import math
from datetime import datetime
from decimal import Decimal
from typing import Any

import pandas as pd
import streamlit as st

from src.analysis.composite import PRESET_DISPLAY_LABELS, PRESET_RATIONALE
from src.analysis.magic_formula import MagicFormulaResult
from src.analysis.monte_carlo import (
    percentiles_for_fan_chart,
    render_fan_chart_plotly,
    simulate_gbm_paths,
)
from src.analysis.ranking_judge import RankingResult, RankingSignalBundle
from src.analysis.sentiment import SentimentResult
from src.config.settings import settings
from src.dashboard.views._screener_compute import compute_mu_for_monte_carlo
from src.dashboard.views._screener_session import (
    DEFAULT_NEWS_LENSES,
    TOP_PICKS_FOR_NEWS,
    ScreeningSession,
)
from src.dashboard.widgets.ranking_card import render_ranking_card
from src.data.famous_holdings import get_famous_owners, render_owner_badges
from src.data.news import MarketContext
from src.ui.components import (
    composite_radar_chart,
    format_lenses_applied,
    format_sentiment_emoji,
    format_sentiment_label,
)


# ---------------------------------------------------------------------------
# Provenance ユーティリティ
# ---------------------------------------------------------------------------


def _decimal_default(obj: object) -> str:
    """JSON シリアライザ: ``Decimal`` / ``datetime`` → ``str`` 変換 (Provenance 用)。

    ``json.dumps(..., default=_decimal_default)`` で
    :class:`decimal.Decimal` / :class:`datetime.datetime` を文字列化する。
    Phase 5.4.4 で Claude セクションの Provenance expander から呼び出される。
    Phase 6 で ``src/analysis/_provenance.py`` に集約候補（handoff §2.5）。
    """
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Not JSON serializable: {type(obj).__name__}")


# ---------------------------------------------------------------------------
# 推奨根拠カード描画（Phase 2、ニュース + センチメント + レンズ統合）
# ---------------------------------------------------------------------------


def render_recommendation_card(
    *,
    rank: int,
    ticker: str,
    magic_formula_row: dict[str, Any],
    market_context: MarketContext | None,
    sentiment: SentimentResult,
    lenses_applied: tuple[str, ...],
) -> None:
    """推奨根拠カード 1 枚を描画（結果テーブル直下に並ぶ）。"""
    score = sentiment.sentiment_score
    emoji = format_sentiment_emoji(score)
    label = format_sentiment_label(score)

    rank_emoji = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]
    rank_label = rank_emoji[rank - 1] if rank <= len(rank_emoji) else f"#{rank}"

    with st.container(border=True):
        # ヘッダー: ランク + ティッカー + Magic Formula スコア + センチメント
        header_cols = st.columns([1, 4, 3])
        with header_cols[0]:
            st.markdown(f"### {rank_label}")
        with header_cols[1]:
            st.markdown(f"### **{ticker}**")
            mf = magic_formula_row
            st.caption(
                f"Magic Formula スコア `{mf.get('magic_formula_score', '—')}` ／ "
                f"ROC `{mf.get('roc', '—')}` ／ EY `{mf.get('earnings_yield', '—')}`"
                + (
                    f"\nセクター: {mf.get('sector')}"
                    if mf.get("sector")
                    else ""
                )
            )
        with header_cols[2]:
            st.markdown(f"### {emoji} {label}")
            st.caption(
                f"score `{score}` / conf `{sentiment.confidence}`"
            )

        # 要約（推奨根拠の中心）
        if sentiment.summary:
            st.markdown(f"💡 **推奨根拠**: {sentiment.summary}")

        # 主要テーマ + リスクシグナル
        cols = st.columns(2)
        with cols[0]:
            if sentiment.key_themes:
                st.markdown("**主要テーマ**")
                for theme in sentiment.key_themes:
                    st.markdown(f"- {theme}")
            else:
                st.caption("主要テーマ: —")
        with cols[1]:
            if sentiment.risk_signals:
                st.markdown("⚠️ **リスクシグナル**")
                for signal in sentiment.risk_signals:
                    st.markdown(f"- {signal}")
            else:
                st.caption("リスクシグナル: —")

        # 適用レンズ + ソース URL
        if lenses_applied:
            st.caption(f"適用レンズ: {format_lenses_applied(lenses_applied)}")

        if market_context is not None:
            all_news = pd.concat(
                [
                    market_context.ticker_news,
                    market_context.macro_news,
                    market_context.geopolitical_news,
                    market_context.research,
                ],
                ignore_index=True,
                sort=False,
            )
            if len(all_news) > 0 and "url" in all_news.columns:
                with st.expander(f"🔗 ソース URL ({len(all_news)} 件、上位 5 表示)"):
                    for _, row in all_news.head(5).iterrows():
                        title = str(row.get("title", "")).strip()
                        url = str(row.get("url", "")).strip()
                        if url and url != "nan":
                            st.markdown(f"- [{title or url}]({url})")

        # Provenance（CLAUDE.md §9.8.5 必須）
        with st.expander("ⓘ 出所追跡情報"):
            md = sentiment.metadata
            st.json(
                {
                    "model_version": md.model_version,
                    "calculation_method": md.calculation_method,
                    "input_news_count": md.input_news_count,
                    "academic_source": md.academic_source,
                    "calculated_at": md.calculated_at.isoformat(),
                    "code_commit": md.code_commit,
                    "lenses_applied": list(lenses_applied),
                }
            )


# ---------------------------------------------------------------------------
# Magic Formula 結果テーブル + 各セクション
# ---------------------------------------------------------------------------


def _display_provenance(result: MagicFormulaResult) -> None:
    """Provenance 開示 expander (CLAUDE.md §9.8.5)。"""
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


_NumericOrNone = Decimal | float | int | None


def _is_missing(x: object) -> bool:
    """欠損値判定 (None / NaN / inf / pd.NA / Decimal NaN/inf すべて吸収)。

    Phase 6.1 review (code-reviewer + python-reviewer 2 視点一致) で
    ``float('inf')`` / ``pd.NA`` / ``Decimal('NaN')`` がガード漏れすると
    指摘されたため統一ヘルパーに集約。``pd.isna`` は ``float('inf')`` を
    ``False`` 扱いするため ``math.isinf`` で明示判定する。
    """
    if x is None:
        return True
    if isinstance(x, Decimal):
        return x.is_nan() or x.is_infinite()
    if isinstance(x, float):
        return math.isnan(x) or math.isinf(x)
    try:
        return bool(pd.isna(x))
    except (TypeError, ValueError):
        return False


def _format_decimal_pct(x: _NumericOrNone) -> str:
    """Decimal/数値を百分率文字列に変換 (CLAUDE.md §9.1: float を経由しない)。"""
    if _is_missing(x):
        return "—"
    pct = Decimal(str(x)) * Decimal("100")
    return f"{pct:.2f}%"


def _format_market_cap_usd_billion(x: _NumericOrNone) -> str:
    """時価総額 (USD) を ``$NNN.NB`` 表示に整形 (CLAUDE.md §9.1: float を経由しない)。"""
    if _is_missing(x):
        return "—"
    billion = Decimal(str(x)) / Decimal("1000000000")
    return f"${billion:,.1f}B"


def _display_magic_formula_table(result: MagicFormulaResult) -> None:
    """Magic Formula 結果テーブル (上位 N 銘柄の ROC / EY ランキング)。"""
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
    display_df["roc"] = display_df["roc"].apply(_format_decimal_pct)
    display_df["earnings_yield"] = display_df["earnings_yield"].apply(
        _format_decimal_pct
    )
    if "market_cap" in display_df.columns:
        display_df["market_cap"] = display_df["market_cap"].apply(
            _format_market_cap_usd_billion
        )

    rename_map = {
        "ticker": "ティッカー",
        "magic_formula_score": "合算スコア（小さいほど良い）",
        "roc": "資本利益率(ROC)",
        "earnings_yield": "益利回り(EY)",
        "roc_rank": "ROC 順位",
        "ey_rank": "EY 順位",
        "sector": "セクター",
        "market_cap": "時価総額",
    }
    display_df = display_df.rename(columns=rename_map)
    st.dataframe(display_df, use_container_width=True, hide_index=True)


def _display_recommendation_cards(
    analyses: list[tuple[int, str, dict[str, Any], Any]],
) -> None:
    """推奨根拠カード描画 (Phase 2: ニュース・センチメント・レンズ統合)。

    `analyses` は run_button 経路で計算済みの結果リスト。本関数は描画専門で、
    re-fetch / re-analyze は行わない。
    """
    st.subheader(f"📋 上位 {TOP_PICKS_FOR_NEWS} 銘柄の推奨根拠")
    st.caption(
        f"Tavily/Exa で 4 系統ニュース取得 + 投資家レンズ "
        f"({format_lenses_applied(DEFAULT_NEWS_LENSES)}) + Claude Haiku "
        "でセンチメント分析。「なぜ推すか」の根拠をカードで併記。"
    )

    for rank, ticker_name, mf_dict, analysis in analyses:
        if analysis is None:
            with st.container(border=True):
                st.markdown(f"### {rank}️⃣ **{ticker_name}**")
                st.warning(
                    "⚠️ ニュース・センチメント分析に失敗。"
                    "API キー / レート制限 / ネットワークを確認してください。"
                )
            continue
        mc, sent, _ = analysis
        mf_display = {
            "magic_formula_score": mf_dict.get("magic_formula_score", "—"),
            "roc": (
                _format_decimal_pct(mf_dict["roc"]) if "roc" in mf_dict else "—"
            ),
            "earnings_yield": (
                _format_decimal_pct(mf_dict["earnings_yield"])
                if "earnings_yield" in mf_dict
                else "—"
            ),
            "sector": mf_dict.get("sector", ""),
        }
        render_recommendation_card(
            rank=rank,
            ticker=ticker_name,
            magic_formula_row=mf_display,
            market_context=mc,
            sentiment=sent,
            lenses_applied=DEFAULT_NEWS_LENSES,
        )


def _display_composite_section(
    *,
    composite_rows: list[dict[str, Any]],
    composite_warnings: list[tuple[str, list[Any]]],
    radar_data: list[tuple[str, float, dict[str, float]]],
    composite_preset: str,
) -> None:
    """Composite Score テーブル + 警告 expander + 7 軸レーダー (Phase 3.1a)。"""
    st.subheader("📋 Composite Score 詳細（投資家視点の総合スコア）")
    st.caption(
        f"投資スタイル: **{PRESET_DISPLAY_LABELS[composite_preset]}** — "
        f"{PRESET_RATIONALE[composite_preset]}"
    )
    # §4.2 #3: Half-Kelly 推奨サイズの注記（暫定値の根拠を明示、§9.4 / §9.7）
    st.info(
        "📌 **Half-Kelly 推奨** は暫定値で計算: "
        "**勝率 60%**（Magic Formula 経験則、Greenblatt 2010）/ "
        "**損益比 2.0**（ATR 2R ストップ設計）/ "
        "**1 銘柄上限 5%**（Overconfidence 対策、Thorp 2006）。"
        "実バックテスト結果が揃い次第、銘柄別の実測値で更新予定。"
    )

    if composite_rows:
        st.dataframe(
            pd.DataFrame(composite_rows)
            .drop(columns=["_ticker_raw"])
            .sort_values("Composite", ascending=False),
            use_container_width=True,
            hide_index=True,
        )
        if composite_warnings:
            with st.expander(
                f"⚠️ 警告詳細（{len(composite_warnings)} 銘柄）"
            ):
                for tk, warns in composite_warnings:
                    st.markdown(f"**{tk}**")
                    for w in warns:
                        icon = (
                            "🚨" if w.severity == "RED"
                            else ("⚠️" if w.severity == "AMBER" else "ℹ️")
                        )
                        st.markdown(f"- {icon} `{w.code}`: {w.message}")
        st.caption(
            "Q=Quality / V=Value / I=Income / G=Growth / R=Risk / "
            "M=Momentum / S=Sentiment（各 0-100）。"
            "Composite はプリセット重み付け合算（0-100）。"
            "詳細設計: `docs/long-term-investment-architecture.md`"
        )

        # 7 軸レーダーチャート — 上位 3 銘柄を並べて視覚比較
        top_n_radar = sorted(
            radar_data, key=lambda r: r[1], reverse=True
        )[:3]
        if top_n_radar:
            st.markdown("##### 🎯 上位銘柄 7 軸レーダーチャート")
            cols = st.columns(len(top_n_radar))
            for col, (tk, score, subs) in zip(
                cols, top_n_radar, strict=False
            ):
                with col:
                    fig = composite_radar_chart(ticker=tk, sub_scores=subs)
                    st.plotly_chart(
                        fig,
                        use_container_width=True,
                        key=f"radar_{tk}",
                    )
                    st.caption(f"Composite: **{score:.1f}** / 100")
    else:
        st.info(
            "Composite Score を計算できる銘柄がありませんでした"
            "（ファンダ取得失敗 or 必須フィールド欠損）"
        )


def _display_risk_warnings(
    *,
    real_mode: bool,
    enable_news_cards: bool,
    enable_composite: bool,
) -> None:
    """リスク警告メッセージ (CLAUDE.md §9.4 / §9.7)。"""
    risk_messages = [
        "**過去パフォーマンス ≠ 将来**: 直近 5 年は SP500 にアンダーパフォーム",
        "**Value Trap リスク**: 構造不況業種は永久に割安なまま",
        "**認知バイアス対策**: Confirmation Bias を避け、反対意見も検討すること",
    ]
    if not real_mode:
        risk_messages.insert(
            0, "**デモデータ**: このページは合成 10 銘柄のサンプルです"
        )
    if enable_news_cards:
        risk_messages.append(
            "**センチメントは補助情報**: ニュース要約は判断の補助、最終判断は自分で"
        )
    if enable_composite and real_mode:
        risk_messages.append(
            "**総合スコアは Phase 3.1b 時点の暫定値**: ROIC/WACC・連続増配年数・"
            "13F 機関投資家保有・株主優待は Phase 3.2 以降で精緻化予定"
        )
    st.warning("⚠️ **リスク警告**\n\n- " + "\n- ".join(risk_messages))


def _display_claude_section(
    ranking_results: list[RankingResult],
    signal_bundles: list[RankingSignalBundle],
) -> None:
    """Claude TOP N 銘柄の詳細カードセクション (Phase 5.4.2)。

    ``settings.ranking_top_detail_count`` (既定 5) 件を ``ranking_score`` 降順で
    並べ、各銘柄カードに Monte Carlo fan chart (個別銘柄向け簡易シミュレーション)
    を埋め込む。``fallback_reason`` 付きの結果が混じっている場合は冒頭に縮退件数
    の warning を表示する (CLAUDE.md §9.4 リスク警告併記)。

    Monte Carlo 設計:
        - ``start_price=100.0`` の相対値ベースで fan chart を描く
          (絶対株価は通貨混在 + 銘柄横断比較のノイズになるため避ける)
        - ``mu`` は ``momentum_12m / 100`` で年率換算した近似値
          (Phase 6 で realized return に置換予定)
        - ``sigma=0.25`` 暫定 (Phase 6 で realized vol に置換予定)
        - ``n_paths=1000``、CLAUDE.md §9.3 「Monte Carlo は最低 1000 パス」準拠

    Args:
        ranking_results: ``rank_with_claude_batch`` の戻り値要素リスト。
            ``signal_bundles`` と同順序・同長を呼び出し側が保証する。
        signal_bundles: ``aggregate_signals_for_universe`` の戻り値。
    """
    st.subheader("🤖 Claude による総合判定")

    fallback_count = sum(
        1 for r in ranking_results if r.fallback_reason is not None
    )
    if fallback_count > 0:
        st.warning(
            f"⚠️ {fallback_count}/{len(ranking_results)} 銘柄が数式縮退中"
            "（Claude 判定不可、Stage 1 由来の埋め値で表示）"
        )

    sorted_pairs = sorted(
        zip(ranking_results, signal_bundles, strict=True),
        key=lambda p: p[0].ranking_score,
        reverse=True,
    )

    for rank, (result, bundle) in enumerate(
        sorted_pairs[: settings.ranking_top_detail_count], start=1
    ):
        st.markdown(f"### #{rank} — {bundle.ticker}")
        # Monte Carlo: momentum_12m を mu の近似値として使用 (年率)。
        # 計算は compute 層の compute_mu_for_monte_carlo に集約 (handoff §4.16)。
        mu_value = compute_mu_for_monte_carlo(bundle)
        # TODO(Phase 6): sigma を realized vol、start_price を実価格に置換 (handoff §5.4)
        paths = simulate_gbm_paths(
            start_price=100.0,  # 相対価格 (基準 100)
            mu=mu_value,
            sigma=0.25,
            days=settings.mc_horizon_days,
            n_paths=settings.mc_simulations,
            seed=42,  # CLAUDE.md §9.8 Provenance: 決定論性確保
        )
        pct_df = percentiles_for_fan_chart(paths)
        fig = render_fan_chart_plotly(pct_df, bundle.ticker)
        render_ranking_card(bundle.ticker, result, bundle, fig)
        st.divider()

    # CLAUDE.md §9.3 一本線予測禁止規約の念押し
    st.warning(
        "⚠️ **これは投資助言ではありません。** 最終判断はユーザー自身で行ってください。"
        "AI 出力は確率分布の参考情報です。"
    )

    # Provenance expander (CLAUDE.md §9.8.5)
    # Decimal / datetime は ``_decimal_default`` で文字列化することで JSON 直列化可能にする。
    with st.expander("ⓘ Provenance — Claude への入力と出力 JSON"):
        for result, bundle in zip(
            ranking_results, signal_bundles, strict=True
        ):
            st.markdown(f"#### {bundle.ticker}")
            # asdict は Decimal を Decimal のまま残すため、json.dumps で str 化
            # してから loads し直して st.json に流す。
            input_bundle = json.loads(
                json.dumps(dataclasses.asdict(bundle), default=_decimal_default)
            )
            output_result = result.model_dump(mode="json")
            st.json(
                {
                    "input_bundle": input_bundle,
                    "output_result": output_result,
                }
            )


# ---------------------------------------------------------------------------
# Entry point: ScreeningSession 1 引数で全描画を実行
# ---------------------------------------------------------------------------


def render_screening_results(session: ScreeningSession) -> None:
    """ScreeningSession から Magic Formula 結果セクション全体を描画する。

    run_button 経路 + session_state 経路の両方から呼べる純粋な描画関数。
    計算は呼び出し側 (``_screener_compute.run_screening_pipeline``) の責務で、
    本関数はデータ表示のみ。

    §12.3 解消: BUY フォーム submit による rerun で run_button==False に
    なっても、session_state["screening_session"] に保存した ``ScreeningSession``
    を本関数に流し込めば結果テーブル全体を再描画できる。

    表示順序 (既存挙動を完全保全、Phase 5.4.4 の出力と bit-equal):
        1. ✅ 抽出件数 success メッセージ
        2. ⓘ Provenance 開示 (CLAUDE.md §9.8.5)
        3. Magic Formula 結果テーブル
        4. 推奨根拠カード (enable_news_cards & analyses != None のとき)
        5. Composite Score 詳細 + 警告 expander + 7 軸レーダーチャート
           (enable_composite & real_mode のとき)
        6. Claude TOP N 詳細カード (Phase 5.4.2、ranking_results が非 None のとき)
        7. リスク警告 (CLAUDE.md §9.4 / §9.7)
    """
    st.success(
        f"✅ Top {len(session.result.result)} 銘柄を抽出 "
        f"({session.result.metadata.calculated_at.strftime('%Y-%m-%d %H:%M:%S UTC')})"
    )

    # ── 1. Provenance 開示 ───────────────────────────────────────
    _display_provenance(session.result)

    # ── 2. Magic Formula 結果テーブル ────────────────────────────
    _display_magic_formula_table(session.result)

    # ── 3. 推奨根拠カード (Phase 2) ──────────────────────────────
    if session.enable_news_cards and session.analyses is not None:
        _display_recommendation_cards(session.analyses)

    # ── 4. Composite Score 詳細 (Phase 3.1a) ─────────────────────
    if session.enable_composite and session.real_mode:
        _display_composite_section(
            composite_rows=session.composite_rows,
            composite_warnings=session.composite_warnings,
            radar_data=session.radar_data,
            composite_preset=session.composite_preset,
        )

    # ── 5. Claude TOP N 詳細カード (Phase 5.4.2) ─────────────────
    # Sonnet 判定が成功した場合のみ表示。縮退時は ranking_results=None で
    # スキップされる (Composite ランキングのみで動作継続)。
    if session.ranking_results is not None and session.signal_bundles is not None:
        _display_claude_section(session.ranking_results, session.signal_bundles)

    # ── 6. リスク警告 (CLAUDE.md §9.4 / §9.7) ───────────────────
    _display_risk_warnings(
        real_mode=session.real_mode,
        enable_news_cards=session.enable_news_cards,
        enable_composite=session.enable_composite,
    )
