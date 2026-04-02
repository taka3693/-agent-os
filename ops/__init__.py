"""Agent-OS Operations Module

AGI Capabilities:
- Proactive: proactive_observer, proactive_generator, proactive_runner
- Goals: goal_store, goal_decomposer, progress_tracker
- Meta-cognition: capability_model, self_assessor, limitation_detector
- Multimodal: multimodal_input, vision_processor, output_generator
- External: github_observer, environment_monitor, event_reactor

Approval System:
- approval_queue, approval_decision, approval_executor, approval_facade

Core:
- action_fingerprint, action_queue, cooldown, health, policy
"""

# AGI exports
from ops.proactive_observer import observe_system
from ops.proactive_generator import generate_proactive_tasks
from ops.goal_store import create_goal, get_goal, list_goals
from ops.capability_model import CAPABILITIES, get_capability
from ops.self_assessor import assess_task
from ops.limitation_detector import detect_limitation
