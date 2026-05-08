"""Momentum サブスコア — Jegadeesh-Titman / AQR MOM factor。

学術根拠:
    Jegadeesh, N., & Titman, S. (1993). "Returns to Buying Winners and Selling Losers."
        12 ヶ月モメンタムの上位 decile が長期 outperformance を生む。
    Asness, Frazzini, Pedersen — AQR Momentum factor (MOM) の標準実装。
    Druckenmiller — トレンドフォロー型の代表（マクロ × momentum）。

スコアリング設計（Phase 3.1b）:
    +60 12m return (25%+ で満点、JT 1993 上位 decile threshold)
    +40 1m return  (5%+  で満点、短期トレンド確認)

最終 score = clip(合算, 0, 100)。負リターンは 0 点（Falling Knife 警告は
``warnings.py`` 側が独立判定するため、ここでは二重ペナルティを課さない）。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Final

# ---------------------------------------------------------------------------
# 設定定数
# ---------------------------------------------------------------------------

RETURN_12M_SATURATION: Final[Decimal] = Decimal("0.25")
"""12 ヶ月リターン飽和点（25% で 60 点満点）— JT 1993 上位 decile。"""

RETURN_1M_SATURATION: Final[Decimal] = Decimal("0.05")
"""1 ヶ月リターン飽和点（5% で 40 点満点）。"""

RETURN_12M_MAX_PTS: Final[float] = 60.0
RETURN_1M_MAX_PTS: Final[float] = 40.0


# ---------------------------------------------------------------------------
# データクラス
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MomentumSubScoreInputs:
    """Momentum サブスコア計算の入力値。

    リターンは小数（0.20 = +20%）で受ける。価格時系列からの計算は呼び出し側で
    行う（``src/data/eodhd.py`` の price 履歴を ``(P_t / P_{t-N}) - 1`` で）。
    """

    return_12m: Decimal | None
    return_1m: Decimal | None


@dataclass(frozen=True)
class MomentumSubScoreResult:
    """Momentum サブスコアの結果。"""

    return_12m: Decimal | None
    return_1m: Decimal | None
    score: float
    components: dict[str, float]


# ---------------------------------------------------------------------------
# 個別計算ヘルパー
# ---------------------------------------------------------------------------


def _return_points(
    ret: Decimal | None,
    saturation: Decimal,
    max_pts: float,
) -> float:
    """リターンを 0..max_pts に線形マッピング。負・None は 0 点。"""
    if ret is None or ret <= 0:
        return 0.0
    ratio = float(ret) / float(saturation)
    return max(0.0, min(max_pts, ratio * max_pts))


# ---------------------------------------------------------------------------
# 主関数
# ---------------------------------------------------------------------------


def compute_momentum_subscore(
    inputs: MomentumSubScoreInputs,
) -> MomentumSubScoreResult:
    """Momentum サブスコア（0-100）を算出。

    Args:
        inputs: :class:`MomentumSubScoreInputs`

    Returns:
        :class:`MomentumSubScoreResult`（リターン pass-through + 2 軸合算）
    """
    pts_12m = _return_points(
        inputs.return_12m, RETURN_12M_SATURATION, RETURN_12M_MAX_PTS
    )
    pts_1m = _return_points(
        inputs.return_1m, RETURN_1M_SATURATION, RETURN_1M_MAX_PTS
    )
    score = max(0.0, min(100.0, pts_12m + pts_1m))

    return MomentumSubScoreResult(
        return_12m=inputs.return_12m,
        return_1m=inputs.return_1m,
        score=score,
        components={
            "return_12m_pts": pts_12m,
            "return_1m_pts": pts_1m,
        },
    )
