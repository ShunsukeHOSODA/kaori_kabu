"""UI コンポーネントの純粋関数の単体テスト。

``render_*`` 系の Streamlit 命令は本テストの範囲外。score → emoji 変換や
lens タプル → ラベル化など純粋関数だけを対象とする。
"""

from __future__ import annotations

from decimal import Decimal

import pytest


@pytest.mark.unit
class TestFormatSentimentEmoji:
    """センチメントスコア → 信号灯絵文字。

    閾値:
        score >=  0.3 → 🟢 (強気)
        score <= -0.3 → 🔴 (弱気)
        それ以外      → 🟡 (中立)
    """

    @pytest.mark.parametrize(
        "score, expected",
        [
            (Decimal("0.65"), "🟢"),
            (Decimal("0.3"), "🟢"),
            (Decimal("0.29"), "🟡"),
            (Decimal("0"), "🟡"),
            (Decimal("-0.29"), "🟡"),
            (Decimal("-0.3"), "🔴"),
            (Decimal("-0.8"), "🔴"),
        ],
    )
    def test_境界値マッピング(self, score: Decimal, expected: str) -> None:
        from ui.components import format_sentiment_emoji

        assert format_sentiment_emoji(score) == expected


@pytest.mark.unit
class TestFormatSentimentLabel:
    """センチメントスコア → 日本語ラベル。"""

    @pytest.mark.parametrize(
        "score, expected",
        [
            (Decimal("0.65"), "強気"),
            (Decimal("0.3"), "強気"),
            (Decimal("0"), "中立"),
            (Decimal("-0.5"), "弱気"),
        ],
    )
    def test_境界値マッピング(self, score: Decimal, expected: str) -> None:
        from ui.components import format_sentiment_label

        assert format_sentiment_label(score) == expected


@pytest.mark.unit
class TestFormatLensesApplied:
    """投資家レンズ名タプル → 表示用文字列。"""

    def test_複数レンズはセパレータで結合(self) -> None:
        from ui.components import format_lenses_applied

        result = format_lenses_applied(("Buffett_Munger", "Burry"))

        assert "Buffett" in result
        assert "Burry" in result

    def test_空タプルはダッシュ(self) -> None:
        from ui.components import format_lenses_applied

        assert format_lenses_applied(()) == "—"


@pytest.mark.unit
class TestCompositeRadarChart:
    """7 軸 Composite Score のレーダーチャート（Phase 3.1b）。"""

    def test_Plotly_Figure_を返す(self) -> None:
        import plotly.graph_objects as go

        from ui.components import composite_radar_chart

        fig = composite_radar_chart(
            ticker="AAPL",
            sub_scores={
                "Q": 80.0,
                "V": 60.0,
                "I": 50.0,
                "G": 70.0,
                "R": 75.0,
                "M": 55.0,
                "S": 40.0,
            },
        )
        assert isinstance(fig, go.Figure)

    def test_7軸ラベル全て含む(self) -> None:
        from ui.components import composite_radar_chart

        fig = composite_radar_chart(
            ticker="AAPL",
            sub_scores={
                "Q": 80.0,
                "V": 60.0,
                "I": 50.0,
                "G": 70.0,
                "R": 75.0,
                "M": 55.0,
                "S": 40.0,
            },
        )
        trace = fig.data[0]
        theta_vals = list(trace.theta)
        for axis_label in (
            "Quality",
            "Value",
            "Income",
            "Growth",
            "Risk",
            "Momentum",
            "Sentiment",
        ):
            assert axis_label in theta_vals

    def test_スコア値が_r軸に反映(self) -> None:
        from ui.components import composite_radar_chart

        fig = composite_radar_chart(
            ticker="AAPL",
            sub_scores={
                "Q": 80.0,
                "V": 60.0,
                "I": 50.0,
                "G": 70.0,
                "R": 75.0,
                "M": 55.0,
                "S": 40.0,
            },
        )
        r_vals = list(fig.data[0].r)
        assert all(0.0 <= v <= 100.0 for v in r_vals)
        assert 80.0 in r_vals
        assert 40.0 in r_vals

    def test_ticker_名がタイトルに反映(self) -> None:
        from ui.components import composite_radar_chart

        fig = composite_radar_chart(
            ticker="トヨタ",
            sub_scores={
                "Q": 50.0,
                "V": 50.0,
                "I": 50.0,
                "G": 50.0,
                "R": 50.0,
                "M": 50.0,
                "S": 50.0,
            },
        )
        title_text = fig.layout.title.text or ""
        assert "トヨタ" in title_text

    def test_欠損キーはゼロで補完(self) -> None:
        """V/G/M が省略された場合（Phase 3.1a 互換）でも壊れない。"""
        from ui.components import composite_radar_chart

        fig = composite_radar_chart(
            ticker="LEGACY",
            sub_scores={"Q": 70.0, "I": 60.0, "R": 80.0, "S": 50.0},
        )
        r_vals = list(fig.data[0].r)
        assert 0.0 in r_vals  # V/G/M はゼロで補完
