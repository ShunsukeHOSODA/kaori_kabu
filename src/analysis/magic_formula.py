"""Magic Formula スクリーナー（Greenblatt 2010）。

学術根拠:
    Greenblatt, J. (2010). *The Little Book That Still Beats the Market*. Ch.5

計算式:
    ROC (Return on Capital) = EBIT / (Net Working Capital + Net Fixed Assets)
    Earnings Yield (EY)     = EBIT / Enterprise Value
    最終スコア              = rank(ROC) + rank(EY)（合算ランキング、低いほど高評価）
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

import pandas as pd

# ---------------------------------------------------------------------------
# Provenance metadata（CLAUDE.md §9.8.2 必須）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MagicFormulaMetadata:
    """Magic Formula 計算結果の出所情報。

    後で「なぜこの銘柄を買ったか」を完全再現するため、
    計算方法・学術根拠・実行時刻・データ出所・コードバージョンを記録する。

    Attributes:
        calculation_method: アルゴリズム ID（例: ``magic_formula_v1``）
        academic_source: 学術的根拠（論文・章節）
        calculated_at: 計算実行時刻（tz-aware UTC 推奨）
        input_data_period: 計算入力データの期間（例: ``2020-01-01 to 2025-12-31``）
        input_data_source: データ取得元（例: ``EODHD``）
        input_cache_hit: 入力データがキャッシュヒットだったか
        code_commit: 計算時の git commit short hash（再現性確認用）
    """

    calculation_method: str
    academic_source: str
    calculated_at: datetime
    input_data_period: str | None = None
    input_data_source: str | None = None
    input_cache_hit: bool | None = None
    code_commit: str | None = None


@dataclass(frozen=True)
class MagicFormulaResult:
    """Magic Formula スクリーニング結果と出所情報のラッパー。"""

    result: pd.DataFrame
    metadata: MagicFormulaMetadata


# ---------------------------------------------------------------------------
# 計算ロジック
# ---------------------------------------------------------------------------


def calculate_roc(
    ebit: Decimal,
    net_working_capital: Decimal,
    net_fixed_assets: Decimal,
) -> Decimal:
    """ROC = EBIT / (Net Working Capital + Net Fixed Assets)。

    Greenblatt 2010 Ch.5 の定義。分母は「事業に投下されている運転資本」を表し、
    ROE / ROA より厳密に「稼ぐために必要な資本」を捉える（負債性資金や投資資産を除外）。
    """
    return ebit / (net_working_capital + net_fixed_assets)


def calculate_earnings_yield(
    ebit: Decimal,
    enterprise_value: Decimal,
) -> Decimal:
    """EY (Earnings Yield) = EBIT / Enterprise Value。

    Greenblatt 2010 Ch.5 が P/E ratio の代わりに EBIT/EV を採用する理由:
        資本構成（負債比率）に依存せず純粋な事業稼ぐ力を測れる。
        負債比率の高い会社が見かけ上「割安」になる罠（PER の罠）を回避できる。
        EV = 時価総額 + 純有利子負債 であり、買収価格に近い概念。
    """
    return ebit / enterprise_value


def compute_magic_formula_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Magic Formula スコア（ROC ランク + EY ランク合算）を算出。

    入力 DataFrame の必須カラム:
        ticker, ebit, net_working_capital, net_fixed_assets, enterprise_value

    追加されるカラム:
        roc                  : Return on Capital
        earnings_yield       : EBIT / Enterprise Value
        roc_rank             : ROC の降順ランク（最大が 1）
        ey_rank              : EY の降順ランク（最大が 1）
        magic_formula_score  : roc_rank + ey_rank（小さいほど良い）

    Greenblatt の核心:
        ROC（質）と EY（割安度）を独立にランク付けし合算することで、
        「質が極端に高い」「割安度が極端に高い」だけの偏った銘柄を排除し、
        両軸でバランスの取れた銘柄を抽出する。
    """
    out = df.copy()
    out["roc"] = out.apply(
        lambda r: calculate_roc(
            r["ebit"], r["net_working_capital"], r["net_fixed_assets"]
        ),
        axis=1,
    )
    out["earnings_yield"] = out.apply(
        lambda r: calculate_earnings_yield(r["ebit"], r["enterprise_value"]),
        axis=1,
    )
    out["roc_rank"] = out["roc"].rank(ascending=False, method="min").astype(int)
    out["ey_rank"] = (
        out["earnings_yield"].rank(ascending=False, method="min").astype(int)
    )
    out["magic_formula_score"] = out["roc_rank"] + out["ey_rank"]
    return out


def select_top_n(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """合算スコア（magic_formula_score）が小さい上位 N 銘柄を抽出。

    入力 DataFrame は事前に :func:`compute_magic_formula_scores` が適用されている前提。
    Greenblatt 推奨ホールド数は 20-30 銘柄（十分な分散とシグナル強度のバランス）。
    """
    return (
        df.sort_values("magic_formula_score", ascending=True)
        .head(n)
        .reset_index(drop=True)
    )


def filter_qualified_stocks(df: pd.DataFrame) -> pd.DataFrame:
    """Magic Formula スクリーニング適格銘柄のみを残す。

    除外条件:
        - 負の EBIT（赤字会社）— Greenblatt 推奨フィルタ。
          ROC が負になりランクの解釈が破綻するため。
    """
    return df[df["ebit"] > Decimal("0")].reset_index(drop=True)


def screen_magic_formula(df: pd.DataFrame, n: int = 30) -> pd.DataFrame:
    """完全 pipeline: 適格フィルタ → スコア算出 → Top N 抽出。

    UI / agent からはこの関数を呼ぶ。Provenance metadata 付き版は
    :func:`screen_magic_formula_with_provenance` を使う（CLAUDE.md §9.8.2）。

    Args:
        df: 銘柄 DataFrame（必須カラム: ticker, ebit, net_working_capital,
            net_fixed_assets, enterprise_value）
        n: 抽出する上位銘柄数（デフォルト 30、Greenblatt 推奨）
    """
    qualified = filter_qualified_stocks(df)
    scored = compute_magic_formula_scores(qualified)
    return select_top_n(scored, n)


# ---------------------------------------------------------------------------
# Provenance 付きエンドツーエンド API
# ---------------------------------------------------------------------------


def _get_current_git_commit() -> str | None:
    """現在の git commit short hash を取得。失敗時は None。"""
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


def screen_magic_formula_with_provenance(
    df: pd.DataFrame,
    n: int = 30,
    *,
    input_data_source: str | None = None,
    input_data_period: str | None = None,
    input_cache_hit: bool | None = None,
) -> MagicFormulaResult:
    """:func:`screen_magic_formula` + 出所追跡 metadata 付与（CLAUDE.md §9.8.2）。

    Provenance 規約により、シグナル出力には必ず計算方法・学術根拠・実行時刻・
    データ出所・コードバージョンを付与する。後で「なぜこの銘柄を買ったか」を
    完全再現可能にする。
    """
    result_df = screen_magic_formula(df, n)
    metadata = MagicFormulaMetadata(
        calculation_method="magic_formula_v1",
        academic_source=(
            'Greenblatt 2010 "The Little Book That Still Beats the Market" Ch.5'
        ),
        calculated_at=datetime.now(timezone.utc),
        input_data_source=input_data_source,
        input_data_period=input_data_period,
        input_cache_hit=input_cache_hit,
        code_commit=_get_current_git_commit(),
    )
    return MagicFormulaResult(result=result_df, metadata=metadata)
