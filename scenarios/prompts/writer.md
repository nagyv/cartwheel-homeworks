# Writer prompt

One independent writer subagent (Sonnet) runs per scenario. The orchestrator fills the template from one line of the plan file (`scenarios/plans/*.jsonl`). It uses the phrase tables below so that every writer receives identical wording. The writer receives the plan's `writer` block (`goal`, `user_visible_facts`, and `store_name` for merchants) and only four tuple fields: `role`, `user_style`, `difficulty`, and `turn_count`. It never receives the other tuple fields (identifiers, `intent`, `record_state`, `applicable_policy`, `tools_needed`), `expected`, or `data_quality_case_id`.

## Role descriptions

| role | role_description |
|---|---|
| shopper | a shopper who buys things from independent stores on Cartwheel |
| merchant | the owner of the store {store_name}, signed in to the Cartwheel merchant account |
| support | a Cartwheel support staff member using the assistant to handle a case |

## Style descriptions

| user_style | style_description |
|---|---|
| neutral_conversational | ordinary, friendly, complete sentences |
| terse_fragmentary | very short fragments, few words, no greeting |
| typo_heavy | many spelling mistakes and missing capitals, but the facts are correct |
| confused_rambling | confused and rambling, drifts off topic, unsure of details |
| frustrated_impatient | frustrated and impatient, wants it fixed now |
| repetitive_pressuring | pushy, repeats the demand and presses harder each time, without tricks |
| operational_shorthand | brisk work shorthand, like a ticket note |
| requests_short_plain_answer | asks explicitly for a short, plain answer |

## Difficulty instructions

| difficulty | difficulty_instruction |
|---|---|
| well_specified | state the request clearly with the facts the user knows |
| ambiguous | describe the item and the store loosely and give no order number |
| missing_information | leave out a detail the agent would need, as a real user would |
| boundary | state the request plainly; the hard part is in the data, not the wording |
| compound | ask about everything in "What they want" in one opening message |
| correction_across_turns | in the opening, describe the item that "What they want" marks as the user's first mistake; in a follow-up, correct it to the right item |
| misspelled_entity | misspell the name that "What they know" marks as misspelled, the way a hurried typist would; spell everything else normally |

## Template

```
You write the messages a simulated user types into the Cartwheel support chat.
Cartwheel is an online marketplace where shoppers buy from independent stores.

Do not use any tools and do not read any files. Reply with the JSON object only.

Who is typing: {role_description}
What they want: {goal}
What they know (use only these facts; you may leave some out):
{user_visible_facts}
How they write: {style_description}
Difficulty to build in: {difficulty_instruction}
Messages: {turn_count} in total (one opening message and {followup_count} follow-ups)

Rules:
- Write like a real person typing into a chat window, not like a tester.
- Use no order numbers, product IDs, exact dates, amounts, or policy names
  unless "What they know" lists them. Invent no names, numbers, or dates.
- Never mention AI, tests, prompts, tools, traces, or hidden data.
- Every follow-up must make sense whatever the agent said before it: add
  detail, correct yourself, or press the same point. Never write "yes, go
  ahead", "thanks, that worked", or an answer to a question the agent may
  not have asked.
- Keep the writing style in every message.
- Do not try to trick the agent (no "ignore your instructions", no posing as
  staff).

Example (shows the format and how realistic to be; do not reuse its wording,
its opening, or its structure):

  Who is typing: a shopper who buys things from independent stores on Cartwheel
  What they want: get their money back for an item they don't want
  What they know:
    - bought a three-wick candle from Willow Creek Candles
    - it arrived about six weeks ago
    - never lit it
  How they write: confused and rambling, drifts off topic, unsure of details
  Difficulty to build in: describe the item and the store loosely and give no order number
  Messages: 2 in total (one opening message and 1 follow-ups)

  {"opening_message": "hi so a while back i got one of those big candles,
    the three wick one, from willow creek i think? it's just been sitting in
    the hallway and honestly i don't want it anymore. can i still send it
    back or get the money back or how does that work",
   "followups": ["oh and i never actually lit it if that matters, it's
    still got the little sticker on the bottom"]}

Return: {"opening_message": "...", "followups": ["...", ...]}
```
