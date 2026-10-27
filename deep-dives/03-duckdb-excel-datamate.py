"""Chuyên đề 3 — DuckDB làm execution engine & xử lý "Excel bẩn" cho DataMate.

Mục đích
--------
Code minh họa, chạy hoàn toàn OFFLINE trong Docker, không gọi API, không tải
extension, không truy cập mạng. Nó không phải pipeline thi đấu hoàn chỉnh và
chưa từng chạy trên dữ liệu ZAIC thật: mọi tên bảng/cột trong ví dụ SQL đều là
placeholder mà người dùng phải khớp lại với schema + rulebook của đúng split.

Nguyên tắc xuyên suốt
----------------------
1. Không đoán mù. Số hoặc ngày mơ hồ không được ép kiểu lặng lẽ: hàm trả về
   ``None`` kèm một ``ParseIssue`` để tầng quyết định (abstain/unanswerable)
   nhìn thấy.
2. ``calendar.csv`` của đúng split là chuẩn cho mọi câu hỏi âm lịch. Thư viện
   âm lịch chỉ là fallback và phải được gắn cờ là fallback — không bao giờ
   thay lịch Việt Nam bằng lịch Trung Quốc.
3. DuckDB là engine thực thi duy nhất cho câu hỏi đã làm sạch; Python chỉ làm
   tiền xử lý (đọc Excel bẩn) và kiểm chứng, không phải nơi tính toán chính.

Thư viện dùng trong file này (đã kiểm chứng trong venv thử ngày 2026-10-27):
    duckdb   2.0.0  (MIT theo tài liệu thứ cấp — kiểm tra lại LICENSE khi đóng Docker)
    pandas   3.1.0  (BSD-3-Clause theo tài liệu thứ cấp — kiểm tra lại LICENSE khi đóng Docker)
    openpyxl 3.1.5  (MIT, xác nhận từ metadata gói trong venv thử)
Phiên bản pin trong Dockerfile phải được kiểm tra lại lúc build; đừng copy
số phiên bản ở đây mà không kiểm tra.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Literal

import duckdb
import pandas as pd
from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet


# ---------------------------------------------------------------------------
# Kiểu dữ liệu chung cho audit
# ---------------------------------------------------------------------------


@dataclass
class ParseIssue:
    """Một ô/giá trị không thể chuyển đổi an toàn — không được bỏ qua lặng lẽ."""

    kind: str  # ví dụ: "ambiguous_number", "invalid_date", "merged_id_not_filled"
    field: str
    raw: Any
    message: str


@dataclass
class CleanedSheet:
    """Kết quả đọc một sheet Excel sau tiền xử lý."""

    frame: pd.DataFrame
    header_mapping: dict[str, str] = field(default_factory=dict)
    """Map: tên cột SQL-safe -> tên gốc (các phần header nối bằng ' | ')."""
    issues: list[ParseIssue] = field(default_factory=list)
    dropped_blank_rows: int = 0


# ---------------------------------------------------------------------------
# 1. Số kiểu Việt Nam
# ---------------------------------------------------------------------------

# Lưu ý: nhóm hàng nghìn phải lặp ít nhất 2 lần (``1.000.000``) mới xác
# định duy nhất. ``1.500`` chỉ có một nhóm 3 chữ số nên ở chế độ auto là
# MƠ HỒ (1500 hay 1.5) và phải bị gắn cờ, không được đoán.
_VN_THOUSANDS_RE = re.compile(r"^\d{1,3}(?:\.\d{3}){2,}$")
_EN_THOUSANDS_RE = re.compile(r"^\d{1,3}(?:,\d{3}){2,}$")
_SINGLE_SEP_3DIGITS = re.compile(r"^\d{1,3}[.,]\d{3}$")


def parse_vn_number(
    raw: Any, *, locale: Literal["auto", "vn", "en"] = "auto"
) -> tuple[float | None, str | None]:
    """Chuyển một giá trị kiểu tiền/số Việt Nam sang float.

    Quy tắc (không đoán mù):
      * Cả '.' và ',' đều có mặt: dấu phân tách xuất hiện CUỐI CÙNG là dấu
        thập phân, dấu còn lại là hàng nghìn. Ví dụ ``1.000.000,50`` -> 1000000.5
        (kiểu VN) và ``1,000,000.50`` -> 1000000.5 (kiểu US).
      * Chỉ một loại dấu lặp theo nhóm 3 chữ số (``1.000.000`` hoặc
        ``1,000,000``): đó là dấu hàng nghìn.
      * Một dấu duy nhất với đúng 3 chữ số sau nó (``1.500`` / ``1,500``):
        MƠ HỒ — có thể là 1500 (hàng nghìn) hoặc 1.5 (thập phân). Ở chế độ
        ``auto`` hàm trả về ``(None, issue)`` thay vì đoán. Muốn ép, truyền
        ``locale="vn"`` hoặc ``locale="en"`` một cách có chủ đích theo từng cột,
        và ghi lại lựa chọn đó trong audit.
      * Ký tự '%' KHÔNG được chuyển đổi lặng lẽ: phần trăm là một type đáp án
        riêng của DataMate, phải xử lý ở tầng formatter, không phải ở đây.
      * Dấu ngoặc đơn kiểu kế toán ``(1.000)`` được hiểu là số âm.

    Returns:
        (giá trị float hoặc None, thông điệp issue hoặc None).
    """
    if raw is None:
        return None, None
    if isinstance(raw, bool):
        return None, "boolean_not_a_number"
    if isinstance(raw, (int, float)):
        return float(raw), None
    text = str(raw).strip()
    if not text:
        return None, None
    if "%" in text:
        return None, "percent_not_converted_here"
    # Bỏ ký hiệu tiền tệ ở đầu/cuối, giữ lại dấu và chữ số.
    text = re.sub(r"^(VND|VNĐ|₫|đ)\s*|\s*(VND|VNĐ|₫|đ)$", "", text).strip()
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative, text = True, text[1:-1].strip()
    if text.startswith("-"):
        negative, text = True, text[1:].strip()
    text = text.replace("\u00a0", "").replace(" ", "")
    if not re.fullmatch(r"\d+(?:[.,]\d+)*", text):
        return None, f"unparseable_number: {raw!r}"

    def _apply(thousands: str, decimal: str) -> float | None:
        body = text.replace(thousands, "")
        if decimal != ".":
            body = body.replace(decimal, ".")
        # Kiểm tra lại: sau khi bỏ dấu hàng nghìn, phần thập phân (nếu có)
        # không được chứa thêm dấu phân tách.
        try:
            value = float(body)
        except ValueError:
            return None
        return -value if negative else value

    has_dot, has_comma = "." in text, "," in text
    if locale == "vn":
        # Dạng VN hợp lệ: số nguyên thuần ("1000") hoặc nhóm '.' hàng
        # nghìn (mỗi nhóm 3 chữ số), tùy chọn phần thập phân sau ','.
        # "1.5" không phải dạng VN hợp lệ -> issue. Phiên bản trước dùng
        # \d{1,3} ở đầu nên từ chối cả số nguyên 4 chữ số như "1000".
        if re.fullmatch(r"\d+(?:\.\d{3})*(?:,\d+)?", text):
            return _apply(".", ","), None
        return None, f"not_a_valid_vn_number: {raw!r}"
    if locale == "en":
        # Dạng EN hợp lệ: số nguyên thuần hoặc nhóm ',' hàng nghìn,
        # tùy chọn phần thập phân sau '.'.
        if re.fullmatch(r"\d+(?:,\d{3})*(?:\.\d+)?", text):
            return _apply(",", "."), None
        return None, f"not_a_valid_en_number: {raw!r}"
    # locale == "auto"
    if has_dot and has_comma:
        # Dấu cuối cùng là thập phân — quy tắc này xác định duy nhất.
        if text.rfind(".") > text.rfind(","):
            return _apply(",", "."), None
        return _apply(".", ","), None
    if has_dot and _VN_THOUSANDS_RE.match(text):
        return _apply(".", "."), None
    if has_comma and _EN_THOUSANDS_RE.match(text):
        return _apply(",", ","), None
    if _SINGLE_SEP_3DIGITS.match(text):
        return None, f"ambiguous_number (1.500 vs 1.5): {raw!r}"
    # Một dấu duy nhất với 1–2 chữ số sau nó: chỉ có thể là thập phân.
    if has_dot or has_comma:
        return _apply("", "." if has_dot else ","), None
    # Số nguyên thuần. Phiên bản trước trả float(text) mà quên áp dấu
    # âm, nên "-100" và "(100)" đều thành +100.0.
    return (-float(text) if negative else float(text)), None


def parse_vn_money(
    raw: Any, *, locale: Literal["auto", "vn", "en"] = "auto"
) -> tuple[Decimal | None, str | None]:
    """Parse a money cell to ``Decimal``, never via float.

    Contract split (this is the fix for the demo's float-for-money):
    ``parse_vn_number`` returns float and is ONLY for generic quantities
    where a binary-float rounding is acceptable. Any value that will be
    summed, compared, or formatted as an answer amount MUST go through
    this function: it applies the same separator/sign rules as
    :func:`parse_vn_number` but keeps the exact decimal value, so
    0.1 + 0.2 style float artefacts can never leak into a revenue total.
    A caller that converts this Decimal to float before formatting has
    broken the contract, not the parser.
    """
    from decimal import Decimal as _Decimal

    if raw is None:
        return None, None
    if isinstance(raw, bool):
        return None, "boolean_not_a_number"
    if isinstance(raw, int):
        return _Decimal(raw), None
    if isinstance(raw, float):
        # str() round-trips the shortest decimal the float prints as;
        # it does not recover a decimal the float never represented.
        return _Decimal(str(raw)), None
    text = str(raw).strip()
    if not text:
        return None, None
    if "%" in text:
        return None, "percent_not_converted_here"
    text = re.sub(r"^(VND|VNĐ|₫|đ)\s*|\s*(VND|VNĐ|₫|đ)$", "", text).strip()
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative, text = True, text[1:-1].strip()
    if text.startswith("-"):
        negative, text = True, text[1:].strip()
    text = text.replace("\u00a0", "").replace(" ", "")
    if not re.fullmatch(r"\d+(?:[.,]\d+)*", text):
        return None, f"unparseable_number: {raw!r}"
    has_dot, has_comma = "." in text, "," in text
    if locale == "vn":
        if not re.fullmatch(r"\d+(?:\.\d{3})*(?:,\d+)?", text):
            return None, f"not_a_valid_vn_number: {raw!r}"
        body = text.replace(".", "")
        if "," in body:
            body = body.replace(",", ".")
    elif locale == "en":
        if not re.fullmatch(r"\d+(?:,\d{3})*(?:\.\d+)?", text):
            return None, f"not_a_valid_en_number: {raw!r}"
        body = text.replace(",", "")
    elif has_dot and has_comma:
        body = text.replace(",", "") if text.rfind(".") > text.rfind(",") else text.replace(".", "").replace(",", ".")
    elif has_dot and _VN_THOUSANDS_RE.match(text):
        body = text.replace(".", "")
    elif has_comma and _EN_THOUSANDS_RE.match(text):
        body = text.replace(",", "")
    elif _SINGLE_SEP_3DIGITS.match(text):
        return None, f"ambiguous_number (1.500 vs 1.5): {raw!r}"
    elif has_dot or has_comma:
        body = text.replace(",", ".")
    else:
        body = text
    try:
        value = _Decimal(body)
    except Exception:
        return None, f"unparseable_number: {raw!r}"
    return (-value if negative else value), None


def parse_number_column(
    frame: pd.DataFrame,
    column: str,
    *,
    locale: Literal["auto", "vn", "en"] = "auto",
) -> tuple[pd.DataFrame, list[ParseIssue]]:
    """Ép một cột sang số, giữ lại mọi ô mơ hồ dưới dạng None + issue.

    Không bao giờ điền 0 cho ô lỗi: 0 là một giá trị hợp lệ và sẽ làm lệch
    tổng/doanh thu, trong khi None + issue cho phép tầng abstain quyết định.
    """
    out = frame.copy()
    issues: list[ParseIssue] = []
    parsed: list[float | None] = []
    for idx, raw in frame[column].items():
        value, issue = parse_vn_number(raw, locale=locale)
        if issue is not None:
            issues.append(
                ParseIssue(
                    kind="number",
                    field=column,
                    raw=raw,
                    message=f"row {idx}: {issue}",
                )
            )
        parsed.append(value)
    out[column] = pd.Series(parsed, index=frame.index, dtype="Float64")
    return out, issues


# ---------------------------------------------------------------------------
# 2. Ngày kiểu Việt Nam dd/mm/yyyy -> ISO yyyy-mm-dd
# ---------------------------------------------------------------------------

_ISO_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_VN_DATE_RE = re.compile(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})$")


def parse_vn_date(raw: Any) -> tuple[date | None, str | None]:
    """Chuyển một giá trị ngày Việt Nam sang ``datetime.date`` (ISO).

    Quy ước duy nhất được áp dụng: thứ tự dd/mm/yyyy (ngày trước, tháng sau),
    đúng chuẩn Việt Nam. Ngày không hợp lệ theo lịch (31/02, tháng 13, ...)
    KHÔNG được ép kiểu lặng lẽ mà trả về issue. Năm 2 chữ số bị từ chối vì
    mơ hồ (không đoán thế kỷ). Chuỗi ISO yyyy-mm-dd được giữ nguyên sau khi
    kiểm tra tính hợp lệ.
    """
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None, None
    if isinstance(raw, datetime):
        return raw.date(), None
    if isinstance(raw, date):
        return raw, None
    text = str(raw).strip()
    if not text:
        return None, None
    match = _ISO_RE.match(text)
    if match:
        year, month, day = (int(g) for g in match.groups())
    else:
        match = _VN_DATE_RE.match(text)
        if not match:
            return None, f"unparseable_date: {raw!r}"
        day, month, year = (int(g) for g in match.groups())
    try:
        return date(year, month, day), None
    except ValueError:
        return None, f"invalid_calendar_date: {raw!r}"


def parse_date_column(
    frame: pd.DataFrame, column: str
) -> tuple[pd.DataFrame, list[ParseIssue]]:
    """Ép một cột sang ngày ISO, ô lỗi thành None (pandas NaT) + issue."""
    out = frame.copy()
    issues: list[ParseIssue] = []
    parsed: list[date | None] = []
    for idx, raw in frame[column].items():
        value, issue = parse_vn_date(raw)
        if issue is not None:
            issues.append(
                ParseIssue(
                    kind="date",
                    field=column,
                    raw=raw,
                    message=f"row {idx}: {issue}",
                )
            )
        parsed.append(value)
    out[column] = pd.Series(
        pd.to_datetime(pd.Series(parsed, index=frame.index)), index=frame.index
    )
    return out, issues


# ---------------------------------------------------------------------------
# 3. Header nhiều cấp + merged cells + dòng trống
# ---------------------------------------------------------------------------

_ID_LIKE = re.compile(r"(^|_)(id|ma|code|so_)(_|$)", re.IGNORECASE)


def _to_ascii(text: str) -> str:
    """Bỏ dấu tiếng Việt một cách xác định để tạo tên cột SQL-safe.

    Dùng NFKD để tách dấu tổ hợp; riêng ``đ/Đ`` không tách được bằng NFKD
    nên map tay sang ``d/D``. Tên gốc đầy đủ dấu vẫn giữ trong mapping audit,
    nên việc bỏ dấu ở đây chỉ ảnh hưởng tên kỹ thuật, không mất thông tin.
    """
    text = text.replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def flatten_headers(header_rows: list[list[Any]]) -> tuple[list[str], dict[str, str]]:
    """Gộp header nhiều cấp thành tên cột duy nhất, SQL-safe, có audit map.

    Ví dụ header 2 cấp [["Doanh thu", "", "Số lượng"], ["", "Đã trừ CK", ""]]:
    cột 1 -> "Doanh thu | Đã trừ CK" -> "Doanh_thu_Da_tru_CK" (xem mapping).
    Tên trùng nhau được hậu tố _2, _3 một cách xác định (theo thứ tự cột),
    không bao giờ ghi đè lặng lẽ một cột lên cột khác.
    """
    if not header_rows:
        return [], {}
    n_cols = max(len(row) for row in header_rows)
    names: list[str] = []
    mapping: dict[str, str] = {}
    seen: dict[str, int] = {}
    for col in range(n_cols):
        parts = [
            str(row[col]).strip()
            for row in header_rows
            if col < len(row) and row[col] is not None and str(row[col]).strip()
        ]
        original = " | ".join(parts) if parts else f"col_{col + 1}"
        safe = re.sub(r"[^0-9A-Za-z_]+", "_", _to_ascii(original)).strip("_") or f"col_{col + 1}"
        if not safe[0].isalpha() and safe[0] != "_":
            safe = f"c_{safe}"
        count = seen.get(safe, 0) + 1
        seen[safe] = count
        final = safe if count == 1 else f"{safe}_{count}"
        names.append(final)
        mapping[final] = original
    return names, mapping


def _looks_like_id_column(header_name: str) -> bool:
    """Heuristic bảo vệ: cột mã/ID không được forward-fill qua merged range."""
    lowered = header_name.lower()
    return bool(_ID_LIKE.search(lowered) or "mã" in lowered)


def read_excel_sheet(
    path: str | Path,
    *,
    sheet: str | int = 0,
    header_rows: int | None = None,
) -> CleanedSheet:
    """Đọc một sheet .xlsx bẩn thành DataFrame đã làm sạch ở mức cấu trúc.

    Xử lý, theo đúng thứ tự:
      1. Merged cells: điền giá trị ô góc trên-trái vào TOÀN BỘ vùng merge —
         nhưng CHỈ trong vùng đó, không bao giờ tràn sang dòng/cột ngoài vùng.
         Ngoại lệ bảo vệ: nếu cột đích trông như cột mã/ID và vùng merge
         trải trên nhiều dòng, KHÔNG điền (mỗi dòng có thể là một mã khác
         nhau) mà ghi issue để con người/quy tắc nghiệp vụ quyết định.
      2. Dòng trống hoàn toàn: bỏ, đếm số dòng đã bỏ.
      3. Header nhiều cấp: ``header_rows`` cấp đầu tiên là header; nếu
         ``header_rows=None`` thì tự đoán: dòng đầu có >=50% ô trống và dòng
         thứ hai có giá trị -> 2 cấp, ngược lại 1 cấp.
      4. Cột trống hoàn toàn được GIỮ LẠI (schema linking cần thấy nó) và ghi
         issue, không xóa lặng lẽ.

    Lưu ý: openpyxl với ``data_only=True`` đọc giá trị đã tính của công thức,
    không đọc chuỗi công thức; file .xls cũ (không phải .xlsx) không được hỗ trợ.
    """
    workbook = load_workbook(path, data_only=True, read_only=False)
    try:
        ws: Worksheet = workbook[sheet] if isinstance(sheet, str) else workbook.worksheets[sheet]
        rows: list[list[Any]] = [list(row) for row in ws.iter_rows(values_only=True)]
        merged = list(ws.merged_cells.ranges)
    finally:
        workbook.close()
    if not rows:
        return CleanedSheet(frame=pd.DataFrame(), issues=[])
    if header_rows is None:
        first = rows[0]
        empty_ratio = sum(1 for v in first if v is None or str(v).strip() == "") / max(len(first), 1)
        header_rows = 2 if (empty_ratio >= 0.5 and len(rows) > 1) else 1
    header_part, body = rows[:header_rows], rows[header_rows:]
    names, mapping = flatten_headers(header_part)
    n_cols = len(names)
    # Áp merged-cell fill TRÊN body (chỉ số dòng body, không chạm header).
    issues: list[ParseIssue] = []
    # Map (row_idx_body, col_idx) -> giá trị điền, chỉ trong vùng merge.
    filled: dict[tuple[int, int], Any] = {}
    _guard_seen: set[tuple[str, str]] = set()
    for rng in merged:
        # merged range dùng chỉ số 1-based của toàn sheet; header chiếm
        # header_rows dòng đầu, nên dòng body = sheet_row - header_rows - 1.
        top_value = rows[rng.min_row - 1][rng.min_col - 1] if rng.min_row - 1 < len(rows) else None
        for sheet_row in range(rng.min_row, rng.max_row + 1):
            body_row = sheet_row - header_rows - 1
            if body_row < 0:
                continue  # merge nằm trong vùng header: đã xử lý ở flatten.
            for col in range(rng.min_col - 1, rng.max_col):
                if col >= n_cols:
                    continue
                if (
                    rng.max_row - rng.min_row >= 1
                    and _looks_like_id_column(names[col])
                ):
                    # Một issue cho mỗi (vùng merge, cột), không lặp lại theo
                    # từng ô trong vùng.
                    key = (rng.coord, names[col])
                    if key not in _guard_seen:
                        _guard_seen.add(key)
                        issues.append(
                            ParseIssue(
                                kind="merged_id_not_filled",
                                field=names[col],
                                raw=rng.coord,
                                message=(
                                    "merged range spans multiple rows on an ID-like "
                                    "column; not forward-filled"
                                ),
                            )
                        )
                    continue
                filled[(body_row, col)] = top_value
    cleaned_body: list[list[Any]] = []
    dropped = 0
    for r_idx, row in enumerate(body):
        row = list(row) + [None] * max(0, n_cols - len(row))
        row = row[:n_cols]
        for (br, bc), value in filled.items():
            if br == r_idx:
                row[bc] = value
        if all(v is None or (isinstance(v, str) and v.strip() == "") for v in row):
            dropped += 1
            continue
        cleaned_body.append(row)
    frame = pd.DataFrame(cleaned_body, columns=names)
    for col in names:
        if frame[col].isna().all():
            issues.append(
                ParseIssue(
                    kind="empty_column_kept",
                    field=col,
                    raw=None,
                    message="column is entirely empty but kept for schema linking",
                )
            )
    return CleanedSheet(
        frame=frame, header_mapping=mapping, issues=issues, dropped_blank_rows=dropped
    )


# ---------------------------------------------------------------------------
# 4. DuckDB store: một engine thực thi cho CSV / Excel đã làm sạch / SQLite
# ---------------------------------------------------------------------------

_VIEW_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _check_view_name(name: str) -> str:
    """Tên view phải là identifier SQL hợp lệ — chống injection qua tên bảng."""
    if not _VIEW_NAME_RE.match(name):
        raise ValueError(f"invalid view name (must match [A-Za-z_][A-Za-z0-9_]*): {name!r}")
    return name


_WRITE_KEYWORDS = {
    "insert", "update", "delete", "drop", "create", "alter", "truncate",
    "copy", "attach", "detach", "pragma", "call", "execute", "grant",
    "revoke", "merge", "vacuum",
    # NOTE: "replace" is intentionally NOT banned: REPLACE() is a common
    # string function in SELECTs; banning the word would false-positive
    # on legitimate reads. Write-REPLACE (REPLACE INTO) is already
    # rejected by the SELECT/WITH first-token rule above.
}
_FILE_FUNCTIONS = {
    "read_csv", "read_csv_auto", "read_parquet", "read_json", "read_json_auto",
    "read_xlsx", "st_read", "parquet_scan", "csv_scan", "read_blob", "read_text",
}


def _assert_readonly_sql(sql: str) -> None:
    """Reject anything that is not one SELECT/WITH statement.

    Strips leading ``--``/``/* */`` comments first so a write cannot hide
    behind a comment prefix. Keyword matching is whole-word and
    case-insensitive; a keyword inside a string literal is a false
    positive the caller must avoid (this guard is syntactic, not a SQL
    parser -- see :meth:`DuckDBStore.query`).
    """
    if not isinstance(sql, str) or not sql.strip():
        raise ValueError("empty SQL")
    cleaned = sql.strip()
    while cleaned.startswith("--"):
        cleaned = cleaned.split("\n", 1)[1].lstrip() if "\n" in cleaned else ""
    while cleaned.startswith("/*"):
        end = cleaned.find("*/")
        if end == -1:
            raise ValueError("unterminated SQL comment")
        cleaned = cleaned[end + 2:].lstrip()
    first = re.match(r"([A-Za-z]+)", cleaned)
    if first is None or first.group(1).upper() not in ("SELECT", "WITH"):
        raise ValueError("only a single SELECT/WITH statement is allowed")
    body = cleaned[len(first.group(1)):]
    if ";" in body.rstrip().rstrip(";"):
        raise ValueError("multiple SQL statements are not allowed")
    words = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", cleaned.lower()))
    banned = (words & _WRITE_KEYWORDS) | (words & _FILE_FUNCTIONS)
    if banned:
        raise ValueError(f"SQL contains banned keyword/function: {sorted(banned)}")


class DuckDBStore:
    """DuckDB in-memory làm engine thực thi duy nhất cho câu hỏi đã làm sạch.

    Không dùng DuckDB sqlite extension (cần tải về -> vi phạm offline):
    SQLite được đọc bằng module ``sqlite3`` của stdlib rồi register vào DuckDB.
    CSV cũng đi qua pandas sau khi đã kiểm soát kiểu, để mọi nguồn đều qua
    cùng một lớp view thống nhất mà LLM nhìn thấy.
    """

    def __init__(self, database: str = ":memory:") -> None:
        self.con = duckdb.connect(database)
        self.views: list[str] = []

    def register_frame(self, name: str, frame: pd.DataFrame) -> None:
        """Đăng ký một DataFrame thành view có thể truy vấn bằng SQL."""
        _check_view_name(name)
        self.con.register(name, frame)
        if name not in self.views:
            self.views.append(name)

    def load_sqlite(self, path: str | Path, *, tables: Iterable[str] | None = None) -> list[str]:
        """Đọc các bảng SQLite bằng stdlib rồi register vào DuckDB."""
        loaded: list[str] = []
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
            available = [
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            ]
            wanted = list(tables) if tables is not None else available
            for table in wanted:
                if table not in available:
                    raise ValueError(f"SQLite table not found: {table!r}")
                frame = pd.read_sql_query(f'SELECT * FROM "{table}"', conn)
                self.register_frame(table, frame)
                loaded.append(table)
        return loaded

    def load_calendar(
        self,
        path: str | Path,
        *,
        view: str = "calendar",
        columns: dict[str, str] | None = None,
    ) -> None:
        """Nạp ``calendar.csv`` của đúng split thành view lịch âm–dương.

        ``columns`` map tên cột trong file -> tên chuẩn:
        mặc định {"solar_date": "solar_date", "lunar_year": "lunar_year",
        "lunar_month": "lunar_month", "lunar_day": "lunar_day"}.
        Nếu file thiếu bất kỳ cột nào, hàm raise ValueError — không đoán tên
        cột, không tự sinh lịch âm bằng thư viện thay thế.
        """
        mapping = columns or {
            "solar_date": "solar_date",
            "lunar_year": "lunar_year",
            "lunar_month": "lunar_month",
            "lunar_day": "lunar_day",
        }
        frame = pd.read_csv(path)
        missing = [c for c in mapping if c not in frame.columns]
        if missing:
            raise ValueError(f"calendar.csv missing columns: {missing}")
        frame = frame.rename(columns=mapping)
        # dayfirst=True: a dd/mm/yyyy string in calendar.csv must not be
        # silently read as mm/dd/yyyy (pandas defaults are ambiguous for
        # day<=12). ISO yyyy-mm-dd strings are unaffected by dayfirst.
        frame["solar_date"] = pd.to_datetime(
            frame["solar_date"], dayfirst=True, format="mixed"
        ).dt.date
        for col in ("lunar_year", "lunar_month", "lunar_day"):
            frame[col] = frame[col].astype("Int64")
        self.register_frame(view, frame)

    def query(self, sql: str, params: list[Any] | None = None) -> pd.DataFrame:
        """Chạy một câu SQL chỉ-đọc và trả về DataFrame (kết quả nhỏ).

        Giới hạn được THỰC THI ở đây, không chỉ ghi trong docstring như
        phiên bản trước: câu phải bắt đầu bằng SELECT/WITH (sau khi bỏ
        comment), chỉ chứa một statement, và không chứa từ khóa ghi hay
        hàm đọc file (read_csv/read_parquet/...). Đây vẫn là guard cú
        pháp, KHÔNG phải sandbox hệ điều hành: DuckDB chạy cùng process
        vẫn có thể bị khai thác qua hàm khác, nên pipeline thật cần
        chạy DuckDB trong process riêng với filesystem bị giới hạn nếu
        SQL do model sinh ra được coi là không tin cậy.
        """
        _assert_readonly_sql(sql)
        return self.con.execute(sql, params or []).fetchdf()

    def close(self) -> None:
        """Đóng kết nối DuckDB."""
        self.con.close()


# ---------------------------------------------------------------------------
# 5. SQL mẫu cho câu hỏi gắn mốc âm lịch (dùng calendar.csv làm chuẩn)
# ---------------------------------------------------------------------------

def tet_window_sql(
    tet_lunar_year: int,
    *,
    orders_view: str = "orders",
    lines_view: str = "order_lines",
    calendar_view: str = "calendar",
    order_date_col: str = "order_date",
    order_id_col: str = "order_id",
    line_order_col: str = "order_id",
    line_amount_col: str = "line_amount_after_discount",
    line_status_col: str = "line_status",
) -> tuple[str, list[Any]]:
    """SQL doanh thu trong cửa sổ Tết của một năm âm lịch.

    Cửa sổ Tết (theo rulebook đã ghi nhận cho DataMate, phải đối chiếu lại
    với rulebook của đúng split trước khi dùng): từ 23 tháng Chạp năm âm
    lịch Y đến mùng 10 tháng Giêng năm âm lịch Y+1. Vì cửa sổ cắt qua hai
    năm âm lịch nên điều kiện phải là OR của hai nửa — một điều kiện
    ``lunar_year = Y`` duy nhất sẽ MẤT nửa tháng Giêng.

    Các tên cột/bảng là placeholder: khớp lại với schema thật và với quy tắc
    doanh thu của split.

    Quy tắc loại trừ (SỬA SO VỚI PHIÊN BẢN TRƯỚC): phiên bản trước chỉ
    lọc dòng ``line_status NOT IN ('cancelled', 'returned')``. Rulebook
    đã ghi nhận cho DataMate nói doanh thu loại "đơn bị hủy / đơn có
    hàng trả" -- tức loại ở MỨC ĐƠN HÀNG: một đơn có bất kỳ dòng trả nào
    thì toàn bộ đơn bị loại, kể cả các dòng còn tốt của nó. SQL dưới
    đây thực thi mức đơn hàng bằng NOT EXISTS, và giữ thêm lọc dòng
    như một vành đai thứ hai. ĐÂY LÀ DIỄN GIẢI của cụm "any-returned
    orders" trong ghi chú rulebook, CHƯA đối chiếu nguyên văn rulebook
    của đúng split -- nếu rulebook thật chỉ loại theo dòng, bỏ mệnh đề
    NOT EXISTS đi và ghi lại lý do. Đừng dùng SQL này mà không kiểm
    tra điểm đó.

    Returns:
        (câu SQL có placeholder ``?``, danh sách tham số theo thứ tự).
    """
    for name in (orders_view, lines_view, calendar_view):
        _check_view_name(name)
    sql = f"""
    WITH tet_dates AS (
        SELECT solar_date
        FROM {calendar_view}
        WHERE (lunar_year = ? AND lunar_month = 12 AND lunar_day >= 23)
           OR (lunar_year = ? AND lunar_month = 1 AND lunar_day <= 10)
    )
    SELECT SUM(l.{line_amount_col}) AS tet_revenue
    FROM {orders_view} o
    JOIN tet_dates c ON o.{order_date_col} = c.solar_date
    JOIN {lines_view} l ON l.{line_order_col} = o.{order_id_col}
    WHERE l.{line_status_col} NOT IN ('cancelled', 'returned')
      AND NOT EXISTS (
          SELECT 1 FROM {lines_view} l2
          WHERE l2.{line_order_col} = o.{order_id_col}
            AND l2.{line_status_col} IN ('cancelled', 'returned')
      )
    """
    return sql, [tet_lunar_year, tet_lunar_year + 1]


def lunar_day_sql(
    lunar_month: int,
    lunar_day: int,
    *,
    orders_view: str = "orders",
    calendar_view: str = "calendar",
    order_date_col: str = "order_date",
) -> tuple[str, list[Any]]:
    """SQL cho câu hỏi gắn một ngày âm lịch cố định (ví dụ rằm tháng 7).

    Rằm tháng 7 = lunar_month 7, lunar_day 15. Không cần biết năm dương
    lịch tương ứng: join qua ``calendar`` sẽ tự cho ra đúng ngày dương
    của từng năm có trong dữ liệu. Nếu cần giới hạn một năm âm lịch cụ thể,
    thêm điều kiện ``lunar_year = ?``.
    """
    for name in (orders_view, calendar_view):
        _check_view_name(name)
    sql = f"""
    SELECT o.*
    FROM {orders_view} o
    JOIN {calendar_view} c ON o.{order_date_col} = c.solar_date
    WHERE c.lunar_month = ? AND c.lunar_day = ?
    """
    return sql, [lunar_month, lunar_day]


# ---------------------------------------------------------------------------
# Demo tổng hợp (không phải dữ liệu ZAIC) — chạy để kiểm tra code
# ---------------------------------------------------------------------------


def _demo() -> None:
    """Chạy demo trên dữ liệu tổng hợp: Tết 2025 + rằm tháng 7.

    Tết Ất Tỵ: 23 Chạp năm Giáp Thìn ~ 22/01/2025 dương, mùng 10 tháng Giêng
    năm Ất Tỵ ~ 07/02/2025 dương. Demo chỉ dùng vài ngày mẫu quanh cửa sổ để
    chứng minh join qua calendar hoạt động; KHÔNG dùng số liệu này làm bằng
    chứng cho bất kỳ câu hỏi ZAIC nào.
    """
    print("== VN number ==")
    for raw in ("1.000.000,50", "1,000,000.50", "1.000.000", "1,5", "1.500", "31/02/2025"):
        if "/" in str(raw) and raw != "1,5":
            print(f"  {raw!r} -> date {parse_vn_date(raw)}")
        else:
            print(f"  {raw!r} -> number {parse_vn_number(raw)}")
    print("== headers ==")
    names, mapping = flatten_headers([["Doanh thu", "", "Số lượng"], ["", "Đã trừ CK", ""]])
    print(f"  names={names} mapping={mapping}")

    store = DuckDBStore()
    calendar = pd.DataFrame(
        {
            "solar_date": pd.to_datetime(
                ["2025-01-22", "2025-01-23", "2025-02-07", "2025-02-08", "2025-09-06"]
            ).date,
            "lunar_year": [2024, 2025, 2025, 2025, 2025],
            "lunar_month": [12, 12, 1, 1, 7],
            "lunar_day": [23, 24, 10, 11, 15],
        }
    )
    # Lưu ý: dòng 2025-01-22 ở đây gán lunar (2024, 12, 23) theo quy ước demo;
    # dữ liệu thật phải lấy từ calendar.csv của split, không tự gán.
    store.register_frame("calendar", calendar)
    orders = pd.DataFrame(
        {
            "order_id": [1, 2, 3, 4],
            "order_date": pd.to_datetime(
                ["2025-01-22", "2025-02-07", "2025-02-08", "2025-09-06"]
            ).date,
        }
    )
    lines = pd.DataFrame(
        {
            "order_id": [1, 2, 3, 4],
            "line_amount_after_discount": [100.0, 200.0, 999.0, 50.0],
            "line_status": ["ok", "ok", "ok", "ok"],
        }
    )
    store.register_frame("orders", orders)
    store.register_frame("order_lines", lines)
    sql, params = tet_window_sql(2024)
    print("== Tet window revenue (lunar year 2024, demo) ==")
    print(store.query(sql, params).to_string(index=False))
    sql2, params2 = lunar_day_sql(7, 15)
    print("== Orders on lunar 15/7 (demo) ==")
    print(store.query(sql2, params2).to_string(index=False))
    store.close()


if __name__ == "__main__":
    _demo()
