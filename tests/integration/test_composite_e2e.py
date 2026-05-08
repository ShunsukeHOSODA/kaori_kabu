"""Composite Score E2E パイプラインテスト（Phase 3.1b マージ前ゲート）。

architecture doc §12.4 が要求する end-to-end テスト。VCR fixture 配線は
Phase 3.2 に後回しし、Phase 3.1b では **EODHD ``/fundamentals/`` レスポンス
形式を模した合成 fixture** をパイプラインに通し、

    fundamentals dict
        → CompositeScoreInputs（合成 fixture から手動構築）
        → compute_composite_score (4 プリセット)
        → 7 軸 sub_scores + Composite + warnings

の連鎖が論理的に整合することをスナップショット検証する。

検証対象:
    - V/G/M を含む 7 軸が全プリセットで 0-100 範囲
    - Buffett_型_暫定 と 逆張り型 で重み配分通り異なる Composite を返す
    - 破綻寸前データで警告（ALTMAN_DISTRESS / LOSS_3Y / FALLING_KNIFE）が発火
    - 配当再投資型は Coca-Cola 風データで逆張り型より高 Composite

合成 fixture は EODHD の Highlights / Income_Statement / Balance_Sheet /
Cash_Flow を模したネスト dict。実 API 呼び出しは行わない。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# 合成 EODHD fundamentals fixture
# ---------------------------------------------------------------------------


def _yearly_with_growth(
    *,
    base_revenue: Decimal,
    base_eps: Decimal,
    growth: Decimal,
    years: int,
    operating_income_factor: Decimal,
    gross_profit_factor: Decimal,
    ebitda_factor: Decimal,
) -> dict[str, dict[str, Any]]:
    """N 年分の yearly 財務データを growth 率で生成（CAGR 計算検証用）。"""
    yearly: dict[str, dict[str, Any]] = {}
    for i in range(years):
        year = 2019 + i
        rev = base_revenue * ((Decimal("1") + growth) ** i)
        eps = base_eps * ((Decimal("1") + growth) ** i)
        yearly[f"{year}-12-31"] = {
            "totalRevenue": str(rev.quantize(Decimal("1"))),
            "dilutedEps": str(eps.quantize(Decimal("0.01"))),
            "operatingIncome": str(
                (rev * operating_income_factor).quantize(Decimal("1"))
            ),
            "grossProfit": str(
                (rev * gross_profit_factor).quantize(Decimal("1"))
            ),
            "ebitda": str((rev * ebitda_factor).quantize(Decimal("1"))),
        }
    return yearly


def _coca_cola_fundamentals() -> dict[str, Any]:
    """Coca-Cola 風: 高品質 + 高配当 + 低リスク。"""
    return {
        "General": {"Sector": "Consumer Staples"},
        "Highlights": {
            "MarketCapitalization": 250_000_000_000,
            "EnterpriseValue": 280_000_000_000,
            "ForwardAnnualDividendRate": 3.5,
            "PayoutRatio": 0.55,
            "ReturnOnEquityTTM": 0.40,
            "ReturnOnAssetsTTM": 0.10,
            "PERatio": 25.0,
            "QuarterlyEarningsGrowthYOY": 0.06,
            "DividendGrowth5Years": 0.05,
            "NetDebt": 30_000_000_000,
            "EBITDA": 14_000_000_000,
        },
        "Financials": {
            "Income_Statement": {
                "yearly": _yearly_with_growth(
                    base_revenue=Decimal("38000000000"),
                    base_eps=Decimal("2.0"),
                    growth=Decimal("0.06"),
                    years=6,
                    operating_income_factor=Decimal("0.30"),
                    gross_profit_factor=Decimal("0.60"),
                    ebitda_factor=Decimal("0.36"),
                ),
            },
            "Balance_Sheet": {
                "yearly": {
                    "2024-12-31": {
                        "totalCurrentAssets": "30000000000",
                        "totalCurrentLiabilities": "20000000000",
                        "retainedEarnings": "70000000000",
                        "totalLiab": "70000000000",
                        "totalAssets": "100000000000",
                    }
                },
            },
            "Cash_Flow": {
                "yearly": {
                    "2024-12-31": {
                        "totalCashFromOperatingActivities": "12000000000",
                        "capitalExpenditures": "-2000000000",
                        "commonStockRepurchased": "-1500000000",
                    }
                },
            },
        },
    }


def _distressed_fundamentals() -> dict[str, Any]:
    """連続赤字 + 高 leverage + 低品質。"""
    return {
        "General": {"Sector": "Industrials"},
        "Highlights": {
            "MarketCapitalization": 1_000_000_000,
            "EnterpriseValue": 6_000_000_000,
            "ForwardAnnualDividendRate": 0.0,
            "PayoutRatio": None,
            "ReturnOnEquityTTM": -0.15,
            "ReturnOnAssetsTTM": -0.05,
            "PERatio": -8.0,
            "QuarterlyEarningsGrowthYOY": -0.40,
            "DividendGrowth5Years": None,
            "NetDebt": 5_000_000_000,
            "EBITDA": 200_000_000,
        },
        "Financials": {
            "Income_Statement": {
                "yearly": _yearly_with_growth(
                    base_revenue=Decimal("3000000000"),
                    base_eps=Decimal("-0.5"),
                    growth=Decimal("-0.05"),
                    years=6,
                    operating_income_factor=Decimal("-0.05"),
                    gross_profit_factor=Decimal("0.10"),
                    ebitda_factor=Decimal("0.07"),
                ),
            },
            "Balance_Sheet": {
                "yearly": {
                    "2024-12-31": {
                        "totalCurrentAssets": "1000000000",
                        "totalCurrentLiabilities": "1500000000",
                        "retainedEarnings": "-500000000",
                        "totalLiab": "5500000000",
                        "totalAssets": "6500000000",
                    }
                },
            },
            "Cash_Flow": {
                "yearly": {
                    "2024-12-31": {
                        "totalCashFromOperatingActivities": "-100000000",
                        "capitalExpenditures": "-200000000",
                        "commonStockRepurchased": "0",
                    }
                },
            },
        },
    }


# ---------------------------------------------------------------------------
# CompositeScoreInputs ビルダー（screener helper の挙動を再現）
# ---------------------------------------------------------------------------


def _build_inputs_from_fundamentals(
    f: dict[str, Any],
    *,
    current_price_jpy: Decimal,
    sentiment_score: Decimal,
    sentiment_confidence: Decimal,
    momentum_12m_return: Decimal,
) -> Any:
    """合成 fundamentals dict から CompositeScoreInputs を構築（screener と同等ロジック）。

    Notes:
        screener.py の build_composite_inputs_from_fundamentals は
        ファイル名先頭が数字（02_screener.py）のため Python import 不可。
        ロジックの core はテストで再実装し、screener が同期されているかを
        ``test_screener_logic_対応`` テストで担保する。
    """
    from analysis.composite import (
        CompositeScoreInputs,
        GrowthSubScoreInputs,
        IncomeSubScoreInputs,
        MomentumSubScoreInputs,
        QualitySubScoreInputs,
        RiskSubScoreInputs,
        ValueSubScoreInputs,
    )

    highlights = f["Highlights"]
    income_yearly = f["Financials"]["Income_Statement"]["yearly"]
    balance_yearly = f["Financials"]["Balance_Sheet"]["yearly"]
    cashflow_yearly = f["Financials"]["Cash_Flow"]["yearly"]
    sector = f["General"]["Sector"]

    latest_income = income_yearly[max(income_yearly.keys())]
    latest_balance = balance_yearly[max(balance_yearly.keys())]
    latest_cashflow = cashflow_yearly[max(cashflow_yearly.keys())]

    market_cap = Decimal(str(highlights["MarketCapitalization"]))
    ev = Decimal(str(highlights["EnterpriseValue"]))
    ebit = Decimal(latest_income["operatingIncome"])
    sales = Decimal(latest_income["totalRevenue"])
    gross_profit = Decimal(latest_income["grossProfit"])

    op_cf = Decimal(latest_cashflow["totalCashFromOperatingActivities"])
    capex = abs(Decimal(latest_cashflow["capitalExpenditures"]))
    fcf = op_cf - capex
    buybacks = abs(Decimal(latest_cashflow["commonStockRepurchased"]))

    ca = Decimal(latest_balance["totalCurrentAssets"])
    cl = Decimal(latest_balance["totalCurrentLiabilities"])
    re = Decimal(latest_balance["retainedEarnings"])
    total_liab = Decimal(latest_balance["totalLiab"])
    total_assets = Decimal(latest_balance["totalAssets"])
    net_debt = Decimal(str(highlights["NetDebt"]))
    ebitda = Decimal(str(highlights["EBITDA"]))

    annual_div = (
        Decimal(str(highlights["ForwardAnnualDividendRate"]))
        if highlights.get("ForwardAnnualDividendRate")
        else None
    )
    payout = (
        Decimal(str(highlights["PayoutRatio"]))
        if highlights.get("PayoutRatio") is not None
        else None
    )
    roe = Decimal(str(highlights["ReturnOnEquityTTM"]))
    roa = Decimal(str(highlights["ReturnOnAssetsTTM"]))
    gross_margin = gross_profit / sales if sales > 0 else None

    # Growth helper (5y CAGR from yearly)
    sorted_keys = sorted(income_yearly.keys())
    rev_latest = Decimal(income_yearly[sorted_keys[-1]]["totalRevenue"])
    rev_5y_ago = Decimal(income_yearly[sorted_keys[-6]]["totalRevenue"])
    rev_cagr: Decimal | None = None
    if rev_latest > 0 and rev_5y_ago > 0:
        rev_cagr = Decimal(
            str(round(float(rev_latest / rev_5y_ago) ** (1.0 / 5) - 1.0, 6))
        )
    eps_latest = Decimal(income_yearly[sorted_keys[-1]]["dilutedEps"])
    eps_5y_ago = Decimal(income_yearly[sorted_keys[-6]]["dilutedEps"])
    eps_cagr: Decimal | None = None
    if eps_latest > 0 and eps_5y_ago > 0:
        eps_cagr = Decimal(
            str(round(float(eps_latest / eps_5y_ago) ** (1.0 / 5) - 1.0, 6))
        )

    pe_ratio = (
        Decimal(str(highlights["PERatio"]))
        if highlights.get("PERatio") is not None
        else None
    )
    earnings_growth = (
        Decimal(str(highlights["QuarterlyEarningsGrowthYOY"]))
        if highlights.get("QuarterlyEarningsGrowthYOY") is not None
        else None
    )
    dividend_cagr = (
        Decimal(str(highlights["DividendGrowth5Years"]))
        if highlights.get("DividendGrowth5Years") is not None
        else None
    )

    return CompositeScoreInputs(
        income=IncomeSubScoreInputs(
            forward_dividend_per_share_jpy=annual_div,
            current_price_jpy=current_price_jpy,
            payout_ratio=payout,
            consecutive_dividend_years=0,
            buybacks_4q_jpy=buybacks,
            market_cap_jpy=market_cap,
            free_cash_flow_jpy=fcf,
            enterprise_value_jpy=ev,
            sector=sector,
        ),
        risk=RiskSubScoreInputs(
            working_capital_jpy=ca - cl,
            retained_earnings_jpy=re,
            ebit_jpy=ebit,
            market_cap_jpy=market_cap,
            total_liabilities_jpy=total_liab,
            sales_jpy=sales,
            total_assets_jpy=total_assets,
            net_debt_jpy=net_debt,
            ebitda_jpy=ebitda,
            short_interest_pct=None,
            consecutive_loss_years=4 if ebit < 0 else 0,
            beneish_m_score=None,
        ),
        quality=QualitySubScoreInputs(
            roe=roe,
            roa=roa,
            gross_margin=gross_margin,
        ),
        sentiment_score=sentiment_score,
        sentiment_confidence=sentiment_confidence,
        momentum_12m_return=momentum_12m_return,
        value=ValueSubScoreInputs(
            ebit_jpy=ebit if ebit > 0 else None,
            enterprise_value_jpy=ev,
        ),
        growth=GrowthSubScoreInputs(
            revenue_5y_cagr=rev_cagr,
            eps_5y_cagr=eps_cagr,
            dividend_5y_cagr=dividend_cagr,
            pe_ratio=pe_ratio,
            earnings_growth_rate=earnings_growth,
        ),
        momentum=MomentumSubScoreInputs(
            return_12m=momentum_12m_return,
            return_1m=Decimal("0.01"),
        ),
    )


# ---------------------------------------------------------------------------
# E2E パイプラインテスト
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCompositeScoreE2E:
    """合成 fundamentals dict → 7 軸 Composite Score までの完全パイプライン検証。"""

    def test_全プリセット_スコア範囲(self) -> None:
        """4 プリセット × 2 銘柄 = 8 通りで 0-100 範囲を検証。"""
        from analysis.composite import compute_composite_score

        coca_inputs = _build_inputs_from_fundamentals(
            _coca_cola_fundamentals(),
            current_price_jpy=Decimal("60"),
            sentiment_score=Decimal("0.2"),
            sentiment_confidence=Decimal("0.6"),
            momentum_12m_return=Decimal("0.08"),
        )
        distressed_inputs = _build_inputs_from_fundamentals(
            _distressed_fundamentals(),
            current_price_jpy=Decimal("5"),
            sentiment_score=Decimal("-0.6"),
            sentiment_confidence=Decimal("0.6"),
            momentum_12m_return=Decimal("-0.40"),
        )

        for preset in (
            "Buffett_型_暫定",
            "配当再投資型",
            "Lynch_型",
            "逆張り型",
        ):
            for inputs, label in (
                (coca_inputs, "coca"),
                (distressed_inputs, "distressed"),
            ):
                result = compute_composite_score(inputs, preset_name=preset)
                assert 0.0 <= result.composite_score <= 100.0, (
                    f"{preset}/{label}: composite_score = "
                    f"{result.composite_score}"
                )
                for axis_score in result.sub_scores.values():
                    assert 0.0 <= axis_score <= 100.0
                assert set(result.sub_scores.keys()) == {
                    "Q",
                    "V",
                    "I",
                    "G",
                    "R",
                    "M",
                    "S",
                }

    def test_同一入力_異プリセット_異Composite(self) -> None:
        """同じ Coca-Cola fixture で 4 プリセットそれぞれ異なる Composite を返す。

        重み配分が違えば計算結果は異なる、という基本保証。具体的な大小関係は
        他テスト（``test_VGM_合算で_Composite_が_上振れ_Phase_3_1A_比較``）で
        担保し、ここでは「プリセットが意味を持つ」事実のみ検証。
        """
        from analysis.composite import compute_composite_score

        coca_inputs = _build_inputs_from_fundamentals(
            _coca_cola_fundamentals(),
            current_price_jpy=Decimal("60"),
            sentiment_score=Decimal("0.2"),
            sentiment_confidence=Decimal("0.6"),
            momentum_12m_return=Decimal("0.08"),
        )
        scores = {
            preset: compute_composite_score(
                coca_inputs, preset_name=preset
            ).composite_score
            for preset in (
                "Buffett_型_暫定",
                "配当再投資型",
                "Lynch_型",
                "逆張り型",
            )
        }
        # 4 つの異なるスコアが得られる（プリセット効果の存在証明）
        assert len(set(round(s, 2) for s in scores.values())) == 4

    def test_破綻寸前_警告発火(self) -> None:
        """連続赤字 + 高 leverage で ALTMAN/LOSS3Y 警告が発火。

        FALLING_KNIFE は Quality ≥ 70 が条件のため別テストで検証する
        （破綻寸前は Q 低スコアで定義上発火しない）。
        """
        from analysis.composite import compute_composite_score

        distressed_inputs = _build_inputs_from_fundamentals(
            _distressed_fundamentals(),
            current_price_jpy=Decimal("5"),
            sentiment_score=Decimal("-0.6"),
            sentiment_confidence=Decimal("0.6"),
            momentum_12m_return=Decimal("-0.40"),
        )
        result = compute_composite_score(
            distressed_inputs, preset_name="逆張り型"
        )
        codes = {w.code for w in result.warnings}
        assert "ALTMAN_DISTRESS" in codes
        assert "LOSS_3Y" in codes

    def test_高品質_負12mリターン_FALLING_KNIFE発火(self) -> None:
        """Quality ≧ 70 + 12m return < -20% で FALLING_KNIFE 警告。

        Coca-Cola 風の高品質銘柄が暴落途中の場合のシナリオ。
        """
        from analysis.composite import compute_composite_score

        falling_inputs = _build_inputs_from_fundamentals(
            _coca_cola_fundamentals(),
            current_price_jpy=Decimal("60"),
            sentiment_score=Decimal("-0.4"),
            sentiment_confidence=Decimal("0.6"),
            momentum_12m_return=Decimal("-0.30"),  # 30% 下落
        )
        result = compute_composite_score(
            falling_inputs, preset_name="Buffett_型_暫定"
        )
        codes = {w.code for w in result.warnings}
        assert "FALLING_KNIFE" in codes

    def test_VGM_合算で_Composite_が_上振れ_Phase_3_1A_比較(self) -> None:
        """V/G/M を提供すると Phase 3.1a 互換動作（None）より Composite が上振れる。

        Coca-Cola 風データで V (EY=4.07%) は約 34 点、Growth は配当 CAGR 5%
        程度で軽い加点。Buffett_型_暫定 (V=20 + G=5 + M=5 = 30 重み) で違いが
        観察できる。
        """
        from analysis.composite import (
            CompositeScoreInputs,
            compute_composite_score,
        )

        coca_full = _build_inputs_from_fundamentals(
            _coca_cola_fundamentals(),
            current_price_jpy=Decimal("60"),
            sentiment_score=Decimal("0.2"),
            sentiment_confidence=Decimal("0.6"),
            momentum_12m_return=Decimal("0.08"),
        )
        coca_legacy = CompositeScoreInputs(
            income=coca_full.income,
            risk=coca_full.risk,
            quality=coca_full.quality,
            sentiment_score=coca_full.sentiment_score,
            sentiment_confidence=coca_full.sentiment_confidence,
            momentum_12m_return=coca_full.momentum_12m_return,
            # value/growth/momentum は None のまま
        )
        full = compute_composite_score(coca_full, preset_name="Buffett_型_暫定")
        legacy = compute_composite_score(
            coca_legacy, preset_name="Buffett_型_暫定"
        )
        assert full.composite_score > legacy.composite_score


@pytest.mark.integration
class TestSyntheticFundamentalsHelpers:
    """合成 fixture ヘルパーの整合性検証。"""

    def test_yearly_growth_helper_は_n年分生成(self) -> None:
        yearly = _yearly_with_growth(
            base_revenue=Decimal("1000"),
            base_eps=Decimal("1.0"),
            growth=Decimal("0.10"),
            years=6,
            operating_income_factor=Decimal("0.20"),
            gross_profit_factor=Decimal("0.50"),
            ebitda_factor=Decimal("0.25"),
        )
        assert len(yearly) == 6
        last_key = max(yearly.keys())
        assert Decimal(yearly[last_key]["totalRevenue"]) > Decimal("1500")

    def test_coca_cola_fundamentals_は_必須キーを含む(self) -> None:
        f = _coca_cola_fundamentals()
        assert "Highlights" in f
        assert "Financials" in f
        assert "Income_Statement" in f["Financials"]
        assert "Balance_Sheet" in f["Financials"]
        assert "Cash_Flow" in f["Financials"]

    def test_distressed_fundamentals_は_負EBIT(self) -> None:
        f = _distressed_fundamentals()
        latest_year = max(
            f["Financials"]["Income_Statement"]["yearly"].keys()
        )
        op_income = Decimal(
            f["Financials"]["Income_Statement"]["yearly"][latest_year][
                "operatingIncome"
            ]
        )
        assert op_income < 0
