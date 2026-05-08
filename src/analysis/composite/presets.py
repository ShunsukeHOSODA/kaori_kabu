"""投資スタイル別プリセット（重み付け定数）。

Phase 3.1b で 7 軸（Q/V/I/G/R/M/S）対応に拡張。Conviction (C) は Phase 3.2 で
13F + インサイダー統合時に追加予定。

軸記号:
    Q = Quality   (ROE/ROA/Gross Margin)
    V = Value     (Greenblatt EY)
    I = Income    (配当 + Buyback + FCF + 優待)
    G = Growth    (売上/EPS/配当 5y CAGR + PEG)
    R = Risk      (Altman Z + Net Debt/EBITDA + Beneish M)
    M = Momentum  (12m + 1m return)
    S = Sentiment (ニュース・SNS センチメント 0-100 マッピング)

詳細: docs/long-term-investment-architecture.md §3.2, §12.4
"""

from __future__ import annotations

from typing import Final

INVESTOR_PRESETS_PHASE_3_1B: Final[dict[str, dict[str, float]]] = {
    "Buffett_型_暫定": {
        "Q": 25.0,
        "V": 20.0,
        "I": 20.0,
        "G": 5.0,
        "R": 20.0,
        "M": 5.0,
        "S": 5.0,
    },
    "配当再投資型": {
        "Q": 20.0,
        "V": 10.0,
        "I": 50.0,
        "G": 5.0,
        "R": 10.0,
        "M": 0.0,
        "S": 5.0,
    },
    "Lynch_型": {
        "Q": 20.0,
        "V": 15.0,
        "I": 5.0,
        "G": 35.0,
        "R": 5.0,
        "M": 15.0,
        "S": 5.0,
    },
    "逆張り型": {
        "Q": 15.0,
        "V": 35.0,
        "I": 10.0,
        "G": 5.0,
        "R": 25.0,
        "M": 5.0,
        "S": 5.0,
    },
}

INVESTOR_PRESETS_PHASE_3_1A: Final[dict[str, dict[str, float]]] = (
    INVESTOR_PRESETS_PHASE_3_1B
)
"""下位互換エイリアス。既存 import を破壊しないため Phase 3.1A 名を維持。"""

PRESET_DISPLAY_LABELS: Final[dict[str, str]] = {
    "Buffett_型_暫定": "Buffett 型(暫定 — ROIC/WACC は Phase 3.2)",
    "配当再投資型": "配当再投資型（Coca-Cola Buffett モデル）",
    "Lynch_型": "Lynch 型（PEG ≦ 1.0 のテンバガー候補）",
    "逆張り型": "逆張り型（Burry / Pabrai 流の深割安）",
}

PRESET_RATIONALE: Final[dict[str, str]] = {
    "Buffett_型_暫定": "質×価値+配当+リスク回避、長期ホールド型",
    "配当再投資型": "Income 50 重視、配当再投資の複利効果狙い",
    "Lynch_型": "Growth 35 + PEG ≦1 の割安成長株、テンバガー候補",
    "逆張り型": "Value 35 + Risk 回避 25、深割安+倒産リスク排除",
}


def validate_preset_weights(weights: dict[str, float]) -> None:
    """重みの合計が 100 ± 0.01 範囲かを検証。"""
    total = sum(weights.values())
    if abs(total - 100.0) > 0.01:
        raise ValueError(f"Preset weights must sum to 100, got {total}")


for _name, _w in INVESTOR_PRESETS_PHASE_3_1B.items():
    validate_preset_weights(_w)
