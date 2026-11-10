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
- Part D: `tests/test_observability.py` (2 tests via `TestClient`, pass); added dev dependency `httpx2` to remove Starlette's deprecation warning
- Removed the xfail markers from the HW1/HW2 contract tests (now ordinary tests)
- Part E: Langfuse in Docker (project `cartwheel-dev`, login `student@example.com`); 6 traced requests (hw1 #1, #3, #4, #5, #8, #9); every root and tool span checked against the Part A/C rules, all OK. Denial in hw1 #4: trace `7323baf91f08afc9baa93206692c6ad6`
- Token counts: OpenLLMetry 0.62.3 ignores `GenerationSpanData.usage` on the LiteLLM path; fixed with `_GenerationUsageProcessor` in `observability/instrument.py` plus an offline test; confirmed live (trace `74594d074a9b2704dc03da76ff0fd702`)
- Part F: same request (hw1 #1, shopper 1, new session, reseeded, `claude-haiku-5-5`). Original `d108f6949e5e` (trace `a8ed5d9e99c651ed7069ebb193fdced6`) vs one-word edit (`helpful`) `3ab3fa8a8a68` (trace `408b9a9e2d54c963359e74f038942bc8`). Prompt restored via `git checkout`, server restarted, hash back to `d108f6949e5e`
- `hw1-session.jsonl`: 10 observed conversations (live `claude-haiku-5-5`, reseeded before each). The four assessment fields are `"PENDING"` for Viktor

## Next

- Trace record: `hw2-traces.json`

## Known issue (existed before HW2, left as is by Viktor's choice)

- `tests/test_hw_holes.py::test_m2_run_judge_persists_store_predictions_for_prevalence` fails in the full suite only: an earlier test calls `load_env()`, which leaks `LANGFUSE_*` from `.env`, so the test tries live Langfuse at `localhost:3000`. It passes alone, and it fails the same way without the HW2 changes. It blocks the handout's "`uv run pytest` passes" check until it is resolved.

## Deliverables checklist

- [x] Part A: `record_tool_result`, `_set_permission_denied_attributes` in `observability/instrument.py`
- [x] Part B: `create_session` in `server/app.py`; `uv run pytest --runxfail -vv tests/test_hw_holes.py -k "create_session_binds"` passes
- [x] Part C: `post_message` in `server/app.py`
- [x] Part D: `tests/test_observability.py` (wrong-role rejection, cross-session token rejection)
- [ ] Part D checks (first two pass; full suite blocked by the known issue): `uv run pytest --runxfail tests/test_hw_holes.py -k hw2`, `uv run pytest tests/test_observability.py`, `uv run pytest`
- [x] Part E: at least 5 traced requests from `hw1-session.jsonl`, inspected in Langfuse
- [x] Part F: two prompt version hashes recorded; original prompt restored
- [ ] `hw2-traces.json`: exactly 2 traces with the 7 required fields
- [ ] Video (Viktor)

## HW1 leftovers (Viktor)

- [ ] Fill `expected`, `requirement`, `met_requirement`, `problem_source` in `hw1-session.jsonl`
- Possible things to assess: #3 escalated without calling `issue_refund`; #9 refused without calling `get_order`; #10 did not call `cancel_order`

## Notes

- Agent model: `claude-haiku-5-5` (from `.env`)
- Do not apply `homework/module-1/hw2-reference.patch`; it is the instructor solution
