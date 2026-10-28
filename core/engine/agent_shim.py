"""growth_engine.agent_shim — run a loop with a raw LLM API key, no agent
harness required.

Why this exists: every other file in core/engine/ is deterministic Python —
state, scheduling, signal/task I/O, platform API calls. None of it calls an
LLM. That's fine when a real agent (Claude Code, Cursor, etc.) is reading
CLAUDE.md/AGENTS.md and doing the judgment/drafting work on top of this
kernel. It's not fine for a buyer who just has an API key and no agent
harness — there was no path from "I have an OpenAI/Anthropic/Gemini key" to
"the engine does something." This script is that path.

What it does, specifically:
  1. Assembles the same context an agent harness would read first
     (CLAUDE.md, AGENTS.md, architecture.md, the domain contract for the
     requested loop, the last N lines of log.md, and — if --client is
     given — that tenant's own CLAUDE.md/STRATEGY.md).
  2. Sends that context + your instruction to whichever provider you have a
     key for (checked in order: Anthropic, OpenAI, Gemini — first match
     wins; set FOUNDRY_LLM_PROVIDER to force one).
  3. Writes the model's response to domain/<loop>/drafts/ as a dated file
     and appends one line to log.md — same paper trail every other loop in
     this kernel leaves, so a human or a real agent reviewing log.md later
     sees this run too.

What it deliberately does NOT do: write signals/ or tasks/ files itself.
Those have a strict, validated schema (architecture.md) and get consumed by
other automation — an LLM free-text response has no business being written
there directly. This script is a thinking/drafting layer, not a
schema-writing layer, same "no auto-publish" rule as every other loop in
this kernel.

Data-handling note, stated plainly rather than left implicit: step 1 sends
the FULL, VERBATIM text of CLAUDE.md/AGENTS.md/architecture.md and — when
--client is given — that tenant's own CLAUDE.md/STRATEGY.md to whichever
third-party LLM provider is configured. There is no redaction step. If a
tenant's STRATEGY.md contains anything sensitive (client PII, competitor
intel, unreleased pricing), it leaves this machine and goes to Anthropic/
OpenAI/Google the first time this script is run against that tenant. This
is inherent to what the script does, not a bug — but a buyer reselling this
kernel needs to know it's happening so THEY can decide whether that's
acceptable for a given client's data, not discover it after the fact.

Model IDs are intentionally kept in one place (DEFAULT_MODELS below) and
overridable via env vars — provider APIs move fast enough that whatever is
hardcoded here will eventually be stale. Check your provider's current
model list if a call fails with a "model not found" style error.

Usage:
    python agent_shim.py content-engine --task "Draft a brief from today's ad-intel signals"
    python agent_shim.py ad-intel --client Aurora_Skincare --task "Summarize this week's alerts"
    python agent_shim.py lead-qualify --task "Explain the S-Score model to a new hire"
"""

from __future__ import annotations

import argparse
import datetime
import os
from pathlib import Path

import requests
from dotenv import dotenv_values

from tenant import TenantContext, TenantConfigError

from paths import WORKSPACE as HQ_ROOT, CLIENTS_ROOT, LOG_PATH, DOMAIN_CONTRACTS, DOMAIN_WORKSPACE  # noqa: E402

VALID_LOOPS = {
    "command-chase", "ad-intel", "content-engine", "lead-qualify",
}

# Override any of these with the matching env var if the hardcoded default
# has gone stale (provider model catalogs change faster than this file will).
DEFAULT_MODELS = {
    "anthropic": os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929"),
    "openai": os.environ.get("OPENAI_MODEL", "gpt-4o"),
    # "gemini-2.0-flash" (the original default here) returned a real 404 when
    # live-tested against Google's actual current model catalog — confirmed
    # stale, not a code bug. "gemini-flash-latest" is Google's own stable
    # alias for their current recommended flash model, so this default
    # won't need updating every time their model lineup moves (it had moved
    # to 3.x-series names by the time this was tested).
    "gemini": os.environ.get("GEMINI_MODEL", "gemini-flash-latest"),
}

LOG_TAIL_LINES = 30


class AgentShimError(RuntimeError):
    """Raised for any config/provider problem this script can't proceed past."""


def _load_root_env() -> dict[str, str]:
    """Root .env values merged with real process env — process env wins, so
    a buyer can override without editing the file (e.g. in CI)."""
    values = dict(dotenv_values(HQ_ROOT / ".env"))
    values.update({k: v for k, v in os.environ.items() if v})
    return values


def _read_optional(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _log_tail(path: Path, n: int, client: str | None = None) -> str:
    """Last n log lines. For a tenant-scoped run only that tenant's entries are
    returned — the shared root log also holds other clients' activity, and this
    text is sent to a third-party LLM."""
    if not path.exists():
        return "(no log.md yet — this will be the first run logged)"
    text = path.read_text(encoding="utf-8")
    if client:
        blocks = text.split("\n## ")
        mine = [b for b in blocks if b.split("\n", 1)[0].split(" — ", 1)[-1].startswith(f"{client} /")]
        text = "\n## ".join(mine)
    return "\n".join(text.splitlines()[-n:])


def _read_in(root: Path, name: str) -> str:
    """Read root/name, refusing symlinks and anything resolving outside root."""
    path = root / name
    if not path.exists():
        return ""
    if path.is_symlink() or root.resolve() not in path.resolve().parents:
        raise AgentShimError(f"'{name}' in {root.name} is a symlink or escapes the folder — refusing.")
    return path.read_text(encoding="utf-8")


def build_context(loop: str, client: str | None) -> str:
    """Assembles the same read-before-acting bundle AGENTS.md Section 0
    prescribes for any agent — this script follows its own kernel's rules
    instead of being a special case."""
    domain_readme = DOMAIN_CONTRACTS / loop / "README.md"
    if not domain_readme.exists():
        raise AgentShimError(
            f"No domain contract at {domain_readme} — every loop must have one "
            "per AGENTS.md Section 0. Refusing to run without it."
        )

    sections = [
        "# CLAUDE.md (Constitution)",
        _read_optional(HQ_ROOT / "CLAUDE.md"),
        "\n# AGENTS.md (Field Manual)",
        _read_optional(HQ_ROOT / "AGENTS.md"),
        "\n# architecture.md (Schemas)",
        _read_optional(HQ_ROOT / "architecture.md"),
        f"\n# Domain Contract — {loop}",
        domain_readme.read_text(encoding="utf-8"),
        f"\n# log.md (last {LOG_TAIL_LINES} lines)",
        _log_tail(LOG_PATH, LOG_TAIL_LINES, client),
    ]

    if client:
        # Reuse tenant.py's path validation, not a second hand-rolled join —
        # `client` is untrusted (CLI arg, potentially LLM-influenced via a
        # future automated caller) and pathlib silently discards CLIENTS_ROOT
        # entirely if `client` happens to be an absolute path.
        try:
            tenant_root = TenantContext._resolve_root(client)
        except TenantConfigError as e:
            raise AgentShimError(str(e)) from e
        if not tenant_root.is_dir():
            raise AgentShimError(
                f"No tenant folder at {tenant_root} — check spelling/casing "
                f"exactly against {CLIENTS_ROOT}."
            )
        sections += [
            f"\n# Tenant Context — {client}",
            "## CLAUDE.md" if (tenant_root / "CLAUDE.md").exists() else "",
            _read_in(tenant_root, "CLAUDE.md"),
            "## STRATEGY.md" if (tenant_root / "STRATEGY.md").exists() else "",
            _read_in(tenant_root, "STRATEGY.md"),
        ]

    return "\n".join(s for s in sections if s)


def _call_anthropic(api_key: str, system: str, user: str) -> str:
    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": DEFAULT_MODELS["anthropic"],
            "max_tokens": 4096,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        },
        timeout=120,
    )
    response.raise_for_status()
    data = response.json()
    return "".join(block.get("text", "") for block in data.get("content", []))


def _call_openai(api_key: str, system: str, user: str) -> str:
    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "content-type": "application/json"},
        json={
            "model": DEFAULT_MODELS["openai"],
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        timeout=120,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]


def _call_gemini(api_key: str, system: str, user: str) -> str:
    model = DEFAULT_MODELS["gemini"]
    response = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        # Header, not `params={"key": api_key}` — a query-string key ends up
        # embedded in `response.url`, and every requests exception
        # (HTTPError, ConnectionError, Timeout) stringifies to a message that
        # includes the full request URL. That string is exactly what
        # `main()`'s `except requests.RequestException as e: print(...)`
        # prints to stdout on any failure — a bad/expired key would print
        # itself in plaintext. Headers aren't included in that stringified
        # exception, so this closes the leak at the source instead of
        # scrubbing every downstream error handler individually.
        headers={"x-goog-api-key": api_key},
        json={
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"parts": [{"text": user}]}],
        },
        timeout=120,
    )
    response.raise_for_status()
    data = response.json()
    parts = data["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts)


PROVIDERS = {
    "anthropic": ("ANTHROPIC_API_KEY", _call_anthropic),
    "openai": ("OPENAI_API_KEY", _call_openai),
    "gemini": ("GEMINI_API_KEY", _call_gemini),
}


def resolve_provider(env: dict[str, str]) -> tuple[str, str]:
    """Returns (provider_name, api_key). Honors FOUNDRY_LLM_PROVIDER if set
    and that provider's key is present; otherwise first configured key wins,
    checked in a fixed order so behavior is predictable, not dict-order
    dependent."""
    forced = env.get("FOUNDRY_LLM_PROVIDER")
    if forced:
        if forced not in PROVIDERS:
            raise AgentShimError(
                f"FOUNDRY_LLM_PROVIDER='{forced}' is not one of {list(PROVIDERS)}"
            )
        key_name, _ = PROVIDERS[forced]
        if not env.get(key_name):
            raise AgentShimError(
                f"FOUNDRY_LLM_PROVIDER='{forced}' but {key_name} is not set."
            )
        return forced, env[key_name]

    for name, (key_name, _) in PROVIDERS.items():
        if env.get(key_name):
            return name, env[key_name]

    raise AgentShimError(
        "No LLM API key found. Set one of ANTHROPIC_API_KEY, OPENAI_API_KEY, "
        "or GEMINI_API_KEY in the root .env (see templates/.env.example) or "
        "as a real environment variable."
    )


def run(loop: str, client: str | None, task: str) -> int:
    if loop not in VALID_LOOPS:
        raise AgentShimError(f"Unknown loop '{loop}'. Must be one of {sorted(VALID_LOOPS)}")

    env = _load_root_env()
    operator = env.get("OPERATOR_NAME", "the operator")
    provider, api_key = resolve_provider(env)
    context = build_context(loop, client)

    system_prompt = (
        f"{context}\n\n"
        f"---\n"
        f"You are operating as an agent inside this Growth Architect kernel, "
        f"for {operator}. Follow every rule in CLAUDE.md and AGENTS.md above "
        f"exactly — never claim to have sent a message, published content, or "
        f"executed a live platform change; draft only. Ground every claim in "
        f"the context actually given above, not invented specifics."
    )

    call_fn = PROVIDERS[provider][1]
    result = call_fn(api_key, system_prompt, task)

    # Tenant-scoped runs write inside that tenant's own folder so one client's
    # model output (grounded in their STRATEGY.md) never lands in a shared dir.
    if client:
        drafts_dir = CLIENTS_ROOT / client / "04_Reports" / "drafts" / loop
    else:
        drafts_dir = DOMAIN_WORKSPACE / loop / "drafts"
    drafts_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.datetime.now()
    draft_path = drafts_dir / f"{now.strftime('%Y-%m-%d-%H%M%S')}-agent-shim-{provider}.md"
    scope_note = f" (tenant: {client})" if client else " (root scope)"
    draft_path.write_text(
        f"# Agent Shim Run — {loop}{scope_note} — {now.strftime('%Y-%m-%d %H:%M')}\n\n"
        f"**Provider:** {provider} ({DEFAULT_MODELS[provider]})\n"
        f"**Task given:** {task}\n\n"
        f"---\n\n"
        f"> ⚠️ **UNTRUSTED MODEL OUTPUT BELOW.** This is the LLM's raw response —\n"
        f"> not verified, not reviewed. If it recommends running a specific\n"
        f"> command (e.g. `run_loop.py`/`agent_shim.py` with a particular\n"
        f"> `--client` value), do not run it without independently confirming\n"
        f"> that's actually the right tenant — the context fed to this model\n"
        f"> included that tenant's own STRATEGY.md/CLAUDE.md verbatim, and\n"
        f"> those files are lower-trust input than this kernel's own code.\n\n"
        f"{result}\n",
        encoding="utf-8",
    )

    log_line = (
        f"[{now.strftime('%Y-%m-%d %H:%M')}] | {loop} | agent-shim run via {provider}"
        f"{scope_note} | Items: 1 actioned, 0 skipped | "
        f"Next: {operator} reviews {draft_path.relative_to(HQ_ROOT).as_posix()}\n"
    )
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(log_line)

    print(f"[{loop}] agent-shim: response written -> {draft_path}")
    print(result)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one Growth Engine loop with a raw LLM API key — no agent harness required."
    )
    parser.add_argument("loop", choices=sorted(VALID_LOOPS))
    parser.add_argument("--client", default=None, help="Tenant folder name under 02_Active_Clients/, if this run is tenant-scoped.")
    parser.add_argument("--task", required=True, help="Free-text instruction for the model.")
    args = parser.parse_args()

    try:
        return run(args.loop, args.client, args.task)
    except AgentShimError as e:
        print(f"ERROR: {e}")
        return 1
    except requests.RequestException as e:
        print(f"ERROR: LLM API call failed: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
