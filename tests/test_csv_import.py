"""campaigns import must read real-world export shapes and WARN, never silently zero, on what it can't read.
Fixtures mirror documented Meta Ads Manager and Google Ads UI exports (not captured from a client)."""
import pytest

from commands.csv_import import parse_export, to_number

META_EN = (
    "Reporting starts,Reporting ends,Campaign name,Delivery,Budget,Results,Result indicator,Impressions,"
    "Clicks (all),Amount spent (USD)\n"
    "2026-10-01,2026-10-27,GE_MC1_Messages,active,10.00,66,actions:onsite_conversion.messaging_conversation_started_7d,"
    "20643,1555,45.21\n"
    "2026-10-01,2026-10-27,Community Building,inactive,5.00,1,actions:link_click,27523,3685,37.26\n"
    ",,,,,,,48166,5240,82.47\n"
)
GOOGLE_EN = (
    "Campaign report\n"
    "October 1, 2026 - October 27, 2026\n"
    "Campaign status,Campaign,Budget,Impr.,Clicks,Cost,Conversions,Currency code\n"
    "Enabled,KSA | Search | Brand,200.00,\"20,000\",\"1,200\",\"1,400.50\",40.00,SAR\n"
    "Paused,UAE PMax,100.00,\" --\",\" --\",0.00,\" --\",SAR\n"
    "Total: Account,--,\"20,000\",\"1,200\",\"1,400.50\",40.00,\n"
)


def write(tmp_path, text, encoding="utf-8", name="export.csv"):
    path = tmp_path / name
    path.write_bytes(text.encode(encoding))
    return path


def test_meta_english_export_reads_spend_despite_currency_suffix(tmp_path):
    got = parse_export(write(tmp_path, META_EN))
    assert [r["name"] for r in got["rows"]] == ["GE_MC1_Messages", "Community Building"]
    first = got["rows"][0]
    assert first["cost"] == 45.21 and first["impressions"] == 20643 and first["clicks"] == 1555
    assert first["conversions"] == 66 and round(first["cpa"], 2) == 0.69
    assert got["rows"][1]["status"] == "PAUSED"
    assert got["currency"] == "USD"
    assert any("Results" in w for w in got["warnings"])


def test_google_export_skips_title_lines_totals_and_dashes(tmp_path):
    got = parse_export(write(tmp_path, GOOGLE_EN))
    assert [r["name"] for r in got["rows"]] == ["KSA / Search / Brand", "UAE PMax"]
    ksa, uae = got["rows"]
    assert ksa["cost"] == 1400.5 and ksa["impressions"] == 20000 and ksa["status"] == "ENABLED"
    assert uae["status"] == "PAUSED" and uae["impressions"] == 0 and uae["cpa"] is None
    assert got["currency"] == "SAR"


def test_utf16_tab_separated_google_export(tmp_path):
    text = GOOGLE_EN.replace('"', "").replace(",", "\t").replace("20\t000", "20000")
    # only the data rows carry thousands separators, so rebuild a clean TSV instead of regex-patching
    tsv = ("Campaign report\nOctober 2026\n"
           "Campaign status\tCampaign\tImpr.\tClicks\tCost\tConversions\n"
           "Enabled\tBrand\t1000\t100\t50.5\t5\n")
    got = parse_export(write(tmp_path, tsv, encoding="utf-16"))
    assert got["rows"][0]["cost"] == 50.5 and got["rows"][0]["conversions"] == 5


def test_semicolon_delimiter(tmp_path):
    got = parse_export(write(tmp_path, "Campaign;Spend;Impressions;Clicks;Conversions\nA;10;1000;50;2\n"))
    assert got["rows"][0]["cost"] == 10 and got["rows"][0]["clicks"] == 50


def test_arabic_headers_and_digits(tmp_path):
    text = "اسم الحملة,التسليم,النتائج,مرات الظهور,النقرات,المبلغ المنفق (SAR)\nحملة رمضان,active,٤,٢٠٠٠,١٠٠,٥٠٫٥\n"
    got = parse_export(write(tmp_path, text))
    row = got["rows"][0]
    assert row["name"] == "حملة رمضان" and row["cost"] == 50.5 and row["impressions"] == 2000
    assert row["conversions"] == 4 and got["currency"] == "SAR"


def test_missing_spend_column_warns_instead_of_silent_zero(tmp_path):
    got = parse_export(write(tmp_path, "Campaign,Impressions,Clicks\nA,1000,50\n"))
    assert any("No spend column recognised" in w for w in got["warnings"])
    assert any("No conversions column recognised" in w for w in got["warnings"])


def test_adset_level_rows_are_summed_per_campaign(tmp_path):
    text = ("Campaign name,Ad set name,Amount spent (USD),Impressions,Clicks,Purchases\n"
            "C1,AS1,10,100,5,1\nC1,AS2,20,200,10,2\nC2,AS1,5,50,1,0\n")
    got = parse_export(write(tmp_path, text))
    c1 = next(r for r in got["rows"] if r["name"] == "C1")
    assert c1["cost"] == 30 and c1["impressions"] == 300 and c1["conversions"] == 3
    assert any("summed per campaign" in w for w in got["warnings"])


def test_no_campaign_column_is_a_clear_error(tmp_path):
    with pytest.raises(ValueError, match="campaign-name column"):
        parse_export(write(tmp_path, "Foo,Bar,Baz\n1,2,3\n"))


def test_only_totals_is_an_error(tmp_path):
    with pytest.raises(ValueError, match="no campaign rows"):
        parse_export(write(tmp_path, "Campaign,Cost,Clicks\nTotal: Account,10,5\n"))


@pytest.mark.parametrize("cell,expected", [("1,234.5", 1234.5), ("12%", 12.0), ("EGP 1,200", 1200.0),
                                           ("--", None), (" --", None), ("", None), ("abc", None)])
def test_to_number(cell, expected):
    assert to_number(cell) == expected
