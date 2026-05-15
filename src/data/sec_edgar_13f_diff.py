"""SEC EDGAR 13F フィリング QoQ 差分抽出（ticker-centric ラッパー）。

design.md L1051-1060 仕様:
    指定 ticker について、tracked_funds の各ファンドの最新 1Q 差分を返す。
    Phase 5.3.0 Stage 2 で ``bundle.fund_holdings_delta`` を構築するため、
    既存の :func:`data.sec_edgar.compute_qoq_diff`（issuer 全体の diff）を
    ticker 単位にスライスして action/value_change_usd dict に変換する。

仕様の中核:
    - 各ファンドについて :meth:`SECEdgarClient.get_13f_history` で
      最新 + 前期の 2 件を取得
    - :func:`compute_qoq_diff` で 5 区分（新規買い / 売却 / 増持 / 減持 / 保持）
      の diff DataFrame を得る
    - ticker → issuer name 部分一致で該当行を抽出し、日本語 action を
      英語ラベル（NEW / INCREASE / DECREASE / EXIT / HOLD）にマッピング
    - 戻り値は ``{fund_name: {"action": str, "value_change_usd": int}}``
      の dict。ticker が無い fund は含めない（空 dict もあり得る）

失敗時の挙動:
    1 ファンドが HTTPError / NotFound / Parse 失敗した場合、警告ログを
    出して当該 fund を skip。他 fund の処理は継続。

CLAUDE.md §9.2 cache TTL = 90 日を踏襲（既存 SECEdgarClient のキャッシュ
機構を再利用、本モジュールでは追加キャッシュを持たない）。
"""

from __future__ import annotations

import logging
from typing import Any, Final

import httpx
import pandas as pd

from .famous_holdings import TICKER_TO_ISSUER_NAME
from .sec_edgar import (
    SECEdgarClient,
    compute_qoq_diff,
    normalize_cik,
)

logger = logging.getLogger(__name__)

# ============================================================
# TRACKED_FUNDS デフォルト（settings.tracked_funds_cik_list と整合）
# ============================================================
#
# settings.tracked_funds_cik のデフォルトは
#   "0001067983,0001173334,0001649339,0001336528,0001079114"
# の 5 件で、これは順に Berkshire / Pabrai / Burry / Ackman / Greenlight。
# CIK の正確性は SEC EDGAR で要確認 — Burry/Ackman/Greenlight は
# 13F 提出主体 (parent company) と一致しない可能性があり、TODO 印を残す。
TRACKED_FUNDS: Final[dict[str, str]] = {
    "Berkshire_Hathaway": "0001067983",  # 確認済 (BERKSHIRE HATHAWAY INC)
    "Pabrai_Funds": "0001173334",         # 確認済 (PABRAI INVESTMENT FUNDS)
    "Burry_Scion": "0001649339",         # TODO: SCION ASSET MANAGEMENT の正 CIK 要確認
    "Ackman_Pershing": "0001336528",     # TODO: PERSHING SQUARE の正 CIK 要確認
    "Greenlight_Capital": "0001079114",  # TODO: GREENLIGHT CAPITAL の正 CIK 要確認
}


# compute_qoq_diff が返す日本語 action → 仕様の英語ラベル
_ACTION_MAPPING: Final[dict[str, str]] = {
    "新規買い": "NEW",
    "増持": "INCREASE",
    "減持": "DECREASE",
    "売却": "EXIT",
    "保持": "HOLD",
}


# ============================================================
# 内部ヘルパー
# ============================================================


def _resolve_ticker_to_issuer_substring(ticker: str) -> str:
    """ticker → SEC 13F の ``name_of_issuer`` 部分一致用キーワード。

    TICKER_TO_ISSUER_NAME に登録があればそれを使う。未登録なら ticker
    自身を大文字化した文字列をフォールバック（例 ``"NVDA"``）。

    Returns:
        大文字部分一致用文字列（例 ``"APPLE"``）。
    """
    issuer_keyword = TICKER_TO_ISSUER_NAME.get(ticker.upper())
    if issuer_keyword:
        return issuer_keyword
    # フォールバック: ticker 自身を大文字で部分一致
    return ticker.upper()


def _find_ticker_row(
    diff_df: pd.DataFrame, ticker: str
) -> pd.Series | None:
    """diff DataFrame から ticker に該当する 1 行を取り出す（issuer 部分一致）。

    複数行ヒットした場合は ``value_current`` が NaN でない先頭行を優先、
    全て NaN なら先頭行（売却 = EXIT 想定）。
    """
    if diff_df.empty:
        return None
    issuer_keyword = _resolve_ticker_to_issuer_substring(ticker)
    mask = (
        diff_df["name_of_issuer"]
        .fillna("")
        .str.upper()
        .str.contains(issuer_keyword, regex=False, na=False)
    )
    matched = diff_df[mask]
    if matched.empty:
        return None
    # value_current が NaN でない行を優先（NEW / INCREASE / DECREASE / HOLD）
    non_nan = matched[matched["value_current"].notna()]
    if not non_nan.empty:
        return non_nan.iloc[0]
    return matched.iloc[0]


def _row_to_delta(row: pd.Series) -> dict[str, Any]:
    """diff DataFrame 1 行 → ``{"action": str, "value_change_usd": int}``。

    日本語 action を英語ラベルへマッピング、``change_usd`` を ``int`` に
    変換（NaN → 0、ただし NaN は通常ない）。
    """
    jp_action = str(row["action"])
    en_action = _ACTION_MAPPING.get(jp_action, "HOLD")
    change_raw = row.get("change_usd", 0)
    if change_raw is None or (
        isinstance(change_raw, float) and pd.isna(change_raw)
    ):
        change_int = 0
    else:
        change_int = int(change_raw)
    return {"action": en_action, "value_change_usd": change_int}


def _ttl_days_to_seconds(days: int) -> int:
    return max(1, int(days)) * 86_400


# ============================================================
# 公開 API
# ============================================================


def extract_holdings_delta(
    ticker: str,
    *,
    sec_client: SECEdgarClient,
    tracked_funds: dict[str, str] | None = None,
    cache_ttl_days: int = 90,
) -> dict[str, dict[str, Any]]:
    """指定 ticker について tracked_funds 各ファンドの最新 1Q 差分を返す。

    Args:
        ticker: 銘柄ティッカー（例: ``"AAPL"``）。大文字化されて
            ``TICKER_TO_ISSUER_NAME`` で issuer 名キーワードに変換される。
        sec_client: SECEdgarClient 互換クライアント（DI、テストで
            MagicMock 注入）。
        tracked_funds: ``{fund_name: CIK}`` のマッピング。None なら
            :data:`TRACKED_FUNDS` 既定を使用。
        cache_ttl_days: ファンド毎の 13F キャッシュ TTL（既定 90 日）。
            既存 :class:`SECEdgarClient.get_13f_history` の
            ``cache_ttl_sec`` に渡す。

    Returns:
        ``{fund_name: {"action": str, "value_change_usd": int}}``。

        - ``action``: ``"NEW" | "INCREASE" | "DECREASE" | "EXIT" | "HOLD"``
        - ``value_change_usd``: 今期 value - 前期 value（USD 整数）

        ticker をどの fund も保有していない場合は空 dict。

    Note:
        失敗時の挙動:
            1 fund が HTTPError 等で失敗した場合、warning ログ + 該当
            fund を skip して継続。最終戻り値が空 dict になることもある。

        ticker → issuer name 解決:
            CUSIP が ticker から直接引けないため、``TICKER_TO_ISSUER_NAME``
            の issuer 名部分一致を使う。未登録 ticker は ticker 自身で
            一致検索（FAANG 等の単純名や、issuer 名にティッカーが
            含まれる場合は当たる）。
    """
    funds = tracked_funds if tracked_funds is not None else TRACKED_FUNDS
    # Phase 5.3 review (P-H-1 / C-M-2) で「``!= 90`` の魔法数分岐は
    # ``DEFAULT_CACHE_TTL_SEC`` 変更時に無音で乖離する」と指摘されたため
    # 常に変換関数を使う形に簡素化。
    cache_ttl_sec = _ttl_days_to_seconds(cache_ttl_days)

    result: dict[str, dict[str, Any]] = {}
    for fund_name, cik in funds.items():
        # Phase 5.3 review (S-L-2) 対策: CIK 形式を最上流で検証し、
        # 不正値で SEC EDGAR への HTTP 404 を発生させないよう構造的に遮断。
        try:
            normalize_cik(cik)
        except (ValueError, TypeError) as exc:
            logger.warning(
                "extract_holdings_delta: invalid CIK skipped: fund=%s "
                "cik=%r error=%s",
                fund_name,
                cik,
                exc,
            )
            continue

        try:
            # limit=2 で最新 + 前期
            history = sec_client.get_13f_history(
                cik, limit=2, cache_ttl_sec=cache_ttl_sec
            )
        except (httpx.HTTPError, OSError, ValueError, KeyError) as exc:
            # Phase 5.3 review (P-H-2 / C-H-3) 対策: ``except Exception`` の
            # 過剰捕捉を 4 種に絞り込み。AttributeError / TypeError 等の
            # 実装バグは確実に bubble up させて早期検出。
            logger.warning(
                "extract_holdings_delta: skipping %s (CIK=%s): %s: %s",
                fund_name,
                cik,
                type(exc).__name__,
                exc,
            )
            continue

        if not history:
            # 13F-HR が 1 件もなければ skip
            continue

        current_df = history[0]
        # 履歴が 1 件しかなければ前期 = 空 DataFrame（→ 今期保有は NEW）
        if len(history) >= 2:
            previous_df = history[1]
        else:
            previous_df = pd.DataFrame(
                columns=["cusip", "name_of_issuer", "value_usd"]
            )

        # compute_qoq_diff が要求する 3 列を確実に持たせる
        if not {"cusip", "name_of_issuer", "value_usd"}.issubset(
            current_df.columns
        ):
            logger.warning(
                "extract_holdings_delta: %s current_df missing columns, skip",
                fund_name,
            )
            continue
        if not {"cusip", "name_of_issuer", "value_usd"}.issubset(
            previous_df.columns
        ):
            # 空 DataFrame の場合に補完
            previous_df = pd.DataFrame(
                columns=["cusip", "name_of_issuer", "value_usd"]
            )

        try:
            diff = compute_qoq_diff(current_df, previous_df)
        except (ValueError, KeyError, TypeError) as exc:
            # Phase 5.3 review (P-H-2 / C-H-3) 対策: pure function なので
            # 想定失敗は ValueError/KeyError/TypeError に絞られる。実装
            # バグ由来の AttributeError 等は bubble up させて早期検出。
            logger.warning(
                "extract_holdings_delta: compute_qoq_diff failed for %s: %s",
                fund_name,
                exc,
            )
            continue

        row = _find_ticker_row(diff, ticker)
        if row is None:
            # この fund は ticker を保有していない → 含めない
            continue

        result[fund_name] = _row_to_delta(row)

    return result
