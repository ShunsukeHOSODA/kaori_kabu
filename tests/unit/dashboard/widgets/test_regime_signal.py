"""regime_signal.to_signal / render_regime_signal の単体テスト。

CLAUDE.md §9.7（Recency Bias 抑止）の中核 UI 部品なので、
3 状態（Bull/Choppy/Crisis）の正規化と None フォールバックを保証する。
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pandas as pd
import pytest

from analysis.regime import RegimeMetadata, RegimeResult, RegimeState
from dashboard.widgets.regime_signal import (
    RegimeSignal,
    render_regime_signal,
    to_signal,
)


def _make_result(label: str) -> RegimeResult:
    """テスト用に最小 RegimeResult を構築（current_regime だけ可変）。"""
    state_definitions = (
        RegimeState(0, "Bull", 0.001, 0.10, 15.0),
        RegimeState(1, "Choppy", 0.0, 0.15, 20.0),
        RegimeState(2, "Crisis", -0.002, 0.30, 35.0),
    )
    states = pd.Series(["Bull"], index=pd.to_datetime(["2026-05-09"]), name="regime")
    transmat = pd.DataFrame(
        [[0.9, 0.1, 0.0], [0.1, 0.8, 0.1], [0.0, 0.1, 0.9]],
        index=["Bull", "Choppy", "Crisis"],
        columns=["Bull", "Choppy", "Crisis"],
    )
    metadata = RegimeMetadata(
        calculation_method="regime_hmm_v1",
        academic_source="Hamilton 1989",
        calculated_at=datetime.now(timezone.utc),
        n_components=3,
        training_period="2024-01-01 to 2026-05-09",
    )
    return RegimeResult(
        states_per_day=states,
        state_definitions=state_definitions,
        transition_matrix=transmat,
        current_regime=label,  # type: ignore[arg-type]
        metadata=metadata,
    )


@pytest.mark.unit
class TestToSignal:
    """純粋変換 to_signal の検証。"""

    def test_Bull_は緑信号で積極買いOK(self) -> None:
        signal = to_signal(_make_result("Bull"))

        assert signal == RegimeSignal(
            emoji="🟢",
            label_ja="強気相場",
            action_ja="積極買い OK",
            color="normal",
        )

    def test_Choppy_は黄信号で慎重_配当株中心(self) -> None:
        signal = to_signal(_make_result("Choppy"))

        assert signal.emoji == "🟡"
        assert signal.label_ja == "横ばい"
        assert signal.color == "warning"

    def test_Crisis_は赤信号で新規買い停止(self) -> None:
        signal = to_signal(_make_result("Crisis"))

        assert signal.emoji == "🔴"
        assert signal.label_ja == "暴落リスク"
        assert signal.action_ja == "新規買い停止"
        assert signal.color == "error"


@pytest.mark.unit
class TestRenderRegimeSignal:
    """render_regime_signal が container にどのメソッドを呼ぶか検証。"""

    def test_None_のとき_info_を呼んで判定中表示(self) -> None:
        container = MagicMock()

        render_regime_signal(None, container=container)

        container.info.assert_called_once()
        msg = container.info.call_args[0][0]
        assert "判定中" in msg
        container.error.assert_not_called()
        container.warning.assert_not_called()
        container.success.assert_not_called()

    def test_Crisis_のとき_error_メソッドが呼ばれる(self) -> None:
        container = MagicMock()
        # expander コンテキスト動作のモック化
        container.expander.return_value.__enter__ = MagicMock(
            return_value=container.expander.return_value
        )
        container.expander.return_value.__exit__ = MagicMock(return_value=False)

        render_regime_signal(_make_result("Crisis"), container=container)

        container.error.assert_called_once()
        msg = container.error.call_args[0][0]
        assert "🔴" in msg
        assert "暴落リスク" in msg
        assert "新規買い停止" in msg
        # expander 詳細が開示されること
        container.expander.assert_called_once()

    def test_Bull_のとき_success_メソッドが呼ばれる(self) -> None:
        container = MagicMock()
        container.expander.return_value.__enter__ = MagicMock(
            return_value=container.expander.return_value
        )
        container.expander.return_value.__exit__ = MagicMock(return_value=False)

        render_regime_signal(_make_result("Bull"), container=container)

        container.success.assert_called_once()
        container.error.assert_not_called()


@pytest.mark.unit
class TestMetadataPreserved:
    """学術根拠・学習期間が信号灯に欠落しないことの確認（Provenance §9.8）。"""

    def test_training_period_が_None_でもクラッシュしない(self) -> None:
        result = _make_result("Bull")
        result_no_period = replace(
            result,
            metadata=replace(result.metadata, training_period=None),
        )
        container = MagicMock()
        container.expander.return_value.__enter__ = MagicMock(
            return_value=container.expander.return_value
        )
        container.expander.return_value.__exit__ = MagicMock(return_value=False)

        # 例外なく完了すれば OK
        render_regime_signal(result_no_period, container=container)

        container.success.assert_called_once()


@pytest.mark.unit
class TestVixProxyWarning:
    """VIX realized vol 代理使用時の UI 警告（§4.1 #2、handoff-phase4.md）。"""

    def _attach_expander_mock(self, container: MagicMock) -> None:
        container.expander.return_value.__enter__ = MagicMock(
            return_value=container.expander.return_value
        )
        container.expander.return_value.__exit__ = MagicMock(return_value=False)

    def test_realized_vol_proxy使用時にwarningが追加表示される(self) -> None:
        """vix_source == "realized_vol_proxy_v1" のとき
        `container.warning(...)` が「VIX 取得失敗」メッセージ付きで呼ばれる。"""
        result = _make_result("Bull")
        result_proxy = replace(
            result,
            metadata=replace(result.metadata, vix_source="realized_vol_proxy_v1"),
        )
        container = MagicMock()
        self._attach_expander_mock(container)

        render_regime_signal(result_proxy, container=container)

        # Bull の信号灯は success、追加で warning が呼ばれる
        container.success.assert_called_once()
        container.warning.assert_called_once()
        warn_msg = container.warning.call_args[0][0]
        assert "VIX 取得失敗" in warn_msg
        assert "realized vol" in warn_msg.lower() or "代理" in warn_msg

    def test_vix_source_が_EODHD_のときwarningは呼ばれない(self) -> None:
        result = _make_result("Bull")
        result_eodhd = replace(
            result,
            metadata=replace(result.metadata, vix_source="EODHD"),
        )
        container = MagicMock()
        self._attach_expander_mock(container)

        render_regime_signal(result_eodhd, container=container)

        container.success.assert_called_once()
        container.warning.assert_not_called()

    def test_Crisis_かつ代理使用時_errorとwarning両方呼ばれる(self) -> None:
        """信号灯本体（error）と代理警告（warning）は独立して両方表示される。"""
        result = _make_result("Crisis")
        result_proxy = replace(
            result,
            metadata=replace(result.metadata, vix_source="realized_vol_proxy_v1"),
        )
        container = MagicMock()
        self._attach_expander_mock(container)

        render_regime_signal(result_proxy, container=container)

        container.error.assert_called_once()
        container.warning.assert_called_once()
