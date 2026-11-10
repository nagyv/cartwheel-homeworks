# HW2 progress

Branch: `wip/hw2` (from `origin/main`, which includes the HW1 merge, PR #1).
First push: `git push -u origin wip/hw2`.

## Done

- Step 0: created `wip/hw2`
- Step 1: `uv sync` (environment already matched the lock file)
- Step 2: concepts (trace, span, `gen_ai.*` vs `cartwheel.*`)
- Part A: code written; no offline test by Viktor's choice, verify in Langfuse in Part E
- Part B: `create_session` written; `create_session_binds` test passes
- Part C: `post_message` written (root span `cartwheel.session_message`, reply key `reply`); verify live in Part E

## Next

- Part D: `tests/test_observability.py` (two auth tests)
- Before Part E: produce `hw1-session.jsonl` from observed runs (requests drafted by Claude and approved by Viktor; `tool_calls`/`response` from real runs; assessment fields left `"PENDING"` for Viktor)

## Known issue (existed before HW2, left as is by Viktor's choice)

- `tests/test_hw_holes.py::test_m2_run_judge_persists_store_predictions_for_prevalence` fails in the full suite only: an earlier test calls `load_env()`, which leaks `LANGFUSE_*` from `.env`, so the test tries live Langfuse at `localhost:3000`. It passes alone, and it fails the same way without the HW2 changes. It blocks the handout's "`uv run pytest` passes" check until it is resolved.

## Deliverables checklist

- [x] Part A: `record_tool_result`, `_set_permission_denied_attributes` in `observability/instrument.py`
- [x] Part B: `create_session` in `server/app.py`; `uv run pytest --runxfail -vv tests/test_hw_holes.py -k "create_session_binds"` passes
- [x] Part C: `post_message` in `server/app.py`
- [ ] Part D: `tests/test_observability.py` (wrong-role rejection, cross-session token rejection)
- [ ] Part D checks: `uv run pytest --runxfail tests/test_hw_holes.py -k hw2`, `uv run pytest tests/test_observability.py`, `uv run pytest`
- [ ] Part E: at least 5 traced requests from `hw1-session.jsonl`, inspected in Langfuse
- [ ] Part F: two prompt version hashes recorded; original prompt restored
- [ ] `hw2-traces.json`: exactly 2 traces with the 7 required fields
- [ ] Video (Viktor)

## Notes

- Agent model: `claude-haiku-5-5` (from `.env`)
- Do not apply `homework/module-1/hw2-reference.patch`; it is the instructor solution
