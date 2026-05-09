"""risk_metrics_panel.render_risk_metrics_panel の単体テスト。

CLAUDE.md §9.7 / §9.8.5 準拠 — provenance 開示と認知バイアス警告の存在を保証。
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from analysis.risk_metrics import RiskMetrics, RiskMetricsMetadata
from dashboard.widgets.risk_metrics_panel import render_risk_metrics_panel


def _make_metrics(var_confidence: float = 0.05) -> RiskMetrics:
    return RiskMetrics(
        sharpe=1.42,
        sortino=2.10,
        calmar=0.88,
        max_drawdown=-0.18,
        var_95=-0.025,
        cvar_95=-0.038,
        annualized_return=0.15,
        annualized_volatility=0.20,
        metadata=RiskMetricsMetadata(
            calculation_method="risk_metrics_v1",
            academic_source="Sharpe 1966 ...",
            calculated_at=datetime.now(timezone.utc),
            input_data_period="2024-05-09 to 2025-05-08",
            input_data_source="EODHD",
            code_commit="abc1234",
            var_confidence=var_confidence,
            risk_free_rate=0.0,
        ),
    )


def _build_container() -> MagicMock:
    """columns / expander が動作する MagicMock container を構築。"""
    container = MagicMock()
    container.columns.side_effect = lambda n: [MagicMock() for _ in range(n)]
    expander_cm = MagicMock()
    expander_cm.__enter__ = MagicMock(return_value=expander_cm)
    expander_cm.__exit__ = MagicMock(return_value=None)
    container.expander.return_value = expander_cm
    return container


@pytest.mark.unit
class TestRenderRiskMetricsPanel:
    """8 種の metric を 2 行 × 4 列で表示する責務の検証。"""

    def test_columns_を_4_列_2_行で呼び出す(self) -> None:
        container = _build_container()

        render_risk_metrics_panel(_make_metrics(), container=container)

        assert container.columns.call_count == 2
        for call in container.columns.call_args_list:
            assert call.args[0] == 4

    def test_provenance_expander_を_呼び出す(self) -> None:
        container = _build_container()

        render_risk_metrics_panel(_make_metrics(), container=container)

        container.expander.assert_called_once()
        title = container.expander.call_args[0][0]
        assert "Provenance" in title or "計算根拠" in title

    def test_provenance_表示で_認知バイアス警告_と_出所を含む(self) -> None:
        container = _build_container()
        rendered: list[str] = []
        expander_cm = container.expander.return_value
        expander_cm.write.side_effect = lambda msg: rendered.append(str(msg))
        expander_cm.caption.side_effect = lambda msg: rendered.append(str(msg))

        render_risk_metrics_panel(_make_metrics(), container=container)

        joined = "\n".join(rendered)
        assert "Recency Bias" in joined
        assert "Confirmation Bias" in joined
        # データ源・コミット・期間が開示される (CLAUDE.md §9.8.5)
        assert "EODHD" in joined
        assert "abc1234" in joined
        assert "2024-05-09 to 2025-05-08" in joined

    def test_var_confidence_の_percent_が_metric_label_に反映(self) -> None:
        captured_labels: list[str] = []

        def capturing_columns(n: int) -> list[MagicMock]:
            mocks = []
            for _ in range(n):
                m = MagicMock()
                m.metric.side_effect = (
                    lambda label, *args, **kwargs: captured_labels.append(label)
                )
                mocks.append(m)
            return mocks

        container = MagicMock()
        container.columns.side_effect = capturing_columns
        expander_cm = MagicMock()
        expander_cm.__enter__ = MagicMock(return_value=expander_cm)
        expander_cm.__exit__ = MagicMock(return_value=None)
        container.expander.return_value = expander_cm

        render_risk_metrics_panel(
            _make_metrics(var_confidence=0.05), container=container
        )

        assert "VaR (5%)" in captured_labels
        assert "CVaR (5%)" in captured_labels
        assert "シャープレシオ" in captured_labels
        assert "ソルティノレシオ" in captured_labels
        assert "カルマーレシオ" in captured_labels
        assert "最大ドローダウン" in captured_labels
