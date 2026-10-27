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
    "name": ("campaign name", "campaign", "name", "اسم الحملة", "الحملة", "الحملة الإعلانية"),
    "status": ("campaign status", "campaign delivery", "delivery", "status", "التسليم", "حالة الحملة", "الحالة"),
    "budget": ("daily budget", "budget", "الميزانية اليومية", "الميزانية"),
    "spend": ("amount spent", "cost", "spend", "المبلغ المنفق", "التكلفة", "الإنفاق"),
    "impressions": ("impressions", "impr.", "impr", "مرات الظهور", "مرات الإظهار"),
    "clicks": ("clicks", "link clicks", "النقرات", "نقرات الرابط"),
    "conversions": ("conversions", "conv.", "purchases", "website purchases", "results",
                    "التحويلات", "المشتريات", "النتائج"),
}
PAUSED_WORDS = {"paused", "inactive", "off", "removed", "ended", "completed", "archived", "deleted",
                "مؤقت", "متوقف", "غير نشط", "مكتمل"}
SKIP_NAME = re.compile(r"^(total|totals|grand total|account total|إجمالي|المجموع)\b", re.I)
CURRENCY_IN_HEADER = re.compile(r"\(([A-Za-z]{3})\)")
NON_NUMERIC = re.compile(r"[^0-9.\-]")


def _decode(raw: bytes) -> str:
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def _split_rows(text: str) -> list[list[str]]:
    sample = "\n".join(text.splitlines()[:HEADER_SCAN_ROWS + 5])
    delimiter = max(",;\t", key=sample.count)
    return [[c.strip() for c in row] for row in csv.reader(io.StringIO(text), delimiter=delimiter)]


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
    cleaned = NON_NUMERIC.sub("", cell.translate(ARABIC_DIGITS).replace(",", ""))
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


def _currency(headers: list[str], body: list[list[str]], mapping: dict[str, int]) -> str | None:
    if "spend" in mapping:
        found = CURRENCY_IN_HEADER.search(headers[mapping["spend"]])
        if found:
            return found.group(1).upper()
    for i, h in enumerate(headers):
        if _norm(h) in ("currency code", "currency", "العملة") and body and i < len(body[0]):
            return body[0][i].upper() or None
    return None


def _aggregate(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    """Ad-set or ad level exports repeat the campaign name; sum them back to one row per campaign."""
    merged: dict[str, dict[str, Any]] = {}
    for row in rows:
        into = merged.get(row["name"])
        if into is None:
            merged[row["name"]] = dict(row)
            continue
        for key in ("budget", "cost", "impressions", "clicks", "conversions"):
            into[key] += row[key]
        if into["status"] == "PAUSED":
            into["status"] = row["status"]
    return list(merged.values()), len(merged) != len(rows)


def _finish(row: dict[str, Any]) -> dict[str, Any]:
    row["ctr"] = row["clicks"] / row["impressions"] * 100.0 if row["impressions"] > 0 else 0.0
    row["cpa"] = row["cost"] / row["conversions"] if row["conversions"] > 0 else None
    row["today_cost"] = 0.0
    return row


def _warnings(headers: list[str], mapping: dict[str, int], rows: list[dict[str, Any]], aggregated: bool) -> list[str]:
    out: list[str] = []
    labels = {"spend": "spend", "impressions": "impressions", "clicks": "clicks", "conversions": "conversions"}
    for field, label in labels.items():
        if field not in mapping:
            out.append(f"No {label} column recognised (looked for: {', '.join(ALIASES[field][:4])}). "
                       f"{label.capitalize()} shows as 0 for every row, so do not trust totals or CPA.")
    if "spend" in mapping and rows and not any(r["cost"] for r in rows):
        out.append("The spend column is present but every value is empty or zero. Check the export date range.")
    if "conversions" in mapping and _norm(headers[mapping["conversions"]]) in ("results", "النتائج"):
        out.append("'Results' depends on each campaign's objective (messages, leads, clicks, purchases). "
                   "Check 'Result indicator' before comparing CPA across campaigns.")
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
    rows, aggregated = _aggregate(rows)
    return {
        "rows": [_finish(r) for r in rows],
        "warnings": _warnings(headers, mapping, rows, aggregated),
        "columns": {f: headers[i] for f, i in mapping.items()},
        "currency": _currency(headers, body, mapping),
    }
