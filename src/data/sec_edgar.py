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


def compute_qoq_diff(
    current: pd.DataFrame,
    previous: pd.DataFrame,
    *,
    threshold: float = 0.05,
) -> pd.DataFrame:
    """Q-over-Q 差分を ``cusip`` ベースで 5 区分に分類する純粋関数。

    design.md §10.3 の前期比 diff:

    - **新規買い**: 前期 NaN, 今期あり
    - **売却**: 前期あり, 今期 NaN
    - **増持**: 両期あり, 相対差 > +threshold
    - **減持**: 両期あり, 相対差 < -threshold
    - **保持**: 両期あり, |相対差| <= threshold

    Args:
        current: 今期の保有（``cusip`` / ``name_of_issuer`` / ``value_usd`` 必須）
        previous: 前期の保有（同上）
        threshold: 増持・減持の相対差閾値（既定 5% = ``0.05``）

    Returns:
        ``cusip`` / ``name_of_issuer`` / ``value_current`` / ``value_previous``
        / ``change_usd`` / ``action`` の 6 カラム DataFrame。
    """
    cur = current[["cusip", "name_of_issuer", "value_usd"]].rename(
        columns={"value_usd": "value_current", "name_of_issuer": "name_cur"}
    )
    prev = previous[["cusip", "name_of_issuer", "value_usd"]].rename(
        columns={"value_usd": "value_previous", "name_of_issuer": "name_prev"}
    )
    merged = cur.merge(prev, on="cusip", how="outer")

    # name は今期優先で coalesce
    merged["name_of_issuer"] = merged["name_cur"].fillna(merged["name_prev"])

    # change_usd: NaN を 0 扱いで差額計算
    merged["change_usd"] = (
        merged["value_current"].fillna(0) - merged["value_previous"].fillna(0)
    )

    def _classify(row: pd.Series) -> str:
        v_cur = row["value_current"]
        v_prev = row["value_previous"]
        if pd.isna(v_prev):
            return "新規買い"
        if pd.isna(v_cur):
            return "売却"
        if v_prev == 0:
            # 前期 0 → 新規買い扱い（ゼロ除算回避）
            return "新規買い" if v_cur > 0 else "保持"
        rel_diff = (v_cur - v_prev) / v_prev
        if rel_diff > threshold:
            return "増持"
        if rel_diff < -threshold:
            return "減持"
        return "保持"

    merged["action"] = merged.apply(_classify, axis=1)

    return merged[
        [
            "cusip",
            "name_of_issuer",
            "value_current",
            "value_previous",
            "change_usd",
            "action",
        ]
    ]


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

        submissions = self._get_submissions(cik_norm)
        filing = self._find_13fhr_filings(submissions, cik_norm, limit=1)[0]
        df = self._fetch_filing_to_df(cik_norm, filing)

        self.cache.set(CACHE_PROVIDER, cache_key, df)
        return df

    def get_13f_history(
        self,
        cik: str,
        *,
        limit: int = 4,
        cache_ttl_sec: int = DEFAULT_CACHE_TTL_SEC,
    ) -> list[pd.DataFrame]:
        """直近 ``limit`` 個の 13F-HR を新しい順で返す（キャッシュ経由）。

        各 filing は accession 単位でキャッシュされるため、新四半期分のみが
        次回以降 HTTP 呼び出しを発生させる（既存四半期は cache hit）。
        ``submissions`` JSON は最新性チェックのため毎回 fetch。

        Args:
            cik: 任意表記の CIK
            limit: 取得する四半期数（既定 4 = 1 年分）
            cache_ttl_sec: 各 filing のキャッシュ TTL（既定 90 日）

        Returns:
            報告期降順の DataFrame リスト。各 DataFrame は
            :data:`HOLDING_COLUMNS` 形式 + Provenance attrs。

        Raises:
            EDGARNotFoundError: 13F-HR が 1 件も提出されていない場合
        """
        cik_norm = normalize_cik(cik)
        submissions = self._get_submissions(cik_norm)
        filings = self._find_13fhr_filings(submissions, cik_norm, limit=limit)

        results: list[pd.DataFrame] = []
        for filing in filings:
            cache_key = f"13f_{cik_norm}_{filing.accession_no_clean}"
            cached = self.cache.get(CACHE_PROVIDER, cache_key, cache_ttl_sec)
            if cached is not None:
                results.append(cached)
                continue
            df = self._fetch_filing_to_df(cik_norm, filing)
            self.cache.set(CACHE_PROVIDER, cache_key, df)
            results.append(df)
        return results

    # ===== 内部メソッド =====

    def _fetch_filing_to_df(
        self, cik_norm: str, filing: Filing
    ) -> pd.DataFrame:
        """1 件の filing を InfoTable XML 取得 → DataFrame 化（Provenance 付与）。

        ``get_latest_13f`` / ``get_13f_history`` の共通ヘルパー。キャッシュ
        操作は呼び出し側が担当する。
        """
        index_json = self._get_filing_index(cik_norm, filing.accession_no_clean)
        infotable_filename = self._find_infotable_filename(index_json)
        if not infotable_filename:
            raise EDGARNotFoundError(
                f"InfoTable XML not found for {cik_norm}/"
                f"{filing.accession_no_clean}"
            )

        cik_int = str(int(cik_norm))
        endpoint_path = (
            f"/Archives/edgar/data/{cik_int}/"
            f"{filing.accession_no_clean}/{infotable_filename}"
        )
        response = self._request(
            f"{self.base_archives_url}{endpoint_path}", endpoint=endpoint_path
        )
        df = parse_information_table(
            response.content, report_date=filing.report_date
        )

        # メタデータ列を先頭に挿入
        df.insert(0, "cik", cik_norm)
        df.insert(1, "report_date", pd.Timestamp(filing.report_date))
        df.insert(2, "accession_no", filing.accession_no)
        df = df.reindex(columns=list(HOLDING_COLUMNS))

        attach_provenance(
            df,
            source="SEC EDGAR",
            fetched_at=datetime.now(timezone.utc),
            endpoint=endpoint_path,
            params_hash=_params_hash(
                {"cik": cik_norm, "accession_no": filing.accession_no}
            ),
            cache_hit=False,
        )
        return df

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

    def _find_13fhr_filings(
        self,
        submissions: dict[str, Any],
        cik_norm: str,
        *,
        limit: int = 1,
    ) -> list[Filing]:
        """``filings.recent`` 並列配列から 13F-HR を新しい順で最大 ``limit`` 件返す。

        SEC submissions JSON は提出順（新しい順）で並んでいるため、線形走査で
        ``13F-HR`` のみフィルタすれば自然に新しい順になる。

        Raises:
            EDGARNotFoundError: 13F-HR が 1 件も見つからない場合
        """
        recent = submissions.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        accession_nos = recent.get("accessionNumber", [])
        filing_dates = recent.get("filingDate", [])
        report_dates = recent.get("reportDate", [])
        primary_docs = recent.get("primaryDocument", [])

        filings: list[Filing] = []
        for i, form in enumerate(forms):
            if form != "13F-HR":
                continue
            acc_orig, acc_clean = normalize_accession_no(accession_nos[i])
            filings.append(
                Filing(
                    cik=cik_norm,
                    accession_no=acc_orig,
                    accession_no_clean=acc_clean,
                    form=form,
                    filing_date=date.fromisoformat(filing_dates[i]),
                    report_date=date.fromisoformat(report_dates[i]),
                    primary_document=primary_docs[i],
                )
            )
            if len(filings) >= limit:
                break

        if not filings:
            raise EDGARNotFoundError(
                f"No 13F-HR filings found for CIK {cik_norm}"
            )
        return filings

    @staticmethod
    def _find_infotable_filename(index_json: dict[str, Any]) -> str | None:
        """``directory.item`` から InfoTable XML を検索（2 段判別）。

        13F filing の XML 命名は提出代理人によって揺れる:

        - 明示命名: ``form13fInfoTable.xml`` / ``infoTable.xml``（手動・旧）
        - 数値命名: ``50240.xml`` 等（Donnelley 等の代理人が採番）

        判別フロー:
          1. ``"infotable"`` 部分一致 — 明示命名を最優先
          2. ``primary_doc.xml`` / ``*-index.*`` / ``*-headers.*`` を除外した
             残り ``.xml`` — 13F-HR は通常 InfoTable と表紙の 2 ファイルのみ
             なので、表紙を除けば InfoTable

        Step 2 で誤って表紙を選んだ場合、:func:`parse_information_table`
        がルート要素チェックで :class:`EDGARParseError` を上げるため、
        サイレント失敗にはならない。
        """
        directory = index_json.get("directory", {})
        items = directory.get("item", [])

        # Step 1: 明示命名（"infotable" 部分一致）
        for item in items:
            name = item.get("name", "")
            if name.lower().endswith(".xml") and "infotable" in name.lower():
                return name

        # Step 2: フォールバック — primary_doc / index / headers 以外の .xml
        for item in items:
            name = item.get("name", "")
            lname = name.lower()
            if not lname.endswith(".xml"):
                continue
            if lname == "primary_doc.xml":
                continue
            if "-index" in lname or "-headers" in lname:
                continue
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
