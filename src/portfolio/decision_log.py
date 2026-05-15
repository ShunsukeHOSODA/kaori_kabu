"""売買判断ログ（Decision Log、append-only JSONL）。

CLAUDE.md §9.5 / §9.8.3 に準拠:
    - append-only 構造で過去の判断を改ざん不能に保つ
    - Provenance 込み（trigger / code_commit）で「なぜ買ったか」を完全再現
    - 月別ファイル（``{log_dir}/{YYYY-MM}.jsonl``）でローテーション

JSONL 1 行のスキーマ:
    {
        "timestamp": "2026-05-09T14:30:00+00:00",
        "action": "BUY" | "SELL" | "HOLD",
        "ticker": "AAPL",
        "shares": "10",
        "price_jpy": "25000",
        "rationale": "Magic Formula スコア 87/100",
        "trigger": {"skill": "magic-formula-screener", ...} | null,
        "stop_loss_atr_jpy": "22500" | null,
        "code_commit": "edabbe1" | null,
        "news_context": {                          // Phase 2 追加
            "sentiment_score": "0.65",
            "confidence": "0.85",
            "summary": "...",
            "key_themes": [...],
            "risk_signals": [...],
            "source_urls": [...],
            "fetched_at": "...",
            "model_version": "claude-haiku-4-5-20251001",
            "lenses_applied": ["Buffett_Munger", ...]
        } | null,
        "kelly_recommendation": {                  // Phase 4 §4.2 #3 追加
            "win_rate": "0.6",
            "win_loss_ratio": "2.0",
            "full_kelly_fraction": "0.4",
            "fraction_multiplier": "0.5",
            "half_kelly_fraction": "0.2",
            "max_position_pct": "0.05",
            "capped_pct": "0.05",
            "recommended_size_jpy": "50000",
            "portfolio_value_jpy": "1000000",
            "calculation_method": "half_kelly_v1",
            "academic_source": "Thorp 2006 ..."
        } | null,
        "claude_ranking": {                        // Phase 5.4.3 追加
            "ranking_score": 87,
            "recommendation_summary": "...",
            "supporting_signals": ["..."],
            "risk_signals": ["..."],
            "counter_view": "...",
            "lens_views": {
                "Buffett_Munger": "...",
                "Burry": "...",
                "Lynch": "..."
            },
            "confidence": "0.82",
            "confidence_adjusted": "0.78",
            "kelly_multiplier": "0.95",
            "fallback_reason": null,
            "metadata": { ... }
        } | null
    }
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas as pd

    from analysis.sentiment import SentimentResult


def append_decision(
    *,
    log_dir: Path,
    action: str,
    ticker: str,
    shares: Decimal,
    price_jpy: Decimal,
    rationale: str,
    trigger: dict[str, Any] | None = None,
    stop_loss_atr_jpy: Decimal | None = None,
    code_commit: str | None = None,
    news_context: dict[str, Any] | None = None,
    kelly_recommendation: dict[str, Any] | None = None,
    claude_ranking: dict[str, Any] | None = None,
) -> Path:
    """売買判断を JSONL に 1 行追記（append-only）。

    ファイル名は実行時刻の年月で決定（``{log_dir}/{YYYY-MM}.jsonl``）。
    既存があれば追記、なければ作成（親ディレクトリも自動作成）。

    Args:
        log_dir: ログ保存ルート
        action: ``BUY`` / ``SELL`` / ``HOLD``
        ticker: ティッカーシンボル
        shares: 株数（Decimal、文字列で保存される）
        price_jpy: 取引単価 JPY（Decimal、文字列で保存される）
        rationale: 判断根拠（自由記述）
        trigger: 判断のきっかけ（スキル名 / スコア等）
        stop_loss_atr_jpy: ATR トレーリングストップ価格（JPY）
        code_commit: 計算時の git commit short hash
        news_context: 売買時のニュースコンテキスト（Phase 2 追加）。
            :func:`build_news_context_from_sentiment` で SentimentResult から
            構築するのが標準。直接 dict を渡すこともできる。
            「なぜ買ったか」を市場ニュース・地政学・センチメントまで含めて
            完全再現可能にする（CLAUDE.md §9.5 / §9.8）。
        kelly_recommendation: Half-Kelly 計算過程（Phase 4 §4.2 #3 追加）。
            :func:`strategies.kelly.build_kelly_recommendation` で生成するのが
            標準。「なぜこの数量を買ったか」を入力（win_rate / payoff）から
            最終 capped 推奨サイズまで再現可能にする（CLAUDE.md §9.8.3）。
        claude_ranking: Claude Sonnet 4.6 による Stage 2 総合判定結果（Phase
            5.4.3 追加）。:class:`analysis.ranking_judge.RankingResult` を
            ``model_dump(mode="json")`` で dict 化したもの。Sonnet 不在 /
            縮退時は ``None``。「なぜこの銘柄を買ったか」を Claude 判定
            （ranking_score / counter_view / lens_views / kelly_multiplier
            等）まで含めて完全再現可能にする（CLAUDE.md §9.8.3）。

    Returns:
        書き込み先のパス。
    """
    now = datetime.now(timezone.utc)
    log_path = log_dir / f"{now.strftime('%Y-%m')}.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    record: dict[str, Any] = {
        "timestamp": now.isoformat(),
        "action": action,
        "ticker": ticker,
        "shares": str(shares),
        "price_jpy": str(price_jpy),
        "rationale": rationale,
        "trigger": trigger,
        "stop_loss_atr_jpy": (
            str(stop_loss_atr_jpy) if stop_loss_atr_jpy is not None else None
        ),
        "code_commit": code_commit,
        "news_context": news_context,
        "kelly_recommendation": kelly_recommendation,
        "claude_ranking": claude_ranking,
    }

    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return log_path


def build_news_context_from_sentiment(
    sentiment_result: SentimentResult,
    news_df: pd.DataFrame,
    *,
    lenses_applied: tuple[str, ...] = (),
) -> dict[str, Any]:
    """SentimentResult + ニュース DataFrame → JSON 直列化可能な news_context。

    :func:`append_decision` の ``news_context`` 引数にそのまま渡せる形式に
    変換する。Decimal や Timestamp は文字列化、URL リストは ``source_urls``
    に集約する。

    Args:
        sentiment_result: :func:`analyze_sentiment` の戻り値
        news_df: センチメント分析の入力に使ったニュース DataFrame
            （``url`` 列があれば ``source_urls`` に展開）
        lenses_applied: 適用した投資家レンズ名タプル
            （例 ``("Buffett_Munger", "Burry")``）

    Returns:
        JSON 直列化可能な dict（Decimal は文字列、Timestamp は ISO 8601）。
    """
    source_urls: list[str] = []
    if "url" in news_df.columns:
        source_urls = [
            str(u) for u in news_df["url"].tolist() if u and str(u) != "nan"
        ]

    md = sentiment_result.metadata
    return {
        "sentiment_score": str(sentiment_result.sentiment_score),
        "confidence": str(sentiment_result.confidence),
        "summary": sentiment_result.summary,
        "key_themes": list(sentiment_result.key_themes),
        "risk_signals": list(sentiment_result.risk_signals),
        "source_urls": source_urls,
        "fetched_at": md.calculated_at.isoformat(),
        "model_version": md.model_version,
        "calculation_method": md.calculation_method,
        "input_news_count": md.input_news_count,
        "academic_source": md.academic_source,
        "lenses_applied": list(lenses_applied),
    }


def read_decisions(
    *, log_dir: Path, year_month: str
) -> list[dict[str, Any]]:
    """指定月の Decision Log を読み込み（存在しなければ空リスト）。

    Args:
        log_dir: ログディレクトリ
        year_month: ``YYYY-MM`` 形式（例 ``2026-05``）

    Returns:
        各行を dict にパースしたリスト（追記順）。
    """
    log_path = log_dir / f"{year_month}.jsonl"
    if not log_path.exists():
        return []

    records: list[dict[str, Any]] = []
    with log_path.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                records.append(json.loads(stripped))
    return records
