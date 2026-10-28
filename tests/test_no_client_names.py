"""Private client or brand names must never ship in the public repo. Patterns are built from fragments so
this file does not itself contain the names it forbids."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = re.compile("|".join(("grow" + r"[-_ ]?" + "edge", "etla" + "ala", "aqar" + "verse", "wil" + "lma")), re.I)
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "dist", "node_modules"}
TEXT = {".py", ".md", ".txt", ".json", ".yml", ".yaml", ".toml", ".cfg", ".html", ".svg"}


def test_no_client_or_brand_names_in_tracked_text():
    hits = []
    for path in ROOT.rglob("*"):
        if path.suffix.lower() not in TEXT or SKIP_DIRS & set(path.relative_to(ROOT).parts) or not path.is_file():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if FORBIDDEN.search(line):
                hits.append(f"{path.relative_to(ROOT)}:{number}")
    assert not hits, f"client names found: {hits[:10]}"
