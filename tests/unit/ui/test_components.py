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
