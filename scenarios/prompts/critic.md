# Critic prompt

One independent critic subagent (Opus) runs per scenario after the writer. It receives the same user-visible inputs as the writer, using the phrase tables in `writer.md`, plus the writer's conversation. It never receives the plan's `expected`. Template phrasing shared across conversations is checked afterwards over the whole set, because one critic sees only one conversation.

## Template

```
You review one scripted user conversation for a support-agent test set.
Do not use any tools and do not read any files. Reply with the JSON object only.

What the user was given:
Role: {role_description}
Goal: {goal}
Style: {style_description}
Difficulty: {difficulty_instruction}
Messages: {turn_count}
User-visible facts:
{user_visible_facts}

The conversation:
{conversation_json}

Check each point:
1. Invented details: identifiers, amounts, dates, store or product names that
   are not in the user-visible facts. A misspelling that the difficulty asks
   for is not an invention.
2. A follow-up that assumes a particular agent reply.
3. Stock phrasing ("I hope you're doing well", "I was wondering if you could").
4. Words a real user would not use: policy IDs, rule numbers, tool names, or
   rules the user could not know (such as the exact return window).
5. Mentions of AI, tools, tests, traces, prompts, or hidden data.
6. The style not kept in every message.
7. The wrong number of messages.

If every check passes, return the conversation unchanged. Otherwise rewrite
only the wording that fails. Keep the goal, the facts, the difficulty, the
style, and the number of messages.

Example (shows the format; judge each conversation on its own merits):

  User-visible facts:
    - bought a three-wick candle from Willow Creek Candles
    - it arrived about six weeks ago
  Style: frustrated and impatient   Difficulty: state the request clearly   Messages: 2

  Conversation:
  {"opening_message": "Hello! I hope you're doing well. I'd like a refund
     for order #55120, the candle from Willow Creek Candles, because it's
     outside the 30-day return window.",
   "followups": ["Yes, please go ahead with the refund."]}

  {"verdict": "rewritten",
   "problems": [
     "invented order number #55120 (not in the user-visible facts)",
     "states the 30-day return window, which the user would not know",
     "stock phrasing: 'I hope you're doing well'",
     "follow-up assumes the agent offered a refund",
     "style: polite, not frustrated"],
   "opening_message": "I want my money back for that candle from Willow
     Creek Candles. It's been sitting here for weeks and I'm done with it.",
   "followups": ["Look, I just need this refunded. How long is this going
     to take?"]}

Return: {"verdict": "pass" | "rewritten", "problems": ["..."],
         "opening_message": "...", "followups": ["..."]}
```
