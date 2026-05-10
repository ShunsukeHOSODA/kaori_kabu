"""SEC EDGAR 13F-HR クライアントの単体テスト（モック）。

オフライン実行可能。`tests/fixtures/sec_edgar/` の合成 fixture から
`httpx.Client.get` の戻り値を組み立て、URL ごとに固定レスポンスを返す
モックを注入する。

カバー範囲:
    - normalize_cik / normalize_accession_no
    - parse_information_table（USD 直値 / thousands ×1000 補正 / put/call）
    - SECEdgarClient.get_latest_13f（cache hit / cache miss / 全 3 段呼び出し）
    - エラー系（user_agent 未設定 / 13F-HR 不在 / XML 不正）
    - Provenance attrs 付与とキャッシュ越しラウンドトリップ
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pandas as pd
import pytest

FIXTURE_DIR = Path(__file__).parents[2] / "fixtures" / "sec_edgar"


def _load_bytes(name: str) -> bytes:
    return (FIXTURE_DIR / name).read_bytes()


def _make_response(
    status: int, body: bytes, content_type: str = "application/json"
) -> MagicMock:
    """``httpx.Response`` のモックを作成。"""
    response = MagicMock(spec=httpx.Response)
    response.status_code = status
    response.is_success = 200 <= status < 300
    response.reason_phrase = "OK" if response.is_success else "Error"
    response.text = body.decode("utf-8", errors="ignore")
    response.content = body
    if content_type.startswith("application/json"):
        response.json.return_value = json.loads(body)
    response.raise_for_status.return_value = None
    return response


def _routing_http_client(routes: dict[str, MagicMock]) -> MagicMock:
    """URL 部分一致で MagicMock レスポンスを返す ``httpx.Client`` モック。"""
    client = MagicMock(spec=httpx.Client)

    def _get(url: str, **_kwargs: object) -> MagicMock:
        for key, response in routes.items():
            if key in url:
                return response
        return _make_response(404, b'{"error": "not found"}')

    client.get.side_effect = _get
    return client


# ============================================================
# 純粋関数: normalize_cik / normalize_accession_no / parse
# ============================================================


@pytest.mark.unit
class TestNormalizeCIK:
    """CIK 表記揺れの正規化（10 桁ゼロ埋め）。"""

    def test_整数文字列は_10桁ゼロ埋めされる(self) -> None:
        from data.sec_edgar import normalize_cik

        assert normalize_cik("1067983") == "0001067983"

    def test_既に10桁ゼロ埋めならそのまま(self) -> None:
        from data.sec_edgar import normalize_cik

        assert normalize_cik("0001067983") == "0001067983"

    def test_CIKプレフィックス付きは除去される(self) -> None:
        from data.sec_edgar import normalize_cik

        assert normalize_cik("CIK0001067983") == "0001067983"

    def test_小文字cikプレフィックスも除去される(self) -> None:
        from data.sec_edgar import normalize_cik

        assert normalize_cik("cik1067983") == "0001067983"

    def test_空文字は値エラー(self) -> None:
        from data.sec_edgar import normalize_cik

        with pytest.raises(ValueError):
            normalize_cik("")


@pytest.mark.unit
class TestNormalizeAccessionNo:
    """アクセッション番号: ハイフン入り元形式 / ハイフン除去形式の両方を返す。"""

    def test_標準形式_両方返す(self) -> None:
        from data.sec_edgar import normalize_accession_no

        original, clean = normalize_accession_no("0000950123-25-009999")
        assert original == "0000950123-25-009999"
        assert clean == "000095012325009999"

    def test_ハイフンなし入力_両方同じ(self) -> None:
        from data.sec_edgar import normalize_accession_no

        original, clean = normalize_accession_no("000095012325009999")
        assert clean == "000095012325009999"


# ============================================================
# parse_information_table
# ============================================================


@pytest.mark.unit
class TestParseInformationTable:
    """13F Information Table XML → DataFrame パース。"""

    def test_2022Q3以降_USD直値で3行パース(self) -> None:
        from data.sec_edgar import parse_information_table

        xml_bytes = _load_bytes("berkshire_2025q4_infotable.xml")
        df = parse_information_table(
            xml_bytes, report_date=date(2025, 12, 31)
        )

        assert len(df) == 3
        for col in (
            "name_of_issuer",
            "title_of_class",
            "cusip",
            "value_usd",
            "shares",
            "share_type",
            "put_call",
            "voting_sole",
            "voting_shared",
            "voting_none",
        ):
            assert col in df.columns, f"missing column: {col}"

        apple = df[df["cusip"] == "037833100"].iloc[0]
        assert apple["name_of_issuer"] == "APPLE INC"
        assert apple["value_usd"] == 75_673_000_000
        assert apple["shares"] == 300_000_000
        assert apple["share_type"] == "SH"
        assert apple["put_call"] is None or pd.isna(apple["put_call"])

    def test_2022Q3未満_thousands単位で1000倍補正(self) -> None:
        from data.sec_edgar import parse_information_table

        xml_bytes = _load_bytes("pabrai_2020q1_infotable.xml")
        df = parse_information_table(
            xml_bytes, report_date=date(2020, 3, 31)
        )

        micron = df[df["cusip"] == "595112103"].iloc[0]
        assert micron["value_usd"] == 50_000_000
        seagate = df[df["cusip"] == "G7945J104"].iloc[0]
        assert seagate["value_usd"] == 30_000_000
        assert seagate["put_call"] == "Put"

    def test_境界_2022年9月30日はUSD直値扱い(self) -> None:
        """2022-09-30 が境界で、>= は USD（×1 倍）。"""
        from data.sec_edgar import parse_information_table

        xml_bytes = _load_bytes("berkshire_2025q4_infotable.xml")
        df = parse_information_table(
            xml_bytes, report_date=date(2022, 9, 30)
        )
        apple = df[df["cusip"] == "037833100"].iloc[0]
        assert apple["value_usd"] == 75_673_000_000

    def test_不正なXMLは_EDGARParseError(self) -> None:
        from data.sec_edgar import EDGARParseError, parse_information_table

        with pytest.raises(EDGARParseError):
            parse_information_table(
                b"<not-valid-xml>", report_date=date(2025, 12, 31)
            )

    def test_空のinformationTable_空DataFrame(self) -> None:
        from data.sec_edgar import parse_information_table

        empty_xml = (
            b'<?xml version="1.0"?>'
            b'<informationTable xmlns="http://www.sec.gov/edgar/document/'
            b'thirteenf/informationtable"></informationTable>'
        )
        df = parse_information_table(empty_xml, report_date=date(2025, 12, 31))
        assert len(df) == 0
        assert "cusip" in df.columns


# ============================================================
# SECEdgarClient: 設定・初期化
# ============================================================


@pytest.mark.unit
class TestSECEdgarClientConfig:
    """User-Agent 必須チェック。"""

    def test_user_agent_未設定_EDGARConfigError(
        self, tmp_path: Path
    ) -> None:
        from data.cache import ParquetCache
        from data.sec_edgar import EDGARConfigError, SECEdgarClient

        cache = ParquetCache(base_dir=tmp_path)
        with pytest.raises(EDGARConfigError):
            SECEdgarClient(
                user_agent="",
                cache=cache,
                http_client=MagicMock(spec=httpx.Client),
            )

    def test_user_agent_空白のみ_EDGARConfigError(
        self, tmp_path: Path
    ) -> None:
        from data.cache import ParquetCache
        from data.sec_edgar import EDGARConfigError, SECEdgarClient

        cache = ParquetCache(base_dir=tmp_path)
        with pytest.raises(EDGARConfigError):
            SECEdgarClient(
                user_agent="   ",
                cache=cache,
                http_client=MagicMock(spec=httpx.Client),
            )


# ============================================================
# get_latest_13f: フルフロー
# ============================================================


def _build_berkshire_routes() -> dict[str, MagicMock]:
    """Berkshire の標準フロー: submissions → index → infotable.xml。"""
    return {
        "data.sec.gov/submissions/CIK0001067983.json": _make_response(
            200, _load_bytes("berkshire_submissions.json")
        ),
        "/Archives/edgar/data/1067983/000095012326000099/index.json": (
            _make_response(200, _load_bytes("berkshire_index.json"))
        ),
        "/Archives/edgar/data/1067983/000095012326000099/form13fInfoTable.xml": (
            _make_response(
                200,
                _load_bytes("berkshire_2025q4_infotable.xml"),
                content_type="application/xml",
            )
        ),
    }


@pytest.mark.unit
class TestGetLatest13FCacheHit:
    """キャッシュヒット時は HTTP 呼び出しが走らない。"""

    def test_キャッシュヒット時_HTTPは叩かれない(
        self, tmp_path: Path
    ) -> None:
        from data._provenance import attach_provenance
        from data.cache import ParquetCache
        from data.sec_edgar import SECEdgarClient

        cache = ParquetCache(base_dir=tmp_path)
        cached = pd.DataFrame(
            {
                "cik": ["0001067983"],
                "report_date": [pd.Timestamp("2025-12-31")],
                "name_of_issuer": ["CACHED FUND HOLDING"],
                "cusip": ["111111111"],
                "value_usd": [12345],
                "shares": [100],
                "share_type": ["SH"],
                "put_call": [None],
                "voting_sole": [100],
                "voting_shared": [0],
                "voting_none": [0],
                "title_of_class": ["COM"],
                "accession_no": ["x"],
            }
        )
        attach_provenance(
            cached,
            source="SEC EDGAR",
            fetched_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
            endpoint="/Archives/.../form13fInfoTable.xml",
            params_hash="abc",
        )
        cache.set("SEC_EDGAR", "13f_0001067983_latest", cached)

        http_client = MagicMock(spec=httpx.Client)
        client = SECEdgarClient(
            user_agent="kaori_kabu test test@example.com",
            cache=cache,
            http_client=http_client,
        )
        result = client.get_latest_13f("0001067983")

        http_client.get.assert_not_called()
        assert len(result) == 1
        assert result["name_of_issuer"].iloc[0] == "CACHED FUND HOLDING"
        assert result.attrs["cache_hit"] is True


@pytest.mark.unit
class TestGetLatest13FCacheMiss:
    """キャッシュミス時の 3 段フロー。"""

    def test_3段階のHTTP呼び出しでDataFrameを返す(
        self, tmp_path: Path
    ) -> None:
        from data.cache import ParquetCache
        from data.sec_edgar import SECEdgarClient

        cache = ParquetCache(base_dir=tmp_path)
        http_client = _routing_http_client(_build_berkshire_routes())
        client = SECEdgarClient(
            user_agent="kaori_kabu test test@example.com",
            cache=cache,
            http_client=http_client,
        )
        result = client.get_latest_13f("0001067983")

        assert http_client.get.call_count == 3
        assert len(result) == 3
        apple = result[result["cusip"] == "037833100"].iloc[0]
        assert apple["name_of_issuer"] == "APPLE INC"
        assert apple["value_usd"] == 75_673_000_000

    def test_Provenance_attrs_が設定される(self, tmp_path: Path) -> None:
        from data._provenance import REQUIRED_PROVENANCE_KEYS
        from data.cache import ParquetCache
        from data.sec_edgar import SECEdgarClient

        cache = ParquetCache(base_dir=tmp_path)
        client = SECEdgarClient(
            user_agent="kaori_kabu test test@example.com",
            cache=cache,
            http_client=_routing_http_client(_build_berkshire_routes()),
        )
        result = client.get_latest_13f("0001067983")

        assert REQUIRED_PROVENANCE_KEYS <= set(result.attrs.keys())
        assert result.attrs["source"] == "SEC EDGAR"
        assert result.attrs["cache_hit"] is False
        assert "infotable" in result.attrs["endpoint"].lower()

    def test_キャッシュに保存される(self, tmp_path: Path) -> None:
        from data.cache import ParquetCache
        from data.sec_edgar import SECEdgarClient

        cache = ParquetCache(base_dir=tmp_path)
        client = SECEdgarClient(
            user_agent="kaori_kabu test test@example.com",
            cache=cache,
            http_client=_routing_http_client(_build_berkshire_routes()),
        )
        client.get_latest_13f("0001067983")

        cached = cache.get("SEC_EDGAR", "13f_0001067983_latest", 7_776_000)
        assert cached is not None
        assert len(cached) == 3
        assert cached.attrs["cache_hit"] is True


@pytest.mark.unit
class TestGetLatest13FErrors:
    """エラー系。"""

    def test_13F_HRが1件もない_EDGARNotFoundError(
        self, tmp_path: Path
    ) -> None:
        from data.cache import ParquetCache
        from data.sec_edgar import EDGARNotFoundError, SECEdgarClient

        routes = {
            "data.sec.gov/submissions/CIK0001649339.json": _make_response(
                200, _load_bytes("nt_only_submissions.json")
            ),
        }
        cache = ParquetCache(base_dir=tmp_path)
        client = SECEdgarClient(
            user_agent="kaori_kabu test test@example.com",
            cache=cache,
            http_client=_routing_http_client(routes),
        )
        with pytest.raises(EDGARNotFoundError):
            client.get_latest_13f("0001649339")

    def test_HTTP_500レスポンス_EDGARAPIError(self, tmp_path: Path) -> None:
        from data.cache import ParquetCache
        from data.sec_edgar import EDGARAPIError, SECEdgarClient

        routes = {
            "data.sec.gov/submissions/CIK0001067983.json": _make_response(
                500, b'{"error": "internal"}'
            ),
        }
        cache = ParquetCache(base_dir=tmp_path)
        client = SECEdgarClient(
            user_agent="kaori_kabu test test@example.com",
            cache=cache,
            http_client=_routing_http_client(routes),
        )
        with pytest.raises(EDGARAPIError):
            client.get_latest_13f("0001067983")

    def test_user_agent_はエラーメッセージに含まれない(
        self, tmp_path: Path
    ) -> None:
        """PII 漏洩防止: User-Agent はエラーに出さない。"""
        from data.cache import ParquetCache
        from data.sec_edgar import EDGARAPIError, SECEdgarClient

        ua = "kaori_kabu PII-EMAIL-SECRET@example.com"
        routes = {
            "data.sec.gov/submissions/CIK0001067983.json": _make_response(
                500, b'{"error": "internal"}'
            ),
        }
        cache = ParquetCache(base_dir=tmp_path)
        client = SECEdgarClient(
            user_agent=ua,
            cache=cache,
            http_client=_routing_http_client(routes),
        )
        with pytest.raises(EDGARAPIError) as excinfo:
            client.get_latest_13f("0001067983")
        assert "PII-EMAIL-SECRET" not in str(excinfo.value)


@pytest.mark.unit
class TestRequestHeaders:
    """User-Agent ヘッダが必ず付与される（SEC Fair Access Policy 義務）。"""

    def test_全リクエストにUser_Agentヘッダ付与(self, tmp_path: Path) -> None:
        from data.cache import ParquetCache
        from data.sec_edgar import SECEdgarClient

        cache = ParquetCache(base_dir=tmp_path)
        ua = "kaori_kabu test test@example.com"
        http_client = _routing_http_client(_build_berkshire_routes())
        client = SECEdgarClient(
            user_agent=ua, cache=cache, http_client=http_client
        )
        client.get_latest_13f("0001067983")

        for call in http_client.get.call_args_list:
            kwargs = call.kwargs
            headers = kwargs.get("headers", {})
            assert headers.get("User-Agent") == ua


# ============================================================
# _find_infotable_filename: 命名揺れ吸収（Donnelley 数値命名対応）
# ============================================================


@pytest.mark.unit
class TestFindInfoTableFilename:
    """提出代理人ごとの XML 命名揺れを吸収する 2 段判別ロジック。

    実機検証 (.steering/20260510-13f-dynamic) で Berkshire Q4 2025 提出が
    Donnelley 採番の数値ファイル名 (``50240.xml``) で実体化していることを
    確認。Step 1 の "infotable" 部分一致だけだと取りこぼすため、
    Step 2 の表紙除外フォールバックを追加。
    """

    def test_Step1_infotable部分一致が最優先(self) -> None:
        from data.sec_edgar import SECEdgarClient

        index_json = {
            "directory": {
                "item": [
                    {"name": "primary_doc.xml"},
                    {"name": "form13fInfoTable.xml"},
                    {"name": "extra.xml"},  # Step 2 候補
                ]
            }
        }
        # Step 1 が先に hit するので extra.xml ではなく form13fInfoTable.xml
        result = SECEdgarClient._find_infotable_filename(index_json)
        assert result == "form13fInfoTable.xml"

    def test_Step2_Donnelley数値命名_primary_doc除外(self) -> None:
        """Donnelley 提出（実機 Berkshire 2026 提出と同形）。"""
        from data.sec_edgar import SECEdgarClient

        index_json = {
            "directory": {
                "item": [
                    {"name": "0001193125-26-054580-index-headers.html"},
                    {"name": "0001193125-26-054580-index.html"},
                    {"name": "0001193125-26-054580.txt"},
                    {"name": "50240.xml"},  # ← InfoTable
                    {"name": "primary_doc.xml"},
                ]
            }
        }
        result = SECEdgarClient._find_infotable_filename(index_json)
        assert result == "50240.xml"

    def test_Step2_index_headers系XMLは除外(self) -> None:
        """``*-index.xml`` / ``*-headers.xml`` は誤検知しない。"""
        from data.sec_edgar import SECEdgarClient

        index_json = {
            "directory": {
                "item": [
                    {"name": "primary_doc.xml"},
                    {"name": "0000950123-25-009999-index.xml"},
                    {"name": "0000950123-25-009999-headers.xml"},
                    {"name": "data.xml"},  # ← これが残る
                ]
            }
        }
        result = SECEdgarClient._find_infotable_filename(index_json)
        assert result == "data.xml"

    def test_該当なし_None返却(self) -> None:
        from data.sec_edgar import SECEdgarClient

        index_json = {
            "directory": {
                "item": [
                    {"name": "primary_doc.xml"},
                    {"name": "cover.html"},
                ]
            }
        }
        assert SECEdgarClient._find_infotable_filename(index_json) is None

    def test_directory欠損_None返却(self) -> None:
        from data.sec_edgar import SECEdgarClient

        assert SECEdgarClient._find_infotable_filename({}) is None
        assert (
            SECEdgarClient._find_infotable_filename({"directory": {}}) is None
        )
