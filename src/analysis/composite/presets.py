"""投資スタイル別プリセット（重み付け定数）。

Phase 3.1a は Q (Quality) / I (Income) / R (Risk) / S (Sentiment) の
4 サブスコアのみ実装。V/G/M/C は Phase 3.1b 以降。
Phase 3.1a プリセットは 4 軸合計 100 になるよう再配分。

詳細: docs/long-term-investment-architecture.md §3.2
"""

from __future__ import annotations

from typing import Final

INVESTOR_PRESETS_PHASE_3_1A: Final[dict[str, dict[str, float]]] = {
    "Buffett_型_暫定": {
        "Q": 35.0,
        "I": 30.0,
        "R": 30.0,
        "S": 5.0,
    },
    "配当再投資型": {
        "Q": 25.0,
        "I": 60.0,
        "R": 10.0,
        "S": 5.0,
    },
}

PRESET_DISPLAY_LABELS: Final[dict[str, str]] = {
    "Buffett_型_暫定": "Buffett 型(暫定 — ROIC/WACC は Phase 3.2)",
    "配当再投資型": "配当再投資型（Coca-Cola Buffett モデル）",
}

PRESET_RATIONALE: Final[dict[str, str]] = {
    "Buffett_型_暫定": "質×価値+配当+リスク回避、長期ホールド型",
    "配当再投資型": "Income 60 重視、配当再投資の複利効果狙い",
}


def validate_preset_weights(weights: dict[str, float]) -> None:
    """重みの合計が 100 ± 0.01 範囲かを検証。"""
    total = sum(weights.values())
    if abs(total - 100.0) > 0.01:
        raise ValueError(f"Preset weights must sum to 100, got {total}")


for _name, _w in INVESTOR_PRESETS_PHASE_3_1A.items():
    validate_preset_weights(_w)
