"""atr_alert.evaluate_alert / render_alert_row の単体テスト。

CLAUDE.md §9.3「一本線予測禁止」 / §9.5「Decision Log 記録」 / §9.7
「Loss Aversion 対策」を遵守する規律ベース表現を保証する。
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pandas as pd
import pytest

from dashboard.widgets.atr_alert import (
    AtrAlert,
    evaluate_alert,
    render_alert_row,
)


# 全日均一 OHLC: ATR=10, LookbackHigh=110, multiplier=2.5, lookback=5
# → stop = 110 - 10 * 2.5 = 85
_STABLE_OHLC = pd.DataFrame(
    {
        "high": [110.0, 110.0, 110.0, 110.0, 110.0],
        "low": [100.0, 100.0, 100.0, 100.0, 100.0],
        "close": [105.0, 105.0, 105.0, 105.0, 105.0],
    }
)


@pytest.mark.unit
class TestEvaluateAlert:
    """evaluate_alert の status 判定検証。stop=85 を前提。"""

    def test_現在価格が_stop_の余裕圏なら_safe(self) -> None:
        # 現在価格 = 105 > stop * 1.02 = 86.7 → safe
        alert = evaluate_alert(
            "AAPL",
            _STABLE_OHLC,
            Decimal("105"),
            atr_period=5,
            atr_multiplier=Decimal("2.5"),
            lookback=5,
        )

        assert alert.status == "safe"
        assert alert.stop_price == Decimal("85")
        assert alert.ticker == "AAPL"

    def test_現在価格が_stop_接近圏で_near(self) -> None:
        # stop=85, near 閾値 = 85 * 1.02 = 86.7
        # 現在価格 = 86 → 85 ≤ 86 < 86.7 → near
        alert = evaluate_alert(
            "AAPL",
            _STABLE_OHLC,
            Decimal("86"),
            atr_period=5,
            atr_multiplier=Decimal("2.5"),
            lookback=5,
        )

        assert alert.status == "near"

    def test_現在価格が_stop_未満で_breach(self) -> None:
        # stop=85, 現在価格 = 80 < 85 → breach
        alert = evaluate_alert(
            "AAPL",
            _STABLE_OHLC,
            Decimal("80"),
            atr_period=5,
            atr_multiplier=Decimal("2.5"),
            lookback=5,
        )

        assert alert.status == "breach"

    def test_extra_reasons_が_AtrAlert_に保持される(self) -> None:
        alert = evaluate_alert(
            "AAPL",
            _STABLE_OHLC,
            Decimal("105"),
            extra_reasons=("Magic Formula スコア低下 87→62",),
            atr_period=5,
            atr_multiplier=Decimal("2.5"),
            lookback=5,
        )

        assert alert.reason_lines == ("Magic Formula スコア低下 87→62",)

    def test_AtrAlert_は_frozen_で不変(self) -> None:
        alert = evaluate_alert(
            "AAPL",
            _STABLE_OHLC,
            Decimal("105"),
            atr_period=5,
            atr_multiplier=Decimal("2.5"),
            lookback=5,
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            alert.ticker = "TSLA"  # type: ignore[misc]


@pytest.mark.unit
class TestRenderAlertRow:
    """render_alert_row が container にどのメソッドを呼ぶか検証。"""

    def _make_alert(self, status: str) -> AtrAlert:
        return AtrAlert(
            ticker="AAPL",
            current_price=Decimal("24800"),
            stop_price=Decimal("24500"),
            status=status,  # type: ignore[arg-type]
            reason_lines=("Magic Formula スコア低下 87→62",),
        )

    def test_breach_のとき_error_を呼ぶ(self) -> None:
        container = MagicMock()
        alert = self._make_alert("breach")

        render_alert_row(alert, container=container)

        container.error.assert_called_once()
        msg = container.error.call_args[0][0]
        assert "AAPL" in msg
        assert "🔴" in msg
        assert "売却検討" in msg
        assert "理由" in msg
        assert "Magic Formula" in msg

    def test_near_のとき_warning_を呼ぶ(self) -> None:
        container = MagicMock()
        alert = self._make_alert("near")

        render_alert_row(alert, container=container)

        container.warning.assert_called_once()
        msg = container.warning.call_args[0][0]
        assert "🟡" in msg
        assert "接近" in msg

    def test_safe_のとき_success_を呼び_売却検討は出さない(self) -> None:
        container = MagicMock()
        alert = self._make_alert("safe")

        render_alert_row(alert, container=container)

        container.success.assert_called_once()
        msg = container.success.call_args[0][0]
        assert "🟢" in msg
        assert "安全圏" in msg
        # safe のときは "売却検討" を出さない（Confirmation Bias 抑止）
        assert "売却検討" not in msg
