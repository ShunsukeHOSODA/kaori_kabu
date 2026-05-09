"""ATR トレーリングストップアラートウィジェット。

各保有銘柄の OHLC + 現在価格から、ATR トレーリングストップ条件への
到達を判定し、規律ベースの「売却検討」表示を行う。

CLAUDE.md §9.3「一本線予測禁止」 / §9.5「Decision Log 記録」 / §9.7
「Loss Aversion 対策」を遵守。"指示" ではなく "条件到達 + 根拠" で表現する。
ロジック (:func:`evaluate_alert`) は Streamlit 非依存で単体テスト容易。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Final, Literal

import pandas as pd

from src.strategies.atr_stop import calculate_trailing_stop

AlertStatus = Literal["safe", "near", "breach"]

NEAR_THRESHOLD_PCT: Final[Decimal] = Decimal("0.02")
"""ストップ価格の +2% 以内で「接近 (near)」判定。"""


@dataclass(frozen=True)
class AtrAlert:
    """1 銘柄の ATR ストップ判定結果。"""

    ticker: str
    current_price: Decimal
    stop_price: Decimal
    status: AlertStatus
    reason_lines: tuple[str, ...]
    currency: str = "JPY"
    """価格の通貨単位。``JPY`` / ``USD`` 等。デフォルトは JPY（日本株 + 評価額換算後）。"""


def evaluate_alert(
    ticker: str,
    ohlc: pd.DataFrame,
    current_price: Decimal,
    *,
    extra_reasons: tuple[str, ...] = (),
    atr_period: int = 14,
    atr_multiplier: Decimal = Decimal("2.5"),
    lookback: int = 20,
    currency: str = "JPY",
) -> AtrAlert:
    """OHLC + 現在価格 → アラート判定。

    Args:
        ticker: 銘柄シンボル
        ohlc: ``high`` / ``low`` / ``close`` カラムを持つ DataFrame
        current_price: 評価時点の現在価格（``Decimal``、同一通貨）
        extra_reasons: 追加根拠メッセージタプル（規律ベース根拠の併記）
        atr_period: ATR 計算期間（デフォルト 14、Wilder 標準）
        atr_multiplier: ATR 倍数（デフォルト 2.5）
        lookback: 最高値ルックバック期間（デフォルト 20）

    Returns:
        :class:`AtrAlert`。``status``:
            - ``safe``: 現在価格 ≥ ストップ × 1.02
            - ``near``: ストップ × 1.0 ≤ 現在価格 < ストップ × 1.02
            - ``breach``: 現在価格 < ストップ
    """
    stop = calculate_trailing_stop(
        ohlc,
        atr_period=atr_period,
        atr_multiplier=atr_multiplier,
        lookback=lookback,
    )

    if current_price < stop:
        status: AlertStatus = "breach"
    elif current_price < stop * (Decimal("1") + NEAR_THRESHOLD_PCT):
        status = "near"
    else:
        status = "safe"

    return AtrAlert(
        ticker=ticker,
        current_price=current_price,
        stop_price=stop,
        status=status,
        reason_lines=tuple(extra_reasons),
        currency=currency,
    )


_STATUS_DISPLAY: Final[dict[AlertStatus, tuple[str, str, str]]] = {
    "safe": ("🟢", "に余裕あり", "success"),
    "near": ("🟡", "に**接近**", "warning"),
    "breach": ("🔴", "を**抵触**", "error"),
}

# Streamlit の Markdown レンダラは ``$...$`` を KaTeX の inline math として解釈する。
# USD 表示で ``$`` が連続出現すると 2 個目までが数式 delimiter とマッチし、
# 「基準 $277、現在 $293」が「基準 ``277、現在`` 293」と崩れて描画される
# （2026-05-09 実機で確認）。``\$`` でリテラル ``$`` にエスケープする。
_CURRENCY_SYMBOLS: Final[dict[str, str]] = {
    "JPY": "¥",
    "USD": r"\$",
    "EUR": "€",
    "GBP": "£",
}


def _format_price(price: Decimal) -> str:
    """通貨表示用に価格を桁区切り整数 or 小数 2 桁で整形。

    JPY のような大きな数値は桁区切り整数、USD のような小数値は 2 桁で表示。
    """
    if price >= Decimal("100"):
        return f"{int(price):,}"
    return f"{price:.2f}"


def render_alert_row(alert: AtrAlert, *, container: object | None = None) -> None:
    """単一アラートをホーム画面 1 行で描画（規律ベース表現）。

    出力例（status="near"）::

        🟡 **AAPL**: ATR トレーリングストップ条件に**接近**（基準 ¥24,500、現在 ¥24,800）。
        **売却検討**。
        理由（参考）:
          1. Magic Formula スコア低下 87→62

    Args:
        alert: :func:`evaluate_alert` の戻り値
        container: ``st`` モジュール / ``st.container()`` インスタンス
    """
    if container is None:
        import streamlit as st

        container = st

    icon, headline, render_fn_name = _STATUS_DISPLAY[alert.status]
    symbol = _CURRENCY_SYMBOLS.get(alert.currency, alert.currency + " ")
    msg_main = (
        f"{icon} **{alert.ticker}**: ATR トレーリングストップ条件{headline}"
        f"（基準 {symbol}{_format_price(alert.stop_price)}、"
        f"現在 {symbol}{_format_price(alert.current_price)}）。"
    )
    msg_action = "**売却検討**。" if alert.status != "safe" else "現在は安全圏。"
    full_msg = f"{msg_main} {msg_action}"

    if alert.reason_lines:
        bullet_lines = "\n".join(
            f"  {i}. {line}" for i, line in enumerate(alert.reason_lines, start=1)
        )
        full_msg += f"\n\n理由（参考）:\n{bullet_lines}"

    render_fn = getattr(container, render_fn_name)
    render_fn(full_msg)
