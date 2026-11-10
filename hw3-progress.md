# HW3 progress

Interactive walkthrough of `homework/module-1/hw3.md`. Claude proposes each step and waits for Viktor's "go". Viktor makes every review decision, writes the assessments, and records the video.

## Next

- Part A: Viktor brainstorms dimensions; query `data_quality_cases`; then Claude proposes the combined plan for approval

## Done

- Step 0: branch `wip/hw3`, `.sessions.db-*` added to `.gitignore`, this note created
- Step 1: kept `claude-haiku-5-5` (Viktor's choice); seeded; Langfuse up; server on :8010 (Claude runs it in the background); smoke scenario `smoke-0001` (scratchpad only) produced a trace with messages, model, `list_my_orders` call and result, scenario id, token usage; reseeded afterwards

## Steps

- [x] 0. Housekeeping
- [x] 1. Preparation (model in `.env` and the runner `--model` value must match)
- [ ] 2. Part A: dimension plan, **approved by Viktor**
- [ ] 3. Part B: 30 pilot scenarios generated, validated, conversation sample **accepted by Viktor**
- [ ] 3b. Part B: pilot run, at least 10 results **reviewed by Viktor**, at least 5 confirmed failures
- [ ] 4. Part C: 250 final scenarios (175 coverage, 75 challenge, 5 per damaged record), new IDs
- [ ] 4b. Part C: 15 scenarios **reviewed by Viktor** (both groups, all 3 roles, every intent), revisions applied
- [ ] 4c. Part C: 50 monitoring scenarios selected (both groups, all 3 roles)
- [ ] 4d. Part C: `uv run python -m scenarios.validate scenarios/support_scenarios.jsonl --final` passes
- [ ] 5. Part D: data reset, final run, all 250 records `completed`
- [ ] 6. Part E: smoke report, export succeeds, 3 traces checked (one challenge, one multi-turn)
- [ ] 7. Video (Viktor)

## Files to commit

- [ ] `scenarios/pilot_scenarios.jsonl`
- [ ] `scenarios/pilot-results.jsonl`
- [ ] `scenarios/pilot_review.jsonl` (Viktor's decisions)
- [ ] `scenarios/support_scenarios.jsonl`
- [ ] `scenarios/support_review.jsonl` (Viktor's decisions)
- [ ] `scenarios/monitoring_scenarios.jsonl`
- [ ] `scenarios/final-results.jsonl`
- [ ] `reports/smoke-output.txt`
- [ ] `traces/support_traces.json`

## Notes

- `homework/module-1/AGENTS.md` does not exist; the root `AGENTS.md` applies
- HW2 is merged into `main`, so do not apply `hw2-reference.patch`
- Agent model: `claude-haiku-5-5` (kept by Viktor despite the risk of too few failures). Fallback if the pilot finds fewer than 5: add 20 challenge scenarios, or switch to a weaker model
