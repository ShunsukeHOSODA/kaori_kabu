"""Magic Formula スクリーナー（Greenblatt 2010）の単体テスト。

学術根拠:
    Greenblatt, J. (2010). *The Little Book That Still Beats the Market*. Ch.5

計算式:
    ROC (Return on Capital) = EBIT / (Net Working Capital + Net Fixed Assets)
    Earnings Yield (EY)     = EBIT / Enterprise Value
    最終スコア              = rank(ROC) + rank(EY)（合算ランキング、低いほど高評価）

規約:
    - 金額は Decimal 型（CLAUDE.md §9.1）
    - シグナル出力に Provenance metadata 必須（§9.8.2）
"""

from __future__ import annotations

from decimal import Decimal

import pandas as pd
import pytest


@pytest.mark.unit
class TestCalculateROC:
    """ROC（Return on Capital）計算ロジック。

    Greenblatt の定義:
        ROC = EBIT / (Net Working Capital + Net Fixed Assets)

    分母は「事業に投下されている運転資本」を表し、純資産より厳密に
    「稼ぐために必要な資本」を捉える（負債性資金や投資資産を除外）。
    """

    def test_roc_計算_基本ケース(self) -> None:
        """EBIT=100, NWC=200, NFA=300 → ROC = 100/500 = 0.20。"""
        from analysis.magic_formula import calculate_roc

        roc = calculate_roc(
            ebit=Decimal("100"),
            net_working_capital=Decimal("200"),
            net_fixed_assets=Decimal("300"),
        )

        assert roc == Decimal("0.20")


@pytest.mark.unit
class TestCalculateEarningsYield:
    """EY（Earnings Yield）計算ロジック。

    Greenblatt の定義:
        EY = EBIT / Enterprise Value

    P/E ratio の代わりに EBIT/EV を使う理由:
        資本構成（負債比率）に左右されず、純粋な事業稼ぐ力を測れる。
        負債比率の高い会社が見かけ上「割安」になる罠を回避できる。
    """

    def test_ey_計算_基本ケース(self) -> None:
        """EBIT=100, EV=1000 → EY = 100/1000 = 0.10（10%）。"""
        from analysis.magic_formula import calculate_earnings_yield

        ey = calculate_earnings_yield(
            ebit=Decimal("100"),
            enterprise_value=Decimal("1000"),
        )

        assert ey == Decimal("0.10")


@pytest.mark.unit
class TestComputeMagicFormulaScores:
    """ROC ランクと EY ランクの合算による Magic Formula スコア算出。

    Greenblatt の核心アイデア:
        ROC（質）と EY（割安度）の両方で良い銘柄を見つけるため、
        個別ランクを合算する。低スコアほど「質も高く割安」。
        単独指標ではなく合算することで、極端な値に引きずられない。
    """

    def test_3銘柄_ランキング合算スコア(self) -> None:
        """3 銘柄を ROC/EY 計算 → 各々ランク付け → 合算スコア算出。

        計算結果:
            A: ROC=30/100=0.30 (1位), EY=30/300=0.10 (2位) → 合算 1+2=3
            B: ROC=30/200=0.15 (2位), EY=30/200=0.15 (1位) → 合算 2+1=3
            C: ROC=10/100=0.10 (3位), EY=10/200=0.05 (3位) → 合算 3+3=6
        """
        from analysis.magic_formula import compute_magic_formula_scores

        df = pd.DataFrame(
            {
                "ticker": ["A", "B", "C"],
                "ebit": [Decimal("30"), Decimal("30"), Decimal("10")],
                "net_working_capital": [Decimal("50"), Decimal("100"), Decimal("50")],
                "net_fixed_assets": [Decimal("50"), Decimal("100"), Decimal("50")],
                "enterprise_value": [Decimal("300"), Decimal("200"), Decimal("200")],
            }
        )

        result = compute_magic_formula_scores(df)

        # 必須カラムが追加されている
        assert "roc" in result.columns
        assert "earnings_yield" in result.columns
        assert "roc_rank" in result.columns
        assert "ey_rank" in result.columns
        assert "magic_formula_score" in result.columns

        # スコア値検証
        scores = result.set_index("ticker")["magic_formula_score"].to_dict()
        assert scores["A"] == 3
        assert scores["B"] == 3
        assert scores["C"] == 6


@pytest.mark.unit
class TestSelectTopN:
    """Magic Formula 合算スコア上位 N 銘柄抽出。

    Greenblatt 推奨は通常 20-30 銘柄ホールド。十分な分散を保ちつつ、
    シグナルの強さも維持する経験則。
    """

    def test_top2_抽出_4銘柄から(self) -> None:
        """4 銘柄から magic_formula_score が小さい上位 2 銘柄を抽出。

        全 4 銘柄を ROC/EY 完全に等差にし、合算スコアが昇順 [2,4,6,8] に。
        n=2 で A, B が選ばれる。
        """
        from analysis.magic_formula import (
            compute_magic_formula_scores,
            select_top_n,
        )

        df = pd.DataFrame(
            {
                "ticker": ["A", "B", "C", "D"],
                "ebit": [Decimal("40"), Decimal("30"), Decimal("20"), Decimal("10")],
                "net_working_capital": [Decimal("50")] * 4,
                "net_fixed_assets": [Decimal("50")] * 4,
                "enterprise_value": [Decimal("400")] * 4,
            }
        )

        scored = compute_magic_formula_scores(df)
        top = select_top_n(scored, n=2)

        assert len(top) == 2
        assert list(top["ticker"]) == ["A", "B"]


@pytest.mark.unit
class TestFilterQualifiedStocks:
    """Magic Formula スクリーニング適格銘柄フィルタ。

    Greenblatt は赤字会社（負の EBIT）をスクリーニング対象外とする。
    理由:
        - ROC が負になり、ランクの解釈が破綻
        - そもそも「稼ぐ力」を測れない
        - 赤字 → ターンアラウンド狙いは別の戦略
    """

    def test_負のEBIT銘柄を除外(self) -> None:
        """4 銘柄のうち 1 つの EBIT が負。除外されて 3 銘柄が残る。"""
        from analysis.magic_formula import filter_qualified_stocks

        df = pd.DataFrame(
            {
                "ticker": ["A", "B", "C", "D"],
                "ebit": [
                    Decimal("30"),
                    Decimal("-10"),  # 赤字 → 除外
                    Decimal("20"),
                    Decimal("15"),
                ],
                "net_working_capital": [Decimal("50")] * 4,
                "net_fixed_assets": [Decimal("50")] * 4,
                "enterprise_value": [Decimal("200")] * 4,
            }
        )

        filtered = filter_qualified_stocks(df)

        assert len(filtered) == 3
        assert "B" not in list(filtered["ticker"])
        assert set(filtered["ticker"]) == {"A", "C", "D"}


@pytest.mark.unit
class TestScreenMagicFormula:
    """完全 pipeline: 適格フィルタ → スコア算出 → Top N 抽出。

    エンドツーエンドで「ノイズ込みの銘柄リスト → Magic Formula 推奨銘柄」
    まで 1 関数で完結する。UI / agent からはこの関数を呼ぶ。
    """

    def test_pipeline_5銘柄から_負EBIT除外_Top2抽出(self) -> None:
        """5 銘柄、うち 1 つ赤字 → 4 銘柄候補 → Top 2 を抽出。

        想定結果:
            A: EBIT=40 → 候補、合算 1+1=2 (Top 1)
            B: EBIT=-5 → 除外
            C: EBIT=30 → 候補、合算 2+2=4 (Top 2)
            D: EBIT=20 → 候補、合算 3+3=6
            E: EBIT=10 → 候補、合算 4+4=8
        """
        from analysis.magic_formula import screen_magic_formula

        df = pd.DataFrame(
            {
                "ticker": ["A", "B", "C", "D", "E"],
                "ebit": [
                    Decimal("40"),
                    Decimal("-5"),  # 除外
                    Decimal("30"),
                    Decimal("20"),
                    Decimal("10"),
                ],
                "net_working_capital": [Decimal("50")] * 5,
                "net_fixed_assets": [Decimal("50")] * 5,
                "enterprise_value": [Decimal("400")] * 5,
            }
        )

        result = screen_magic_formula(df, n=2)

        assert len(result) == 2
        assert list(result["ticker"]) == ["A", "C"]
        # 除外された B は出てこない
        assert "B" not in list(result["ticker"])


@pytest.mark.unit
class TestMagicFormulaWithProvenance:
    """Provenance metadata を持つ完全 pipeline（CLAUDE.md §9.8.2 必須）。

    シグナル出力に「いつ・何で・どう計算したか」を必ず付与する。
    後で「なぜこの銘柄を買ったか」を完全に再現可能にする要件。
    """

    def test_metadata必須フィールドが揃う(self) -> None:
        """MagicFormulaResult が結果と metadata を持ち、規約必須フィールドを含む。"""
        from analysis.magic_formula import (
            MagicFormulaMetadata,
            MagicFormulaResult,
            screen_magic_formula_with_provenance,
        )

        df = pd.DataFrame(
            {
                "ticker": ["A", "B", "C"],
                "ebit": [Decimal("30"), Decimal("20"), Decimal("10")],
                "net_working_capital": [Decimal("50")] * 3,
                "net_fixed_assets": [Decimal("50")] * 3,
                "enterprise_value": [Decimal("300"), Decimal("200"), Decimal("200")],
            }
        )

        result = screen_magic_formula_with_provenance(df, n=2)

        # 型
        assert isinstance(result, MagicFormulaResult)
        assert isinstance(result.metadata, MagicFormulaMetadata)
        assert isinstance(result.result, pd.DataFrame)

        # 必須フィールド
        assert result.metadata.calculation_method == "magic_formula_v1"
        assert "Greenblatt" in result.metadata.academic_source
        assert "Ch.5" in result.metadata.academic_source
        # tz-aware datetime
        assert result.metadata.calculated_at.tzinfo is not None

        # 結果は Top 2
        assert len(result.result) == 2
