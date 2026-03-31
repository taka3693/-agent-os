---
children_hash: ddec00edb7a302987f7cdae6472e5b0063746085b66a9fc6e8ac685356bf1842
compression_ratio: 0.8428571428571429
condensation_order: 2
covers: [context.md, learning_memory/_index.md]
covers_token_total: 700
summary_level: d2
token_count: 590
type: summary
---
# Architecture Domain Structural Summary (Level d2)

The **architecture** domain defines the design patterns, state management strategies, and safety governance for Agent-OS components, specifically focusing on the Learning Memory Layer.

## Learning Memory Layer (v2)
The Learning Memory Layer is an append-only architectural component designed for tracking agent episodes and deriving insights through a human-in-the-loop framework. 

### Core Architecture & State Management
The system prioritizes data integrity and historical preservation by prohibiting in-place mutation of records. State is persisted within the `state/` directory via two primary JSONL files:
*   `learning_episodes.jsonl`: Original episodes and consolidated classifications.
*   `learning_insights.jsonl`: Generated recommendations derived from episode analysis.

### Operational Workflow & Taxonomy
The layer follows a four-stage pipeline to standardize learning:
1.  **record_episode**: Captures raw activity (depends on `apply_plan_id`).
2.  **classify_outcome**: Categorizes results into a seven-category taxonomy (e.g., `success_clean`, `blocked_by_governance`, `failed_verification`).
3.  **generate_insights**: Produces recommendations based on analyzed outcomes.
4.  **query_similar_episodes**: Facilitates retrieval of historical context for current tasks.

### Governance & Safety Framework
Rigorous constraints are enforced to prevent autonomous drift and minimize risk:
*   **Manual Oversight**: Insights serve as recommendations only; automatic apply, rollback, commit, or promotion of changes is strictly prohibited.
*   **Static Policy**: The system cannot automatically adjust policy or governance rules.
*   **Pilot Constraints**: Operations are restricted to a single repository and a single operator.

## Reference Entries
For further details on the architectural components and implementation specifics, refer to the following entries:
*   **architecture/context.md**: Domain purpose, scope, and high-level design patterns.
*   **architecture/learning_memory/_index.md (d1)**: Detailed summary of the Learning Memory Layer architecture and state management.
*   **learning_memory/context.md**: Key concepts and pilot operation rules.
*   **learning_memory/implementation_design.md**: Technical specifications, API signatures, file paths, and verbatim safety rules.