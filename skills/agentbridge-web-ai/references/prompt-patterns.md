# Prompt patterns

Use these as shapes, not mandatory wording. Include only information the user
has authorized for the paired webpage AI.

## Architecture challenge

```text
You are an independent system architecture reviewer. Challenge the proposed
design; do not assume its current node boundaries or historical approach are
correct.

Goal:
<one concise goal>

Observed facts:
- <fact 1>
- <fact 2>

Open decision:
<one decision>

Return at most 6 items:
1. verdict: proceed / revise / insufficient evidence
2. strongest objection
3. causal mechanism behind the objection
4. smallest experiment or observation that would resolve it
5. one viable alternative
6. confidence and remaining uncertainty
```

The default `ask_chatgpt` path already requires a completion marker for this kind
of structured review. Pass `require_completion_marker=true` explicitly when
writing the call; the transport then waits for a final marker and does not treat
a mid-JSON pause as a complete answer.

## Planning alternative

```text
Act as a second planner, not an executor. Given the goal and constraints below,
propose at most three genuinely different routes. For each route state its key
assumption, main risk, and the first falsifiable check.

Goal: <goal>
Constraints: <constraints>
Known evidence: <facts only>
```

## Incomplete-answer retry

Use only once when the first result is visibly incomplete:

```text
Your prior answer was incomplete. Re-answer only this narrow question:
<single missing decision>

Return no more than 5 bullets, each under 80 Chinese characters.
```
