# Loop Contract: command-chase

## Goal
Ensure no communication (Gmail/WhatsApp/Outlook) goes cold.

## Inputs
- `signals/` (type: unanswered-message)
- `tasks/` (domain: command-chase)

## Outputs
- Drafts in `domain/command-chase/drafts/`
- Updates to `domain/command-chase/STATE.md`
- Run summary in `log.md`

## Verifier Checklist
- [ ] Accuracy of data
- [ ] Voice matches Soul Mandate
- [ ] No auto-execution performed

## Escalation
- Escalate to Mohamed via `signals/` if task fails 3 times.
