"""Half-Kelly ポジションサイザー（CLAUDE.md §5 / §9.7）。

Kelly Criterion:
    f* = p - (1-p) / b
    p: 勝率 (0-1)
    b: 損益比（payoff ratio = 平均利益 / 平均損失）

Half-Kelly（× 0.5）で破滅リスク回避。
1 銘柄上限 5%（``KELLY_MAX_POSITION_PCT``）でさらに保守的。
Overconfidence バイアス対策として全ポジションに適用。

参考:
    Thorp, E. O. (2006). *The Kelly Criterion in Blackjack, Sports Betting,
    and the Stock Market*.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class KellyParams:
    """Kelly 計算の入力パラメータ。

    Attributes:
        win_rate: 勝率（0-1、例 ``Decimal("0.6")`` = 60%）
        win_loss_ratio: 損益比 = 平均利益 / 平均損失（例 ``Decimal("2.0")`` = 2 倍）
    """

    win_rate: Decimal
    win_loss_ratio: Decimal


def calculate_kelly_fraction(params: KellyParams) -> Decimal:
    """Full Kelly fraction を計算。

    ``f* = p - (1-p) / b``

    - 負の Kelly（賭けるべきでない場合）は ``0`` にクリップ
    - 損益比 0 のとき（無リスク無リターン）も ``0`` を返す（ZeroDivisionError 回避）

    Returns:
        Full Kelly fraction（Decimal、0 以上）。
    """
    p = params.win_rate
    q = Decimal("1") - p
    b = params.win_loss_ratio
    if b == 0:
        return Decimal("0")
    f = p - q / b
    return max(f, Decimal("0"))


def calculate_position_size(
    *,
    params: KellyParams,
    portfolio_value_jpy: Decimal,
    fraction_multiplier: Decimal = Decimal("0.5"),
    max_position_pct: Decimal = Decimal("0.05"),
) -> Decimal:
    """推奨ポジションサイズを JPY で算出。

    手順:
        1. Full Kelly fraction を計算
        2. ``fraction_multiplier``（デフォルト Half = 0.5）を適用
        3. ``max_position_pct``（デフォルト 5%）でキャップ
        4. ``portfolio_value_jpy * 最終 fraction``

    Args:
        params: Kelly パラメータ
        portfolio_value_jpy: ポートフォリオ評価額（JPY）
        fraction_multiplier: Kelly 倍率（Half = ``Decimal("0.5")``、
            Quarter = ``Decimal("0.25")`` 等）
        max_position_pct: 1 銘柄上限（小数、``Decimal("0.05")`` = 5%）

    Returns:
        推奨ポジションサイズ（JPY）。負の Kelly なら ``Decimal("0")``。
    """
    full_kelly = calculate_kelly_fraction(params)
    sized = full_kelly * fraction_multiplier
    capped = min(sized, max_position_pct)
    return portfolio_value_jpy * capped
