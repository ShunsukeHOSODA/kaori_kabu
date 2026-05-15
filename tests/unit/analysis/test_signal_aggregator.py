"""signal_aggregator.build_regime_signals の単体テスト（Phase 5.3.0 Agent C）。

Stage 5.3.0 では Regime アダプタ部分のみ先行実装。
後段 Task 5.3.1 で build_signal_bundle 本体テストが追記される。

仕様（design.md L1062-1068）:
    既存 detect_regime_with_provenance() をラップして
    RankingSignalBundle 互換 dict を返す:
        {"regime": "Bull"|"Choppy"|"Crisis",
         "state_probs": {"Bull": Decimal, "Choppy": Decimal, "Crisis": Decimal}}

設計判断:
    既存 RegimeResult には state_probs フィールドが存在しないため、
    current_regime ラベルに one-hot 近似 (1.0 / 0.0) を割り当てる。
    後段で predict_proba 拡張が来たら本テストも更新する想定。

PRD §FR5 多段縮退規約:
    detect_regime_with_provenance が失敗時は Choppy + 均等確率を
    縮退結果として返す（spec docstring 明示要件）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Helper: 軽量 RegimeResult ダミー（hmmlearn 学習を経ない MagicMock 代替）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _FakeRegimeMetadata:
    calculation_method: str = "regime_hmm_v1"
    academic_source: str = "Hamilton 1989"
    n_components: int = 3


@dataclass(frozen=True)
class _FakeRegimeResult:
    """RegimeResult のうち signal_aggregator が参照する属性のみ持つ軽量代替。

    signal_aggregator は ``current_regime`` のみ参照する想定なので
    本 dataclass は最小フィールドで済む。
    """

    current_regime: str
    metadata: _FakeRegimeMetadata = field(default_factory=_FakeRegimeMetadata)


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def synthetic_prices() -> pd.Series:
    """30 日間のダミー価格 Series。実 HMM は呼ばないが入力型を満たす。"""
    rng = np.random.default_rng(42)
    dates = pd.bdate_range("2024-01-02", periods=30)
    log_returns = rng.normal(loc=0.0005, scale=0.01, size=30)
    prices = 100.0 * np.exp(np.cumsum(log_returns))
    return pd.Series(prices, index=dates, name="close")


@pytest.fixture
def synthetic_vix(synthetic_prices: pd.Series) -> pd.Series:
    """30 日間のダミー VIX。実 HMM は呼ばないが入力型を満たす。"""
    rng = np.random.default_rng(7)
    return pd.Series(
        rng.uniform(15.0, 22.0, size=len(synthetic_prices)),
        index=synthetic_prices.index,
        name="vix",
    )


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_regime_signals_を_Bull_state_probs_で返す(
    monkeypatch: pytest.MonkeyPatch,
    synthetic_prices: pd.Series,
    synthetic_vix: pd.Series,
) -> None:
    """detect_regime_with_provenance を Bull 状態で stub 化し、
    返り値 dict が regime="Bull" + state_probs[Bull]=1.0 になることを確認する。
    """
    from analysis import signal_aggregator

    fake = _FakeRegimeResult(current_regime="Bull")

    def _stub(*args: object, **kwargs: object) -> _FakeRegimeResult:
        return fake

    monkeypatch.setattr(
        "analysis.signal_aggregator.detect_regime_with_provenance",
        _stub,
    )

    result = signal_aggregator.build_regime_signals(
        universe_prices=synthetic_prices,
        vix_series=synthetic_vix,
    )

    assert result["regime"] == "Bull"
    state_probs = result["state_probs"]
    assert isinstance(state_probs, dict)
    assert state_probs["Bull"] == Decimal("1.0")
    assert state_probs["Choppy"] == Decimal("0.0")
    assert state_probs["Crisis"] == Decimal("0.0")
    # Decimal 型強制（CLAUDE.md §9.1 数値規約）
    for v in state_probs.values():
        assert isinstance(v, Decimal)


@pytest.mark.unit
def test_VIX_None_かつ_HMM失敗時は縮退dict(
    monkeypatch: pytest.MonkeyPatch,
    synthetic_prices: pd.Series,
) -> None:
    """detect_regime_with_provenance が Exception raise 時は
    PRD §FR5 多段縮退として Choppy + 均等確率 dict を返す。
    """
    from analysis import signal_aggregator

    def _raise(*args: object, **kwargs: object) -> _FakeRegimeResult:
        raise RuntimeError("HMM fit failed: insufficient data")

    monkeypatch.setattr(
        "analysis.signal_aggregator.detect_regime_with_provenance",
        _raise,
    )

    result = signal_aggregator.build_regime_signals(
        universe_prices=synthetic_prices,
        vix_series=None,
    )

    assert result["regime"] == "Choppy"
    state_probs = result["state_probs"]
    assert state_probs["Bull"] == Decimal("0.33")
    assert state_probs["Choppy"] == Decimal("0.34")
    assert state_probs["Crisis"] == Decimal("0.33")
    # 合計 1.00 確認（Decimal 厳密一致）
    total = sum(state_probs.values(), Decimal("0"))
    assert total == Decimal("1.00")


@pytest.mark.unit
def test_DataFrame_入力時_close_列が抽出される(
    monkeypatch: pytest.MonkeyPatch,
    synthetic_prices: pd.Series,
    synthetic_vix: pd.Series,
) -> None:
    """universe_prices が DataFrame で "close" 列を含む場合、
    内部で close 列を Series に抽出して detect_regime_with_provenance に渡す。
    """
    from analysis import signal_aggregator

    captured_prices: list[pd.Series] = []

    def _capture(prices: pd.Series, vix: pd.Series, **kwargs: object) -> _FakeRegimeResult:
        captured_prices.append(prices)
        return _FakeRegimeResult(current_regime="Choppy")

    monkeypatch.setattr(
        "analysis.signal_aggregator.detect_regime_with_provenance",
        _capture,
    )

    df_with_close = pd.DataFrame(
        {
            "open": synthetic_prices.values * 0.99,
            "close": synthetic_prices.values,
        },
        index=synthetic_prices.index,
    )

    result = signal_aggregator.build_regime_signals(
        universe_prices=df_with_close,
        vix_series=synthetic_vix,
    )

    assert result["regime"] == "Choppy"
    assert len(captured_prices) == 1
    captured = captured_prices[0]
    assert isinstance(captured, pd.Series)
    # "close" 列が抽出されている（"open" * 0.99 ではない）
    np.testing.assert_allclose(captured.values, synthetic_prices.values)


@pytest.mark.unit
def test_DataFrame_close列なし時は最初の列を使う(
    monkeypatch: pytest.MonkeyPatch,
    synthetic_prices: pd.Series,
    synthetic_vix: pd.Series,
) -> None:
    """DataFrame で "close" 列がない場合は最初の列を価格として使用する。"""
    from analysis import signal_aggregator

    captured_prices: list[pd.Series] = []

    def _capture(prices: pd.Series, vix: pd.Series, **kwargs: object) -> _FakeRegimeResult:
        captured_prices.append(prices)
        return _FakeRegimeResult(current_regime="Crisis")

    monkeypatch.setattr(
        "analysis.signal_aggregator.detect_regime_with_provenance",
        _capture,
    )

    df_no_close = pd.DataFrame(
        {
            "price": synthetic_prices.values,
            "volume": [1000.0] * len(synthetic_prices),
        },
        index=synthetic_prices.index,
    )

    result = signal_aggregator.build_regime_signals(
        universe_prices=df_no_close,
        vix_series=synthetic_vix,
    )

    assert result["regime"] == "Crisis"
    captured = captured_prices[0]
    np.testing.assert_allclose(captured.values, synthetic_prices.values)


# ---------------------------------------------------------------------------
# Phase 5.3.1: build_signal_bundle テスト (design.md L1099-1135)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildSignalBundle:
    """6 skill 統合 build_signal_bundle の単体テスト (design.md L1099-1135)。

    Phase 5.3 review (P-M-4 / C-M-4) で「test_polymarket_client.py 等は
    クラスレベルに ``@pytest.mark.unit`` が付与されているのに本クラスはメソッド
    レベル」と一貫性欠如が指摘されたため、クラスレベル統一に変更した。
    """

    def test_6_skill_統合で_RankingSignalBundle_返却(self) -> None:
        """正常系: 6 skill 全結果が揃っているケースで RankingSignalBundle を構築。"""
        from unittest.mock import MagicMock

        from analysis.signal_aggregator import build_signal_bundle

        composite = MagicMock(
            composite_score=72.5,
            sub_scores={
                "Q": 90, "V": 50, "I": 30, "G": 60,
                "R": 80, "M": 70, "S": 55,
            },
            preset_name="Buffett_型_暫定",
        )
        mf = MagicMock(
            score=85.0,
            roc_pct=Decimal("32.5"),
            earnings_yield_pct=Decimal("8.2"),
        )
        sent = MagicMock(
            sentiment_score=Decimal("0.4"),
            confidence=Decimal("0.7"),
            key_themes=("iPhone", "AI"),
        )

        bundle = build_signal_bundle(
            ticker="AAPL",
            exchange="US",
            sector="Technology",
            composite_result=composite,
            mf_result=mf,
            sentiment_result=sent,
            momentum_1m=Decimal("3"),
            momentum_12m=Decimal("28"),
            polymarket_macro={"fed_cut_2026": Decimal("0.62")},
            fund_holdings_delta={
                "Berkshire": {"action": "NEW", "value_change_usd": 5_200_000_000},
            },
            regime_signals={
                "regime": "Bull",
                "state_probs": {"Bull": Decimal("0.6"), "Choppy": Decimal("0.3"), "Crisis": Decimal("0.1")},
            },
        )

        assert bundle.ticker == "AAPL"
        assert bundle.exchange == "US"
        assert bundle.sector == "Technology"
        assert bundle.composite_score == 72.5
        assert bundle.sub_scores["Q"] == 90.0
        assert bundle.composite_preset == "Buffett_型_暫定"
        assert bundle.magic_formula_score == 85.0
        assert bundle.roc_pct == Decimal("32.5")
        assert bundle.earnings_yield_pct == Decimal("8.2")
        assert bundle.momentum_1m == Decimal("3")
        assert bundle.momentum_12m == Decimal("28")
        assert bundle.sentiment_score == Decimal("0.4")
        assert bundle.sentiment_confidence == Decimal("0.7")
        assert bundle.sentiment_themes == ("iPhone", "AI")
        assert bundle.polymarket_macro["fed_cut_2026"] == Decimal("0.62")
        assert bundle.fund_holdings_delta["Berkshire"]["action"] == "NEW"
        assert bundle.regime == "Bull"
        assert bundle.regime_state_probs["Bull"] == Decimal("0.6")
        assert bundle.fetched_at.tzinfo is not None  # UTC aware

    def test_skill_失敗時に_空_dict_None_で_continue(self) -> None:
        """縮退系: mf_result=None / regime_signals=None でも安全に bundle 構築。"""
        from unittest.mock import MagicMock

        from analysis.signal_aggregator import build_signal_bundle

        composite = MagicMock(
            composite_score=70.0,
            sub_scores={},  # 空 sub_scores 許容
            preset_name="Buffett_型_暫定",
        )
        sent = MagicMock(
            sentiment_score=Decimal("0"),
            confidence=Decimal("0"),
            key_themes=(),
        )

        bundle = build_signal_bundle(
            ticker="X",
            exchange="US",
            composite_result=composite,
            mf_result=None,  # Magic Formula 失敗ケース
            sentiment_result=sent,
            polymarket_macro={},
            fund_holdings_delta={},
            regime_signals=None,  # HMM 失敗ケース
        )

        assert bundle.ticker == "X"
        assert bundle.magic_formula_score is None
        assert bundle.roc_pct is None
        assert bundle.earnings_yield_pct is None
        assert bundle.polymarket_macro == {}
        assert bundle.fund_holdings_delta == {}
        assert bundle.regime == "Choppy"  # 縮退デフォルト
        assert bundle.regime_state_probs == {}


@pytest.mark.unit
class TestAggregateSignalsForUniverse:
    """aggregate_signals_for_universe の単体テスト (Phase 5.3.1)。"""

    def test_2_銘柄_universe_で_順序保持_skip_なし(self) -> None:
        """全 ticker が composite_results / sentiment_results に揃っているケース。"""
        from unittest.mock import MagicMock

        from analysis.signal_aggregator import aggregate_signals_for_universe

        def _make_composite(score: float) -> MagicMock:
            return MagicMock(
                composite_score=score,
                sub_scores={"Q": score, "V": score},
                preset_name="Buffett_型_暫定",
            )

        def _make_sent() -> MagicMock:
            return MagicMock(
                sentiment_score=Decimal("0"),
                confidence=Decimal("0.5"),
                key_themes=(),
            )

        bundles = aggregate_signals_for_universe(
            ["AAPL", "MSFT"],
            exchange="US",
            composite_results={
                "AAPL": _make_composite(80.0),
                "MSFT": _make_composite(75.0),
            },
            mf_results={},  # 全 None
            sentiment_results={"AAPL": _make_sent(), "MSFT": _make_sent()},
            momentum_results={},
            polymarket_macro={"fed_cut_2026": Decimal("0.5")},
            fund_holdings_delta_by_fund={},
            regime_signals={"regime": "Bull", "state_probs": {"Bull": Decimal("1.0")}},
        )

        assert len(bundles) == 2
        assert [b.ticker for b in bundles] == ["AAPL", "MSFT"]
        assert bundles[0].composite_score == 80.0
        assert bundles[1].composite_score == 75.0
        assert all(b.magic_formula_score is None for b in bundles)
        assert all(b.regime == "Bull" for b in bundles)

    def test_composite_欠損_ticker_は_skip(self) -> None:
        """composite_results に存在しない ticker は skip して bundle 構築をスキップ。"""
        from unittest.mock import MagicMock

        from analysis.signal_aggregator import aggregate_signals_for_universe

        composite = MagicMock(
            composite_score=60.0,
            sub_scores={},
            preset_name="default",
        )
        sent = MagicMock(
            sentiment_score=Decimal("0"),
            confidence=Decimal("0"),
            key_themes=(),
        )

        bundles = aggregate_signals_for_universe(
            ["AAPL", "MISSING", "MSFT"],
            exchange="US",
            composite_results={"AAPL": composite, "MSFT": composite},
            mf_results={},
            sentiment_results={"AAPL": sent, "MSFT": sent},
            momentum_results={},
            polymarket_macro={},
            fund_holdings_delta_by_fund={},
            regime_signals={"regime": "Choppy", "state_probs": {}},
        )

        assert [b.ticker for b in bundles] == ["AAPL", "MSFT"]
