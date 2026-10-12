"""foundry.py CLI surface: economics flags and confirm semantics."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def foundry(*args, cwd=ROOT):
    return subprocess.run([sys.executable, str(ROOT / "foundry.py"), *args], cwd=cwd,
                          capture_output=True, text=True, timeout=60)


def test_economics_breakeven_via_foundry_cli_matches_calc():
    r = foundry("economics", "breakeven", "--price", "499", "--cogs", "150", "--shipping", "45",
                "--fees", "3", "--confirm", "0.85", "--deliver", "0.78", "--return-cost", "30", "--json")
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert round(out["break_even_cpa_per_placed_order"], 3) == 185.538


def test_economics_missing_input_fails_clearly():
    r = foundry("economics", "breakeven", "--price", "499")
    assert r.returncode == 2 and "--cogs is required" in r.stderr
