"""Half-Kelly ポジションサイザーの単体テスト（CLAUDE.md §5 / §9.7）。

Kelly Criterion: f* = p - (1-p) / b
    p: 勝率（win rate, 0-1）
    b: 損益比（payoff ratio, win_loss_ratio）

Half-Kelly（fraction × 0.5）で破滅リスクを回避。
1 銘柄上限 5% (KELLY_MAX_POSITION_PCT) でさらに保守的に。
Overconfidence バイアス対策として全ポジションに適用。

参考: Edward O. Thorp, "The Kelly Criterion in Blackjack, Sports Betting,
       and the Stock Market" (2006).
"""

from __future__ import annotations

from decimal import Decimal

import pytest


@pytest.mark.unit
class TestCalculateKellyFraction:
    """Full Kelly fraction の計算。"""

    def test_勝率60_損益比2_FullKelly_04(self) -> None:
        """f* = 0.6 - 0.4/2.0 = 0.6 - 0.2 = 0.4"""
        from strategies.kelly import KellyParams, calculate_kelly_fraction

        params = KellyParams(
            win_rate=Decimal("0.6"),
            win_loss_ratio=Decimal("2.0"),
        )

        f = calculate_kelly_fraction(params)

        assert f == Decimal("0.4")

    def test_負のKellyは0にクリップ(self) -> None:
        """f* = 0.3 - 0.7/1.0 = -0.4 → 0（負の Kelly は「賭けない」）"""
        from strategies.kelly import KellyParams, calculate_kelly_fraction

        params = KellyParams(
            win_rate=Decimal("0.3"),
            win_loss_ratio=Decimal("1.0"),
        )

        f = calculate_kelly_fraction(params)

        assert f == Decimal("0")

    def test_損益比0_Kelly_0(self) -> None:
        """損益比 0（無リスク・無リターン）→ 0 を返す（ZeroDivision ガード）。"""
        from strategies.kelly import KellyParams, calculate_kelly_fraction

        params = KellyParams(
            win_rate=Decimal("0.5"),
            win_loss_ratio=Decimal("0"),
        )

        f = calculate_kelly_fraction(params)

        assert f == Decimal("0")


@pytest.mark.unit
class TestCalculatePositionSize:
    """Half-Kelly ポジションサイズ（JPY）の計算。"""

    def test_FullKelly大_上限キャップ動作(self) -> None:
        """Full Kelly 0.4 → Half 0.2 > cap 0.05 → cap 適用、1M * 0.05 = 50,000"""
        from strategies.kelly import KellyParams, calculate_position_size

        size = calculate_position_size(
            params=KellyParams(
                win_rate=Decimal("0.6"),
                win_loss_ratio=Decimal("2.0"),
            ),
            portfolio_value_jpy=Decimal("1000000"),
        )

        assert size == Decimal("50000")

    def test_負Kellyならポジションサイズ0(self) -> None:
        from strategies.kelly import KellyParams, calculate_position_size

        size = calculate_position_size(
            params=KellyParams(
                win_rate=Decimal("0.3"),
                win_loss_ratio=Decimal("1.0"),
            ),
            portfolio_value_jpy=Decimal("1000000"),
        )

        assert size == Decimal("0")

    def test_上限以下はHalfKellyそのまま(self) -> None:
        """Full Kelly 0.08 → Half 0.04 < cap 0.05 → そのまま 0.04 適用。

        勝率 0.54、損益比 1 → f* = 0.54 - 0.46 = 0.08
        Half = 0.04 < cap 0.05、portfolio=1M → 40,000 円
        """
        from strategies.kelly import KellyParams, calculate_position_size

        size = calculate_position_size(
            params=KellyParams(
                win_rate=Decimal("0.54"),
                win_loss_ratio=Decimal("1.0"),
            ),
            portfolio_value_jpy=Decimal("1000000"),
        )

        assert size == Decimal("40000")

    def test_カスタム倍率と上限の上書き(self) -> None:
        """fraction_multiplier と max_position_pct を引数で上書き可能。

        Full Kelly 0.4、Quarter-Kelly (× 0.25) → 0.1
        cap 0.08 → 0.08 適用、portfolio=1M → 80,000 円
        """
        from strategies.kelly import KellyParams, calculate_position_size

        size = calculate_position_size(
            params=KellyParams(
                win_rate=Decimal("0.6"),
                win_loss_ratio=Decimal("2.0"),
            ),
            portfolio_value_jpy=Decimal("1000000"),
            fraction_multiplier=Decimal("0.25"),
            max_position_pct=Decimal("0.08"),
        )

        assert size == Decimal("80000")
