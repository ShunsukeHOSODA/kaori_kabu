"""ATR (Average True Range) トレーリングストップの単体テスト。

CLAUDE.md §9.5 / §9.7 に準拠（Loss Aversion 対策、機械的な損切り規律）:
    - True Range = max(High-Low, |High-PrevClose|, |Low-PrevClose|)
    - ATR = N 日の TR 平均（通常 14 日）
    - Trailing Stop = LookbackHigh - ATR * Multiplier（通常 2.5）

参考: J. Welles Wilder Jr., 1978, "New Concepts in Technical Trading Systems"
"""

from __future__ import annotations

from decimal import Decimal

import pandas as pd
import pytest


@pytest.mark.unit
class TestCalculateATR:
    """ATR 計算の検証。"""

    def test_全日均一OHLCで_ATRが固定値になる(self) -> None:
        """全日の OHLC が同じなら TR も均一、ATR = TR。

        TR = max(High-Low, |High-PrevClose|, |Low-PrevClose|)
           = max(110-100, |110-105|, |100-105|) = max(10, 5, 5) = 10
        ATR(period=5) = 10 平均 = 10
        """
        from strategies.atr_stop import calculate_atr

        df = pd.DataFrame(
            {
                "high": [110.0, 110.0, 110.0, 110.0, 110.0],
                "low": [100.0, 100.0, 100.0, 100.0, 100.0],
                "close": [105.0, 105.0, 105.0, 105.0, 105.0],
            }
        )

        atr = calculate_atr(df, period=5)

        assert atr == Decimal("10")

    def test_変動OHLCで_ATR平均(self) -> None:
        """異なる TR の平均が ATR。

        day1 TR = high - low = 10（prev_close なし）
        day2 TR = max(120-110, |120-105|, |110-105|) = max(10, 15, 5) = 15
        day3 TR = max(115-105, |115-115|, |105-115|) = max(10, 0, 10) = 10
        day4 TR = max(110-100, |110-105|, |100-105|) = max(10, 5, 5) = 10
        day5 TR = max(118-108, |118-110|, |108-110|) = max(10, 8, 2) = 10
        ATR(period=5) = (10+15+10+10+10)/5 = 11
        """
        from strategies.atr_stop import calculate_atr

        df = pd.DataFrame(
            {
                "high": [110.0, 120.0, 115.0, 110.0, 118.0],
                "low": [100.0, 110.0, 105.0, 100.0, 108.0],
                "close": [105.0, 115.0, 105.0, 110.0, 110.0],
            }
        )

        atr = calculate_atr(df, period=5)

        assert atr == Decimal("11")

    def test_Decimal型を返す(self) -> None:
        from strategies.atr_stop import calculate_atr

        df = pd.DataFrame(
            {"high": [110.0] * 5, "low": [100.0] * 5, "close": [105.0] * 5}
        )

        atr = calculate_atr(df, period=5)

        assert isinstance(atr, Decimal)


@pytest.mark.unit
class TestCalculateTrailingStop:
    """ATR トレーリングストップ価格の計算。

    Stop = LookbackHigh - ATR * Multiplier
    """

    def test_基本計算_Stop_85(self) -> None:
        """ATR=10, LookbackHigh=110, Multiplier=2.5 → Stop = 110 - 25 = 85"""
        from strategies.atr_stop import calculate_trailing_stop

        df = pd.DataFrame(
            {
                "high": [110.0, 110.0, 110.0, 110.0, 110.0],
                "low": [100.0, 100.0, 100.0, 100.0, 100.0],
                "close": [105.0, 105.0, 105.0, 105.0, 105.0],
            }
        )

        stop = calculate_trailing_stop(
            df, atr_period=5, atr_multiplier=Decimal("2.5"), lookback=5
        )

        assert stop == Decimal("85")

    def test_LookbackHighが正しく取られる(self) -> None:
        """直近 lookback 日の最高値が起点。"""
        from strategies.atr_stop import calculate_trailing_stop

        df = pd.DataFrame(
            {
                "high": [110.0, 115.0, 120.0, 125.0, 130.0],
                "low": [100.0, 105.0, 110.0, 115.0, 120.0],
                "close": [105.0, 110.0, 115.0, 120.0, 125.0],
            }
        )

        stop = calculate_trailing_stop(
            df, atr_period=5, atr_multiplier=Decimal("2.0"), lookback=5
        )

        # ATR は固定 10（差が同じなので）、LookbackHigh=130, Stop = 130 - 20 = 110
        assert stop == Decimal("110")
