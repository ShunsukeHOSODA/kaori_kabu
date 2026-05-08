"""ATR (Average True Range) トレーリングストップ（CLAUDE.md §9.5 / §9.7）。

Wilder 1978 の定義に従い、True Range の N 日平均で ATR を計算。
Stop = LookbackHigh - ATR * Multiplier で買い建て時のトレーリングストップ。

Loss Aversion バイアス対策として全ポジションに機械的に適用する。
価格が Stop を割れば売却シグナル → 規律的損切り。

参考:
    Wilder, J. W. Jr. (1978). *New Concepts in Technical Trading Systems*.
"""

from __future__ import annotations

from decimal import Decimal

import pandas as pd


def calculate_atr(df: pd.DataFrame, *, period: int = 14) -> Decimal:
    """ATR (Average True Range) を計算。

    True Range = max(High-Low, |High-PrevClose|, |Low-PrevClose|)
    ATR = 直近 ``period`` 日の TR 平均

    day1 では ``prev_close`` が NaN のため ``high - low`` のみが TR となる
    （pandas の ``max(axis=1)`` は NaN を skip）。

    Args:
        df: ``high``, ``low``, ``close`` カラムを持つ OHLC DataFrame
        period: 計算期間（デフォルト 14 日、Wilder 標準）

    Returns:
        ATR（Decimal）。
    """
    high = df["high"]
    low = df["low"]
    prev_close = df["close"].shift(1)

    tr_components = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    )
    tr = tr_components.max(axis=1)

    atr_value = tr.tail(period).mean()
    return Decimal(str(atr_value))


def calculate_trailing_stop(
    df: pd.DataFrame,
    *,
    atr_period: int = 14,
    atr_multiplier: Decimal = Decimal("2.5"),
    lookback: int = 20,
) -> Decimal:
    """ATR トレーリングストップ価格を計算。

    ``Stop = LookbackHigh - ATR * Multiplier``

    買い建て時の使い方:
        - 初回は買値の下に設定
        - 価格上昇で LookbackHigh が更新されて Stop も自動上昇（trailing）
        - 価格が Stop を割れば売却シグナル

    Args:
        df: ``high``, ``low``, ``close`` カラムを持つ OHLC DataFrame
        atr_period: ATR 計算期間（デフォルト 14、``ATR_PERIOD``）
        atr_multiplier: ATR 倍数（デフォルト 2.5、``ATR_MULTIPLIER``）
        lookback: 最高値ルックバック期間（デフォルト 20、``TRAILING_STOP_LOOKBACK``）

    Returns:
        トレーリングストップ価格（Decimal）。
    """
    atr = calculate_atr(df, period=atr_period)
    lookback_high = Decimal(str(df["high"].tail(lookback).max()))
    return lookback_high - atr * atr_multiplier
