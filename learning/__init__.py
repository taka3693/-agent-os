"""Agent-OS Learning Module

Learning System:
- pattern_extractor: Extract patterns from execution history
- action_policy: Store and apply learned policies
- learning_runner: Run learning cycles

Self-Improvement:
- failure_analyzer: Detect issues (logs, tests, timeouts)
- fix_proposer: Generate fix proposals (rule-based)
- llm_fix_proposer: Generate fixes using LLM (GLM-5)
- self_improve: Orchestrate improvement cycles
"""

from learning.pattern_extractor import extract_patterns
from learning.action_policy import get_policy, apply_policy
from learning.learning_runner import run_learning_cycle
from learning.self_improve import run_improvement_cycle
