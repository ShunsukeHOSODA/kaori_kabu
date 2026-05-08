"""HMM レジーム検出（regime-detection skill / CLAUDE.md §5）の単体テスト。

学術根拠:
    Hamilton, J. D. (1989). "A New Approach to the Economic Analysis of
    Nonstationary Time Series and the Business Cycle." *Econometrica*, 57(2).

特徴量:
    - log_return  : 日次対数リターン
    - realized_vol: 過去 20 営業日のローリング年率ボラ（× sqrt(252)）
    - vix         : VIX 指数（市場の恐怖指数）

3 状態の解釈:
    - Bull   = 高リターン + 低ボラ
    - Crisis = 低リターン + 高ボラ
    - Choppy = その中間

規約:
    - 数値は float（HMM 内部処理は scipy/numpy のため Decimal 強制対象外、
      ただし表示時は四捨五入）
    - シグナル出力に Provenance metadata 必須（CLAUDE.md §9.8.2）
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def _make_synthetic_market(seed: int = 42) -> tuple[pd.Series, pd.Series]:
    """3 レジームを順に持つ 600 営業日の合成価格 + VIX を生成。

    各 200 日:
        - Bull   : drift +0.08% / day, vol 0.6% / day,  VIX  12-18
        - Choppy : drift  0.00% / day, vol 1.2% / day,  VIX  18-25
        - Crisis : drift -0.20% / day, vol 3.0% / day,  VIX  35-55

    HMM が 3 状態を分離できることをテスト可能にするため、
    各レジームのリターン分布を意図的に十分離す。
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2022-01-03", periods=600)

    bull = rng.normal(loc=0.0008, scale=0.006, size=200)
    choppy = rng.normal(loc=0.0000, scale=0.012, size=200)
    crisis = rng.normal(loc=-0.0020, scale=0.030, size=200)
    log_returns = np.concatenate([bull, choppy, crisis])

    prices = pd.Series(100.0 * np.exp(np.cumsum(log_returns)), index=dates, name="close")

    vix = np.concatenate(
        [
            rng.uniform(12.0, 18.0, size=200),
            rng.uniform(18.0, 25.0, size=200),
            rng.uniform(35.0, 55.0, size=200),
        ]
    )
    vix_series = pd.Series(vix, index=dates, name="vix")

    return prices, vix_series


# ---------------------------------------------------------------------------
# 特徴量準備
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPrepareFeatures:
    """HMM 入力用の特徴量 DataFrame を生成。

    log_return / realized_vol / vix の 3 カラムを揃え、
    rolling window のため発生する先頭 NaN を除去する。
    """

    def test_必須カラムが揃う(self) -> None:
        """戻り DataFrame に log_return / realized_vol / vix が存在する。"""
        from analysis.regime import prepare_features

        prices, vix = _make_synthetic_market()
        features = prepare_features(prices, vix)

        assert {"log_return", "realized_vol", "vix"} <= set(features.columns)

    def test_NaN除去後の行数(self) -> None:
        """rolling 20 営業日のため先頭 19 行が除去される（VIX も同 index 前提）。

        600 日入力 → log_return 計算で 1 行目 NaN → 通常 599 行
        → realized_vol(20) で先頭 19 行 NaN
        → 残る 600 - 20 = 580 行を期待。
        """
        from analysis.regime import prepare_features

        prices, vix = _make_synthetic_market()
        features = prepare_features(prices, vix)

        assert len(features) == 580
        assert not features.isna().any().any()


# ---------------------------------------------------------------------------
# 状態ラベリング
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLabelStates:
    """HMM の隠れ状態 (0/1/2) を Bull / Choppy / Crisis に対応付け。

    GaussianHMM の状態 ID は学習ごとに任意の番号になるため、
    平均リターン最高 → Bull / 最低 → Crisis / 残り → Choppy
    という解釈ルールで人間可読ラベルを後付けする。
    """

    def test_平均リターンが最高の状態にBull_最低にCrisis(self) -> None:
        """各状態の log_return 平均からラベルを決定する。"""
        from analysis.regime import RegimeState, label_states

        # state 0: 平均高 (Bull 候補)、state 1: 平均中 (Choppy)、state 2: 平均低 (Crisis)
        state_means = np.array(
            [
                [0.0010, 0.10, 15.0],   # log_return, realized_vol, vix
                [0.0001, 0.18, 20.0],
                [-0.0020, 0.45, 45.0],
            ]
        )

        states = label_states(state_means)

        assert isinstance(states, tuple)
        assert len(states) == 3
        assert all(isinstance(s, RegimeState) for s in states)

        labels_by_id = {s.state_id: s.label for s in states}
        assert labels_by_id[0] == "Bull"
        assert labels_by_id[1] == "Choppy"
        assert labels_by_id[2] == "Crisis"

    def test_状態IDの順番が逆でも正しくラベリング(self) -> None:
        """state 0 が Crisis、state 2 が Bull のケース。"""
        from analysis.regime import label_states

        state_means = np.array(
            [
                [-0.0020, 0.45, 45.0],  # state 0 = Crisis
                [0.0001, 0.18, 20.0],   # state 1 = Choppy
                [0.0010, 0.10, 15.0],   # state 2 = Bull
            ]
        )

        states = label_states(state_means)
        labels_by_id = {s.state_id: s.label for s in states}

        assert labels_by_id[0] == "Crisis"
        assert labels_by_id[1] == "Choppy"
        assert labels_by_id[2] == "Bull"


# ---------------------------------------------------------------------------
# エンドツーエンド検出
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDetectRegime:
    """合成データで HMM 学習 → 状態予測 → ラベル付与まで通す統合テスト。

    HMM は確率的だが random_state 固定で再現性確保。
    合成データのレジーム境界を厳密に当てる必要はなく、
    出力構造（行数・3 状態揃い・遷移行列形状）を検証する。
    """

    def test_RegimeResult基本構造(self) -> None:
        """戻り値 RegimeResult が必要なフィールドを持つ。"""
        from analysis.regime import RegimeResult, detect_regime

        prices, vix = _make_synthetic_market()
        result = detect_regime(prices, vix)

        assert isinstance(result, RegimeResult)
        # states_per_day: 各日のラベル
        assert isinstance(result.states_per_day, pd.Series)
        assert set(result.states_per_day.unique()) <= {"Bull", "Choppy", "Crisis"}
        # 3 状態定義が揃う
        assert len(result.state_definitions) == 3
        defined_labels = {s.label for s in result.state_definitions}
        assert defined_labels == {"Bull", "Choppy", "Crisis"}

    def test_遷移行列は3x3で各行の和が1(self) -> None:
        """状態遷移確率行列は 3x3、各行の確率和が 1（数値誤差含む）。"""
        from analysis.regime import detect_regime

        prices, vix = _make_synthetic_market()
        result = detect_regime(prices, vix)

        tm = result.transition_matrix
        assert tm.shape == (3, 3)
        row_sums = tm.sum(axis=1).to_numpy()
        np.testing.assert_allclose(row_sums, 1.0, atol=1e-6)
        # index / columns はラベル
        assert set(tm.index) == {"Bull", "Choppy", "Crisis"}
        assert set(tm.columns) == {"Bull", "Choppy", "Crisis"}

    def test_最終日のcurrent_regimeはCrisis合成データで(self) -> None:
        """合成データの最終 200 日は Crisis を意図しているため、
        当該期間の支配的状態は Crisis を期待する（厳密 1 日ではなく多数決）。
        """
        from analysis.regime import detect_regime

        prices, vix = _make_synthetic_market()
        result = detect_regime(prices, vix)

        last_block = result.states_per_day.tail(150)
        crisis_share = (last_block == "Crisis").mean()
        # 完全一致は要求しない（HMM は確率モデル）。過半数で十分
        assert crisis_share > 0.5

    def test_states_per_dayのindexは入力日付と整合(self) -> None:
        """rolling 窓で先頭が落ちるが、残った日付 index は単調増加。"""
        from analysis.regime import detect_regime

        prices, vix = _make_synthetic_market()
        result = detect_regime(prices, vix)

        assert result.states_per_day.index.is_monotonic_increasing
        # 入力 600 日から rolling 20 で 580 行
        assert len(result.states_per_day) == 580


# ---------------------------------------------------------------------------
# Provenance メタデータ
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRegimeWithProvenance:
    """Provenance metadata 必須（CLAUDE.md §9.8.2）。

    シグナル出力には計算方法・学術根拠・実行時刻・状態数・コードバージョンを必ず付与し、
    後で「なぜこの状態判定か」を完全再現可能にする。
    """

    def test_metadata必須フィールドが揃う(self) -> None:
        from analysis.regime import (
            RegimeMetadata,
            RegimeResult,
            detect_regime_with_provenance,
        )

        prices, vix = _make_synthetic_market()
        result = detect_regime_with_provenance(
            prices,
            vix,
            input_data_source="synthetic_test",
        )

        assert isinstance(result, RegimeResult)
        assert isinstance(result.metadata, RegimeMetadata)

        assert result.metadata.calculation_method == "regime_hmm_v1"
        assert "Hamilton" in result.metadata.academic_source
        assert "1989" in result.metadata.academic_source
        assert result.metadata.n_components == 3
        assert result.metadata.calculated_at.tzinfo is not None
        assert result.metadata.input_data_source == "synthetic_test"
