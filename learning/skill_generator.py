"""
Skill Generator for Agent OS Learning

Analyzes existing skills, generates new skill templates,
validates them, and deploys upon approval.
"""

import ast
import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = PROJECT_ROOT / "skills"
TESTS_DIR = PROJECT_ROOT / "tests"
LEARNING_DIR = PROJECT_ROOT / "learning"

# Configure logging
LOG_DIR = LEARNING_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"skill_generator_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class SkillGeneratorError(Exception):
    """Base exception for skill generator errors"""
    pass


def get_existing_skills() -> List[Dict[str, Any]]:
    """
    Get list of existing skills with metadata.

    Returns:
        List of skill dicts with name, path, capabilities, etc.
    """
    skills = []

    if not SKILLS_DIR.exists():
        return skills

    for skill_dir in SKILLS_DIR.iterdir():
        if not skill_dir.is_dir():
            continue

        skill_info = {
            "name": skill_dir.name,
            "path": str(skill_dir),
            "has_init": (skill_dir / "__init__.py").exists(),
            "has_skill_py": (skill_dir / "skill.py").exists(),
            "has_tests": (skill_dir / "tests").exists(),
        }

        # Try to extract capabilities from skill.py
        skill_py = skill_dir / "skill.py"
        if skill_py.exists():
            try:
                capabilities = extract_capabilities(skill_py)
                skill_info["capabilities"] = capabilities
            except Exception as e:
                logger.warning(f"Failed to extract capabilities from {skill_py}: {e}")
                skill_info["capabilities"] = []

        skills.append(skill_info)

    return skills


def extract_capabilities(skill_py: Path) -> List[str]:
    """
    Extract function names (capabilities) from a skill.py file.

    Args:
        skill_py: Path to skill.py

    Returns:
        List of function names
    """
    with open(skill_py, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())

    capabilities = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            # Skip private functions
            if not node.name.startswith("_"):
                capabilities.append(node.name)

    return capabilities


def analyze_skill_gaps() -> Dict[str, Any]:
    """
    Analyze existing skills and identify missing functionality.

    Returns:
        Dict with keys:
        - missing: List of missing capabilities
        - suggestions: List of suggested new skills
        - existing: List of existing skills with capabilities
    """
    logger.info("Analyzing skill gaps...")

    existing_skills = get_existing_skills()
    existing_caps = set()

    # Collect all existing capabilities
    for skill in existing_skills:
        for cap in skill.get("capabilities", []):
            existing_caps.add(cap.lower())

    # Define expected capabilities for a complete agent system
    expected_capabilities = {
        # Core functionality
        "task_execution",
        "task_planning",
        "memory_retrieval",
        "memory_storage",
        "decision_making",
        "error_handling",

        # Communication
        "send_message",
        "receive_message",
        "parse_user_input",
        "format_response",

        # Learning
        "learn_from_feedback",
        "update_knowledge",
        "analyze_failures",
        "improve_performance",

        # External tools
        "web_search",
        "file_read",
        "file_write",
        "code_execution",
        "api_call",

        # Monitoring
        "log_event",
        "track_metrics",
        "health_check",

        # Collaboration
        "delegate_task",
        "coordinate_agents",
        "sync_state",
    }

    # Find missing capabilities
    missing_caps = list(expected_capabilities - existing_caps)

    # Generate suggestions for new skills
    suggestions = generate_skill_suggestions(missing_caps, existing_skills)

    result = {
        "existing": existing_skills,
        "missing": missing_caps,
        "suggestions": suggestions,
        "analyzed_at": datetime.now().isoformat(),
    }

    logger.info(f"Found {len(missing_caps)} missing capabilities, {len(suggestions)} suggestions")
    return result


def generate_skill_suggestions(
    missing_caps: List[str],
    existing_skills: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Generate suggestions for new skills based on missing capabilities.

    Args:
        missing_caps: List of missing capabilities
        existing_skills: List of existing skills

    Returns:
        List of suggested skills with name, description, capabilities
    """
    suggestions = []

    # Group related capabilities into potential skills
    skill_templates = [
        {
            "name": "task_executor",
            "description": "Execute tasks with proper error handling and retry logic",
            "capabilities": ["task_execution", "error_handling"],
        },
        {
            "name": "memory_manager",
            "description": "Manage persistent memory storage and retrieval",
            "capabilities": ["memory_retrieval", "memory_storage"],
        },
        {
            "name": "planner",
            "description": "Break down complex goals into executable tasks",
            "capabilities": ["task_planning", "decision_making"],
        },
        {
            "name": "communicator",
            "description": "Handle message formatting and user interaction",
            "capabilities": ["send_message", "receive_message", "parse_user_input", "format_response"],
        },
        {
            "name": "learner",
            "description": "Learn from feedback and improve performance over time",
            "capabilities": ["learn_from_feedback", "update_knowledge", "improve_performance"],
        },
        {
            "name": "tool_user",
            "description": "Interact with external tools and APIs",
            "capabilities": ["web_search", "file_read", "file_write", "code_execution", "api_call"],
        },
        {
            "name": "monitor",
            "description": "Track metrics, health checks, and system status",
            "capabilities": ["log_event", "track_metrics", "health_check"],
        },
        {
            "name": "coordinator",
            "description": "Coordinate multiple agents and delegate tasks",
            "capabilities": ["delegate_task", "coordinate_agents", "sync_state"],
        },
    ]

    # Check which templates are needed
    existing_names = {s["name"] for s in existing_skills}

    for template in skill_templates:
        if template["name"] in existing_names:
            continue

        # Check if any capabilities are missing
        needed_caps = [cap for cap in template["capabilities"] if cap in missing_caps]
        if needed_caps:
            suggestions.append({
                "name": template["name"],
                "description": template["description"],
                "capabilities": needed_caps,
                "priority": len(needed_caps),  # More missing caps = higher priority
            })

    # Sort by priority (descending)
    suggestions.sort(key=lambda x: x["priority"], reverse=True)

    return suggestions


def generate_skill_template(
    skill_name: str,
    description: str,
    capabilities: List[str]
) -> str:
    """
    Generate skill.py template code.

    Args:
        skill_name: Name of the skill
        description: Description of the skill
        capabilities: List of capabilities/functions to implement

    Returns:
        Generated Python code as string
    """
    # Convert skill_name to class name (PascalCase)
    class_name = "".join(word.capitalize() for word in skill_name.split("_"))

    # Generate function stubs
    function_stubs = []
    for cap in capabilities:
        # Convert capability to function name (snake_case)
        func_name = cap.lower().replace(" ", "_").replace("-", "_")
        function_stubs.append(f"""
def {func_name}(*args, **kwargs):
    '''TODO: Implement {cap}'''
    raise NotImplementedError("{func_name} not yet implemented")
    return {{}}
""")

    template = f'''"""
{description}

Skill: {skill_name}
Generated: {datetime.now().isoformat()}
"""

from typing import Any, Dict, List, Optional


class {class_name}:
    """{description}"""

    def __init__(self):
        self.name = "{skill_name}"
        self.capabilities = {capabilities}

    def get_capabilities(self) -> List[str]:
        """Return list of capabilities this skill provides"""
        return self.capabilities


# Skill functions
{"".join(function_stubs)}


def get_skill() -> {class_name}:
    """Get skill instance"""
    return {class_name}()
'''

    return template


def generate_init_template(skill_name: str) -> str:
    """
    Generate __init__.py template code.

    Args:
        skill_name: Name of the skill

    Returns:
        Generated Python code as string
    """
    template = f'''"""
{skill_name} skill
"""

from .skill import get_skill

__all__ = ["get_skill"]
'''

    return template


def generate_test_template(skill_name: str, capabilities: List[str]) -> str:
    """
    Generate test_skill.py template code.

    Args:
        skill_name: Name of the skill
        capabilities: List of capabilities to test

    Returns:
        Generated Python code as string
    """
    # Generate test cases for each capability
    test_cases = []
    for cap in capabilities:
        func_name = cap.lower().replace(" ", "_").replace("-", "_")
        test_cases.append(f'''
    def test_{func_name}(self):
        """Test {cap} capability"""
        # TODO: Implement test for {func_name}
        self.skipTest("Test not yet implemented")
''')

    template = f'''"""
Tests for {skill_name} skill
"""

import unittest
import sys
from pathlib import Path

# Add skills directory to path
SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"
sys.path.insert(0, str(SKILLS_DIR))


class Test{skill_name.capitalize().replace("_", "")}(unittest.TestCase):
    """Test cases for {skill_name} skill"""

    def setUp(self):
        """Set up test fixtures"""
        from {skill_name} import get_skill
        self.skill = get_skill()

    def test_skill_initialization(self):
        """Test skill can be initialized"""
        self.assertIsNotNone(self.skill)
        self.assertEqual(self.skill.name, "{skill_name}")
{"".join(test_cases)}

    def test_get_capabilities(self):
        """Test get_capabilities returns expected list"""
        caps = self.skill.get_capabilities()
        self.assertIsInstance(caps, list)
        self.assertEqual(len(caps), {len(capabilities)})


if __name__ == "__main__":
    unittest.main()
'''

    return template


def generate_skill(
    skill_name: str,
    description: str,
    capabilities: List[str],
    output_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Generate a new skill with templates.

    Args:
        skill_name: Name of the skill
        description: Description of the skill
        capabilities: List of capabilities/functions
        output_dir: Output directory (defaults to learning/generated_skills)

    Returns:
        Dict with keys:
        - ok: True if generation succeeded
        - path: Path to generated skill directory
        - code: Generated code for skill.py
        - error: Error message (if failed)
    """
    logger.info(f"Generating skill: {skill_name}")

    if output_dir is None:
        output_dir = LEARNING_DIR / "generated_skills"

    skill_dir = output_dir / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)

    result = {
        "ok": False,
        "path": str(skill_dir),
        "code": None,
        "error": None,
    }

    try:
        # Generate skill.py
        skill_code = generate_skill_template(skill_name, description, capabilities)
        skill_py = skill_dir / "skill.py"
        skill_py.write_text(skill_code, encoding="utf-8")
        result["code"] = skill_code

        # Generate __init__.py
        init_code = generate_init_template(skill_name)
        init_py = skill_dir / "__init__.py"
        init_py.write_text(init_code, encoding="utf-8")

        # Generate tests directory
        tests_dir = skill_dir / "tests"
        tests_dir.mkdir(exist_ok=True)

        # Generate test_skill.py
        test_code = generate_test_template(skill_name, capabilities)
        test_py = tests_dir / f"test_{skill_name}.py"
        test_py.write_text(test_code, encoding="utf-8")

        result["ok"] = True
        logger.info(f"Skill generated successfully at {skill_dir}")

    except Exception as e:
        result["error"] = str(e)
        logger.error(f"Failed to generate skill: {e}")

    return result


def validate_skill(skill_path: Path) -> Dict[str, Any]:
    """
    Validate a generated skill.

    Args:
        skill_path: Path to skill directory

    Returns:
        Dict with keys:
        - ok: True if validation passed
        - errors: List of error messages
        - warnings: List of warning messages
    """
    logger.info(f"Validating skill at {skill_path}")

    result = {
        "ok": True,
        "errors": [],
        "warnings": [],
    }

    # Check required files
    required_files = ["__init__.py", "skill.py"]
    for file_name in required_files:
        file_path = skill_path / file_name
        if not file_path.exists():
            result["errors"].append(f"Missing required file: {file_name}")
            result["ok"] = False
        else:
            # Check syntax
            try:
                ast.parse(file_path.read_text(encoding="utf-8"))
            except SyntaxError as e:
                result["errors"].append(f"Syntax error in {file_name}: {e}")
                result["ok"] = False

    # Check tests directory
    tests_dir = skill_path / "tests"
    if not tests_dir.exists():
        result["warnings"].append("No tests directory found")
    else:
        test_files = list(tests_dir.glob("test_*.py"))
        if not test_files:
            result["warnings"].append("No test files found in tests/")

    # Try to import the skill
    try:
        import sys
        sys.path.insert(0, str(skill_path.parent))

        # Try to import get_skill
        module_name = skill_path.name
        module = __import__(module_name)

        if not hasattr(module, "get_skill"):
            result["errors"].append("Module does not export get_skill function")
            result["ok"] = False

    except ImportError as e:
        result["errors"].append(f"Failed to import skill: {e}")
        result["ok"] = False
    except Exception as e:
        result["errors"].append(f"Unexpected error importing skill: {e}")
        result["ok"] = False

    # Run tests if they exist
    if tests_dir.exists():
        for test_file in tests_dir.glob("test_*.py"):
            try:
                test_result = subprocess.run(
                    ["python3", "-m", "pytest", str(test_file), "-v"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=skill_path
                )
                if test_result.returncode != 0:
                    result["warnings"].append(f"Tests failed in {test_file.name}")
            except subprocess.TimeoutExpired:
                result["warnings"].append(f"Tests timed out in {test_file.name}")
            except Exception as e:
                result["warnings"].append(f"Could not run tests in {test_file.name}: {e}")

    if result["ok"] and not result["errors"]:
        logger.info(f"Skill validation passed: {skill_path}")
    else:
        logger.warning(f"Skill validation failed: {skill_path}")

    return result


def deploy_skill(skill_path: Path) -> Dict[str, Any]:
    """
    Deploy a validated skill to the skills/ directory.

    Args:
        skill_path: Path to skill directory (in learning/generated_skills)

    Returns:
        Dict with keys:
        - ok: True if deployment succeeded
        - deployed_path: Path to deployed skill
        - error: Error message (if failed)
    """
    logger.info(f"Deploying skill from {skill_path}")

    result = {
        "ok": False,
        "deployed_path": None,
        "error": None,
    }

    try:
        # Validate first
        validation = validate_skill(skill_path)
        if not validation["ok"]:
            result["error"] = f"Validation failed: {', '.join(validation['errors'])}"
            return result

        # Determine target path
        skill_name = skill_path.name
        target_path = SKILLS_DIR / skill_name

        # Create skills directory if it doesn't exist
        SKILLS_DIR.mkdir(parents=True, exist_ok=True)

        # Copy skill files
        if target_path.exists():
            result["error"] = f"Skill {skill_name} already exists at {target_path}"
            return result

        # Copy directory recursively
        import shutil
        shutil.copytree(skill_path, target_path)

        result["ok"] = True
        result["deployed_path"] = str(target_path)
        logger.info(f"Skill deployed to {target_path}")

    except Exception as e:
        result["error"] = str(e)
        logger.error(f"Failed to deploy skill: {e}")

    return result


def save_skill_generation_log(
    action: str,
    skill_name: str,
    result: Dict[str, Any]
) -> None:
    """
    Save skill generation/deployment log.

    Args:
        action: Action type (generate, validate, deploy)
        skill_name: Name of the skill
        result: Result dict
    """
    log_dir = LEARNING_DIR / "skill_generation_logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "skill_name": skill_name,
        "ok": result.get("ok"),
        "error": result.get("error"),
        "path": result.get("path") or result.get("deployed_path"),
    }

    log_file = log_dir / "skill_generation.jsonl"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")


# Example usage
if __name__ == "__main__":
    print("Skill Generator Demo")

    # Analyze skill gaps
    gaps = analyze_skill_gaps()
    print(f"\nFound {len(gaps['missing'])} missing capabilities")
    print(f"Generated {len(gaps['suggestions'])} suggestions")

    # Generate first suggestion
    if gaps["suggestions"]:
        suggestion = gaps["suggestions"][0]
        print(f"\nGenerating skill: {suggestion['name']}")

        result = generate_skill(
            skill_name=suggestion["name"],
            description=suggestion["description"],
            capabilities=suggestion["capabilities"]
        )

        if result["ok"]:
            print(f"✓ Generated at: {result['path']}")

            # Validate
            validation = validate_skill(Path(result["path"]))
            if validation["ok"]:
                print("✓ Validation passed")
            else:
                print(f"✗ Validation failed: {validation['errors']}")
        else:
            print(f"✗ Generation failed: {result['error']}")
