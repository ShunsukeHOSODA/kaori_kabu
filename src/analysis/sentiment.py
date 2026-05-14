"""ニュースセンチメント分析（Claude Haiku 4.5）— CLAUDE.md §9.8 準拠。

学術根拠:
    Tetlock 2007 "Giving Content to Investor Sentiment"
    Loughran-McDonald 2011 (金融特化センチメント辞書)

設計:
    入力 = ニュース DataFrame（NewsClient.fetch_* または apply_lenses の出力、
    あるいは MarketContext を pd.concat で 1 本化したもの）
    出力 = SentimentResult（score / confidence / themes / risk_signals /
    summary + Provenance metadata）

Claude Haiku 4.5 を選んだ理由:
    - 軽量タスク（ニュース要約 + センチメント定量化）に十分
    - Sonnet 比 3 倍のコスト効率
    - プロンプトキャッシュ併用でさらに削減
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pandas as pd

from analysis._common import extract_json
from analysis._provenance import get_current_git_commit

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

DEFAULT_MODEL: str = "claude-haiku-4-5"
DEFAULT_MODEL_VERSION: str = "claude-haiku-4-5-20251001"
DEFAULT_MAX_TOKENS: int = 2048

SYSTEM_PROMPT: str = """あなたは Tetlock 2007 流のセンチメント分析専門家です。
ニュース記事から銘柄に対する投資家センチメントを定量的に評価し、
構造化 JSON で返却してください。

返却 JSON のスキーマ:
{
  "sentiment_score": float,    // -1.0 (極度の悲観) 〜 +1.0 (極度の楽観)
  "confidence": float,          // 0.0 〜 1.0 (情報の質と量に基づく自信度)
  "key_themes": [string, ...],  // 主要テーマ（最大 5 個）
  "risk_signals": [string, ...],// 警戒すべきリスクシグナル
  "summary": string             // 100-200 文字の日本語要約
}

出力は JSON 単独としてください。前置き・後置きの説明文は不要です。
"""


# ---------------------------------------------------------------------------
# データクラス
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SentimentMetadata:
    """センチメント分析結果の出所情報（CLAUDE.md §9.8.2 必須）。"""

    model: str
    model_version: str
    calculation_method: str
    input_news_count: int
    input_period_start: datetime | None
    input_period_end: datetime | None
    calculated_at: datetime
    academic_source: str
    code_commit: str | None = None


@dataclass(frozen=True)
class SentimentResult:
    """センチメント分析の結果。

    Attributes:
        sentiment_score: -1.0〜+1.0 のスコア。負は弱気、正は強気。
        confidence: 0.0〜1.0 の自信度。記事数が少ない、信頼ソースが少ない
            場合は低くなる。
        key_themes: 主要テーマ（複数）
        risk_signals: 警戒すべきリスクシグナル（複数）
        summary: 100-200 文字の日本語要約
        metadata: Provenance 情報
    """

    sentiment_score: Decimal
    confidence: Decimal
    key_themes: tuple[str, ...]
    risk_signals: tuple[str, ...]
    summary: str
    metadata: SentimentMetadata


# ---------------------------------------------------------------------------
# プロンプト構築
# ---------------------------------------------------------------------------


def build_sentiment_user_message(news_df: pd.DataFrame, ticker: str) -> str:
    """ニュース DataFrame から user メッセージを構築。

    記事は ``[YYYY-MM-DD] title\\n  snippet[:300]`` 形式で 1 件 1 ブロック。
    プロンプトキャッシュ最適化のためヘッダー部とボディ部を分離する。
    """
    rows: list[str] = []
    for _, row in news_df.iterrows():
        published = (
            row.get("published_at") if "published_at" in news_df.columns else None
        )
        if published is not None and pd.notna(published):
            try:
                date_str = pd.Timestamp(published).strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                date_str = "—"
        else:
            date_str = "—"
        title = str(row.get("title", "")).strip()
        snippet = str(row.get("snippet", ""))[:300].strip()
        rows.append(f"[{date_str}] {title}\n  {snippet}")

    body = "\n\n".join(rows)
    separator = "-" * 60
    return (
        f"銘柄: {ticker}\n"
        f"記事数: {len(news_df)} 件\n\n"
        f"ニュース:\n{separator}\n"
        f"{body}\n"
        f"{separator}\n\n"
        f"上記ニュースから JSON 形式でセンチメント分析結果を返してください。"
    )


# ---------------------------------------------------------------------------
# メタデータ構築
#
# JSON 抽出は :func:`analysis._common.extract_json`、git commit 取得は
# :func:`analysis._provenance.get_current_git_commit` に集約済み。
# ---------------------------------------------------------------------------


def _build_metadata(
    news_count: int,
    *,
    news_df: pd.DataFrame | None = None,
    model: str = DEFAULT_MODEL,
) -> SentimentMetadata:
    """SentimentMetadata を構築（input 期間を news_df から推定）。"""
    period_start: datetime | None = None
    period_end: datetime | None = None
    if (
        news_df is not None
        and "published_at" in news_df.columns
        and len(news_df) > 0
    ):
        valid = news_df["published_at"].dropna()
        if len(valid) > 0:
            period_start = pd.Timestamp(valid.min()).to_pydatetime()
            period_end = pd.Timestamp(valid.max()).to_pydatetime()

    return SentimentMetadata(
        model=model,
        model_version=DEFAULT_MODEL_VERSION,
        calculation_method="sentiment_v1",
        input_news_count=news_count,
        input_period_start=period_start,
        input_period_end=period_end,
        calculated_at=datetime.now(timezone.utc),
        academic_source=(
            'Tetlock 2007 "Giving Content to Investor Sentiment" + '
            "Loughran-McDonald 2011"
        ),
        code_commit=get_current_git_commit(),
    )


# ---------------------------------------------------------------------------
# 公開 API
# ---------------------------------------------------------------------------


def analyze_sentiment(
    news_df: pd.DataFrame,
    ticker: str,
    *,
    anthropic_client: Any,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> SentimentResult:
    """ニュース DataFrame に対する Claude Haiku センチメント分析。

    空 DataFrame の場合は API を呼ばず、中立 (0.0, 0.0) を返す。

    Args:
        news_df: ニュース DataFrame（NewsClient 出力スキーマ）
        ticker: 銘柄シンボル（プロンプトに埋め込む）
        anthropic_client: ``anthropic.Anthropic`` インスタンス
        model: モデル名（既定 ``claude-haiku-4-5``）
        max_tokens: 出力上限

    Returns:
        :class:`SentimentResult`（Provenance metadata 付き）
    """
    news_count = len(news_df)
    if news_count == 0:
        return SentimentResult(
            sentiment_score=Decimal("0"),
            confidence=Decimal("0"),
            key_themes=(),
            risk_signals=(),
            summary="ニュースなし — 中立判定。",
            metadata=_build_metadata(0, model=model),
        )

    user_msg = build_sentiment_user_message(news_df, ticker)
    response = anthropic_client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    text = response.content[0].text
    parsed = extract_json(text, context="sentiment analysis response")

    return SentimentResult(
        sentiment_score=Decimal(str(parsed.get("sentiment_score", 0))),
        confidence=Decimal(str(parsed.get("confidence", 0))),
        key_themes=tuple(parsed.get("key_themes", [])),
        risk_signals=tuple(parsed.get("risk_signals", [])),
        summary=str(parsed.get("summary", "")),
        metadata=_build_metadata(news_count, news_df=news_df, model=model),
    )
