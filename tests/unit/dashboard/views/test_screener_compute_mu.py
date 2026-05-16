"""compute_mu_for_monte_carlo helper のテスト (Phase 6.2 #10、handoff §4.16)。

display 層から compute 層へ移管した薄い変換 helper。
``RankingSignalBundle.momentum_12m`` (年率パーセント Decimal) を
``simulate_gbm_paths`` の ``mu: float`` 引数 (相対値) に変換する。

CLAUDE.md §9.1 (Decimal 演算で完結してから最後だけ float 化) を確認。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pytest

from src.dashboard.views._screener_compute import compute_mu_for_monte_carlo


@dataclass(frozen=True)
class _BundleStub:
    """``compute_mu_for_monte_carlo`` が参照する最小フィールドだけを持つ型付き stub。

    2 reviewer 並列指摘 (code-r MEDIUM-2 / python-r LOW-2): ``type: ignore``
    が必要な動的属性代入を避け、mypy/pyright が将来の RankingSignalBundle
    フィールド変更を検出できるよう dataclass で明示する。
    """

    momentum_12m: Decimal | None


def _make_bundle_with_momentum(momentum: Decimal | None) -> _BundleStub:
    """``momentum_12m`` だけを持つ最小 stub bundle を返す。

    ``compute_mu_for_monte_carlo`` は ``bundle.momentum_12m`` のみ参照するため、
    RankingSignalBundle 全フィールドを構築する必要はない。
    """
    return _BundleStub(momentum_12m=momentum)


@pytest.mark.unit
class TestComputeMuForMonteCarlo:
    """compute_mu_for_monte_carlo の Decimal → float 変換テスト。"""

    def test_正常値_年率125パーセント(self) -> None:
        """momentum_12m=12.5 (12.5%) → 0.125 (GBM ドリフト相対値)。"""
        bundle = _make_bundle_with_momentum(Decimal("12.5"))
        assert compute_mu_for_monte_carlo(bundle) == pytest.approx(0.125)

    def test_None_は_デフォルト_0_0(self) -> None:
        """momentum_12m=None → 0.0 (ドリフト 0、純 Brownian motion)。"""
        bundle = _make_bundle_with_momentum(None)
        assert compute_mu_for_monte_carlo(bundle) == 0.0

    def test_負値_は_そのまま_符号維持(self) -> None:
        """momentum_12m=-10.0 (-10%) → -0.1 (下落 drift)。"""
        bundle = _make_bundle_with_momentum(Decimal("-10.0"))
        assert compute_mu_for_monte_carlo(bundle) == pytest.approx(-0.1)

    def test_ゼロ_は_0_0(self) -> None:
        """momentum_12m=0.0 → 0.0 (None と同じ振る舞い、None ガード経由ではない)。"""
        bundle = _make_bundle_with_momentum(Decimal("0"))
        assert compute_mu_for_monte_carlo(bundle) == 0.0

    def test_返り値型_は_float(self) -> None:
        """返り値型は float (simulate_gbm_paths の ``mu: float`` 引数のため)。"""
        bundle = _make_bundle_with_momentum(Decimal("5.0"))
        result = compute_mu_for_monte_carlo(bundle)
        assert isinstance(result, float)
