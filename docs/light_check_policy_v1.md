# Light Check Policy v1

## Purpose

Light Check Policy is a lightweight pre-execution context check that reduces route / layer / intent mix-ups without replacing existing safety systems.

It does **not** replace:
- `execution/guard.py`
- `governance/operating_policy.py`
- controlled scheduler detect/report rules

It is designed to add a short confirmation only when ambiguity is meaningful.

## Scope

Initial v1 scope:
- install
- uninstall
- update

Out of scope:
- delete / publish / send / apply / commit / promote / revert
- code safety validation
- permission decisions

## Reason codes

- `LAYER_COLLISION`
- `RECENT_REVERSE_ACTION`
- `ROUTE_AMBIGUITY`

## Design principles

1. Single short confirmation
2. One issue per check
3. Maximum two choices
4. No repeated checks for the same topic within the current task
5. Preserve execution flow after confirmation

## Execution position

Recommended order:

`intent/router -> light_check_policy -> execution_policy -> guard/governance`

For v1 implementation in Agent-OS, the first integration point is the task execution path in `runner/run_task_once.py` before skill dispatch.

## Output schema

```json
{
  "check_required": true,
  "reason_codes": ["LAYER_COLLISION", "RECENT_REVERSE_ACTION"],
  "topic_key": "scrapling_install_route",
  "question": "確認: 今回は ClawHub ではなく Scrapling本体を直接入れる認識でよいでござるか？",
  "choices": [
    {"id": "clawhub_skill", "label": "ClawHub skill"},
    {"id": "direct_install", "label": "Scrapling本体の直入れ"}
  ],
  "ttl_scope": "current_task",
  "recheck_allowed": false
}
```

## Minimal v1 behavior

- Detect install/uninstall/update wording
- Detect whether the same target appears in multiple layers
- Detect whether the immediately recent action is the reverse of the current request
- Detect whether multiple routes are known for the target
- If triggered, return a structured check payload instead of silently selecting a route

## Notes

- v1 should prefer conservative, explicit matching over clever heuristics
- v1 should log checks for later tuning
- v1 should avoid broad NLP-style ambiguity detection
