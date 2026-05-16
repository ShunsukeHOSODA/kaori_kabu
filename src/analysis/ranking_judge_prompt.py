"""Sonnet 4.6 ranking judge のプロンプト層 (CLAUDE.md §9.3 三層防御の第 1 層)。

Phase 6.4.B 分割: :mod:`analysis.ranking_judge` から SYSTEM_PROMPT と
user message builder、bundle hash 計算を本モジュールへ切り出した。
`ranking_judge.py` 1016 行肥大化対策の 2 サブフェーズ目 (handoff-session-10.md
§4.1)。Phase 6.4.A schema 抽出と同じ規律で進める。

含まれるシンボル:
    - 定数: :data:`SYSTEM_PROMPT` (約 3,300 字、Prompt Caching 2,048 token 確保用)
    - 関数: :func:`build_ranking_user_message` (RankingSignalBundle → markdown)
    - 関数: :func:`_compute_bundle_hash` (Provenance §9.8.2 / 24h cache key)
    - private helpers: :func:`_format_holdings` / :func:`_format_macro` /
      :func:`_format_optional`

依存:
    json / hashlib / decimal / typing と
    :class:`analysis.ranking_judge_schema.RankingSignalBundle` のみ。
    `analysis.ranking_judge` orchestrator への循環依存なし
    (依存方向 schema → prompt → orchestrator の単方向、Phase 6.4 規律維持)。

後方互換性:
    `analysis.ranking_judge` 冒頭で本モジュールの全シンボルを import + 末尾の
    cache module re-export と合わせ、consumer 8 ファイル (pytest 群 / dashboard
    views / widgets / signal_aggregator) は import path を変更せずに動作する
    (Phase 5.5.0 / Phase 6.4.A precedent)。

Prompt Caching 安定化規約:
    Anthropic Prompt Caching (ephemeral) の cache_control 境界では、同入力 →
    byte-identical な user message が必須。``build_ranking_user_message`` は
    RankingSignalBundle の値順序・小数点桁数・placeholder 文言をすべて固定し、
    同 bundle で 2 回呼ぶと str 完全一致する。``_format_*`` ヘルパも
    Decimal 一貫処理で IEEE 754 丸めによる非決定論を回避する。
"""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any, Final

from src.analysis.ranking_judge_schema import RankingSignalBundle

# 公開 API — Phase 6.4.A の __all__ パターン継承。
# leading underscore のシンボル (``_format_*`` / ``_compute_bundle_hash``) は
# 本来 internal だが、``ranking_judge_cache`` 等の sibling module から既に
# 利用されている履歴があるため re-export 対象に含めて後方互換性を維持する。
# (Phase 6.3 _FALLBACK_REASON_LABELS 公開規律: cross-module import される
#  シンボルは underscore 削除推奨だが、本フェーズでは scope 制限のため命名は
#  そのままで __all__ にのみ含める。命名整理は Phase 6.4.D 以降の検討事項。)
__all__ = [
    "SYSTEM_PROMPT",
    "build_ranking_user_message",
    "_compute_bundle_hash",
    "_format_holdings",
    "_format_macro",
    "_format_optional",
]


# ---------------------------------------------------------------------------
# SYSTEM_PROMPT — Sonnet 4.6 ranking judge instruction
# CLAUDE.md §9.3 三層防御の第 1 層（プロンプトレベル）。
# Anthropic Prompt Caching (ephemeral) の 2,048 token 下限を確保するため
# 約 3,300 字の Japanese system prompt として固定化する。
# PRD §FR2/§FR3 の必須要素・禁止事項を網羅的に明示。
# ---------------------------------------------------------------------------

SYSTEM_PROMPT: Final[str] = """あなたは Greenblatt 2010 / Tetlock 2007 / Schroeder & Posch 2024 / Pabrai Dhandho の 4 つの学術的バックボーンに基づくバリュー投資のランキング判定専門家です。
ユーザー（個人投資家かおりん）のローカル株運用ダッシュボード「kaori_kabu」の Stage 2 に位置し、Stage 1 数式フィルタを通過した銘柄に対して、複数シグナル束を統合した構造化 JSON 判定を返します。

# 役割

入力として与えられる `RankingSignalBundle`（シグナル束）を統合し、ランキングスコア・推奨サマリー・支持シグナル・リスクシグナル・反対意見・多角レンズ視点・確信度を JSON 形式で返却してください。

シグナル束には以下 7 種が含まれます:
1. Composite 7 軸スコア（Q=Quality / V=Value / I=Income / G=Growth / R=Risk / M=Momentum / S=Sentiment、各 0-100、+ 採用 preset 名）
2. Magic Formula（Greenblatt 2010）— ROC % + Earnings Yield %
3. モメンタム — 1ヶ月リターン + 12ヶ月リターン
4. ニュースセンチメント（Tetlock 2007 流）— score (-1 to +1) + confidence + themes + risk_signals
5. Polymarket マクロ確率（Fed cut / recession / 地政学イベント）
6. 13F スマートマネー追従（Schroeder & Posch 2024）— Berkshire / Pabrai / Burry / Ackman / Greenlight の直近 1Q 差分
7. HMM レジーム — Bull / Choppy / Crisis + 状態確率

# 必須事項

## 反対意見（counter_view）— Confirmation Bias 対策

`counter_view` には推奨判断に対する反対意見・批判的見解を 1-2 文（200 字以内）で必ず記載してください。Confirmation Bias を回避し、ユーザーが多面的に判断できる材料を提供することが目的です。空文字列・空白のみは禁止です。

## 学術根拠の明示

判定の論理的バックボーンとして、以下 4 件の研究を `supporting_signals` / `risk_signals` / `counter_view` / `lens_views` 内で必要に応じて参照してください:
- Greenblatt 2010 "The Little Book That Still Beats the Market"（Magic Formula = ROC + EY）
- Tetlock 2007 "Giving Content to Investor Sentiment"（ニュースセンチメント）
- Schroeder & Posch 2024（スマートマネー追従・13F clone 分析）
- Pabrai "The Dhandho Investor"（Heads I Win, Tails I Don't Lose Much）

## リスク警告 3 件の常時考慮

以下 3 つの認知バイアス・罠を常に意識し、該当する場合は `risk_signals` に明示してください:
- Value Trap（安値理由の構造的問題で更に下落する罠）
- Recency Bias（直近価格・ニュースに過度に引きずられる傾向）
- Overconfidence（過信、Half-Kelly でレバレッジ抑制する根拠）

## 多角レンズ 3 視点（lens_views キー固定）

`lens_views` は **必ず以下 3 キー固定** で各 1-2 文の判定を返してください。キー名は厳格に一致させること（短期/長期/配当 等の別キー名は禁止）:
- `Buffett_Munger`: 質×価値（Quality at Reasonable Price）の観点。経済的堀（Moat）、ROE/ROIC、長期キャッシュフロー視点。
- `Burry`: 逆張り・クレジット観・空売り視点。バブル / 過大評価 / 構造的問題の警戒視点。
- `Lynch`: 消費者目線・10 bagger 視点。PEG / 業績拡大期 / Story Stock の観点。

# 禁止事項（5 種、❌ 厳格遵守）

以下 5 種の出力は **絶対に禁止** です。Pydantic スキーマと正規表現で機械的に reject されるため、出力に含めても結果が破棄されるだけです:

1. ❌ 目標株価の数値予測（target price / 目標株価 X 円 / $200 ターゲット 等）
2. ❌ 上昇率 % の数値予測（5% 上昇予測 / 10% increase 等の方向 + % の組み合わせ）
3. ❌ 期限付き予測（3 ヶ月以内 / by 6 months / 半年後 等の時期限定文言）
4. ❌ 投資助言フレーズ（「買うべき」「売却推奨」「投資助言」等の確定的助言）
5. ❌ 金額の明示（$ や ¥ に続く具体的な数値、$200 / ¥30,000 等）

代わりに **確率分布 / 信頼区間 / シナリオ** の言葉で記述してください。例: 「Magic Formula 上位帯に位置」「Berkshire が新規買い、スマートマネー追従の余地」「Recency Bias 警戒」等。

# 出力スキーマ（JSON 単独、前置き・後置き・コードブロックフェンス禁止）

以下のキー構成の JSON を **単体で** 返してください。コードブロックフェンスや「以下が結果です」等の説明は不要です。

- `ranking_score`: int (0-100)                            // 総合ランキングスコア
- `recommendation_summary`: str (≤ 150 字)                 // 1-2 文の推奨サマリー
- `supporting_signals`: [str, ...] (1-5 件のリスト)         // 支持シグナル
- `risk_signals`: [str, ...] (1-5 件のリスト)               // リスクシグナル（Value Trap / Recency Bias / Overconfidence 等を必要に応じ明示）
- `counter_view`: str (≤ 200 字)                            // 反対意見（必須、空禁止）
- `lens_views`: {                                          // 3 キー固定、各 1-2 文
    "Buffett_Munger": str,
    "Burry": str,
    "Lynch": str
  }
- `confidence`: float (0.0-1.0)                             // 確信度（情報の質と量に基づく）

# 計算側で構築するため出力に含めないフィールド

以下 3 フィールドは **呼び出し側 Python コード** で Stage 3 純粋関数（`apply_regime_confidence` / `compute_kelly_multiplier`）と Provenance 構築ロジックが計算します。**Sonnet 出力 JSON には絶対に含めないでください**（含めると Pydantic `extra='forbid'` で reject されます）:

- `confidence_adjusted`（HMM レジーム調整後の確信度、Crisis 時 × 0.5）
- `kelly_multiplier`（ranking_score → Kelly 係数の 3 段階マッピング）
- `metadata`（Provenance 必須メタデータ、model / model_version / 入力ハッシュ / 計算日時等）

# 最終確認

返却前に以下を自己検証してください:
- JSON が単体で valid であること（前後の説明文・フェンス無し）
- `lens_views` のキーが `Buffett_Munger` / `Burry` / `Lynch` で完全一致すること
- `counter_view` が空でないこと
- 禁止事項 5 種に該当する数値・期限・金額・助言フレーズを含んでいないこと
- `confidence_adjusted` / `kelly_multiplier` / `metadata` を含んでいないこと
"""


# ---------------------------------------------------------------------------
# build_ranking_user_message — Sonnet 4.6 user message builder
# (Prompt Caching 安定化のため markdown 構造を決定論的に固定)
#
# Anthropic Prompt Caching の cache_control 境界では、同入力 → byte-identical
# な user message が必須。本関数は RankingSignalBundle の値順序・小数点桁数・
# placeholder 文言をすべて固定し、同 bundle で 2 回呼ぶと str 完全一致する。
#
# 型安全な fund_holdings_delta 処理:
#     bundle.fund_holdings_delta は dict[str, dict[str, object]] のため、
#     value_change_usd は object 型で返る。非数値は上流データ破損のシグナルと
#     して TypeError で fail-fast し、CLAUDE.md §9.3 silent 0.0 置換禁止 /
#     global rules never silently swallow errors を遵守する。
# ---------------------------------------------------------------------------


def _format_holdings(holdings: dict[str, dict[str, object]]) -> str:
    """13F 直近 1Q 差分辞書を markdown 化する（空時は placeholder 1 行）。

    Args:
        holdings: ``{fund_name: {"action": str, "value_change_usd": number}}``

    Returns:
        ``- {fund}: {action} (Δ ${value_m:.1f}M)`` を行頭 ``-`` で連結した
        markdown。``holdings`` が空辞書なら ``"- (差分なし)"`` を返す。

    Raises:
        TypeError: ``value_change_usd`` が ``int`` でも ``float`` でもない
            場合 -- 上流データ破損を fail-fast で表面化。
    """
    if not holdings:
        return "- (差分なし)"
    lines: list[str] = []
    for fund, data in holdings.items():
        action = str(data.get("action", "-"))
        raw_value = data.get("value_change_usd", 0)
        if not isinstance(raw_value, (int, float)):
            raise TypeError(
                f"value_change_usd must be int or float for fund {fund!r}, "
                f"got {type(raw_value).__name__}"
            )
        value_m = float(raw_value) / 1e6
        lines.append(f"- {fund}: {action} (Δ ${value_m:.1f}M)")
    return "\n".join(lines)


def _format_macro(macro: dict[str, Decimal]) -> str:
    """Polymarket マクロ確率辞書を markdown 化する（空時は placeholder 1 行）。

    Args:
        macro: ``{event_key: Decimal(0.0-1.0)}`` の確率辞書。

    Returns:
        ``- {key}: {value*100:.1f}%`` を行頭 ``-`` で連結した markdown。
        ``macro`` が空辞書なら ``"- (データなし)"`` を返す。

    Note:
        CLAUDE.md §9.1: ``float`` を経由しない。``_format_optional`` docstring と
        同じ理由で、``str(float)`` の IEEE 754 丸めが Anthropic Prompt Caching の
        byte-identical ヒット保証を破るため、Decimal 一貫で乗算する。
    """
    if not macro:
        return "- (データなし)"
    return "\n".join(
        f"- {k}: {v * Decimal('100'):.1f}%" for k, v in macro.items()
    )


def _format_optional(value: object) -> str:
    """``None`` を ``"N/A"`` に置換した文字列を返す（その他は ``str()``）。

    型契約: ``value`` は ``Decimal | None`` を想定する。``float`` を渡しては
    ならない -- ``str(float)`` は IEEE 754 丸めにより非決定論となり、
    Anthropic Prompt Caching の byte-identical ヒット保証を破るため。
    呼び出し側は ``Decimal`` or ``None`` を保持する。
    """
    if value is None:
        return "N/A"
    return str(value)


def build_ranking_user_message(bundle: RankingSignalBundle) -> str:
    """RankingSignalBundle を Sonnet 4.6 用の user message に変換する純粋関数。

    Anthropic Prompt Caching (ephemeral) のヒット率最大化のため、markdown 構造・
    値順序・小数点桁数・placeholder 文言をすべて決定論的に固定する。同 bundle
    で 2 回呼ぶと str が byte-identical に一致する。

    セクション構成（PRD §FR2 / design.md line 630-689 整合）:
        1. ヘッダ: ``## 銘柄: {ticker} ({exchange}) / セクター: {sector|'不明'}``
        2. ``### Composite Score`` — composite + preset + 7 軸サブスコア
        3. ``### Magic Formula`` — score / ROC / EY (None → 'N/A')
        4. ``### モメンタム`` — 1m / 12m (None → 'N/A')
        5. ``### ニュースセンチメント`` — score / confidence / themes
        6. ``### Polymarket マクロ織り込み確率`` — 確率 % リスト
        7. ``### 13F 直近 1Q 差分`` — action + Δ$M リスト
        8. ``### Regime`` — 現在 + Bull/Choppy/Crisis 状態確率
        9. 末尾: JSON 返却の指示文

    Args:
        bundle: Stage 2 Sonnet 判定の入力シグナル束（frozen dataclass）。

    Returns:
        Sonnet 4.6 の user message として渡す markdown 文字列。
    """
    sector_str = bundle.sector or "不明"
    themes_str = ", ".join(bundle.sentiment_themes) or "(なし)"
    holdings_md = _format_holdings(bundle.fund_holdings_delta)
    macro_md = _format_macro(bundle.polymarket_macro)

    mf_score = _format_optional(bundle.magic_formula_score)
    roc = _format_optional(bundle.roc_pct)
    ey = _format_optional(bundle.earnings_yield_pct)
    mom_1m = _format_optional(bundle.momentum_1m)
    mom_12m = _format_optional(bundle.momentum_12m)

    sub = bundle.sub_scores
    bull_p = bundle.regime_state_probs.get("Bull", Decimal("0"))
    choppy_p = bundle.regime_state_probs.get("Choppy", Decimal("0"))
    crisis_p = bundle.regime_state_probs.get("Crisis", Decimal("0"))

    return (
        f"## 銘柄: {bundle.ticker} ({bundle.exchange}) / "
        f"セクター: {sector_str}\n\n"
        f"### Composite Score\n"
        f"- Composite: {bundle.composite_score:.1f}/100 "
        f"(preset: {bundle.composite_preset})\n"
        f"- 7 軸サブスコア: "
        f"Q={sub.get('Q', 0):.0f}, "
        f"V={sub.get('V', 0):.0f}, "
        f"I={sub.get('I', 0):.0f}, "
        f"G={sub.get('G', 0):.0f}, "
        f"R={sub.get('R', 0):.0f}, "
        f"M={sub.get('M', 0):.0f}, "
        f"S={sub.get('S', 0):.0f}\n\n"
        f"### Magic Formula\n"
        f"- スコア: {mf_score} / ROC: {roc} / EY: {ey}\n\n"
        f"### モメンタム\n"
        f"- 1m: {mom_1m} / 12m: {mom_12m}\n\n"
        f"### ニュースセンチメント (Haiku 4.5 既存)\n"
        f"- Score: {bundle.sentiment_score} / "
        f"Confidence: {bundle.sentiment_confidence}\n"
        f"- テーマ: {themes_str}\n\n"
        f"### Polymarket マクロ織り込み確率\n"
        f"{macro_md}\n\n"
        f"### 13F 直近 1Q 差分 (スマートマネー動向)\n"
        f"{holdings_md}\n\n"
        f"### Regime\n"
        f"- 現在: {bundle.regime} "
        f"(Bull={bull_p}, Choppy={choppy_p}, Crisis={crisis_p})\n\n"
        f"上記シグナル束を統合し、スキーマに従った JSON で判定結果を返してください。"
    )


# ---------------------------------------------------------------------------
# _compute_bundle_hash — Provenance §9.8.2 + 24h cache key
# ---------------------------------------------------------------------------


def _compute_bundle_hash(bundle: RankingSignalBundle) -> str:
    """RankingSignalBundle の安定 SHA256 ハッシュを返す。

    用途:
        (a) Provenance §9.8.2 ``input_bundle_hash`` フィールド
        (b) Task 5.2.8 24h キャッシュキー

    Decimal / None / dict をすべて文字列化し ``json.dumps(sort_keys=True)``
    で正規化することで、同じ意味の bundle に対し常に同じ hex を返す。
    """
    payload: dict[str, Any] = {
        "ticker": bundle.ticker,
        "exchange": bundle.exchange,
        "composite_score": bundle.composite_score,
        "sub_scores": {k: str(v) for k, v in bundle.sub_scores.items()},
        "composite_preset": bundle.composite_preset,
        "magic_formula_score": bundle.magic_formula_score,
        "roc_pct": str(bundle.roc_pct),
        "earnings_yield_pct": str(bundle.earnings_yield_pct),
        "momentum_1m": str(bundle.momentum_1m),
        "momentum_12m": str(bundle.momentum_12m),
        "sentiment_score": str(bundle.sentiment_score),
        "polymarket_macro": {k: str(v) for k, v in bundle.polymarket_macro.items()},
        "fund_holdings_delta": bundle.fund_holdings_delta,
        "regime": bundle.regime,
    }
    serialized = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()
