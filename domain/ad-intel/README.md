# Loop Contract: ad-intel

## Goal
Monitor ad performance and draft competitor interceptions.

## Inputs
- `signals/` (type: performance-alert)
- `tasks/` (domain: ad-intel)

## Outputs
- Drafts in `domain/ad-intel/drafts/`
- Updates to `domain/ad-intel/STATE.md`
- Run summary in `log.md`

## Verifier Checklist
- [ ] Accuracy of data
- [ ] Voice matches Soul Mandate
- [ ] No auto-execution performed

## Escalation
- Escalate to Mohamed via `signals/` if task fails 3 times.
