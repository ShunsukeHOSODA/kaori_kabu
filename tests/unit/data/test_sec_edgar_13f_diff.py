"""SEC EDGAR 13F QoQ 差分抽出（extract_holdings_delta）の単体テスト。

design.md L1051-1060 仕様:
    指定 ticker について、tracked_funds の各ファンドの最新 1Q 差分を返す。
    戻り値: {fund_name: {"action": "NEW|INCREASE|DECREASE|EXIT|HOLD",
                         "value_change_usd": int}, ...}

テスト戦略:
    - SECEdgarClient は MagicMock(spec=SECEdgarClient) で DI
    - get_13f_history は [current_df, previous_df] のリストを返す
    - parse_information_table 同等の DataFrame を直接組み立てる
    - ticker → issuer_name 変換は TICKER_TO_ISSUER_NAME を再利用
"""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pandas as pd
import pytest


def _make_holding_df(rows: list[dict[str, object]]) -> pd.DataFrame:
    """parse_information_table 互換の最小 DataFrame を組む。

    compute_qoq_diff が必要とするのは ``cusip`` / ``name_of_issuer`` /
    ``value_usd`` の 3 列のみ。それ以外のメタ列は省略。
    """
    if not rows:
        return pd.DataFrame(
            {
                "cusip": pd.Series(dtype=object),
                "name_of_issuer": pd.Series(dtype=object),
                "value_usd": pd.Series(dtype="int64"),
            }
        )
    return pd.DataFrame(rows)


# ============================================================
# extract_holdings_delta: action 判定（NEW / INCREASE / DECREASE / EXIT / HOLD）
# ============================================================


@pytest.mark.unit
class TestExtractHoldingsDeltaActions:
    """action 5 区分判定。"""

    def test_NEW_前期になく今期にある(self) -> None:
        from data.sec_edgar import SECEdgarClient
        from data.sec_edgar_13f_diff import extract_holdings_delta

        # 今期: AAPL あり、前期: AAPL なし
        current = _make_holding_df(
            [{"cusip": "037833100", "name_of_issuer": "APPLE INC", "value_usd": 1_000_000}]
        )
        previous = _make_holding_df([])

        sec_client = MagicMock(spec=SECEdgarClient)
        sec_client.get_13f_history.return_value = [current, previous]

        result = extract_holdings_delta(
            "AAPL",
            sec_client=sec_client,
            tracked_funds={"Berkshire_Hathaway": "0001067983"},
        )

        assert "Berkshire_Hathaway" in result
        assert result["Berkshire_Hathaway"]["action"] == "NEW"
        assert result["Berkshire_Hathaway"]["value_change_usd"] == 1_000_000

    def test_INCREASE_前期より今期が大きい(self) -> None:
        from data.sec_edgar import SECEdgarClient
        from data.sec_edgar_13f_diff import extract_holdings_delta

        current = _make_holding_df(
            [{"cusip": "037833100", "name_of_issuer": "APPLE INC", "value_usd": 150_000_000}]
        )
        previous = _make_holding_df(
            [{"cusip": "037833100", "name_of_issuer": "APPLE INC", "value_usd": 100_000_000}]
        )

        sec_client = MagicMock(spec=SECEdgarClient)
        sec_client.get_13f_history.return_value = [current, previous]

        result = extract_holdings_delta(
            "AAPL",
            sec_client=sec_client,
            tracked_funds={"Berkshire_Hathaway": "0001067983"},
        )

        assert result["Berkshire_Hathaway"]["action"] == "INCREASE"
        assert result["Berkshire_Hathaway"]["value_change_usd"] == 50_000_000

    def test_EXIT_前期にあり今期にない(self) -> None:
        from data.sec_edgar import SECEdgarClient
        from data.sec_edgar_13f_diff import extract_holdings_delta

        current = _make_holding_df([])
        previous = _make_holding_df(
            [{"cusip": "037833100", "name_of_issuer": "APPLE INC", "value_usd": 80_000_000}]
        )

        sec_client = MagicMock(spec=SECEdgarClient)
        sec_client.get_13f_history.return_value = [current, previous]

        result = extract_holdings_delta(
            "AAPL",
            sec_client=sec_client,
            tracked_funds={"Berkshire_Hathaway": "0001067983"},
        )

        assert result["Berkshire_Hathaway"]["action"] == "EXIT"
        assert result["Berkshire_Hathaway"]["value_change_usd"] == -80_000_000


# ============================================================
# extract_holdings_delta: ticker が無いケース
# ============================================================


@pytest.mark.unit
class TestExtractHoldingsDeltaMissing:
    """ticker が両期に無い場合は空 dict / 該当 fund を含めない。"""

    def test_ticker_が_どの_filing_にもない場合は空_dict(self) -> None:
        from data.sec_edgar import SECEdgarClient
        from data.sec_edgar_13f_diff import extract_holdings_delta

        # 今期・前期とも別銘柄しか持っていない
        current = _make_holding_df(
            [{"cusip": "594918104", "name_of_issuer": "MICROSOFT CORP", "value_usd": 5_000_000}]
        )
        previous = _make_holding_df(
            [{"cusip": "594918104", "name_of_issuer": "MICROSOFT CORP", "value_usd": 4_500_000}]
        )

        sec_client = MagicMock(spec=SECEdgarClient)
        sec_client.get_13f_history.return_value = [current, previous]

        result = extract_holdings_delta(
            "AAPL",
            sec_client=sec_client,
            tracked_funds={"Berkshire_Hathaway": "0001067983"},
        )

        # AAPL を持ってない fund は結果に含まれない
        assert result == {}


# ============================================================
# extract_holdings_delta: fetch 失敗時の resilience
# ============================================================


@pytest.mark.unit
class TestExtractHoldingsDeltaResilience:
    """1 fund が失敗しても他 fund は処理を続行する。"""

    def test_fetch_失敗時は_該当_fund_を_skip_して継続(self) -> None:
        from data.sec_edgar import SECEdgarClient
        from data.sec_edgar_13f_diff import extract_holdings_delta

        current_ok = _make_holding_df(
            [{"cusip": "037833100", "name_of_issuer": "APPLE INC", "value_usd": 2_000_000}]
        )
        previous_ok = _make_holding_df([])  # NEW position

        sec_client = MagicMock(spec=SECEdgarClient)

        def _history_side_effect(cik: str, **_kwargs: object) -> list[pd.DataFrame]:
            # Berkshire は成功、Pabrai は HTTPError で失敗
            if cik == "0001067983":
                return [current_ok, previous_ok]
            raise httpx.HTTPError("simulated network error")

        sec_client.get_13f_history.side_effect = _history_side_effect

        result = extract_holdings_delta(
            "AAPL",
            sec_client=sec_client,
            tracked_funds={
                "Berkshire_Hathaway": "0001067983",
                "Pabrai_Funds": "0001173334",
            },
        )

        # Berkshire は NEW で含まれ、Pabrai は skip
        assert "Berkshire_Hathaway" in result
        assert result["Berkshire_Hathaway"]["action"] == "NEW"
        assert "Pabrai_Funds" not in result


# ============================================================
# extract_holdings_delta: 履歴が 1 件しかない場合（前期なし）
# ============================================================


@pytest.mark.unit
class TestExtractHoldingsDeltaInsufficientHistory:
    """get_13f_history が 1 件しか返さない場合 → 前期 = 空として扱う。"""

    def test_履歴1件のみ_今期保有あり_は_NEW扱い(self) -> None:
        from data.sec_edgar import SECEdgarClient
        from data.sec_edgar_13f_diff import extract_holdings_delta

        current = _make_holding_df(
            [{"cusip": "037833100", "name_of_issuer": "APPLE INC", "value_usd": 3_000_000}]
        )

        sec_client = MagicMock(spec=SECEdgarClient)
        sec_client.get_13f_history.return_value = [current]  # 1 件のみ

        result = extract_holdings_delta(
            "AAPL",
            sec_client=sec_client,
            tracked_funds={"Berkshire_Hathaway": "0001067983"},
        )

        assert result["Berkshire_Hathaway"]["action"] == "NEW"
        assert result["Berkshire_Hathaway"]["value_change_usd"] == 3_000_000


# ============================================================
# TRACKED_FUNDS デフォルト
# ============================================================


@pytest.mark.unit
class TestTrackedFundsDefault:
    """tracked_funds=None なら TRACKED_FUNDS 既定を使う。"""

    def test_tracked_funds_None_でも_TRACKED_FUNDS_を使って動作(self) -> None:
        from data.sec_edgar import SECEdgarClient
        from data.sec_edgar_13f_diff import TRACKED_FUNDS, extract_holdings_delta

        sec_client = MagicMock(spec=SECEdgarClient)
        # 全 fund で空 history（ticker 無し）→ 戻り値は空 dict
        sec_client.get_13f_history.return_value = [_make_holding_df([])]

        result = extract_holdings_delta("AAPL", sec_client=sec_client)

        # 全 fund について get_13f_history が呼ばれている
        assert sec_client.get_13f_history.call_count == len(TRACKED_FUNDS)
        assert result == {}
