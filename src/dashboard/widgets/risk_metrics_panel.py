"""リスク指標パネルウィジェット（Phase 3.2 / CLAUDE.md §9.7 / §9.8.5）。

保有ポートフォリオの :class:`src.analysis.risk_metrics.RiskMetrics` を
4 列 × 2 行のメトリクスグリッドで表示し、provenance を expander で開示する。
``comparison`` を渡すと vs ベンチマーク行（α / β / IR / Up/Down Capture）も併記。

ロジック分離（``container`` 注入）で Streamlit 非依存の単体テスト容易。
"""

from __future__ import annotations

from src.analysis.risk_metrics import BenchmarkComparison, RiskMetrics


def render_risk_metrics_panel(
    metrics: RiskMetrics,
    *,
    comparison: BenchmarkComparison | None = None,
    container: object | None = None,
) -> None:
    """リスク指標 8 種を 2 行 × 4 列で表示し、provenance を折りたたみで開示。

    Args:
        metrics: :func:`src.analysis.risk_metrics.compute_risk_metrics` 戻り値
        container: ``st`` モジュール / ``st.container()`` インスタンス。
            未指定時は import-on-call で ``streamlit`` を使う。
            （テスト時は ``unittest.mock.MagicMock`` を渡す）
    """
    if container is None:
        import streamlit as st

        container = st

    var_pct = int(metrics.metadata.var_confidence * 100)

    # 1 行目: Sharpe / Sortino / Calmar / Max DD
    row1 = container.columns(4)  # type: ignore[attr-defined]
    row1[0].metric(
        "シャープレシオ",
        f"{metrics.sharpe:.2f}",
        help="年率超過リターン / 年率ボラ。1.0 以上で良好、2.0 以上で優秀。",
    )
    row1[1].metric(
        "ソルティノレシオ",
        f"{metrics.sortino:.2f}",
        help="下方ボラのみで Sharpe 化。下落リスク対比のリターン効率。",
    )
    row1[2].metric(
        "カルマーレシオ",
        f"{metrics.calmar:.2f}",
        help="年率リターン / |Max DD|。1.0 以上で良好。",
    )
    row1[3].metric(
        "最大ドローダウン",
        f"{metrics.max_drawdown * 100:+.2f}%",
        help="期間中の最大下落率（ピークから谷まで）。-20% 超は要注意。",
    )

    # 2 行目: VaR / CVaR / 年率リターン / 年率ボラ
    row2 = container.columns(4)  # type: ignore[attr-defined]
    row2[0].metric(
        f"VaR ({var_pct}%)",
        f"{metrics.var_95 * 100:+.2f}%",
        help=f"日次 {var_pct}% 確率で発生する下落幅（過去分布から）。",
    )
    row2[1].metric(
        f"CVaR ({var_pct}%)",
        f"{metrics.cvar_95 * 100:+.2f}%",
        help="VaR 越え（テール）時の平均損失率。VaR より悪い。",
    )
    row2[2].metric(
        "年率リターン",
        f"{metrics.annualized_return * 100:+.2f}%",
        help="日次リターンの年率換算（252 営業日）。",
    )
    row2[3].metric(
        "年率ボラ",
        f"{metrics.annualized_volatility * 100:+.2f}%",
        help="日次リターン標準偏差の年率換算。",
    )

    # vs ベンチマーク比較（任意、CLAUDE.md §9.4 シグナル根拠併記）
    if comparison is not None:
        bench_label = comparison.metadata.benchmark_label
        container.subheader(f"📐 vs {bench_label}")  # type: ignore[attr-defined]
        container.caption(  # type: ignore[attr-defined]
            "α (アルファ) は超過リターン、β (ベータ) は市場感応度、"
            "IR は超過リターンの効率、Up/Down Capture は上昇/下落局面捕捉率。"
        )
        cmp_row1 = container.columns(4)  # type: ignore[attr-defined]
        cmp_row1[0].metric(
            "α (年率)",
            f"{comparison.alpha * 100:+.2f}%",
            help="ベンチマークを超過する年率リターン。+ で勝ち、- で負け。",
        )
        cmp_row1[1].metric(
            "β",
            f"{comparison.beta:.2f}",
            help="市場変動感応度。1.0 がベンチ並み、<1 が低ボラ、>1 が高ボラ。",
        )
        cmp_row1[2].metric(
            "Information Ratio",
            f"{comparison.information_ratio:.2f}",
            help="超過リターン / Tracking Error。0.5 以上で良好、1.0 で優秀。",
        )
        cmp_row1[3].metric(
            "Tracking Error",
            f"{comparison.tracking_error * 100:.2f}%",
            help="ベンチとの差分の年率標準偏差。小さいほどベンチ追随。",
        )
        cmp_row2 = container.columns(2)  # type: ignore[attr-defined]
        cmp_row2[0].metric(
            "Up Capture",
            f"{comparison.up_capture * 100:.1f}%",
            help="ベンチが上昇する局面でどれだけ追随できたか（100% でベンチ並み）。",
        )
        cmp_row2[1].metric(
            "Down Capture",
            f"{comparison.down_capture * 100:.1f}%",
            help="ベンチが下落する局面での損失捕捉率（< 100% で下落耐性あり）。",
        )

    # Provenance disclosure (CLAUDE.md §9.8.5)
    expander = container.expander("ⓘ 計算根拠（Provenance）")  # type: ignore[attr-defined]
    with expander:
        expander.write(f"**判定方法**: `{metrics.metadata.calculation_method}`")
        expander.write(f"**学術根拠**: {metrics.metadata.academic_source}")
        expander.write(f"**データ期間**: {metrics.metadata.input_data_period}")
        expander.write(
            f"**データ源**: {metrics.metadata.input_data_source or '不明'}"
        )
        expander.write(
            f"**コードコミット**: `{metrics.metadata.code_commit or 'unknown'}`"
        )
        expander.write(
            f"**VaR 信頼区間**: {metrics.metadata.var_confidence * 100:.0f}%"
        )
        if comparison is not None:
            expander.write(
                f"**ベンチマーク**: `{comparison.metadata.benchmark_label}`"
                f" (期間: {comparison.metadata.input_data_period})"
            )
            expander.write(
                f"**ベンチマーク学術根拠**: {comparison.metadata.academic_source}"
            )
        expander.caption(
            "⚠️ 認知バイアス対策: 過去の数字は将来を保証しない (Recency Bias)。"
            "高 Sharpe でも一時的な追い風かもしれない (Confirmation Bias)。"
        )
