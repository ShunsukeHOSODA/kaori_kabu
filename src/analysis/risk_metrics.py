"""保有ポートフォリオのリスク指標計算（Phase 3.2 / CLAUDE.md §5 / §9.8）。

Sharpe / Sortino / Calmar / Max DD / VaR / CVaR を ``empyrical-reloaded`` で
計算し、完全な provenance metadata を付与する。

学術根拠:
    Sharpe, W. F. (1966). "Mutual Fund Performance." J. of Business 39(1).
    Sortino, F. & Price, L. (1994). "Performance Measurement in a Downside
        Risk Framework." J. of Investing 3(3).
    Young, T. W. (1991). "Calmar Ratio." Futures Magazine.
    Rockafellar, R. T. & Uryasev, S. (2000). "Optimization of Conditional
        Value-at-Risk." J. of Risk 2(3).

Note:
    empyrical は returns を ``daily simple returns``（``pct_change``）として
    扱い、年率化は内部で 252 営業日係数（既定）を使用する。
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Final

import empyrical as ep
import pandas as pd

VAR_CONFIDENCE_DEFAULT: Final[float] = 0.05
"""VaR / CVaR の既定信頼区間（5% percentile）。"""

WEIGHT_TOLERANCE: Final[float] = 1e-6
"""ウェイト合計が 1.0 から逸脱して許容する誤差（Decimal → float 変換用）。"""


@dataclass(frozen=True)
class RiskMetricsMetadata:
    """リスク指標計算の出所情報（CLAUDE.md §9.8.2 必須メタデータ）。"""

    calculation_method: str
    academic_source: str
    calculated_at: datetime
    input_data_period: str
    input_data_source: str | None
    code_commit: str | None
    var_confidence: float
    risk_free_rate: float


@dataclass(frozen=True)
class BenchmarkMetadata:
    """ベンチマーク比較の出所情報（CLAUDE.md §9.8.2 必須メタデータ）。"""

    calculation_method: str
    academic_source: str
    calculated_at: datetime
    input_data_period: str
    input_data_source: str | None
    code_commit: str | None
    benchmark_label: str


@dataclass(frozen=True)
class BenchmarkComparison:
    """ポートフォリオ vs ベンチマークの比較指標（immutable）。

    すべての値は ``daily simple returns`` 入力から派生。年率指標は
    ``empyrical`` の 252 営業日換算による。

    Attributes:
        alpha: Jensen's alpha（年率超過リターン、>0 で勝ち）
        beta: 市場感応度（=1 がベンチ追随、<1 が低ボラ、>1 が高ボラ）
        information_ratio: (年率超過リターン) / (年率 Tracking Error)
        tracking_error: 差分リターンの年率標準偏差
        up_capture: 上昇局面捕捉率（1.0 でベンチ並み、>1.0 で上回り）
        down_capture: 下落局面捕捉率（1.0 でベンチ並み、<1.0 で耐性あり）
        metadata: provenance metadata
    """

    alpha: float
    beta: float
    information_ratio: float
    tracking_error: float
    up_capture: float
    down_capture: float
    metadata: BenchmarkMetadata


@dataclass(frozen=True)
class RiskMetrics:
    """保有ポートフォリオのリスク指標一式（immutable）。

    すべての値は ``daily simple returns`` 入力からの派生で、
    年率指標は ``empyrical`` の 252 営業日換算による。

    Attributes:
        sharpe: シャープレシオ（年率超過リターン / 年率ボラ）
        sortino: ソルティノレシオ（下方リスクのみで Sharpe 化）
        calmar: カルマーレシオ（年率リターン / |Max DD|）
        max_drawdown: 最大ドローダウン（``≤ 0``、empyrical 仕様）
        var_95: 5% Value at Risk（daily、``≤ 0``）
        cvar_95: 5% Conditional VaR（daily、``≤ 0``、VaR 越えテール平均）
        annualized_return: 年率リターン
        annualized_volatility: 年率ボラ
        metadata: provenance metadata
    """

    sharpe: float
    sortino: float
    calmar: float
    max_drawdown: float
    var_95: float
    cvar_95: float
    annualized_return: float
    annualized_volatility: float
    metadata: RiskMetricsMetadata


def compute_portfolio_returns(
    prices_by_ticker: Mapping[str, pd.Series],
    weights_by_ticker: Mapping[str, Decimal],
) -> pd.Series:
    """ウェイト付きポートフォリオの daily simple returns を計算。

    各銘柄の ``prices`` を ``pct_change`` し、共通日付に inner join したうえで
    ``weight × return`` の合算を返す。

    Args:
        prices_by_ticker: ティッカー → 終値 ``pd.Series``（DatetimeIndex）の dict
        weights_by_ticker: ティッカー → ウェイト（``Decimal``）。合計 1.0 必須。

    Returns:
        ポートフォリオ daily returns ``pd.Series``（dropna 後、name="portfolio_return"）

    Raises:
        ValueError: 入力が空、ティッカー集合不一致、ウェイト合計 ≠ 1.0
    """
    if not prices_by_ticker:
        raise ValueError("prices_by_ticker is empty")
    if set(prices_by_ticker.keys()) != set(weights_by_ticker.keys()):
        raise ValueError(
            f"ticker sets must match: prices={sorted(prices_by_ticker.keys())} "
            f"weights={sorted(weights_by_ticker.keys())}"
        )

    total_weight = float(sum(weights_by_ticker.values()))
    if abs(total_weight - 1.0) > WEIGHT_TOLERANCE:
        raise ValueError(f"weights must sum to 1.0, got {total_weight}")

    returns_df = pd.DataFrame(
        {ticker: prices.pct_change() for ticker, prices in prices_by_ticker.items()}
    ).dropna(how="any")

    portfolio_returns = pd.Series(0.0, index=returns_df.index)
    for ticker, weight in weights_by_ticker.items():
        portfolio_returns = portfolio_returns + returns_df[ticker] * float(weight)
    portfolio_returns.name = "portfolio_return"
    return portfolio_returns


def compute_risk_metrics(
    returns: pd.Series,
    *,
    risk_free_rate: float = 0.0,
    var_confidence: float = VAR_CONFIDENCE_DEFAULT,
    input_data_source: str | None = None,
) -> RiskMetrics:
    """daily returns ``pd.Series`` → リスク指標 + provenance。

    Args:
        returns: ``daily simple returns`` Series（DatetimeIndex 推奨）
        risk_free_rate: 年率無リスク金利（empyrical 仕様、既定 0.0）
        var_confidence: VaR/CVaR の信頼区間（既定 0.05 = 5%）
        input_data_source: メタデータのデータ源ラベル（例 "EODHD"）

    Raises:
        ValueError: ``len(returns) < 2``（empyrical の最小要件）
    """
    if len(returns) < 2:
        raise ValueError(
            f"returns must have ≥ 2 observations for risk metrics, got {len(returns)}"
        )

    sharpe = float(ep.sharpe_ratio(returns, risk_free=risk_free_rate))
    sortino = float(ep.sortino_ratio(returns))
    calmar = float(ep.calmar_ratio(returns))
    max_dd = float(ep.max_drawdown(returns))
    var = float(ep.value_at_risk(returns, cutoff=var_confidence))
    cvar = float(ep.conditional_value_at_risk(returns, cutoff=var_confidence))
    ann_return = float(ep.annual_return(returns))
    ann_vol = float(ep.annual_volatility(returns))

    period_str = _format_period(returns.index.min(), returns.index.max())

    metadata = RiskMetricsMetadata(
        calculation_method="risk_metrics_v1",
        academic_source=(
            'Sharpe 1966 "Mutual Fund Performance"; '
            'Sortino & Price 1994 "Downside Risk Framework"; '
            'Young 1991 "Calmar Ratio"; '
            'Rockafellar & Uryasev 2000 "VaR/CVaR Optimization"'
        ),
        calculated_at=datetime.now(timezone.utc),
        input_data_period=period_str,
        input_data_source=input_data_source,
        code_commit=_get_current_git_commit(),
        var_confidence=var_confidence,
        risk_free_rate=risk_free_rate,
    )

    return RiskMetrics(
        sharpe=sharpe,
        sortino=sortino,
        calmar=calmar,
        max_drawdown=max_dd,
        var_95=var,
        cvar_95=cvar,
        annualized_return=ann_return,
        annualized_volatility=ann_vol,
        metadata=metadata,
    )


def compute_benchmark_comparison(
    returns: pd.Series,
    benchmark_returns: pd.Series,
    *,
    benchmark_label: str,
    input_data_source: str | None = None,
) -> BenchmarkComparison:
    """ポートフォリオ vs ベンチマークの相対指標 + provenance を返す。

    両系列を共通日付で inner join した後、empyrical-reloaded で α/β/IR/TE/
    Up-Down Capture を計算する。「Sharpe 0.8 は高いの？低いの？」の判断を
    可能にし、Recency Bias / Confirmation Bias 抑止（CLAUDE.md §9.7）。

    Args:
        returns: ポートフォリオの daily simple returns
        benchmark_returns: ベンチマークの daily simple returns（SPY/TOPIX 等）
        benchmark_label: ベンチマーク表示名（例 ``"S&P500"``、UI 表示用）
        input_data_source: メタデータのデータ源ラベル（例 ``"EODHD"``）

    Raises:
        ValueError: 共通日付が無い、または観測数 < 2

    学術根拠:
        Jensen, M. C. (1968). "The Performance of Mutual Funds."
            J. of Finance 23(2). — Jensen's alpha
        Sharpe, W. F. (1992). "Asset Allocation: Management Style and
            Performance Measurement." J. of Portfolio Management. — IR
        Goodwin, T. H. (1998). "The Information Ratio."
            Financial Analysts Journal. — IR 改訂版
    """
    common_idx = returns.index.intersection(benchmark_returns.index)
    if len(common_idx) < 2:
        raise ValueError(
            "共通日付が 2 件未満で比較不能 "
            f"(returns={len(returns)}, benchmark={len(benchmark_returns)}, "
            f"common={len(common_idx)})"
        )
    aligned_port = returns.loc[common_idx]
    aligned_bench = benchmark_returns.loc[common_idx]

    alpha = float(ep.alpha(aligned_port, aligned_bench))
    beta = float(ep.beta(aligned_port, aligned_bench))
    info_ratio = float(ep.excess_sharpe(aligned_port, aligned_bench))
    # empyrical-reloaded には tracking_error 関数が存在しないため自前計算。
    # TE = std(R_p - R_b) × √252（daily → 年率）。Goodwin 1998 の標準式。
    tracking_err = float(
        (aligned_port - aligned_bench).std(ddof=1) * (252 ** 0.5)
    )
    up_cap = float(ep.up_capture(aligned_port, aligned_bench))
    down_cap = float(ep.down_capture(aligned_port, aligned_bench))

    period_str = _format_period(common_idx.min(), common_idx.max())

    metadata = BenchmarkMetadata(
        calculation_method="benchmark_comparison_v1",
        academic_source=(
            'Jensen 1968 "Performance of Mutual Funds" (alpha); '
            'Sharpe 1992 "Asset Allocation Style/Performance" (IR); '
            'Goodwin 1998 "The Information Ratio"'
        ),
        calculated_at=datetime.now(timezone.utc),
        input_data_period=period_str,
        input_data_source=input_data_source,
        code_commit=_get_current_git_commit(),
        benchmark_label=benchmark_label,
    )

    return BenchmarkComparison(
        alpha=alpha,
        beta=beta,
        information_ratio=info_ratio,
        tracking_error=tracking_err,
        up_capture=up_cap,
        down_capture=down_cap,
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# 内部ヘルパ
# ---------------------------------------------------------------------------


def _format_period(start: object, end: object) -> str:
    """期間文字列 ``YYYY-MM-DD to YYYY-MM-DD`` を生成。

    DatetimeIndex の min/max は ``Timestamp`` だが、念のため ``date()`` の存在を
    duck-typing で判定し、文字列フォールバックも用意する。
    """
    if hasattr(start, "date") and hasattr(end, "date"):
        return f"{start.date()} to {end.date()}"  # type: ignore[attr-defined]
    return f"{start} to {end}"


def _get_current_git_commit() -> str | None:
    """現在の git commit short hash。失敗時は ``None``。

    Note:
        ``regime.py`` の同名 helper と仕様一致。Phase 3.2 後の共通化候補
        （``src/analysis/_provenance.py`` への抽出）。
    """
    try:
        completed = subprocess.run(  # noqa: S603, S607 — 固定引数のみ、シェル経由なし
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None
