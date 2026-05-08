"""Growth サブスコア — Lynch 流テンバガー条件 + DGR 配当成長。

学術根拠:
    Lynch, P. (1989). *One Up On Wall Street*.
        PEG = PER / 期待成長率（%）。 PEG ≦ 1.0 が「割安成長株」の目安。
        テンバガー（10 倍株）の条件として 売上 CAGR 15-25% 帯を提示。
    Buffett-Munger — 高 ROE × 内部成長の複利効果。
    DGR (Dividend Growth Rate) — 配当持続力の代理指標、配当王銘柄選定の核。

スコアリング設計（Phase 3.1b）:
    +30 売上 5y CAGR (15%+ で満点、線形)
    +30 EPS 5y CAGR (15%+ で満点)
    +20 配当 5y CAGR (8%+ で満点) — 無配企業は 0 点（ペナルティではない）
    +20 PEG (≤1.0 で満点、≥2.0 で 0、線形補間)

最終 score = clip(合算, 0, 100)。負成長・赤字は 0 点だがペナルティは課さない
（Risk サブスコアが別途 Altman Z で破綻リスクを警告する役割を持つため）。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Final

# ---------------------------------------------------------------------------
# 設定定数
# ---------------------------------------------------------------------------

REVENUE_CAGR_SATURATION: Final[Decimal] = Decimal("0.15")
"""売上 5y CAGR 飽和点（15% で 30 点満点）— Lynch テンバガー基準下限。"""

EPS_CAGR_SATURATION: Final[Decimal] = Decimal("0.15")
"""EPS 5y CAGR 飽和点（15% で 30 点満点）。"""

DIVIDEND_CAGR_SATURATION: Final[Decimal] = Decimal("0.08")
"""配当 5y CAGR 飽和点（8% で 20 点満点）— DGR 配当王水準。"""

PEG_FAIR_VALUE: Final[Decimal] = Decimal("1.0")
"""PEG fair value 基準（Lynch 1989）。これ以下で満点。"""

PEG_OVERVALUED: Final[Decimal] = Decimal("2.0")
"""PEG 割高基準。これ以上で 0 点。"""

REVENUE_MAX_PTS: Final[float] = 30.0
EPS_MAX_PTS: Final[float] = 30.0
DIVIDEND_MAX_PTS: Final[float] = 20.0
PEG_MAX_PTS: Final[float] = 20.0


# ---------------------------------------------------------------------------
# データクラス
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GrowthSubScoreInputs:
    """Growth サブスコア計算の入力値。

    各 CAGR は小数表現（0.15 = 15%）。``earnings_growth_rate`` は PEG 計算用の
    期待利益成長率（forward 推奨、historic でも可）。
    """

    revenue_5y_cagr: Decimal | None
    eps_5y_cagr: Decimal | None
    dividend_5y_cagr: Decimal | None
    pe_ratio: Decimal | None
    earnings_growth_rate: Decimal | None


@dataclass(frozen=True)
class GrowthSubScoreResult:
    """Growth サブスコアの結果。"""

    revenue_5y_cagr: Decimal | None
    eps_5y_cagr: Decimal | None
    dividend_5y_cagr: Decimal | None
    peg: Decimal | None
    score: float
    components: dict[str, float]


# ---------------------------------------------------------------------------
# 個別計算ヘルパー
# ---------------------------------------------------------------------------


def calculate_peg(
    pe_ratio: Decimal | None,
    earnings_growth_rate: Decimal | None,
) -> Decimal | None:
    """``PEG = PER / (成長率 * 100)``。

    Lynch 1989 が PER 単独の落とし穴（成長企業を割高判定する罠）を回避するため
    導入した指標。成長率は forward growth または historic growth。

    無効ケース（``None`` を返す）:
        - 入力 ``None``
        - PER ≤ 0（赤字会社）
        - 成長率 ≤ 0（マイナス成長は PEG 解釈が破綻）
    """
    if pe_ratio is None or earnings_growth_rate is None:
        return None
    if pe_ratio <= 0 or earnings_growth_rate <= 0:
        return None
    # earnings_growth_rate は小数（0.20 = 20%）なので * 100 で % 化
    return pe_ratio / (earnings_growth_rate * Decimal("100"))


def _cagr_points(
    cagr: Decimal | None,
    saturation: Decimal,
    max_pts: float,
) -> float:
    """CAGR を 0..max_pts に線形マッピング。負成長・None は 0 点。"""
    if cagr is None or cagr <= 0:
        return 0.0
    ratio = float(cagr) / float(saturation)
    return max(0.0, min(max_pts, ratio * max_pts))


def _peg_points(peg: Decimal | None) -> float:
    """PEG を 0..PEG_MAX_PTS に線形マッピング。

    PEG ≤ 1.0 → 満点、PEG ≥ 2.0 → 0、間は線形補間。
    None（未計算）は 0 点。
    """
    if peg is None:
        return 0.0
    if peg <= PEG_FAIR_VALUE:
        return PEG_MAX_PTS
    if peg >= PEG_OVERVALUED:
        return 0.0
    # 1.0 < peg < 2.0 の線形補間
    span = float(PEG_OVERVALUED - PEG_FAIR_VALUE)
    excess = float(peg - PEG_FAIR_VALUE)
    return max(0.0, PEG_MAX_PTS * (1.0 - excess / span))


# ---------------------------------------------------------------------------
# 主関数
# ---------------------------------------------------------------------------


def compute_growth_subscore(
    inputs: GrowthSubScoreInputs,
) -> GrowthSubScoreResult:
    """Growth サブスコア（0-100）を算出。

    Args:
        inputs: :class:`GrowthSubScoreInputs`

    Returns:
        :class:`GrowthSubScoreResult`（PEG + 4 軸 components + 合算 score）
    """
    revenue_pts = _cagr_points(
        inputs.revenue_5y_cagr, REVENUE_CAGR_SATURATION, REVENUE_MAX_PTS
    )
    eps_pts = _cagr_points(inputs.eps_5y_cagr, EPS_CAGR_SATURATION, EPS_MAX_PTS)
    dividend_pts = _cagr_points(
        inputs.dividend_5y_cagr, DIVIDEND_CAGR_SATURATION, DIVIDEND_MAX_PTS
    )
    peg = calculate_peg(
        pe_ratio=inputs.pe_ratio,
        earnings_growth_rate=inputs.earnings_growth_rate,
    )
    peg_pts = _peg_points(peg)

    score = max(0.0, min(100.0, revenue_pts + eps_pts + dividend_pts + peg_pts))

    return GrowthSubScoreResult(
        revenue_5y_cagr=inputs.revenue_5y_cagr,
        eps_5y_cagr=inputs.eps_5y_cagr,
        dividend_5y_cagr=inputs.dividend_5y_cagr,
        peg=peg,
        score=score,
        components={
            "revenue_cagr_pts": revenue_pts,
            "eps_cagr_pts": eps_pts,
            "dividend_cagr_pts": dividend_pts,
            "peg_pts": peg_pts,
        },
    )
