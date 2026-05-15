"""Composite Score テーブル → BUY 確定 → Decision Log 書き込みのロジック層。

§4.2 #3 残課題（handoff-phase4.md §11.3）に対応。
02_screener.py の Streamlit UI から呼ばれる本体ロジックを切り出し、
pytest でカバー可能にする（UI 描画と完全独立、Streamlit ランタイム不要）。

CLAUDE.md §9.5 / §9.8.3 に準拠:
    - Kelly 計算過程を build_kelly_recommendation で自動付与
    - trigger に screener metadata（preset / composite_score / sub_scores）
      を埋めて「なぜこのスコアで買ったか」を完全再現可能に
    - rationale を composite_score + preset から自動生成、ユーザー追記を末尾結合
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from src.portfolio.decision_log import ClaudeRankingDict, append_decision
from src.strategies.kelly import KellyParams, build_kelly_recommendation


@dataclass(frozen=True)
class ScreenerTrigger:
    """Composite Score テーブルから BUY を仕掛けた時の screening metadata。

    Provenance §9.8.3 で trigger フィールドに埋める dict のソース。後で
    「この銘柄をどのプリセットでどのスコアで選んだか」を完全再現可能に。

    Attributes:
        skill: トリガースキル名（例 ``"composite-score-screener"``）
        preset: スクリーニングに使ったプリセット（例 ``"Buffett_型_暫定"``）
        composite_score: 0-100 の総合スコア
        sub_scores: 7 軸（Q / V / I / G / R / M / S）の個別スコア
        screener_run_at: スクリーニング実行時刻（ISO 8601）
    """

    skill: str
    preset: str
    composite_score: Decimal
    sub_scores: dict[str, Decimal] = field(default_factory=dict)
    screener_run_at: str = ""


@dataclass(frozen=True)
class BuyOrderRequest:
    """BUY 注文 1 件分のリクエスト（UI 層が組み立てる DTO）。

    Attributes:
        ticker: ティッカーシンボル
        shares: 株数
        price_jpy: 単価（JPY）
        trigger: スクリーナー由来の screening metadata
        kelly_params: Kelly 計算に使う勝率 / 損益比
        portfolio_value_jpy: ポートフォリオ評価額（Kelly 基準）
        additional_rationale: ユーザー記述の追加根拠（任意）
        stop_loss_atr_jpy: ATR トレーリングストップ価格（任意）
        code_commit: 計算時の git commit short hash（任意）
        claude_ranking: Claude による Stage 2 総合判定結果
            （:meth:`RankingResult.model_dump(mode="json")` の dict）。
            Phase 5.4.3 追加。Anthropic API キー不在時 / Sonnet 縮退時は
            ``None``。Decision Log に格納されることで「なぜ買ったか」を
            Claude 判定まで含めて完全再現可能（CLAUDE.md §9.8.3）。
    """

    ticker: str
    shares: Decimal
    price_jpy: Decimal
    trigger: ScreenerTrigger
    kelly_params: KellyParams
    portfolio_value_jpy: Decimal
    additional_rationale: str = ""
    stop_loss_atr_jpy: Decimal | None = None
    code_commit: str | None = None
    claude_ranking: ClaudeRankingDict | None = None


def submit_buy_order(
    request: BuyOrderRequest,
    *,
    log_dir: Path,
) -> Path:
    """BUY 注文を Decision Log に追記。Kelly + trigger + rationale を自動付与。

    手順:
        1. :func:`strategies.kelly.build_kelly_recommendation` で Kelly 計算過程を
           dict 化（Provenance §9.8.3）
        2. ScreenerTrigger を JSON シリアライズ可能な dict に整形
        3. composite_score + preset + 追加根拠 から rationale を組み立て
        4. :func:`portfolio.decision_log.append_decision` に委譲して JSONL 書き込み

    Args:
        request: BUY 注文リクエスト
        log_dir: Decision Log ディレクトリ（``settings.decision_log_dir``）

    Returns:
        書き込み先 JSONL パス（``{log_dir}/{YYYY-MM}.jsonl``）。
    """
    kelly_rec = build_kelly_recommendation(
        params=request.kelly_params,
        portfolio_value_jpy=request.portfolio_value_jpy,
    )

    trigger_dict = {
        "skill": request.trigger.skill,
        "preset": request.trigger.preset,
        "composite_score": str(request.trigger.composite_score),
        "sub_scores": {
            k: str(v) for k, v in request.trigger.sub_scores.items()
        },
        "screener_run_at": request.trigger.screener_run_at,
    }

    rationale = _build_rationale(
        ticker=request.ticker,
        composite_score=request.trigger.composite_score,
        preset=request.trigger.preset,
        additional=request.additional_rationale,
    )

    return append_decision(
        log_dir=log_dir,
        action="BUY",
        ticker=request.ticker,
        shares=request.shares,
        price_jpy=request.price_jpy,
        rationale=rationale,
        trigger=trigger_dict,
        stop_loss_atr_jpy=request.stop_loss_atr_jpy,
        code_commit=request.code_commit,
        kelly_recommendation=kelly_rec,
        claude_ranking=request.claude_ranking,
    )


def _build_rationale(
    *,
    ticker: str,
    composite_score: Decimal,
    preset: str,
    additional: str,
) -> str:
    """rationale 自動生成。Composite Score + preset を必須項目として埋め込む。"""
    base = (
        f"{ticker} Composite Score {composite_score}/100 "
        f"（{preset} プリセット）"
    )
    additional_stripped = additional.strip()
    if additional_stripped:
        return f"{base}。追加根拠: {additional_stripped}"
    return base
