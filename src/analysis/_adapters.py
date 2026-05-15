"""Skill 出力 dataclass を signal_aggregator の Protocol 契約に適合させる adapter。

設計判断:
    - Phase 5.3.2 で導入した :class:`MagicFormulaResultProtocol` は per-ticker view を
      要求するが、既存 :class:`MagicFormulaResult` は DataFrame ベース。
    - DataFrame 構造を変更せず adapter 層で吸収することで、既存コード
      (02_screener.py の Provenance 表示等) への破壊的変更を回避。
    - 比率 → パーセント変換は本層で完結 (signal_aggregator は %表記前提)。

CLAUDE.md §9.1 数値規約:
    比率 → パーセントは ``Decimal(str(value)) * Decimal("100")`` 形式で
    生成し、float 経由の丸め誤差を回避する。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .magic_formula import MagicFormulaResult


@dataclass(frozen=True)
class MagicFormulaPerTickerView:
    """ticker 1 件分の Magic Formula 結果 view。

    :class:`analysis.signal_aggregator.MagicFormulaResultProtocol` の
    構造的契約 (score / roc_pct / earnings_yield_pct) を満たす。

    Attributes:
        score: ``magic_formula_score`` (低いほど良い、float 化)。
        roc_pct: ROC (%、例: 比率 0.28 → ``Decimal("28")`` = 28%)。
        earnings_yield_pct: EY (%)。
    """

    score: float
    roc_pct: Decimal
    earnings_yield_pct: Decimal


def magic_formula_result_to_per_ticker_dict(
    result: MagicFormulaResult,
) -> dict[str, MagicFormulaPerTickerView]:
    """:class:`MagicFormulaResult.result` (DataFrame) を ticker → view dict に変換。

    入力 DataFrame の必須カラム:
        ``ticker`` / ``magic_formula_score`` / ``roc`` (比率) /
        ``earnings_yield`` (比率)。
    比率 → パーセントは ``* 100`` で正規化し ``Decimal`` 化する。
    """
    out: dict[str, MagicFormulaPerTickerView] = {}
    for _, row in result.result.iterrows():
        ticker = str(row["ticker"])
        # roc / earnings_yield は Decimal で持たれている前提だが、float の
        # 場合も str 経由で精度を保つ。
        roc_ratio = row["roc"]
        ey_ratio = row["earnings_yield"]
        out[ticker] = MagicFormulaPerTickerView(
            score=float(row["magic_formula_score"]),
            roc_pct=Decimal(str(roc_ratio)) * Decimal("100"),
            earnings_yield_pct=Decimal(str(ey_ratio)) * Decimal("100"),
        )
    return out
