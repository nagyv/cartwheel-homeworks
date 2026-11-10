"""Join plan lines with critic-approved conversations into a scenario file.

The `writer` block is planning input only and is dropped. The critic verdicts
are written to a log next to the plan so every rewrite stays traceable.

Usage:
    uv run python -m scripts.hw3.assemble scenarios/plans/pilot_plan.jsonl \
        CRITIC_OUTPUT.jsonl scenarios/pilot_scenarios.jsonl
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("critic", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    critic = {}
    for line in args.critic.read_text().splitlines():
        if line.strip():
            record = json.loads(line)
            critic[record["id"]] = record

    scenarios = []
    for line in args.plan.read_text().splitlines():
        if not line.strip():
            continue
        plan = json.loads(line)
        conversation = critic[plan["id"]]
        followups = conversation["followups"]
        if plan["tuple"]["turn_count"] != 1 + len(followups):
            raise SystemExit(f"{plan['id']}: turn_count {plan['tuple']['turn_count']} but {len(followups)} followups")
        scenarios.append({
            "id": plan["id"],
            "scenario_group": plan["scenario_group"],
            "data_quality_case_id": plan["data_quality_case_id"],
            "tuple": plan["tuple"],
            "opening_message": conversation["opening_message"],
            "followups": followups,
            "expected": plan["expected"],
        })

    args.output.write_text("".join(json.dumps(s, ensure_ascii=False) + "\n" for s in scenarios))
    log = args.plan.with_name(args.plan.stem.replace("_plan", "") + "_critic_log.jsonl")
    log.write_text("".join(json.dumps(critic[s["id"]], ensure_ascii=False) + "\n" for s in scenarios))
    print(f"wrote {len(scenarios)} scenarios to {args.output} and the critic log to {log}")


if __name__ == "__main__":
    main()
