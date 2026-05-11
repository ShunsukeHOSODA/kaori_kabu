"""市場レジーム信号灯ウィジェット。

HMM レジーム検出結果（:class:`src.analysis.regime.RegimeResult`）を受け取り、
🟢/🟡/🔴 の信号灯 + 推奨アクション + 折りたたみ詳細を 1 行で表示する。

CLAUDE.md §9.7 認知バイアス警告（Recency Bias 抑止）の中核 UI。
ロジック (:func:`to_signal`) は Streamlit 非依存で単体テスト容易。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from src.analysis.regime import RegimeLabel, RegimeResult


@dataclass(frozen=True)
class RegimeSignal:
    """信号灯表示用の正規化結果（テスト & UI 共通）。"""

    emoji: Literal["🟢", "🟡", "🔴"]
    label_ja: str
    action_ja: str
    color: Literal["normal", "warning", "error"]


_LABEL_MAP: Final[dict[RegimeLabel, RegimeSignal]] = {
    "Bull": RegimeSignal("🟢", "強気相場", "積極買い OK", "normal"),
    "Choppy": RegimeSignal("🟡", "横ばい", "慎重・配当株中心", "warning"),
    "Crisis": RegimeSignal("🔴", "暴落リスク", "新規買い停止", "error"),
}


def to_signal(result: RegimeResult) -> RegimeSignal:
    """RegimeResult.current_regime → RegimeSignal の純粋変換。"""
    return _LABEL_MAP[result.current_regime]


def render_regime_signal(
    result: RegimeResult | None,
    *,
    container: object | None = None,
) -> None:
    """ホーム画面 1 行で信号灯を表示、折りたたみで詳細を出す。

    Args:
        result: HMM レジーム検出結果。``None`` のときは「判定中」フォールバック表示。
        container: ``st`` モジュール または ``st.container()`` インスタンス。
            未指定時は import-on-call で ``streamlit`` を使う（テスト時は MagicMock を渡す）。
    """
    if container is None:
        import streamlit as st

        container = st

    if result is None:
        container.info("🟢 市場の機嫌: **判定中**（VIX データ取得待ち）")  # type: ignore[attr-defined]
        return

    signal = to_signal(result)
    msg = f"{signal.emoji} 市場の機嫌: **{signal.label_ja}** — {signal.action_ja}"
    if signal.color == "error":
        container.error(msg)  # type: ignore[attr-defined]
    elif signal.color == "warning":
        container.warning(msg)  # type: ignore[attr-defined]
    else:
        container.success(msg)  # type: ignore[attr-defined]

    # VIX 取得失敗 → SPY realized vol 代理使用時の警告（§4.1 #2、handoff-phase4.md）。
    # Provenance §9.8: vix_source が "realized_vol_proxy_v1" のときのみ表示。
    if result.metadata.vix_source == "realized_vol_proxy_v1":
        container.warning(  # type: ignore[attr-defined]
            "⚠️ VIX 取得失敗 → SPY realized vol を代理使用中。"
            "判定精度が低下している可能性があります"
            "（市場の恐怖指数 = implied vol に対し、代理は過去 30 日 realized vol）"
        )

    # 詳細（学習期間・出所・判定方法）は折りたたみで開示
    expander = container.expander("ⓘ 詳細（HMM 学習結果）")  # type: ignore[attr-defined]
    with expander:
        expander.write(f"判定方法: {result.metadata.calculation_method}")
        if result.metadata.training_period:
            expander.write(f"学習期間: {result.metadata.training_period}")
        expander.write(f"出所: {result.metadata.academic_source}")
        if result.metadata.vix_source:
            expander.write(f"VIX 出所: {result.metadata.vix_source}")
