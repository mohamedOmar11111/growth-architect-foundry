# Changelog

## Unreleased
- **New:** `scripts/build_claude_web_pack.py` builds a claude.ai plugin zip and a standalone skill zip with the
  engine bundled inside the skill (stdlib only, offline). Checked by running the engine from the extracted zip, and
  the plugin upload plus a first run were confirmed working in claude.ai by the author.

## 1.5.0 - 2026-10-28
- **Fix:** `campaigns import` now reads real export shapes: title lines above the header, `Amount spent (USD)`-style
  headers, `--` cells, `Total:` rows, UTF-16/tab and `;` files, Arabic column names and digits, ad-set-level rows
  (summed per campaign). Unrecognised spend/impressions/clicks/conversions columns now warn in the report instead of a
  silent 0, and the report lists the columns used and the currency.
- **New: CSV mode.** After `campaigns import`, with no credentials configured, `account audit`, `account diagnose`
  and `account report` judge the imported data instead of the setup: a 0-100 performance score with named components
  (withheld when there are no conversions; marked provisional under 30), per-campaign calls (Scale / Keep / Too early /
  Cut / Stop), ranked findings, and Do today / Test this week / Stop actions. The client report and WhatsApp digest
  come in English and Arabic. Heuristics are fixed and listed in `commands/perf.py`; a campaign needs 10 conversions
  before it is called a winner or loser. `diagnose` also ranks a finding confirmed by data above a hypothesis.

## 1.4.3
- **Fix (found on a real read-only Meta pull):** messaging campaigns always reported 0 conversions,
  because `messaging_conversation_started_7d` was not counted, and `offsite_conversion` matched only the
  bare name. New `count_conversions` canonicalises Meta action types and takes the max per event, so
  `purchase` / `omni_purchase` / `offsite_conversion.fb_pixel_purchase` are not double counted.
- Includes the 1.4.2 changes below (1.4.2 was never tagged).

## 1.4.2
- **Fix:** `state.config_status` misspelled the Google Ads developer-token env key
  (`GOOGLE_ADS_DEVELOTER_TOKEN` → `GOOGLE_ADS_DEVELOPER_TOKEN`), so a correctly configured account
  was reported as missing the key.
- **Fix:** `read_ad_report` now picks up all three report sources — `*-ad-intel-report.md`,
  `*-meta-ads-report.md` and `*-live-pull.md` (was: ad-intel only, silently ignoring Meta/live data).
- **Fix:** `forecast project` was imported and documented but unreachable — registered in the CLI
  dispatch table and now returns real observed/target spend + conversions in `--json`.
- **New:** `economics leadgen` — break-even CPL / CPQL and funnel profit for lead-gen and WhatsApp
  funnels (deal value, qualify/close rates, optional spend+leads for a period verdict).
- **New:** `campaigns import --file <export.csv>` — converts a platform CSV export into a standard
  ad-intel report so diagnose/campaigns/forecast work with zero API access.
- **Docs:** command count corrected to 31, agent personas to 61, diagram types to 40, smoke-test checks to 12.
- **New:** `account report --format whatsapp` — copy-ready client digest for EN and AR.

## 1.4.1
- **Codex plugin:** `.codex-plugin/plugin.json` and `.agents/plugins/marketplace.json`, with icon, logo and
  screenshots, so Foundry can be listed in Codex plugin catalogs. The HOL plugin scanner (v3.49.0, the
  version the Codex plugin catalog pins) scores it 100/100 with no findings.
- `SECURITY.md` (private vulnerability reporting, supported versions, known limits).
- `requirements.lock` (pinned dependency snapshot), Dependabot for GitHub Actions and pip, `.codexignore`.
- Placeholder passwords in two bundled example personas now read an environment variable.

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
