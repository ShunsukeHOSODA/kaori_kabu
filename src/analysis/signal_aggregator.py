"""Phase 5.3 シグナル束統合層。

6 skill (Composite Score / Magic Formula / sentiment / Polymarket /
13F diff / Regime) の出力を Stage 2 Sonnet 判定の入力
:class:`analysis.ranking_judge.RankingSignalBundle` に統合する
オーケストレーション関数群。

本ファイルが提供する API:
    :func:`build_regime_signals`
        既存 :func:`analysis.regime.detect_regime_with_provenance` を
        ラップし、``RankingSignalBundle`` の ``regime`` /
        ``regime_state_probs`` フィールドへ流し込める辞書を返す
        アダプタ (Phase 5.3.0 Agent C)。設計 spec: design.md L1062-1068。
    :func:`build_signal_bundle`
        単一銘柄の 6 skill 出力を 1 つの ``RankingSignalBundle`` に
        統合する純粋関数 (Phase 5.3.1)。design.md L1140-1206。
    :func:`aggregate_signals_for_universe`
        ユニバース (複数銘柄) について ``build_signal_bundle`` を
        繰り返し呼び、``list[RankingSignalBundle]`` を返す
        (Phase 5.3.1)。design.md L1188-1206。

設計判断:
    - 既存 ``RegimeResult`` には state-level の確率分布 (predict_proba 相当)
      が含まれないため、``current_regime`` ラベルに one-hot 近似
      (該当ラベル = ``Decimal("1.0")``、他 = ``Decimal("0.0")``) を割り当てる。
      後段で ``detect_regime`` 側に predict_proba が追加されたら本関数も
      同時に更新する想定。
    - キャッシュは ``detect_regime_with_provenance`` 自身の挙動に委ねる
      （本関数で独自 cache を重ねると CLAUDE.md §9.2 の TTL 二重管理に
      なるため）。
    - PRD §FR5 「多段縮退」の精神に従い、上流 HMM が例外を投げた場合は
      Choppy + 均等 1/3 配分の縮退結果を返す（spec docstring 明示要件）。

CLAUDE.md §9.1 数値規約:
    確率値は ``Decimal(str(prob))`` 形式で生成し、float 経由の
    丸め誤差を回避する。

CLAUDE.md §9.8 Provenance 規約:
    本アダプタは戻り値 dict に provenance metadata を含めない。
    呼び出し側 (Task 5.3.1 build_signal_bundle) で
    ``RankingSignalBundle.fetched_at`` 等の上位メタデータと共に
    Provenance を組み立てる想定。
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Final, Literal

import pandas as pd

from analysis.ranking_judge import RankingSignalBundle
from analysis.regime import detect_regime_with_provenance

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

_DEFAULT_CACHE_TTL_SEC: Final[int] = 24 * 3600
"""EOD データ既定キャッシュ TTL（CLAUDE.md §9.2 規約準拠の 24h）。

現状は :func:`detect_regime_with_provenance` 側のキャッシュ層へ署名整合の
ために引数を渡す目的のみで保持。将来 ``detect_regime_with_provenance`` に
``cache_ttl_sec`` 引数が追加された際のシグネチャ前方互換性を確保する。
"""

_REGIME_LABELS: Final[tuple[str, str, str]] = ("Bull", "Choppy", "Crisis")
"""HMM の解釈ラベル順序。``analysis.regime.ALL_LABELS`` と一致。"""

_FALLBACK_REGIME: Final[str] = "Choppy"
"""HMM 失敗時に返す縮退レジーム（最も保守的な中立解釈）。"""

# 均等配分は厳密に 1.00 へ合わせるため 0.33 / 0.34 / 0.33 とする。
_FALLBACK_PROBS: Final[dict[str, Decimal]] = {
    "Bull": Decimal("0.33"),
    "Choppy": Decimal("0.34"),
    "Crisis": Decimal("0.33"),
}


# ---------------------------------------------------------------------------
# 内部ヘルパー
# ---------------------------------------------------------------------------


def _extract_price_series(
    universe_prices: pd.Series | pd.DataFrame,
) -> pd.Series:
    """``universe_prices`` を ``pd.Series`` に正規化する。

    DataFrame の場合:
        - "close" カラムがあればそれを採用
        - なければ最初の列を採用
    既に Series ならそのまま返す。
    """
    if isinstance(universe_prices, pd.DataFrame):
        if "close" in universe_prices.columns:
            return universe_prices["close"]
        return universe_prices.iloc[:, 0]
    return universe_prices


def _onehot_state_probs(regime_label: str) -> dict[str, Decimal]:
    """``regime_label`` を one-hot Decimal 確率辞書に変換する。

    既存 ``RegimeResult`` が state 確率を保持しないことへの暫定対応。
    """
    return {
        label: Decimal("1.0") if label == regime_label else Decimal("0.0")
        for label in _REGIME_LABELS
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_regime_signals(
    *,
    universe_prices: pd.Series | pd.DataFrame,
    vix_series: pd.Series | None = None,
    cache_ttl_sec: int = _DEFAULT_CACHE_TTL_SEC,
) -> dict[str, object]:
    """既存 ``detect_regime_with_provenance`` をラップし
    :class:`RankingSignalBundle` 互換の dict を返すアダプタ。

    Args:
        universe_prices: ユニバース代表価格系列（S&P 500 等）。
            ``pd.Series`` または ``pd.DataFrame``（DataFrame の場合は
            ``"close"`` 列があればそれを、無ければ最初の列を使用）。
        vix_series: VIX 系列。``None`` の場合は
            :func:`analysis.regime.compute_realized_volatility` で
            realized vol 代理を計算して下流に渡す。
        cache_ttl_sec: キャッシュ TTL 秒数（既定 24h）。現状は引数として
            受理するのみ（``detect_regime_with_provenance`` 側で未使用）。

    Returns:
        ``{
            "regime": "Bull" | "Choppy" | "Crisis",
            "state_probs": {"Bull": Decimal, "Choppy": Decimal, "Crisis": Decimal}
        }``

    Notes:
        - HMM 計算失敗時（``Exception`` 全般）は PRD §FR5 多段縮退として
          ``{"regime": "Choppy", "state_probs": 均等配分}`` を返す。
        - state_probs は現状 one-hot 近似。``detect_regime`` に
          ``predict_proba`` 拡張が来たら同時更新する。
    """
    _ = cache_ttl_sec  # 現状未使用、将来の TTL 引数前方互換のため保持

    try:
        prices = _extract_price_series(universe_prices)

        # vix_series が None の場合、:func:`compute_realized_volatility` で
        # realized vol 代理を事前計算して渡す（detect_regime_with_provenance は
        # vix 引数を必須としているため）。
        if vix_series is None:
            from analysis.regime import compute_realized_volatility

            vix_input = compute_realized_volatility(prices)
            vix_source: str | None = "realized_vol_proxy_v1"
        else:
            vix_input = vix_series
            vix_source = None

        result = detect_regime_with_provenance(
            prices,
            vix_input,
            vix_source=vix_source,
        )
        regime_label = str(result.current_regime)
        return {
            "regime": regime_label,
            "state_probs": _onehot_state_probs(regime_label),
        }
    except Exception:  # noqa: BLE001 — PRD §FR5 多段縮退規約
        # HMM 失敗時の縮退。原因例外は呼び出し側のロギング層で扱う想定。
        return {
            "regime": _FALLBACK_REGIME,
            "state_probs": dict(_FALLBACK_PROBS),
        }


# ---------------------------------------------------------------------------
# Phase 5.3.1: 6 skill 統合 build_signal_bundle
# ---------------------------------------------------------------------------


def build_signal_bundle(
    *,
    ticker: str,
    exchange: Literal["US", "JP"],
    sector: str | None = None,
    composite_result: Any,
    mf_result: Any | None,
    sentiment_result: Any,
    momentum_1m: Decimal | None = None,
    momentum_12m: Decimal | None = None,
    polymarket_macro: dict[str, Decimal] | None = None,
    fund_holdings_delta: dict[str, dict[str, object]] | None = None,
    regime_signals: dict[str, object] | None = None,
) -> RankingSignalBundle:
    """6 skill の出力を 1 つの :class:`RankingSignalBundle` に統合する。

    呼び出し側で失敗した skill は空 dict / None でフォールバック済みである前提。
    PRD §FR5 多段縮退の上位フォーマット層 (design.md L1147-1177)。

    Args:
        ticker: 銘柄ティッカー (例 ``"AAPL"`` / ``"7203.T"``)。
            ``RankingSignalBundle.__post_init__`` で文字種検証される。
        exchange: 取引所 (``"US"`` or ``"JP"``)。
        sector: 業種 (None 可)。
        composite_result: Composite Score 計算結果 (``composite_score`` /
            ``sub_scores`` / ``preset_name`` 属性を持つオブジェクト)。
        mf_result: Magic Formula 結果 (``score`` / ``roc_pct`` /
            ``earnings_yield_pct`` 属性を持つ)。失敗時は ``None``。
        sentiment_result: ニュースセンチメント結果 (``sentiment_score`` /
            ``confidence`` / ``key_themes`` 属性を持つ)。
        momentum_1m: 1ヶ月モメンタム (Decimal、None 可)。
        momentum_12m: 12ヶ月モメンタム (Decimal、None 可)。
        polymarket_macro: Polymarket 確率辞書 (None なら空 dict 扱い)。
        fund_holdings_delta: 13F QoQ 差分辞書 (None なら空 dict 扱い)。
        regime_signals: :func:`build_regime_signals` の戻り値。``None`` の
            ときは ``"Choppy"`` + 空 ``state_probs`` を縮退デフォルトとして採用。

    Returns:
        :class:`RankingSignalBundle` (frozen dataclass、即座に Stage 2
        Sonnet 判定に渡せる形)。
    """
    regime_label: str = "Choppy"
    state_probs: dict[str, Decimal] = {}
    if regime_signals is not None:
        regime_raw = regime_signals.get("regime", "Choppy")
        if regime_raw in ("Bull", "Choppy", "Crisis"):
            regime_label = str(regime_raw)
        raw_probs = regime_signals.get("state_probs", {})
        if isinstance(raw_probs, dict):
            state_probs = raw_probs

    return RankingSignalBundle(
        ticker=ticker,
        exchange=exchange,
        sector=sector,
        composite_score=float(composite_result.composite_score),
        sub_scores={k: float(v) for k, v in composite_result.sub_scores.items()},
        composite_preset=str(composite_result.preset_name),
        magic_formula_score=float(mf_result.score) if mf_result is not None else None,
        roc_pct=Decimal(str(mf_result.roc_pct)) if mf_result is not None else None,
        earnings_yield_pct=(
            Decimal(str(mf_result.earnings_yield_pct))
            if mf_result is not None
            else None
        ),
        momentum_1m=momentum_1m,
        momentum_12m=momentum_12m,
        sentiment_score=Decimal(str(sentiment_result.sentiment_score)),
        sentiment_confidence=Decimal(str(sentiment_result.confidence)),
        sentiment_themes=tuple(sentiment_result.key_themes),
        polymarket_macro=polymarket_macro or {},
        fund_holdings_delta=fund_holdings_delta or {},
        regime=regime_label,  # type: ignore[arg-type]
        regime_state_probs=state_probs,
        fetched_at=datetime.now(UTC),
    )


def aggregate_signals_for_universe(
    tickers: list[str],
    *,
    exchange: Literal["US", "JP"],
    composite_results: dict[str, Any],
    mf_results: dict[str, Any],
    sentiment_results: dict[str, Any],
    momentum_results: dict[str, dict[str, Decimal]],
    polymarket_macro: dict[str, Decimal],
    fund_holdings_delta_by_fund: dict[str, dict[str, object]],
    regime_signals: dict[str, object],
    sector_by_ticker: dict[str, str | None] | None = None,
) -> list[RankingSignalBundle]:
    """ユニバース (複数銘柄) を :class:`RankingSignalBundle` のリストに変換する。

    ``composite_results`` または ``sentiment_results`` に存在しない ticker は
    skip (上流データの一貫性は呼び出し側の責務)。

    Args:
        tickers: 対象ティッカーリスト。順序保持。
        exchange: 取引所 (``"US"`` or ``"JP"``)。
        composite_results: ``{ticker: composite_result}``
        mf_results: ``{ticker: mf_result}`` (欠損は None 扱い)
        sentiment_results: ``{ticker: sentiment_result}`` (必須)
        momentum_results: ``{ticker: {"1m": Decimal, "12m": Decimal}}``
        polymarket_macro: マクロ確率 (全ユニバース共通)
        fund_holdings_delta_by_fund: 13F 差分 (全ユニバース共通、
            ticker per ファンドビューに事前変換済みの想定)
        regime_signals: :func:`build_regime_signals` の戻り値 (全ユニバース共通)
        sector_by_ticker: ティッカー → セクター名のマップ (省略時 None)

    Returns:
        :class:`RankingSignalBundle` のリスト。入力 ``tickers`` の順序を維持。
    """
    sector_map = sector_by_ticker or {}
    bundles: list[RankingSignalBundle] = []
    for ticker in tickers:
        if ticker not in composite_results:
            continue
        if ticker not in sentiment_results:
            continue
        ticker_momentum = momentum_results.get(ticker, {})
        bundles.append(
            build_signal_bundle(
                ticker=ticker,
                exchange=exchange,
                sector=sector_map.get(ticker),
                composite_result=composite_results[ticker],
                mf_result=mf_results.get(ticker),
                sentiment_result=sentiment_results[ticker],
                momentum_1m=ticker_momentum.get("1m"),
                momentum_12m=ticker_momentum.get("12m"),
                polymarket_macro=polymarket_macro,
                fund_holdings_delta=fund_holdings_delta_by_fund,
                regime_signals=regime_signals,
            )
        )
    return bundles
