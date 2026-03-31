---
children_hash: c3d07f562b04a48f4e6cc046d3aefc93c70b02dc8f6a6104ce0e93e7459b1cf9
compression_ratio: 0.8447488584474886
condensation_order: 3
covers: [architecture/_index.md]
covers_token_total: 657
summary_level: d3
token_count: 555
type: summary
---
# Architecture Domain Structural Summary (Level d3)

The **architecture** domain establishes the design patterns, state management, and safety governance for Agent-OS, centered on a non-mutating Learning Memory Layer for episode tracking and insight derivation.

## Learning Memory Layer (v2)
An append-only architectural component that utilizes a human-in-the-loop framework to standardize agent learning without autonomous drift.

### State Management & Persistence
The system enforces historical preservation by prohibiting in-place record mutation. Persistent state is maintained within the `state/` directory via two primary JSONL schemas:
*   `learning_episodes.jsonl`: Captures raw activity and consolidated outcome classifications.
*   `learning_insights.jsonl`: Stores generated recommendations derived from episode analysis.

### Standardized Operational Workflow
Standardization is achieved through a four-stage pipeline:
1.  **Record**: Captures activity (dependent on `apply_plan_id`).
2.  **Classify**: Categorizes outcomes into a seven-part taxonomy (e.g., `success_clean`, `blocked_by_governance`, `failed_verification`).
3.  **Generate**: Produces insights and recommendations based on analyzed outcomes.
4.  **Query**: Facilitates historical context retrieval for current task execution.

### Governance & Pilot Constraints
Strict safety boundaries are enforced to minimize operational risk:
*   **Recommendation Only**: Insights cannot be automatically applied, committed, or promoted; manual oversight is mandatory.
*   **Static Policy**: The system is barred from autonomous policy or governance rule adjustments.
*   **Scope Limitation**: Operations are restricted to a single repository and a single operator during the pilot phase.

## Reference Entries
For specific implementation details, refer to the following child entries:
*   **architecture/context.md**: Domain purpose and high-level design patterns.
*   **architecture/learning_memory/_index.md**: Summary of layer architecture and state management.
*   **learning_memory/context.md**: Pilot operation rules and key concepts.
*   **learning_memory/implementation_design.md**: API signatures, file paths, and verbatim safety constraints.