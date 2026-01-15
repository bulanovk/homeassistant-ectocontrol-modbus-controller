## Summary

Please use this template when opening a PR that implements items from `IMPLEMENTATION_PLAN.md`.

## Mapped Checklist
- Link to plan: IMPLEMENTATION_PLAN.md
- Link to checklist: PR_CHECKLIST.md

Fill the tasks that this PR implements and tick them off.

## Reviewer checklist
- [ ] Code changes map to PR_CHECKLIST.md TODOs
- [ ] Unit/integration tests added or updated
- [ ] New entities added to `manifest.json` and forwarded in `async_setup_entry`
- [ ] Unique IDs follow `ectocontrol_{slave_id}_{feature}` format
- [ ] Any new dependencies added to `requirements.txt`

## What this PR implements
- (List tasks from PR_CHECKLIST.md)

## How to test
- Run unit tests: `pytest tests` or `pytest -q`
- Start HA in dev container and verify entities created for a mock config entry

## Notes
- If any optional advanced features are included, explain rationale and testing performed.
