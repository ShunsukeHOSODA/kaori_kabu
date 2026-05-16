"""compute_mu_for_monte_carlo helper のテスト (Phase 6.3 §4.1 派生、reviewer HIGH-2)。

Phase 6.2 で display 層 → compute 層に移管されていた薄い変換 helper を、
Phase 6.3 で更に analysis 層 (``src/analysis/ranking_judge.py``) へ移管した
(handoff §2.4)。``RankingSignalBundle`` の owner と同居させることで
dashboard 層 → analysis 層への依存方向を正しくし、analysis 層内で完結する
純粋変換 helper にした (旧テストファイル ``test_screener_compute_mu.py`` から
本ファイルへ rename)。

Phase 6.3 reviewer 2 視点一致 fix:
    bundle 全体ではなく ``momentum_12m: Decimal | None`` のスカラーを受ける
    シグネチャに変更し、``apply_regime_confidence`` / ``compute_kelly_multiplier``
    と Stage 3 純粋関数群の引数粒度一貫性を保つ。
    旧 ``_BundleStub`` dataclass + ``type: ignore[arg-type]`` は不要になり削除。

``momentum_12m`` (年率パーセント Decimal) を ``monte_carlo.simulate_gbm_paths``
の ``mu: float`` 引数 (相対値) に変換する。
CLAUDE.md §9.1 (Decimal 演算で完結してから最後だけ float 化) を確認。
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.analysis.ranking_judge import compute_mu_for_monte_carlo


@pytest.mark.unit
class TestComputeMuForMonteCarlo:
    """compute_mu_for_monte_carlo の Decimal → float 変換テスト。"""

    def test_正常値_年率125パーセント(self) -> None:
        """momentum_12m=12.5 (12.5%) → 0.125 (GBM ドリフト相対値)。"""
        assert compute_mu_for_monte_carlo(Decimal("12.5")) == pytest.approx(0.125)

    def test_None_は_デフォルト_0_0(self) -> None:
        """momentum_12m=None → 0.0 (ドリフト 0、純 Brownian motion)。"""
        assert compute_mu_for_monte_carlo(None) == 0.0

    def test_負値_は_そのまま_符号維持(self) -> None:
        """momentum_12m=-10.0 (-10%) → -0.1 (下落 drift)。"""
        assert compute_mu_for_monte_carlo(Decimal("-10.0")) == pytest.approx(-0.1)

    def test_ゼロ_は_0_0(self) -> None:
        """momentum_12m=0.0 → 0.0 (None と同じ振る舞い、None ガード経由ではない)。"""
        assert compute_mu_for_monte_carlo(Decimal("0")) == 0.0

    def test_返り値型_は_float(self) -> None:
        """返り値型は float (simulate_gbm_paths の ``mu: float`` 引数のため)。"""
        result = compute_mu_for_monte_carlo(Decimal("5.0"))
        assert isinstance(result, float)
