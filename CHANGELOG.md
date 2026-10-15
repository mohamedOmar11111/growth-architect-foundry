# Changelog

## 1.4.0
- **ChatGPT:** Custom GPT pack (`scripts/build_chatgpt_pack.py`): offline engine zip, GPT instructions
  (under the 8,000-character cap) and knowledge files. Runs in Code Interpreter with no network, so live
  ad writes are impossible there.
- **Standard-library only:** every read-only command now runs without python-dotenv, PyYAML, requests or
  google-ads (`envfile.py` fallbacks; command modules import lazily). Tested with those imports blocked.
- **Codex:** verified with the real CLI (`codex debug prompt-input` discovery check in CI; manual
  `codex exec` run).
- **Removed:** Gemini CLI extension (`gemini-extension.json`) and its docs/tests. Gemini remains an
  optional LLM provider for `agent_shim.py`.

## 1.3.0
- **Safety:** live writes (`live pause`, `live budget`) now need a person typing the campaign key at a
  real terminal, on top of `--confirm`. AI agent shells have no terminal, so they exit 3 ("refused")
  in every agent, not just Claude Code.
- **Machine contract:** `--json` on every command prints one object (`schema_version` 1); exit codes
  0 ok / 1 failed / 2 bad input / 3 refused.
- **Agents:** works with OpenCode, Gemini CLI, Freebuff/Codebuff, Codex, Cursor via one Agent Skill,
  `AGENTS.md`, `scripts/install_agent.py` and a Gemini extension manifest.
- **CI:** Ubuntu/Windows/macOS x Python 3.10/3.13 matrix; nightly real-agent conformance job.
- **Fix:** `economics` without `--confirm` crashed (unset flag was read as a 0% rate).
- Cursor rule replaced with a pointer to `AGENTS.md`.

## 1.2.0
- Agent Skills layout (`skills/growth-architect-foundry`), `AGENTS.md`, Gemini extension, installer.

## 1.1.0
- Claude Code plugin, workspace/engine path split, red-team hardening (budget-cap bypass, tenant
  aliasing and symlinks, log forgery, cross-tenant log leakage, CI hardening).
