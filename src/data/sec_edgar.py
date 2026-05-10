"""SEC EDGAR 13F-HR クライアント（CLAUDE.md §9.2 / §9.8）。

5 ファンド（Berkshire / Pabrai / Burry / Ackman / Einhorn）の四半期 13F-HR
保有データを SEC EDGAR REST API から動的取得する。:class:`ParquetCache`
経由で API 呼び出しを最小化、Provenance metadata を自動付与。

API リファレンス:
    https://www.sec.gov/edgar/sec-api-documentation
    https://data.sec.gov/submissions/CIK{padded10}.json
    https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_no_clean}/

レート制限:
    10 req/sec（SEC Fair Access Policy）。User-Agent ヘッダ必須。
    13F-HR は四半期更新（45 日提出遅延）→ キャッシュ TTL = 90 日。

設計判断:
    - ``value`` 単位は 2022Q3 SEC 改定で **整数 USD**（以前は thousands）。
      ``report_date >= 2022-09-30`` で判定し、それ以前は ×1,000 補正する。
    - User-Agent は PII（email）を含むためエラーメッセージには出さない。
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Final

import httpx
import pandas as pd

from ._provenance import attach_provenance
from .cache import ParquetCache

logger = logging.getLogger(__name__)

EDGAR_BASE_DATA_URL: Final[str] = "https://data.sec.gov"
EDGAR_BASE_ARCHIVES_URL: Final[str] = "https://www.sec.gov"
CACHE_PROVIDER: Final[str] = "SEC_EDGAR"
DEFAULT_CACHE_TTL_SEC: Final[int] = 7_776_000  # 90 日
DEFAULT_RATE_LIMIT_PER_SEC: Final[int] = 10

# 2022Q3 SEC ルール改定: 以降は ``value`` 整数 USD、それ以前は thousands。
VALUE_UNIT_BOUNDARY: Final[date] = date(2022, 9, 30)

# 13F Information Table XML namespace
INFOTABLE_NS: Final[str] = (
    "http://www.sec.gov/edgar/document/thirteenf/informationtable"
)

# parse_information_table が返す 10 カラム
PARSED_COLUMNS: Final[tuple[str, ...]] = (
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
)

# get_latest_13f が返す最終 13 カラム順
HOLDING_COLUMNS: Final[tuple[str, ...]] = (
    "cik",
    "report_date",
    "accession_no",
    *PARSED_COLUMNS,
)


# ============================================================
# 例外
# ============================================================


class EDGARConfigError(Exception):
    """設定エラー（User-Agent 未設定など）。"""


class EDGARNotFoundError(Exception):
    """対象データが見つからない（13F-HR 未提出 / InfoTable XML 不在）。"""


class EDGARAPIError(Exception):
    """SEC EDGAR HTTP エラー。

    User-Agent は SEC 規約で email 等の PII を含むため、エラーメッセージ
    には絶対に含めない（ログ・スタックトレース漏洩対策）。
    """


class EDGARParseError(Exception):
    """13F XML パース失敗。"""


# ============================================================
# データクラス
# ============================================================


@dataclass(frozen=True)
class Filing:
    """13F filing メタデータ（補助）。"""

    cik: str
    accession_no: str          # ハイフン入り元形式（例: 0000950123-25-009999）
    accession_no_clean: str    # ハイフン除去（例: 000095012325009999）
    form: str                  # 13F-HR / 13F-NT / 13F-HR/A 等
    filing_date: date          # SEC 受理日
    report_date: date          # 四半期末日（保有時点）
    primary_document: str


# ============================================================
# 純粋関数
# ============================================================


def normalize_cik(cik: str) -> str:
    """CIK 表記揺れを 10 桁ゼロ埋めに正規化。

    Args:
        cik: ``"1067983"`` / ``"0001067983"`` / ``"CIK0001067983"`` のいずれか

    Returns:
        ``"0001067983"`` 形式

    Raises:
        ValueError: 空文字 / プレフィックス除去後に数字でない場合
    """
    if not cik or not cik.strip():
        raise ValueError("cik must be non-empty")
    s = cik.strip()
    s = re.sub(r"^[Cc][Ii][Kk]", "", s)
    if not s.isdigit():
        raise ValueError(f"cik must be numeric after stripping prefix: {cik!r}")
    return s.zfill(10)


def normalize_accession_no(acc: str) -> tuple[str, str]:
    """アクセッション番号を ``(元形式, ハイフン除去形式)`` で返す。

    元形式が既にハイフンなしでも、その文字列をそのまま「元」として返却。
    """
    return acc, acc.replace("-", "")


def _strip_namespace(tag: str) -> str:
    """``{namespace}local`` → ``local``。"""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _find_text(element: ET.Element | None, name: str) -> str | None:
    """子要素の text を namespace 非依存で検索。"""
    if element is None:
        return None
    for child in element:
        if _strip_namespace(child.tag) == name:
            return child.text
    return None


def _find_element(element: ET.Element, name: str) -> ET.Element | None:
    for child in element:
        if _strip_namespace(child.tag) == name:
            return child
    return None


def _empty_parsed_df() -> pd.DataFrame:
    """parse_information_table の空 DataFrame（10 カラム）。"""
    return pd.DataFrame({col: pd.Series(dtype=object) for col in PARSED_COLUMNS})


def _to_int(text: str | None) -> int:
    """13F XML の数値テキストを int 化（None/空白は 0）。"""
    if text is None:
        return 0
    stripped = text.strip()
    if not stripped:
        return 0
    return int(stripped)


def parse_information_table(
    xml_bytes: bytes, *, report_date: date
) -> pd.DataFrame:
    """13F Information Table XML → DataFrame パース。

    Args:
        xml_bytes: XML バイト列
        report_date: 13F-HR の reportDate（``value`` 単位判定に使用）

    Returns:
        :data:`PARSED_COLUMNS` の 10 カラム DataFrame。空の InfoTable
        なら 0 行 + 全カラム。

    Raises:
        EDGARParseError: XML パース失敗 / 想定外のルート要素
    """
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise EDGARParseError(f"failed to parse 13F XML: {exc}") from exc

    if _strip_namespace(root.tag) != "informationTable":
        raise EDGARParseError(
            f"unexpected root element: {_strip_namespace(root.tag)}"
        )

    # 2022-09-30 以降は USD 直値（×1）、それ以前は thousands（×1000）
    value_multiplier = 1 if report_date >= VALUE_UNIT_BOUNDARY else 1_000

    rows: list[dict[str, Any]] = []
    for info in root:
        if _strip_namespace(info.tag) != "infoTable":
            continue
        shrs = _find_element(info, "shrsOrPrnAmt")
        voting = _find_element(info, "votingAuthority")
        rows.append(
            {
                "name_of_issuer": _find_text(info, "nameOfIssuer") or "",
                "title_of_class": _find_text(info, "titleOfClass") or "",
                "cusip": _find_text(info, "cusip") or "",
                "value_usd": _to_int(_find_text(info, "value")) * value_multiplier,
                "shares": _to_int(_find_text(shrs, "sshPrnamt")),
                "share_type": _find_text(shrs, "sshPrnamtType") or "",
                "put_call": _find_text(info, "putCall"),
                "voting_sole": _to_int(_find_text(voting, "Sole")),
                "voting_shared": _to_int(_find_text(voting, "Shared")),
                "voting_none": _to_int(_find_text(voting, "None")),
            }
        )

    if not rows:
        return _empty_parsed_df()
    return pd.DataFrame(rows)


def _params_hash(params: dict[str, Any]) -> str:
    """リクエストパラメータの SHA256（先頭 16 文字）。再現性確認用。"""
    serialized = json.dumps(params, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


def _make_default_http_client() -> httpx.Client:
    return httpx.Client(timeout=30.0, follow_redirects=True)


# ============================================================
# クライアント
# ============================================================


@dataclass(frozen=True)
class SECEdgarClient:
    """SEC EDGAR 13F-HR クライアント。

    Args:
        user_agent: SEC Fair Access Policy で必須。「会社名 メール」形式。
            空文字なら :class:`EDGARConfigError`。
        cache: ParquetCache インスタンス
        http_client: httpx.Client（テスト時はモック注入）
        rate_limit_per_sec: 10 req/sec（SEC 既定）
        base_data_url / base_archives_url: テスト時オーバーライド可

    Note:
        frozen dataclass だが、レート制限の前回呼び出し時刻は ``_state``
        辞書の中身として可変（dict 参照自体は不変）。これにより frozen の
        利点を残しつつ最小限の状態を持つ。
    """

    user_agent: str
    cache: ParquetCache
    http_client: httpx.Client = field(default_factory=_make_default_http_client)
    rate_limit_per_sec: int = DEFAULT_RATE_LIMIT_PER_SEC
    base_data_url: str = EDGAR_BASE_DATA_URL
    base_archives_url: str = EDGAR_BASE_ARCHIVES_URL
    _state: dict[str, Any] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if not self.user_agent or not self.user_agent.strip():
            raise EDGARConfigError(
                "SEC EDGAR requires a User-Agent header (set "
                "SEC_EDGAR_USER_AGENT in .env, format: "
                "'YourName your-email@example.com')"
            )

    # ===== 公開 API =====

    def get_latest_13f(
        self, cik: str, *, cache_ttl_sec: int = DEFAULT_CACHE_TTL_SEC
    ) -> pd.DataFrame:
        """最新 13F-HR の保有一覧を取得（キャッシュ経由）。

        Args:
            cik: 任意表記の CIK（自動正規化）
            cache_ttl_sec: キャッシュ TTL（既定 90 日）

        Returns:
            :data:`HOLDING_COLUMNS` の 13 カラム DataFrame + Provenance attrs

        Raises:
            EDGARNotFoundError: 13F-HR 未提出 / InfoTable XML 不在
            EDGARAPIError: HTTP エラー
            EDGARParseError: XML パース失敗
        """
        cik_norm = normalize_cik(cik)
        cache_key = f"13f_{cik_norm}_latest"
        cached = self.cache.get(CACHE_PROVIDER, cache_key, cache_ttl_sec)
        if cached is not None:
            return cached

        latest = self._find_latest_13fhr(self._get_submissions(cik_norm), cik_norm)
        index_json = self._get_filing_index(cik_norm, latest.accession_no_clean)
        infotable_filename = self._find_infotable_filename(index_json)
        if not infotable_filename:
            raise EDGARNotFoundError(
                f"InfoTable XML not found for {cik_norm}/"
                f"{latest.accession_no_clean}"
            )

        cik_int = str(int(cik_norm))
        endpoint_path = (
            f"/Archives/edgar/data/{cik_int}/"
            f"{latest.accession_no_clean}/{infotable_filename}"
        )
        response = self._request(
            f"{self.base_archives_url}{endpoint_path}", endpoint=endpoint_path
        )
        df = parse_information_table(
            response.content, report_date=latest.report_date
        )

        # メタデータ列を先頭に挿入
        df.insert(0, "cik", cik_norm)
        df.insert(1, "report_date", pd.Timestamp(latest.report_date))
        df.insert(2, "accession_no", latest.accession_no)
        df = df.reindex(columns=list(HOLDING_COLUMNS))

        attach_provenance(
            df,
            source="SEC EDGAR",
            fetched_at=datetime.now(timezone.utc),
            endpoint=endpoint_path,
            params_hash=_params_hash(
                {"cik": cik_norm, "accession_no": latest.accession_no}
            ),
            cache_hit=False,
        )

        self.cache.set(CACHE_PROVIDER, cache_key, df)
        return df

    # ===== 内部メソッド =====

    def _get_submissions(self, cik_norm: str) -> dict[str, Any]:
        endpoint = f"/submissions/CIK{cik_norm}.json"
        response = self._request(
            f"{self.base_data_url}{endpoint}", endpoint=endpoint
        )
        return response.json()

    def _get_filing_index(
        self, cik_norm: str, acc_no_clean: str
    ) -> dict[str, Any]:
        cik_int = str(int(cik_norm))
        endpoint = f"/Archives/edgar/data/{cik_int}/{acc_no_clean}/index.json"
        response = self._request(
            f"{self.base_archives_url}{endpoint}", endpoint=endpoint
        )
        return response.json()

    def _find_latest_13fhr(
        self, submissions: dict[str, Any], cik_norm: str
    ) -> Filing:
        """``filings.recent`` 並列配列から最新 13F-HR を 1 件返す。"""
        recent = submissions.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        accession_nos = recent.get("accessionNumber", [])
        filing_dates = recent.get("filingDate", [])
        report_dates = recent.get("reportDate", [])
        primary_docs = recent.get("primaryDocument", [])

        for i, form in enumerate(forms):
            if form == "13F-HR":
                acc_orig, acc_clean = normalize_accession_no(accession_nos[i])
                return Filing(
                    cik=cik_norm,
                    accession_no=acc_orig,
                    accession_no_clean=acc_clean,
                    form=form,
                    filing_date=date.fromisoformat(filing_dates[i]),
                    report_date=date.fromisoformat(report_dates[i]),
                    primary_document=primary_docs[i],
                )
        raise EDGARNotFoundError(
            f"No 13F-HR filings found for CIK {cik_norm}"
        )

    @staticmethod
    def _find_infotable_filename(index_json: dict[str, Any]) -> str | None:
        """``directory.item`` から ``*infotable*.xml`` を検索。"""
        directory = index_json.get("directory", {})
        items = directory.get("item", [])
        for item in items:
            name = item.get("name", "")
            if name.lower().endswith(".xml") and "infotable" in name.lower():
                return name
        return None

    def _request(self, url: str, *, endpoint: str) -> httpx.Response:
        """User-Agent ヘッダ付き GET（レート制限 + エラー変換）。"""
        self._enforce_rate_limit()
        try:
            response = self.http_client.get(
                url,
                headers={
                    "User-Agent": self.user_agent,
                    "Accept-Encoding": "gzip, deflate",
                },
            )
        except httpx.HTTPError as exc:
            # User-Agent は絶対に含めない
            raise EDGARAPIError(
                f"SEC EDGAR HTTP error for {endpoint}: {type(exc).__name__}"
            ) from exc
        if not response.is_success:
            body_preview = (response.text or "")[:200]
            raise EDGARAPIError(
                f"SEC EDGAR {response.status_code} for {endpoint}: "
                f"{body_preview}"
            )
        return response

    def _enforce_rate_limit(self) -> None:
        """10 req/sec を超えないよう ``time.sleep`` で待機。"""
        last = self._state.get("last_request_at")
        min_interval = 1.0 / self.rate_limit_per_sec
        if last is not None:
            elapsed = time.monotonic() - last
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
        self._state["last_request_at"] = time.monotonic()
