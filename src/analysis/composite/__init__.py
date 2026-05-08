"""Composite Investment Score（Phase 3）公開 API。

世界一の投資家視座（Buffett-Munger / Lynch / Druckenmiller / Dalio /
Pabrai / Burry / Ackman / AQR / Coca-Cola Buffett モデル）を 8 サブスコア
で網羅し、投資スタイル別プリセットで重み付け合算する。

設計詳細は :doc:`docs/long-term-investment-architecture.md` 参照。
"""

from __future__ import annotations

from .subscores.income import (
    IncomeSubScoreInputs,
    IncomeSubScoreResult,
    compute_income_subscore,
)

__all__ = [
    "IncomeSubScoreInputs",
    "IncomeSubScoreResult",
    "compute_income_subscore",
]
