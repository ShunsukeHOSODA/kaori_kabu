"""ranking_card.render_ranking_card の単体テスト。

Phase 5.4.0-B TDD。Streamlit / Plotly を mock し、純粋描画責務のみ検証する。

検証項目:
    1. ``st.markdown`` が複数回呼ばれる（ヘッダー / blockquote / チップ / レンズ）
    2. ticker + ranking_score 文字列がいずれかの markdown 呼び出しに含まれる
    3. ``supporting_signals`` テキストが markdown 呼び出しに含まれる
    4. ``mc_figure`` を渡すと ``st.plotly_chart`` が 1 回以上呼ばれる
    5. ``mc_figure=None`` だと ``st.plotly_chart`` が呼ばれず ``st.info`` が呼ばれる
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from analysis.ranking_judge import (
    RankingMetadata,
    RankingResult,
    RankingSignalBundle,
)

# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_st():
    """``ranking_card.st`` を MagicMock に差し替え。

    ``st.container(border=True)`` の戻り値は ``with`` 文サポートが必要なため
    ``__enter__``/``__exit__`` を MagicMock で実装。``st.tabs`` も 3 要素の
    context manager リストを返す。
    """
    with patch("src.dashboard.widgets.ranking_card.st") as m:
        # st.container(border=True) を with 文サポート可能にする
        container_cm = MagicMock()
        container_cm.__enter__ = MagicMock(return_value=None)
        container_cm.__exit__ = MagicMock(return_value=False)
        m.container.return_value = container_cm

        # st.tabs(...) も同様に 3 要素の with サポート MagicMock リストを返す
        tab_mocks = []
        for _ in range(3):
            tab = MagicMock()
            tab.__enter__ = MagicMock(return_value=None)
            tab.__exit__ = MagicMock(return_value=False)
            tab_mocks.append(tab)
        m.tabs.return_value = tab_mocks

        yield m


def _make_metadata() -> RankingMetadata:
    """テスト用最小 RankingMetadata。"""
    return RankingMetadata(
        model="claude-sonnet-4-6",
        model_version="claude-sonnet-4-6-20250514",
        calculation_method="ranking_judge_v1",
        input_bundle_hash="a" * 64,
        cache_hit=False,
        cache_age_sec=None,
        input_tokens=1000,
        output_tokens=500,
        input_tokens_cached=0,
        calculated_at=datetime.now(UTC),
        academic_source="Greenblatt 2010 + Tetlock 2007",
        code_commit="abc1234",
    )


def _make_ranking_result(
    *,
    fallback_reason: str | None = None,
) -> RankingResult:
    """テスト用最小 RankingResult。

    Sonnet 出力の必須スキーマ (Buffett_Munger/Burry/Lynch 3 キー固定 +
    supporting/risk_signals 1 件以上 + counter_view 非空) を満たす。
    """
    return RankingResult(
        ranking_score=85,
        recommendation_summary="Magic Formula 上位、Berkshire 新規買いでスマートマネー追従の余地。",
        supporting_signals=(
            "Magic Formula スコア 87/100",
            "Berkshire が新規買い",
        ),
        risk_signals=(
            "Value Trap 警戒",
            "Recency Bias 注意",
        ),
        counter_view="直近 3 ヶ月モメンタムは弱含み、Recency Bias の罠に注意。",
        lens_views={
            "Buffett_Munger": "Moat 強固、ROIC 28% で QARP 条件を満たす。",
            "Burry": "信用拡大局面の終盤、空売り余地は限定的。",
            "Lynch": "PEG 0.8 で割安、消費者目線では認知拡大期。",
        },
        confidence=Decimal("0.75"),
        confidence_adjusted=Decimal("0.75"),
        kelly_multiplier=Decimal("0.5"),
        fallback_reason=fallback_reason,
        metadata=_make_metadata(),
    )


def _make_signal_bundle() -> RankingSignalBundle:
    """テスト用最小 RankingSignalBundle。"""
    return RankingSignalBundle(
        ticker="AAPL",
        exchange="US",
        sector="Technology",
        composite_score=82.5,
        sub_scores={
            "Q": 90.0,
            "V": 70.0,
            "I": 60.0,
            "G": 85.0,
            "R": 75.0,
            "M": 88.0,
            "S": 70.0,
        },
        composite_preset="Buffett_型_暫定",
        magic_formula_score=87.0,
        roc_pct=Decimal("28.0"),
        earnings_yield_pct=Decimal("6.5"),
        momentum_1m=Decimal("0.03"),
        momentum_12m=Decimal("0.25"),
        sentiment_score=Decimal("0.4"),
        sentiment_confidence=Decimal("0.7"),
        sentiment_themes=("earnings beat", "guidance up"),
        polymarket_macro={"fed_cut_2026": Decimal("0.62")},
        fund_holdings_delta={
            "Berkshire": {"action": "NEW", "value_change": 1_000_000}
        },
        regime="Bull",
        regime_state_probs={
            "Bull": Decimal("0.8"),
            "Choppy": Decimal("0.15"),
            "Crisis": Decimal("0.05"),
        },
        fetched_at=datetime.now(UTC),
    )


def _all_markdown_text(mock_st: MagicMock) -> str:
    """``st.markdown`` の全呼び出し引数を 1 文字列に結合する。"""
    parts: list[str] = []
    for call in mock_st.markdown.call_args_list:
        if call.args:
            parts.append(str(call.args[0]))
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# テスト
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRenderRankingCard:
    """render_ranking_card の描画責務を検証。"""

    def test_render_calls_st_markdown(self, mock_st: MagicMock) -> None:
        """st.markdown が複数回呼ばれる（少なくとも 5 回: ヘッダー/サマリー/
        支持/リスク/反対意見 + レンズ）。"""
        from src.dashboard.widgets.ranking_card import render_ranking_card

        render_ranking_card(
            ticker="AAPL",
            ranking_result=_make_ranking_result(),
            signal_bundle=_make_signal_bundle(),
            mc_figure=None,
        )

        assert mock_st.markdown.call_count >= 5

    def test_render_displays_ticker_and_score(
        self, mock_st: MagicMock
    ) -> None:
        """ヘッダー markdown に ticker と ranking_score が含まれる。"""
        from src.dashboard.widgets.ranking_card import render_ranking_card

        render_ranking_card(
            ticker="AAPL",
            ranking_result=_make_ranking_result(),
            signal_bundle=_make_signal_bundle(),
            mc_figure=None,
        )

        all_md = _all_markdown_text(mock_st)
        assert "AAPL" in all_md
        # ranking_score=85 → "85.0/100" として表示
        assert "85" in all_md
        assert "/100" in all_md

    def test_render_supporting_signals_displayed(
        self, mock_st: MagicMock
    ) -> None:
        """supporting_signals のテキストが markdown 呼び出しに含まれる。"""
        from src.dashboard.widgets.ranking_card import render_ranking_card

        render_ranking_card(
            ticker="AAPL",
            ranking_result=_make_ranking_result(),
            signal_bundle=_make_signal_bundle(),
            mc_figure=None,
        )

        all_md = _all_markdown_text(mock_st)
        assert "Magic Formula スコア 87/100" in all_md
        assert "Berkshire が新規買い" in all_md
        # risk_signals も併記されているか（§9.4 リスク警告併記）
        assert "Value Trap 警戒" in all_md
        # counter_view も描画されているか（§9.7 Confirmation Bias 対策）
        assert "Recency Bias の罠に注意" in all_md

    def test_render_with_mc_figure_calls_plotly_chart(
        self, mock_st: MagicMock
    ) -> None:
        """mc_figure を渡すと st.plotly_chart が 1 回以上呼ばれる。"""
        from src.dashboard.widgets.ranking_card import render_ranking_card

        fake_figure = MagicMock()  # plotly.graph_objects.Figure の代替
        render_ranking_card(
            ticker="AAPL",
            ranking_result=_make_ranking_result(),
            signal_bundle=_make_signal_bundle(),
            mc_figure=fake_figure,
        )

        assert mock_st.plotly_chart.call_count >= 1
        # use_container_width=True で呼ばれているか
        call_kwargs = mock_st.plotly_chart.call_args.kwargs
        assert call_kwargs.get("use_container_width") is True

    def test_render_without_mc_figure_skips_plotly(
        self, mock_st: MagicMock
    ) -> None:
        """mc_figure=None なら st.plotly_chart が呼ばれず st.info が呼ばれる。"""
        from src.dashboard.widgets.ranking_card import render_ranking_card

        render_ranking_card(
            ticker="AAPL",
            ranking_result=_make_ranking_result(),
            signal_bundle=_make_signal_bundle(),
            mc_figure=None,
        )

        assert mock_st.plotly_chart.call_count == 0
        # 未計算メッセージが st.info で表示されている
        assert mock_st.info.call_count >= 1
        info_msg = str(mock_st.info.call_args.args[0])
        assert "Monte Carlo" in info_msg


@pytest.mark.unit
class TestFallbackReasonHandling:
    """fallback_reason が非 None のときの縮退表示を検証（補足テスト）。"""

    def test_fallback_displays_warning_and_skips_plotly(
        self, mock_st: MagicMock
    ) -> None:
        """fallback_reason がある時は st.warning が呼ばれ、mc_figure を
        渡しても plotly_chart はスキップされる（誤誘導回避）。"""
        from src.dashboard.widgets.ranking_card import render_ranking_card

        fake_figure = MagicMock()
        render_ranking_card(
            ticker="AAPL",
            ranking_result=_make_ranking_result(
                fallback_reason="API timeout after 3 retries"
            ),
            signal_bundle=_make_signal_bundle(),
            mc_figure=fake_figure,
        )

        assert mock_st.warning.call_count >= 1
        warning_msg = str(mock_st.warning.call_args.args[0])
        assert "縮退" in warning_msg
        assert "API timeout" in warning_msg
        # 縮退時は MC をスキップする
        assert mock_st.plotly_chart.call_count == 0
