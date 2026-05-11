"""HMM レジーム検出（CLAUDE.md §5 / regime-detection skill）。

市場の状態を Bull / Choppy / Crisis の 3 段階に分類し、Crisis 時の
新規買い停止・現金比率上昇という規律を提供する。

学術根拠:
    Hamilton, J. D. (1989). "A New Approach to the Economic Analysis of
    Nonstationary Time Series and the Business Cycle." *Econometrica*, 57(2).

特徴量:
    log_return  : 日次対数リターン
    realized_vol: 過去 20 営業日のローリング年率ボラ（× sqrt(252)）
    vix         : VIX 指数（市場の恐怖指数）

3 状態の解釈ルール（学習後に決定）:
    Bull   = 平均リターン最高 → 推奨アクション: 積極買い OK（緑）
    Crisis = 平均リターン最低 → 推奨アクション: 新規買い停止（赤）
    Choppy = 残り 1 状態     → 推奨アクション: 慎重・配当株中心（黄）

限界:
    - 過去依存（レジーム変化の検知は遅延あり）
    - 状態数 3 は人為的（Hamilton 原典は 2 状態）
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

ROLLING_WINDOW: int = 20
"""realized_vol の rolling 窓（営業日）。約 1 ヶ月のボラを表す業界標準。"""

ANNUALIZATION_FACTOR: float = float(np.sqrt(252))
"""日次ボラ → 年率ボラ変換係数（営業日 252 日基準）。"""

DEFAULT_N_COMPONENTS: int = 3
"""HMM の隠れ状態数。Bull / Choppy / Crisis に対応。"""

DEFAULT_RANDOM_STATE: int = 42
"""学習の再現性確保用シード。"""

RegimeLabel = Literal["Bull", "Choppy", "Crisis"]
ALL_LABELS: tuple[RegimeLabel, ...] = ("Bull", "Choppy", "Crisis")


# ---------------------------------------------------------------------------
# データクラス
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegimeState:
    """単一隠れ状態の解釈情報。

    HMM の状態 ID は学習ごとに任意の番号になるため、
    平均リターン・ボラから人間可読ラベルを後付けする。
    """

    state_id: int
    label: RegimeLabel
    mean_log_return: float
    mean_realized_vol: float
    mean_vix: float


@dataclass(frozen=True)
class RegimeMetadata:
    """レジーム検出結果の出所情報（CLAUDE.md §9.8.2 必須）。"""

    calculation_method: str
    academic_source: str
    calculated_at: datetime
    n_components: int
    training_period: str | None = None
    input_data_source: str | None = None
    code_commit: str | None = None
    vix_source: str | None = None
    """VIX 入力の出所。"EODHD" / "realized_vol_proxy_v1" / None。

    代理ボラ使用時は UI で警告表示するための分岐キー（handoff-phase4.md §4.1）。
    """


@dataclass(frozen=True)
class RegimeResult:
    """レジーム検出のエンドツーエンド結果。

    Attributes:
        states_per_day: 日付 index → ラベル（"Bull"/"Choppy"/"Crisis"）の Series
        state_definitions: 3 状態の解釈情報（state_id, label, 各特徴量平均）
        transition_matrix: ラベル名を index/columns とする 3x3 遷移確率行列
        current_regime: 最終日のラベル
        metadata: provenance metadata
    """

    states_per_day: pd.Series
    state_definitions: tuple[RegimeState, ...]
    transition_matrix: pd.DataFrame
    current_regime: RegimeLabel
    metadata: RegimeMetadata


# ---------------------------------------------------------------------------
# 特徴量準備
# ---------------------------------------------------------------------------


def compute_realized_volatility(
    prices: pd.Series,
    window: int = 30,
) -> pd.Series:
    """SPY 終値から年率 realized volatility を VIX 代理として算出（§4.1 #2）。

    EODHD INDX 経路で VIX 取得失敗時のフォールバック。
    VIX は ann. implied vol (%) で通常 10-50 範囲なので、
    realized vol を × 100 して同スケールに揃える。

    計算:
        log_return = ln(p_t / p_{t-1})
        proxy = rolling(window).std(log_return) * sqrt(252) * 100

    Args:
        prices: 終値 Series（日付 index）
        window: rolling 窓（営業日、既定 30 ≒ 1.5 ヶ月）

    Returns:
        VIX 代理 Series（同 index、先頭 ``window`` 行は NaN）。

    Notes:
        - 学術的に realized vol ≠ implied vol だが、HMM 学習の特徴量としては
          高ボラ状態を識別する代替として十分機能する（Hamilton 1989 系の
          regime-switching では realized vol を直接特徴量にする例が一般的）。
        - 代理使用時は :class:`RegimeMetadata.vix_source` に
          ``"realized_vol_proxy_v1"`` を入れて UI で警告表示する。
    """
    log_returns = np.log(prices / prices.shift(1))
    realized_vol = log_returns.rolling(window).std() * ANNUALIZATION_FACTOR
    return realized_vol * 100.0


def prepare_features(prices: pd.Series, vix: pd.Series) -> pd.DataFrame:
    """HMM 入力用の特徴量 DataFrame を生成。

    log_return = ln(p_t / p_{t-1})
    realized_vol = log_return の rolling(20) 標準偏差 × sqrt(252)

    rolling 窓が埋まらない先頭行（先頭 1 行の log_return NaN +
    rolling 19 行）は除去する。

    Args:
        prices: 終値 Series（日付 index）
        vix: VIX 指数 Series（同 index 推奨、片方欠損時は inner join）

    Returns:
        ``log_return`` / ``realized_vol`` / ``vix`` 3 列の DataFrame。
    """
    log_returns = np.log(prices / prices.shift(1))
    realized_vol = log_returns.rolling(ROLLING_WINDOW).std() * ANNUALIZATION_FACTOR

    df = pd.DataFrame(
        {
            "log_return": log_returns,
            "realized_vol": realized_vol,
            "vix": vix,
        }
    )
    return df.dropna()


# ---------------------------------------------------------------------------
# 状態ラベリング
# ---------------------------------------------------------------------------


def label_states(state_means: np.ndarray) -> tuple[RegimeState, ...]:
    """学習後の状態平均から Bull / Choppy / Crisis ラベルを割り当てる。

    入力 ``state_means`` は shape ``(n_components, n_features)`` で、
    1 列目が log_return、2 列目が realized_vol、3 列目が vix である前提
    （:func:`prepare_features` が出すカラム順と一致）。

    割り当てルール:
        平均 log_return が最大の state → Bull
        平均 log_return が最小の state → Crisis
        残り 1 state                  → Choppy

    Returns:
        state_id 昇順の :class:`RegimeState` タプル（長さ 3）。
    """
    if state_means.shape[0] != 3:
        raise ValueError(
            f"label_states expects 3 states, got {state_means.shape[0]}"
        )

    mean_returns = state_means[:, 0]
    bull_id = int(np.argmax(mean_returns))
    crisis_id = int(np.argmin(mean_returns))
    choppy_id = ({0, 1, 2} - {bull_id, crisis_id}).pop()

    label_by_id: dict[int, RegimeLabel] = {
        bull_id: "Bull",
        choppy_id: "Choppy",
        crisis_id: "Crisis",
    }

    return tuple(
        RegimeState(
            state_id=i,
            label=label_by_id[i],
            mean_log_return=float(state_means[i, 0]),
            mean_realized_vol=float(state_means[i, 1]),
            mean_vix=float(state_means[i, 2]),
        )
        for i in range(3)
    )


# ---------------------------------------------------------------------------
# モデル学習・予測
# ---------------------------------------------------------------------------


def fit_regime_model(
    features: pd.DataFrame,
    n_components: int = DEFAULT_N_COMPONENTS,
    random_state: int = DEFAULT_RANDOM_STATE,
) -> GaussianHMM:
    """GaussianHMM を学習。

    full covariance を採用（特徴量間の相関を保持）。
    n_iter=1000 で十分な収束マージンを確保。
    """
    model = GaussianHMM(
        n_components=n_components,
        covariance_type="full",
        n_iter=1000,
        random_state=random_state,
    )
    model.fit(features.to_numpy())
    return model


def detect_regime(
    prices: pd.Series,
    vix: pd.Series,
    n_components: int = DEFAULT_N_COMPONENTS,
    random_state: int = DEFAULT_RANDOM_STATE,
) -> RegimeResult:
    """価格 + VIX → 特徴量 → HMM 学習 → ラベル付与 までエンドツーエンド実行。

    Args:
        prices: 終値 Series（日付 index）
        vix: VIX 指数 Series
        n_components: 隠れ状態数（既定 3）
        random_state: 学習シード

    Returns:
        :class:`RegimeResult`（metadata は最小限。完全な provenance 付与は
        :func:`detect_regime_with_provenance` を使う）。
    """
    features = prepare_features(prices, vix)
    model = fit_regime_model(
        features, n_components=n_components, random_state=random_state
    )

    state_definitions = label_states(model.means_)
    label_by_id = {s.state_id: s.label for s in state_definitions}

    raw_states = model.predict(features.to_numpy())
    states_per_day = pd.Series(
        [label_by_id[int(s)] for s in raw_states],
        index=features.index,
        name="regime",
    )

    transition_matrix = _build_transition_matrix(model.transmat_, label_by_id)
    current_regime: RegimeLabel = states_per_day.iloc[-1]

    metadata = RegimeMetadata(
        calculation_method="regime_hmm_v1",
        academic_source=(
            'Hamilton 1989 "A New Approach to the Economic Analysis of '
            'Nonstationary Time Series and the Business Cycle" Econometrica 57(2)'
        ),
        calculated_at=datetime.now(timezone.utc),
        n_components=n_components,
    )

    return RegimeResult(
        states_per_day=states_per_day,
        state_definitions=state_definitions,
        transition_matrix=transition_matrix,
        current_regime=current_regime,
        metadata=metadata,
    )


def _build_transition_matrix(
    transmat: np.ndarray,
    label_by_id: dict[int, RegimeLabel],
) -> pd.DataFrame:
    """HMM の transmat_ (state-id 行列) をラベル名 index/columns に並び替える。

    並び順は ``ALL_LABELS`` (Bull, Choppy, Crisis) 固定。
    """
    id_by_label = {v: k for k, v in label_by_id.items()}
    ordered_ids = [id_by_label[label] for label in ALL_LABELS]
    reordered = transmat[np.ix_(ordered_ids, ordered_ids)]
    return pd.DataFrame(reordered, index=list(ALL_LABELS), columns=list(ALL_LABELS))


# ---------------------------------------------------------------------------
# Provenance 付き API
# ---------------------------------------------------------------------------


def _get_current_git_commit() -> str | None:
    """現在の git commit short hash。失敗時は None。"""
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


def detect_regime_with_provenance(
    prices: pd.Series,
    vix: pd.Series,
    *,
    n_components: int = DEFAULT_N_COMPONENTS,
    random_state: int = DEFAULT_RANDOM_STATE,
    input_data_source: str | None = None,
    vix_source: str | None = None,
) -> RegimeResult:
    """:func:`detect_regime` + 完全な provenance metadata 付与（CLAUDE.md §9.8.2）。

    入力データ期間・データ出所・git commit を metadata に追加し、
    後で「なぜこの状態判定か」を完全再現可能にする。

    Args:
        prices: 終値 Series
        vix: VIX 入力（取得失敗時は :func:`compute_realized_volatility` の代理を渡す）
        input_data_source: SPY 等 prices の出所
        vix_source: VIX 入力の出所。"EODHD" / "realized_vol_proxy_v1" / None。
    """
    result = detect_regime(
        prices, vix, n_components=n_components, random_state=random_state
    )

    training_period = (
        f"{result.states_per_day.index.min().date()}"
        f" to {result.states_per_day.index.max().date()}"
    )

    enriched_metadata = RegimeMetadata(
        calculation_method=result.metadata.calculation_method,
        academic_source=result.metadata.academic_source,
        calculated_at=result.metadata.calculated_at,
        n_components=result.metadata.n_components,
        training_period=training_period,
        input_data_source=input_data_source,
        code_commit=_get_current_git_commit(),
        vix_source=vix_source,
    )

    return RegimeResult(
        states_per_day=result.states_per_day,
        state_definitions=result.state_definitions,
        transition_matrix=result.transition_matrix,
        current_regime=result.current_regime,
        metadata=enriched_metadata,
    )
