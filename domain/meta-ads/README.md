# Loop Contract: meta-ads

## Goal
Monitor Meta (Facebook/Instagram) Ads performance and hand off winning
organic-worthy ad angles to content-engine — same shape as ad-intel's
contract, different platform.

## Inputs
- `signals/` (type: performance-alert)
- `tasks/` (domain: meta-ads)
- Tenant's `.env`: `META_ACCESS_TOKEN`, `META_AD_ACCOUNT_ID`

## Outputs
- Report in `02_Reports/` (via tenant.reports_dir)
- `content-idea` signals for campaigns above the CTR/click threshold —
  deduped against already-pending signals (see core/engine/precedent.py)
- Run summary in `log.md`

## Verifier Checklist
- [ ] Accuracy of data
- [ ] No auto-execution performed — read-only against the live account
- [ ] Currency/budget math correct for this tenant's ad account currency
      (see meta_ads.py's docstring on the cents-vs-minor-unit assumption)

## Escalation
- Escalate to the operator via `signals/` if a live API call fails 3 times.
