---
children_hash: 9e348275e36579df4caec240e82372016a31fe877c0ed330f0e15fdc550762b4
compression_ratio: 0.925
condensation_order: 1
covers: [context.md, implementation_design.md]
covers_token_total: 600
summary_level: d1
token_count: 555
type: summary
---
# Learning Memory Layer Structural Summary (Level d1)

The Learning Memory Layer for Agent-OS v2 is an append-only architectural component designed to track agent episodes and derive insights through a human-in-the-loop, safety-first framework.

## Core Architecture & State Management
The system utilizes an append-only design to ensure data integrity and historical preservation. State is persisted in two primary JSONL files located in the `state/` directory:
*   `learning_episodes.jsonl`: Stores original episodes and consolidated classifications.
*   `learning_insights.jsonl`: Stores generated insights derived from episode analysis.

**Key Technical Decision**: In-place mutation of episode records is strictly prohibited to ensure a reliable audit trail.

## Operational Workflow
The layer operates through a four-stage pipeline:
1.  **record_episode**: Captures raw agent activity (depends on `apply_plan_id`).
2.  **classify_outcome**: Categorizes the result using a standardized taxonomy.
3.  **generate_insights**: Produces recommendations based on outcomes.
4.  **query_similar_episodes**: enables retrieval of historical context for current tasks.

## Taxonomy & Classification
Outcomes are classified into a seven-category taxonomy to standardize learning:
*   `success_clean`, `success_high_friction`
*   `blocked_by_governance`, `failed_verification`
*   `rejected_low_confidence`, `stale_abandoned`, `revert_recommended`

## Governance & Safety Rules
The implementation enforces rigorous constraints to prevent autonomous drift:
*   **No Automation**: Automatic apply, rollback, commit, or promotion of changes is prohibited.
*   **No Auto-tuning**: Policy and governance rules cannot be automatically adjusted by the system.
*   **Human-in-the-Loop**: Insights serve as recommendations only and require manual operator oversight.
*   **Pilot Constraints**: Operations are limited to a single repository and a single operator to minimize risk.

## Reference Entries
For detailed implementation specifics, refer to:
*   **context.md**: General overview, key concepts, and pilot operation rules.
*   **implementation_design.md**: Technical specifications, file paths, API flow, and verbatim safety rules.