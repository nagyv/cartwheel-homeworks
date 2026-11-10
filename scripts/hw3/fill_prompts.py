"""Fill the writer or critic prompt template for each plan line.

Deterministic templating only. The writer receives the plan's `writer` block
and four tuple fields (role, user_style, difficulty, turn_count); nothing else
from the plan reaches the prompt.

Usage:
    uv run python -m scripts.hw3.fill_prompts writer scenarios/plans/pilot_plan.jsonl OUT_DIR
    uv run python -m scripts.hw3.fill_prompts critic scenarios/plans/pilot_plan.jsonl OUT_DIR \
        --conversations WRITER_OUTPUT.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

PROMPTS = Path(__file__).resolve().parents[2] / "scenarios" / "prompts"


def _table(markdown: str, header: str) -> dict[str, str]:
    rows: dict[str, str] = {}
    lines = markdown.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(f"| {header} |"))
    for line in lines[start + 2:]:
        if not line.startswith("|"):
            break
        key, value = [cell.strip() for cell in line.strip("|").split("|")]
        rows[key] = value
    return rows


def _template(markdown: str) -> str:
    match = re.search(r"## Template\n\n```\n(.*?)\n```", markdown, re.S)
    if match is None:
        raise SystemExit("template block not found")
    return match.group(1)


def writer_values(plan: dict[str, Any], tables: dict[str, dict[str, str]]) -> dict[str, str]:
    tuple_, writer = plan["tuple"], plan["writer"]
    role = tables["role"][tuple_["role"]].replace("{store_name}", writer.get("store_name", ""))
    return {
        "role_description": role,
        "goal": writer["goal"],
        "user_visible_facts": "\n".join(f"  - {fact}" for fact in writer["user_visible_facts"]),
        "style_description": tables["user_style"][tuple_["user_style"]],
        "difficulty_instruction": tables["difficulty"][tuple_["difficulty"]],
        "turn_count": str(tuple_["turn_count"]),
        "followup_count": str(tuple_["turn_count"] - 1),
    }


def fill(template: str, values: dict[str, str]) -> str:
    text = template
    for key, value in values.items():
        text = text.replace("{" + key + "}", value)
    leftover = re.findall(r"\{(role_description|goal|user_visible_facts|style_description|difficulty_instruction|turn_count|followup_count|conversation_json)\}", text)
    if leftover:
        raise SystemExit(f"unfilled placeholders: {leftover}")
    return text


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=["writer", "critic"])
    parser.add_argument("plan", type=Path)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--conversations", type=Path)
    args = parser.parse_args()

    writer_md = (PROMPTS / "writer.md").read_text()
    tables = {
        "role": _table(writer_md, "role"),
        "user_style": _table(writer_md, "user_style"),
        "difficulty": _table(writer_md, "difficulty"),
    }
    template = _template((PROMPTS / f"{args.kind}.md").read_text())
    conversations: dict[str, dict[str, Any]] = {}
    if args.kind == "critic":
        if args.conversations is None:
            raise SystemExit("--conversations is required for the critic")
        for line in args.conversations.read_text().splitlines():
            if line.strip():
                record = json.loads(line)
                conversations[record["id"]] = record

    args.out_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for line in args.plan.read_text().splitlines():
        if not line.strip():
            continue
        plan = json.loads(line)
        values = writer_values(plan, tables)
        if args.kind == "critic":
            conversation = conversations[plan["id"]]
            values["conversation_json"] = json.dumps(
                {"opening_message": conversation["opening_message"], "followups": conversation["followups"]},
                ensure_ascii=False,
            )
        (args.out_dir / f"{plan['id']}.txt").write_text(fill(template, values) + "\n")
        count += 1
    print(f"wrote {count} {args.kind} prompts to {args.out_dir}")


if __name__ == "__main__":
    main()
