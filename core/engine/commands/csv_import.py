"""Parse an Ads Manager / Google Ads CSV export into campaign rows, loudly.

Real exports are messy: title lines above the header, `Amount spent (USD)` style headers, `--` for
empty cells, `Total:` rows, UTF-16 tab-separated files, Arabic column names. The rule here is that
a column we cannot recognise must produce a WARNING in the report, never a silent zero.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Any

from utils import sanitize_text

HEADER_SCAN_ROWS = 15
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬", "0123456789.,")

# field -> accepted normalised headers, best first (parentheses stripped, lower case).
ALIASES: dict[str, tuple[str, ...]] = {
    "name": ("campaign name", "campaign", "ad set name", "ad name", "name", "اسم الحملة", "الحملة",
             "الحملة الإعلانية", "اسم المجموعة الإعلانية"),
    "indicator": ("result indicator", "مؤشر النتيجة"),
    "status": ("campaign status", "campaign delivery", "ad set delivery", "ad delivery", "delivery", "status", "التسليم", "حالة الحملة", "الحالة"),
    "budget": ("daily budget", "ad set budget", "budget", "الميزانية اليومية", "الميزانية"),
    "spend": ("amount spent", "cost", "spend", "المبلغ المنفق", "التكلفة", "الإنفاق"),
    "impressions": ("impressions", "impr.", "impr", "مرات الظهور", "مرات الإظهار"),
    "clicks": ("clicks", "link clicks", "النقرات", "نقرات الرابط"),
    "conversions": ("conversions", "conv.", "purchases", "website purchases", "results",
                    "التحويلات", "المشتريات", "النتائج"),
}
NON_CONVERSION_RESULTS = {"link_click", "reach", "impressions", "post_engagement", "video_view", "landing_page_view"}
LEVELS = {"ad set name": "ad set", "ad name": "ad", "اسم المجموعة الإعلانية": "ad set"}
PAUSED_WORDS = {"paused", "inactive", "off", "removed", "ended", "completed", "archived", "deleted",
                "مؤقت", "متوقف", "غير نشط", "مكتمل"}
SKIP_NAME = re.compile(r"^(total|totals|grand total|account total|إجمالي|المجموع)\s*(:.*)?$", re.I)
CURRENCY_IN_HEADER = re.compile(r"\(([A-Za-z]{3})\)")
NON_NUMERIC = re.compile(r"[^0-9.\-]")
NON_NUMERIC_KEEP_SEP = re.compile(r"[^0-9.,\-]")
THOUSANDS_ONLY = re.compile(r"^-?\d{1,3}(,\d{3})+$")


def _decode(raw: bytes) -> str:
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def _split_rows(text: str) -> list[list[str]]:
    """Try each delimiter and keep the one that exposes the widest campaign header row."""
    best: list[list[str]] = []
    best_width = -1
    for delimiter in ",;\t":
        rows = [[c.strip() for c in row] for row in csv.reader(io.StringIO(text), delimiter=delimiter)]
        start = _find_header(rows)
        width = len(rows[start]) if start is not None else 0
        if width > best_width:
            best, best_width = rows, width
    return best


def _norm(header: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\([^)]*\)", "", header)).strip().lower()


def _find_header(rows: list[list[str]]) -> int | None:
    names = set(ALIASES["name"])
    for i, row in enumerate(rows[:HEADER_SCAN_ROWS]):
        if sum(1 for c in row if c) >= 3 and any(_norm(c) in names for c in row):
            return i
    return None


def to_number(cell: str) -> float | None:
    """'1,234.5', '12%', 'EGP 1,200', '--' -> number or None (never raises)."""
    text = NON_NUMERIC_KEEP_SEP.sub("", cell.translate(ARABIC_DIGITS))
    if "," in text and "." in text:      # the last separator is the decimal mark: 1.234,50 or 1,234.50
        decimal = "," if text.rfind(",") > text.rfind(".") else "."
        text = text.replace("," if decimal == "." else ".", "").replace(decimal, ".")
    elif "," in text:                    # 1,234 / 1,234,567 are thousands; 12,5 / 1234,50 are decimals
        text = text.replace(",", "") if THOUSANDS_ONLY.match(text) else text.replace(",", ".")
    cleaned = NON_NUMERIC.sub("", text)
    if cleaned in ("", "-", "."):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _map_columns(headers: list[str]) -> dict[str, int]:
    """field -> column index, taking the best-ranked alias present."""
    normed = [_norm(h) for h in headers]
    mapping: dict[str, int] = {}
    for field, aliases in ALIASES.items():
        for alias in aliases:
            if alias in normed:
                mapping[field] = normed.index(alias)
                break
    return mapping


def _status(raw: str) -> str:
    text = raw.strip().lower().replace("_", " ")
    if not text:
        return "ENABLED"
    return "PAUSED" if text in PAUSED_WORDS else text.upper()


def _currencies(headers: list[str], body: list[list[str]], mapping: dict[str, int]) -> set[str]:
    if "spend" in mapping:
        found = CURRENCY_IN_HEADER.search(headers[mapping["spend"]])
        if found:
            return {found.group(1).upper()}
    for i, h in enumerate(headers):
        if _norm(h) in ("currency code", "currency", "العملة"):
            return {r[i].upper() for r in body if i < len(r) and r[i] and not SKIP_NAME.match(r[i])}
    return set()


def _aggregate(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    """Ad-set or ad level exports repeat the campaign name; sum them back to one row per campaign."""
    merged: dict[str, dict[str, Any]] = {}
    for row in rows:
        into = merged.get(row["name"])
        if into is None:
            merged[row["name"]] = dict(row)
            continue
        for key in ("cost", "impressions", "clicks", "conversions"):
            into[key] += row[key]
        into["budget"] = max(into["budget"], row["budget"])   # CBO repeats the campaign budget per ad set
        if into["status"] == "PAUSED":
            into["status"] = row["status"]
    return list(merged.values()), len(merged) != len(rows)


def _unique_names(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ad set names repeat across campaigns; they are different rows, so number the repeats instead of merging."""
    seen: dict[str, int] = {}
    for row in rows:
        seen[row["name"]] = seen.get(row["name"], 0) + 1
        if seen[row["name"]] > 1:
            row["name"] = f"{row['name']} ({seen[row['name']]})"
    return rows


def _conversions_basis(headers: list[str], body: list[list[str]], mapping: dict[str, int]) -> str | None:
    """What 'Results' counts: the single result type, or 'mixed' / 'unknown' / 'non_conversion'. None if no Results column."""
    if "conversions" not in mapping or _norm(headers[mapping["conversions"]]) not in ("results", "النتائج"):
        return None
    if "indicator" not in mapping:
        return "unknown"
    kinds = {r[mapping["indicator"]].split(":")[-1].strip() for r in body
             if mapping["indicator"] < len(r) and r[mapping["indicator"]].strip()}
    kinds.discard("")
    if len(kinds) != 1:
        return "mixed" if kinds else "unknown"
    kind = next(iter(kinds))
    return "non_conversion" if kind in NON_CONVERSION_RESULTS else kind


def _period(headers: list[str], body: list[list[str]]) -> str | None:
    """'2026-09-27 to 2026-10-26' from Meta's Reporting starts / ends columns, when present."""
    cols = {_norm(h): i for i, h in enumerate(headers)}
    if "reporting starts" not in cols or "reporting ends" not in cols:
        return None
    starts = [r[cols["reporting starts"]] for r in body if cols["reporting starts"] < len(r) and r[cols["reporting starts"]]]
    ends = [r[cols["reporting ends"]] for r in body if cols["reporting ends"] < len(r) and r[cols["reporting ends"]]]
    return f"{min(starts)} to {max(ends)}" if starts and ends else None


def _finish(row: dict[str, Any]) -> dict[str, Any]:
    row["ctr"] = row["clicks"] / row["impressions"] * 100.0 if row["impressions"] > 0 else 0.0
    row["cpa"] = row["cost"] / row["conversions"] if row["conversions"] > 0 else None
    row["today_cost"] = 0.0
    return row


def _warnings(headers: list[str], mapping: dict[str, int], rows: list[dict[str, Any]], aggregated: bool,
              currencies: set[str], level: str, basis: str | None) -> list[str]:
    out: list[str] = []
    labels = {"spend": "spend", "impressions": "impressions", "clicks": "clicks", "conversions": "conversions"}
    for field, label in labels.items():
        if field not in mapping:
            out.append(f"No {label} column recognised (looked for: {', '.join(ALIASES[field][:4])}). "
                       f"{label.capitalize()} shows as 0 for every row, so do not trust totals or CPA.")
    if "spend" in mapping and rows and not any(r["cost"] for r in rows):
        out.append("The spend column is present but every value is empty or zero. Check the export date range.")
    if level != "campaign":
        out.append(f"This is an {level}-level export: each row is an {level}, not a campaign. "
                   "Calls and the score are per " + level + ".")
    if basis in ("mixed", "unknown", "non_conversion"):
        out.append("'Results' counts a different thing per objective (messages, leads, clicks, purchases"
                   + (", reach or clicks here" if basis == "non_conversion" else "")
                   + "). Roles never say Scale on it; export a purchase or lead column to unlock that.")
    if len(currencies) > 1:
        out.append(f"The file mixes currencies ({', '.join(sorted(currencies))}); totals add them together as if "
                   "they were one currency. Export one currency at a time.")
    if aggregated:
        out.append("The file has several rows per campaign (ad set or ad level); they were summed per campaign.")
    used = set(mapping.values())
    unknown = [sanitize_text(h, 40) for i, h in enumerate(headers) if h and i not in used]
    if unknown:
        out.append("Columns ignored: " + ", ".join(unknown[:12]) + (" ..." if len(unknown) > 12 else ""))
    return out


def parse_export(path: Path) -> dict[str, Any]:
    """Returns {rows, warnings, columns, currency}; raises ValueError with a helpful message."""
    rows_raw = _split_rows(_decode(path.read_bytes()))
    start = _find_header(rows_raw)
    if start is None:
        first = next((r for r in rows_raw if any(r)), [])
        raise ValueError("Could not find a campaign-name column (looked for: campaign, campaign name, "
                         f"اسم الحملة). First row seen: {first[:8]}")
    headers, body = rows_raw[start], [r for r in rows_raw[start + 1:] if any(r)]
    mapping = _map_columns(headers)

    def cell(row: list[str], field: str) -> str:
        return row[mapping[field]] if field in mapping and mapping[field] < len(row) else ""

    rows: list[dict[str, Any]] = []
    for r in body:
        name = sanitize_text(cell(r, "name"), 120)
        if not re.search(r"\w", name) or any(SKIP_NAME.match(c) for c in r[:3]):
            continue  # blank, "--", or a "Total: Account" row (Google puts it in the first column)
        rows.append({
            "name": name, "status": _status(cell(r, "status")),
            "budget": to_number(cell(r, "budget")) or 0.0, "cost": to_number(cell(r, "spend")) or 0.0,
            "impressions": int(to_number(cell(r, "impressions")) or 0),
            "clicks": int(to_number(cell(r, "clicks")) or 0),
            "conversions": to_number(cell(r, "conversions")) or 0.0,
        })
    if not rows:
        raise ValueError("The file has a header but no campaign rows (only totals or blank lines).")
    level = LEVELS.get(_norm(headers[mapping["name"]]), "campaign")
    rows, aggregated = _aggregate(rows) if level == "campaign" else (_unique_names(rows), False)
    currencies = _currencies(headers, body, mapping)
    basis = _conversions_basis(headers, body, mapping)
    return {
        "level": level, "conversions_basis": basis, "period": _period(headers, body),
        "rows": [_finish(r) for r in rows],
        "warnings": _warnings(headers, mapping, rows, aggregated, currencies, level, basis),
        "columns": {f: headers[i] for f, i in mapping.items()},
        "currency": next(iter(currencies)) if len(currencies) == 1 else None,
    }
