"""smoke_test.py — one command, objective proof this kernel actually works.

Run: python scripts/smoke_test.py

This is not a code review or a README claim — it exercises the real,
live behavior a buyer would care about and reports a clear pass/fail per
check, plus a final tally. Exit code 0 only if every check passes.

Why this exists: "trust me, it works" isn't something you can hand a buyer
(or verify yourself after a change) without re-running the manual walkthrough
by hand every time. This is that walkthrough, automated, self-cleaning, and
repeatable — run it after every change to this repo, and hand it to anyone
evaluating whether to buy this kernel so they can verify it themselves
instead of taking your word for it.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ENGINE_DIR = REPO_ROOT / "core" / "engine"
DEMO_TENANT = REPO_ROOT / "02_Active_Clients" / "Aurora_Skincare"
DEMO_SIGNAL = DEMO_TENANT / "signals" / "2026-01-15-vitamin-c-serum-content-opportunity.md"

results: list[tuple[str, bool, str]] = []


def check(name: str, fn) -> None:
    try:
        ok, detail = fn()
    except Exception as e:  # noqa: BLE001 — a check that crashes is a failure, not a script bug
        ok, detail = False, f"raised {type(e).__name__}: {e}"
    results.append((name, ok, detail))
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}")
    if detail and not ok:
        for line in detail.splitlines():
            print(f"       {line}")


def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    # Force UTF-8 both ways: the report command writes Arabic, and a Windows
    # pipe defaults to a legacy codepage that can't encode it.
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "FOUNDRY_WORKSPACE": str(REPO_ROOT)}
    return subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, timeout=60,
        encoding="utf-8", errors="replace", env=env,
    )


def _tail_lines(text: str, n: int = 6) -> str:
    """Last N lines, not last N characters — truncating by character count
    cuts mid-word and produces garbage like 'ecent call last)' instead of
    a readable traceback tail."""
    return "\n".join(text.strip().splitlines()[-n:])


def check_seed_db() -> tuple[bool, str]:
    result = run([sys.executable, "scripts/seed_db.py"], REPO_ROOT)
    return result.returncode == 0, _tail_lines(result.stderr) if result.returncode else ""


def check_verify_engine() -> tuple[bool, str]:
    result = run([sys.executable, "scripts/tests/verify_engine.py"], REPO_ROOT)
    return result.returncode == 0, result.stdout.strip()


def check_engine_imports() -> tuple[bool, str]:
    code = (
        "import root_bus, tenant, signals, tasks, telegram, utils, agent_shim, precedent; "
        "import loops.ad_intel, loops.meta_ads, loops.content_engine, "
        "loops.social_calendar, loops.creative_brief, loops.lead_qualify"
    )
    result = run([sys.executable, "-c", code], ENGINE_DIR)
    return result.returncode == 0, _tail_lines(result.stderr) if result.returncode else ""


def check_path_traversal_blocked() -> tuple[bool, str]:
    """Regression test for the CRITICAL path-traversal fix — must stay
    blocked on every future change, not just pass once during the audit."""
    code = (
        "from tenant import TenantContext, TenantConfigError\n"
        "blocked = 0\n"
        "for bad in ('C:\\\\Windows', '..', '../../etc'):\n"
        "    try:\n"
        "        TenantContext(bad)\n"
        "    except TenantConfigError:\n"
        "        blocked += 1\n"
        "assert blocked == 3, f'only {blocked}/3 malicious names were blocked'\n"
        "print('all 3 blocked')"
    )
    result = run([sys.executable, "-c", code], ENGINE_DIR)
    return result.returncode == 0, _tail_lines(result.stderr) if result.returncode else result.stdout.strip()


def check_ad_intel_dedup() -> tuple[bool, str]:
    """Regression test for the duplicate-signal bug: ad-intel recalculates
    a rolling 7-day window every 6h while content-engine only runs every
    3 days, so an unguarded write would spam ~28 near-identical signals
    for one campaign that stays hot for a week. Confirms one campaign
    writes once, a second call for the SAME campaign is skipped, and a
    genuinely different campaign is NOT falsely blocked (the actual bug
    that shipped once already: threshold=0.55 was an untested guess that
    sat above the true-positive similarity score and silently defeated
    this exact check)."""
    code = (
        "from tenant import TenantContext\n"
        "from loops.ad_intel import _signal_content_opportunities\n"
        "t = TenantContext('Aurora_Skincare')\n"
        "campaign_a = {'name': 'Smoke Test Campaign A', 'status': 'ENABLED', "
        "'budget': 50.0, 'today_cost': 10.0, 'impressions_7d': 10000, "
        "'clicks_7d': 600, 'cost_7d': 300.0, 'conversions_7d': 40.0, "
        "'ctr_7d': 6.0, 'cpa_7d': 7.5}\n"
        "campaign_b = dict(campaign_a, name='Smoke Test Campaign B')\n"
        "w1 = _signal_content_opportunities(t, {'x': campaign_a})\n"
        "w2 = _signal_content_opportunities(t, {'x': campaign_a})\n"
        "w3 = _signal_content_opportunities(t, {'x': campaign_b})\n"
        "assert len(w1) == 1, f'first write failed: {w1}'\n"
        "assert len(w2) == 0, f'duplicate NOT skipped: {w2}'\n"
        "assert len(w3) == 1, f'different campaign falsely blocked: {w3}'\n"
        "print('dedup correct: first write ok, duplicate skipped, different campaign not blocked')"
    )
    env_path = DEMO_TENANT / ".env"
    if not env_path.exists():
        shutil.copy(DEMO_TENANT / ".env.example", env_path)
    result = run([sys.executable, "-c", code], ENGINE_DIR)
    return result.returncode == 0, _tail_lines(result.stderr) if result.returncode else result.stdout.strip()


def check_meta_ads_dedup() -> tuple[bool, str]:
    """Same regression shape as check_ad_intel_dedup — meta_ads.py reuses
    the identical precedent.py dedup pattern, worth its own independent
    check rather than assuming "it's the same code so it's fine"."""
    code = (
        "from tenant import TenantContext\n"
        "from loops.meta_ads import _aggregate, _check_alerts, _signal_content_opportunities\n"
        "t = TenantContext('Aurora_Skincare')\n"
        "attrs = {'c1': {'name': 'Meta Smoke Test Campaign', 'status': 'ACTIVE', 'budget': 40.0}}\n"
        "rows = [{'campaign_id': 'c1', 'date': '2020-01-01', 'impressions': 9000, "
        "'clicks': 500, 'spend': 35.0, 'conversions': 20.0}]\n"
        "summaries = {'c1': _aggregate(rows, attrs, 'c1')}\n"
        "w1 = _signal_content_opportunities(t, summaries)\n"
        "w2 = _signal_content_opportunities(t, summaries)\n"
        "assert len(w1) == 1, f'first write failed: {w1}'\n"
        "assert len(w2) == 0, f'duplicate NOT skipped: {w2}'\n"
        "assert _check_alerts({'status': 'ACTIVE', 'spend_7d': 0, 'budget': 0, 'name': 'x'}), "
        "'zero-spend alert did not fire'\n"
        "print('meta-ads dedup + alert logic correct')"
    )
    env_path = DEMO_TENANT / ".env"
    if not env_path.exists():
        shutil.copy(DEMO_TENANT / ".env.example", env_path)
    result = run([sys.executable, "-c", code], ENGINE_DIR)
    return result.returncode == 0, _tail_lines(result.stderr) if result.returncode else result.stdout.strip()


def check_live_loop_run() -> tuple[bool, str]:
    """The real end-to-end proof: a signal actually becomes a brief + task
    against the demo tenant, using nothing but what ships in this repo."""
    env_path = DEMO_TENANT / ".env"
    env_example = DEMO_TENANT / ".env.example"
    content_dir = DEMO_TENANT / "02_Content"
    tasks_dir = DEMO_TENANT / "tasks"

    if not env_path.exists():
        shutil.copy(env_example, env_path)

    result = run(
        [sys.executable, "run_loop.py", "content-engine", "--client", "Aurora_Skincare"],
        ENGINE_DIR,
    )
    if result.returncode != 0:
        return False, _tail_lines(result.stdout) or _tail_lines(result.stderr)

    brief_exists = content_dir.exists() and any(content_dir.glob("*brief*.md"))
    task_exists = tasks_dir.exists() and any(tasks_dir.glob("*.md"))
    signal_text = DEMO_SIGNAL.read_text(encoding="utf-8")
    signal_linked = "linked-task: none" not in signal_text

    if not (brief_exists and task_exists and signal_linked):
        return False, (
            f"brief_exists={brief_exists} task_exists={task_exists} "
            f"signal_linked={signal_linked}"
        )
    return True, ""


def check_social_calendar() -> tuple[bool, str]:
    """Runs social-calendar against the brief check_live_loop_run just
    produced — confirms it schedules once, then is idempotent on a second
    run against the same brief (marker-based skip, not signal-based)."""
    result = run(
        [sys.executable, "run_loop.py", "social-calendar", "--client", "Aurora_Skincare"],
        ENGINE_DIR,
    )
    if result.returncode != 0:
        return False, _tail_lines(result.stdout) or _tail_lines(result.stderr)

    calendar_path = DEMO_TENANT / "02_Content" / "calendar" / "content_calendar.md"
    if not calendar_path.exists():
        return False, "content_calendar.md was not created"
    first_run_rows = len(calendar_path.read_text(encoding="utf-8").splitlines())

    result2 = run(
        [sys.executable, "run_loop.py", "social-calendar", "--client", "Aurora_Skincare"],
        ENGINE_DIR,
    )
    second_run_rows = len(calendar_path.read_text(encoding="utf-8").splitlines())
    if second_run_rows != first_run_rows:
        return False, (
            f"not idempotent — row count changed from {first_run_rows} to "
            f"{second_run_rows} on a second run against the same brief"
        )
    return True, ""


def check_creative_brief_requires_key() -> tuple[bool, str]:
    """creative-brief is the one loop that calls an LLM — confirms it
    fails loud with a clear error when no provider key is configured,
    rather than silently no-op'ing or crashing with a bare traceback.
    Explicitly scrubs any real LLM keys from the subprocess env so this
    check is deterministic regardless of what's set on the host machine
    running this test."""
    code = (
        "from tenant import TenantContext\n"
        "from loops.creative_brief import run\n"
        "from agent_shim import AgentShimError\n"
        "t = TenantContext('Aurora_Skincare')\n"
        "try:\n"
        "    run(t)\n"
        "    raise SystemExit('FAIL: should have raised — no key was configured')\n"
        "except AgentShimError as e:\n"
        "    print(f'Correctly failed loud: {e}')\n"
    )
    scrubbed_env = {
        k: v for k, v in os.environ.items()
        if k not in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "FOUNDRY_LLM_PROVIDER")
    }
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=ENGINE_DIR, capture_output=True,
        text=True, timeout=30, env={**scrubbed_env, "FOUNDRY_WORKSPACE": str(REPO_ROOT)},
    )
    return result.returncode == 0, _tail_lines(result.stderr) if result.returncode else result.stdout.strip()


def check_foundry_cli() -> tuple[bool, str]:
    """The new unified CLI must dispatch all command groups correctly against
    the demo tenant — verifying the full foundry.py routing works end to end."""
    env_path = DEMO_TENANT / ".env"
    if not env_path.exists():
        shutil.copy(DEMO_TENANT / ".env.example", env_path)

    runs = [
        (["foundry.py", "account", "audit", "--client", "Aurora_Skincare"],
         ["VERDICT", "Dimension Scores"]),
        (["foundry.py", "account", "diagnose", "--client", "Aurora_Skincare"],
         ["VERDICT", "Funnel Ladder"]),
        (["foundry.py", "account", "report", "--client", "Aurora_Skincare", "--lang", "en"],
         ["VERDICT", "The Numbers"]),
        (["foundry.py", "tracking", "check", "--client", "Aurora_Skincare"],
         ["Tracking Readiness"]),
        (["foundry.py", "tracking", "events", "--client", "Aurora_Skincare"],
         ["Optimization Events"]),
        (["foundry.py", "content", "pipeline", "--client", "Aurora_Skincare"],
         ["Content Pipeline"]),
        (["foundry.py", "ops", "status", "--client", "Aurora_Skincare"],
         ["Engine Status"]),
        (["foundry.py", "ops", "cadence", "--client", "Aurora_Skincare"],
         ["Loop Cadence"]),
        (["foundry.py", "campaigns", "list", "--client", "Aurora_Skincare"],
         []),
        (["foundry.py", "season", "plan", "--client", "Aurora_Skincare"],
         ["Seasonal Plan"]),
        (["foundry.py", "tenants", "list"],
         ["Tenants"]),
    ]
    for cmd, markers in runs:
        result = run([sys.executable, *cmd], REPO_ROOT)
        if result.returncode != 0:
            return False, f"'{' '.join(cmd)}' exited {result.returncode}: {_tail_lines(result.stdout)}"
        missing = [m for m in markers if m not in result.stdout]
        if missing:
            return False, f"'{' '.join(cmd)}' is missing markers: {missing}"
    # Live read commands with placeholder credentials must FAIL LOUD (non-zero,
    # FETCH FAILED) — never report a failed pull as an empty account.
    for verb in ("pull", "optimize"):
        result = run([sys.executable, "foundry.py", "live", verb, "--client", "Aurora_Skincare"], REPO_ROOT)
        if result.returncode == 0 or not ("FETCH FAILED" in result.stderr or "no ad platform configured" in result.stderr):
            return False, f"live {verb} with placeholder creds should exit non-zero (FETCH FAILED or not configured); got rc={result.returncode}"
    return True, "foundry CLI dispatches all groups correctly"


def check_command_surface() -> tuple[bool, str]:
    """The operator-facing verbs must run against the demo tenant with zero
    real credentials and produce their contracted output — audit scores,
    diagnose names a bottleneck, report renders in both languages."""
    env_path = DEMO_TENANT / ".env"
    if not env_path.exists():
        shutil.copy(DEMO_TENANT / ".env.example", env_path)

    runs = [
        (["run_loop.py", "audit", "--client", "Aurora_Skincare"], ["VERDICT", "Dimension Scores", "Top Fixes", "Do Not Touch", "30-Day Plan"]),
        (["run_loop.py", "diagnose", "--client", "Aurora_Skincare"], ["VERDICT", "Funnel Ladder", "Findings", "The One Fix", "Honest Limits"]),
        (["run_loop.py", "report", "--client", "Aurora_Skincare", "--lang", "en"], ["VERDICT", "The Numbers", "Decisions Needed"]),
        (["run_loop.py", "report", "--client", "Aurora_Skincare", "--lang", "ar"], ["الخلاصة"]),
    ]
    for cmd, markers in runs:
        result = run([sys.executable, *cmd], ENGINE_DIR)
        if result.returncode != 0:
            return False, f"'{' '.join(cmd)}' exited {result.returncode}: {_tail_lines(result.stdout)}"
        missing = [m for m in markers if m not in result.stdout]
        if missing:
            return False, f"'{' '.join(cmd)}' is missing markers: {missing}"
    return True, "audit / diagnose / report (en+ar) all ran and honored their output contract"


def check_calc_determinism() -> tuple[bool, str]:
    """The calculator is the verification layer for every money-critical
    number this kernel quotes — so its answers are pinned to hand-computed
    values here, not just "it didn't crash"."""
    cases = [
        (
            ["calc.py", "breakeven", "--price", "499", "--cogs", "150",
             "--shipping", "45", "--fees", "3", "--confirm", "0.85",
             "--deliver", "0.78", "--return-cost", "30", "--json"],
            {"break_even_cpa_per_placed_order": 185.538, "break_even_roas": 1.78312},
        ),
        (
            ["calc.py", "cod", "--spend", "20000", "--orders", "400", "--aov", "499",
             "--confirm", "0.85", "--deliver", "0.78", "--cogs", "150",
             "--ship-out", "45", "--fees", "3", "--return-cost", "30", "--json"],
            {"real_roas": 6.61674, "gross_profit_after_ads": 54215.2},
        ),
        (
            ["calc.py", "learning", "--cpa", "120", "--json"],
            {"weekly_budget": 6000.0, "daily_budget": 857.142857},
        ),
        (
            ["calc.py", "vat", "--budget", "10000", "--country", "SA", "--json"],
            {"net": 8695.652174, "vat": 1304.347826},
        ),
    ]
    for cmd, expected in cases:
        result = run([sys.executable, *cmd], ENGINE_DIR)
        if result.returncode != 0:
            return False, f"'{' '.join(cmd)}' exited {result.returncode}: {_tail_lines(result.stderr)}"
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            return False, f"'{' '.join(cmd)}' did not return JSON: {e}"
        for key, want in expected.items():
            got = payload.get(key)
            if got is None or abs(float(got) - want) > 0.01:
                return False, f"'{' '.join(cmd)}': {key} = {got}, expected {want}"

    bad = run([sys.executable, "calc.py", "vat", "--budget", "100",
               "--country", "ZZ", "--json"], ENGINE_DIR)
    if bad.returncode != 2:
        return False, f"invalid country should exit 2, got {bad.returncode}"
    return True, "breakeven/cod/learning/vat match hand-computed values; bad input exits 2"


def cleanup() -> None:
    """Reset the demo tenant to its shipped state so this script is
    repeatable and doesn't accumulate test cruft in a tracked folder."""
    shutil.rmtree(DEMO_TENANT / "02_Content", ignore_errors=True)
    shutil.rmtree(DEMO_TENANT / "tasks", ignore_errors=True)
    shutil.rmtree(DEMO_TENANT / "04_Reports", ignore_errors=True)
    (DEMO_TENANT / ".env").unlink(missing_ok=True)
    # check_ad_intel_dedup() writes real signal files for its fake test
    # campaigns — remove anything in signals/ that isn't the one tracked
    # demo signal, so this script stays repeatable.
    signals_dir = DEMO_TENANT / "signals"
    if signals_dir.exists():
        for f in signals_dir.glob("*.md"):
            if f != DEMO_SIGNAL:
                f.unlink()
    # Restore tracked files — only works in a git repo (skip gracefully otherwise)
    try:
        subprocess.run(
            ["git", "checkout", "--", str(DEMO_SIGNAL.relative_to(REPO_ROOT))],
            cwd=REPO_ROOT, capture_output=True, timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass  # not a git repo yet — acceptable during initial setup
    log_path = REPO_ROOT / "log.md"
    if log_path.exists():
        log_path.unlink()


def main() -> int:
    print(f"Growth Architect Kernel — smoke test\nRepo: {REPO_ROOT}\n")

    check("hq.db seeds cleanly", check_seed_db)
    check("Kernel roster verifies (11 squads / 29 agents)", check_verify_engine)
    check("All engine modules import cleanly", check_engine_imports)
    check("Path traversal is blocked (security regression)", check_path_traversal_blocked)
    check("Live loop run: signal -> brief -> task (Aurora_Skincare)", check_live_loop_run)
    check("ad-intel dedup blocks duplicates, not different campaigns", check_ad_intel_dedup)
    check("meta-ads dedup + alert logic correct", check_meta_ads_dedup)
    check("social-calendar schedules briefs, idempotent on rerun", check_social_calendar)
    check("creative-brief fails loud with no LLM key configured", check_creative_brief_requires_key)
    check("Commands run: audit / diagnose / report (en + ar)", check_command_surface)
    check("calc.py matches hand-computed money math", check_calc_determinism)
    check("Foundry CLI: full command surface (13 commands)", check_foundry_cli)

    cleanup()

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"\n{passed}/{total} checks passed")

    if passed != total:
        print("\nFAILED checks:")
        for name, ok, detail in results:
            if not ok:
                print(f"  - {name}: {detail}")
        return 1

    print("All checks passed — this is a working install, verified live, not by inspection.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
