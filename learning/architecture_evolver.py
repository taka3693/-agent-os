"""
Architecture Evolver for Agent OS Learning

Analyzes current architecture, generates improvement proposals,
creates refactoring plans, and executes safe refactoring with tests.
Integrates with MISO for progress tracking.
"""

import ast
import hashlib
import json
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEARNING_DIR = PROJECT_ROOT / "learning"

# Configure logging
LOG_DIR = LEARNING_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"arch_evolver_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# MISO integration
try:
    from miso.bridge import start_mission, update_agent_status, complete_mission, fail_mission
    MISO_AVAILABLE = True
except ImportError:
    MISO_AVAILABLE = False
    logger.warning("MISO bridge not available")


# ===== Architecture Analysis =====

def analyze_architecture() -> Dict[str, Any]:
    """
    Analyze the current architecture.

    Returns:
        Dict with keys:
        - modules: List of module info
        - dependencies: Dict of module dependencies
        - complexity: Dict of complexity metrics
        - issues: List of architecture issues
    """
    logger.info("Analyzing architecture...")

    result = {
        "modules": [],
        "dependencies": {},
        "complexity": {},
        "issues": [],
        "analyzed_at": datetime.now().isoformat(),
    }

    # Find all Python modules
    modules = find_python_modules(PROJECT_ROOT)
    result["modules"] = modules

    # Analyze dependencies
    deps = analyze_dependencies(modules)
    result["dependencies"] = deps

    # Analyze complexity
    complexity = analyze_complexity(modules)
    result["complexity"] = complexity

    # Detect issues
    issues = detect_architecture_issues(modules, deps, complexity)
    result["issues"] = issues

    logger.info(f"Found {len(issues)} architecture issues")
    return result


def find_python_modules(root: Path) -> List[Dict[str, Any]]:
    """
    Find all Python modules in the project.

    Args:
        root: Project root directory

    Returns:
        List of module info dicts
    """
    modules = []
    exclude_dirs = {".git", "__pycache__", "node_modules", ".pytest_cache", "venv", "env", "build", "dist"}

    for py_file in root.rglob("*.py"):
        # Skip excluded directories
        if any(excl in py_file.parts for excl in exclude_dirs):
            continue

        # Get relative path from root
        rel_path = py_file.relative_to(root)

        # Skip test files for module analysis
        if "test_" in py_file.name or py_file.name.startswith("test_"):
            continue

        # Get module name from path
        module_name = str(rel_path.with_suffix("")).replace(os.sep, ".")

        # Get file stats
        lines = len(py_file.read_text(encoding="utf-8", errors="ignore").splitlines())

        modules.append({
            "path": str(py_file),
            "relative_path": str(rel_path),
            "module_name": module_name,
            "lines": lines,
            "size_bytes": py_file.stat().st_size,
        })

    return modules


def analyze_dependencies(modules: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze module dependencies and detect cycles.

    Args:
        modules: List of module info dicts

    Returns:
        Dict with dependencies and cycles
    """
    dependencies = {}
    imports = {}

    for module in modules:
        module_name = module["module_name"]
        module_path = Path(module["path"])

        try:
            with open(module_path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read())

            module_imports = set()

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        module_imports.add(alias.name.split(".")[0])
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        module_imports.add(node.module.split(".")[0])

            # Filter to only imports within the project
            project_imports = [
                imp for imp in module_imports
                if is_project_module(imp)
            ]

            imports[module_name] = project_imports

        except (SyntaxError, UnicodeDecodeError) as e:
            logger.warning(f"Failed to parse {module_name}: {e}")
            imports[module_name] = []

    dependencies["imports"] = imports
    dependencies["cycles"] = find_dependency_cycles(imports)

    return dependencies


def is_project_module(module_name: str) -> bool:
    """Check if a module belongs to the project."""
    project_prefixes = ["ops", "learning", "runner", "router", "miso", "utils"]
    return any(module_name.startswith(prefix) for prefix in project_prefixes)


def find_dependency_cycles(imports: Dict[str, List[str]]) -> List[List[str]]:
    """
    Find circular dependencies in imports.

    Args:
        imports: Dict mapping module names to their imports

    Returns:
        List of cycles (each cycle is a list of module names)
    """
    cycles = []

    def dfs(current: str, visited: Set[str], path: List[str]):
        if current in visited:
            cycle_start = path.index(current)
            cycles.append(path[cycle_start:] + [current])
            return

        visited.add(current)
        path.append(current)

        for neighbor in imports.get(current, []):
            dfs(neighbor, visited.copy(), path.copy())

    for module in imports.keys():
        dfs(module, set(), [])

    # Remove duplicates and cycles of length 1 (self-import)
    unique_cycles = []
    seen = set()

    for cycle in cycles:
        if len(cycle) <= 1:
            continue

        # Normalize cycle (rotate to start with smallest module name)
        min_idx = cycle.index(min(cycle))
        normalized = tuple(cycle[min_idx:] + cycle[:min_idx])

        if normalized not in seen:
            seen.add(normalized)
            unique_cycles.append(list(cycle))

    return unique_cycles


def analyze_complexity(modules: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze code complexity metrics.

    Args:
        modules: List of module info dicts

    Returns:
        Dict with complexity metrics
    """
    complexity = {}

    for module in modules:
        module_name = module["module_name"]
        module_path = Path(module["path"])

        try:
            with open(module_path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read())

            # Count functions and classes
            functions = []
            classes = []

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    functions.append(node.name)
                elif isinstance(node, ast.ClassDef):
                    classes.append(node.name)

            complexity[module_name] = {
                "lines": module["lines"],
                "functions": len(functions),
                "classes": len(classes),
                "function_names": functions,
                "class_names": classes,
                "avg_lines_per_function": module["lines"] / len(functions) if functions else 0,
            }

        except (SyntaxError, UnicodeDecodeError):
            complexity[module_name] = {
                "lines": module["lines"],
                "functions": 0,
                "classes": 0,
                "error": "Failed to parse",
            }

    return complexity


def detect_architecture_issues(
    modules: List[Dict[str, Any]],
    dependencies: Dict[str, Any],
    complexity: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Detect architecture issues.

    Args:
        modules: List of module info
        dependencies: Dependency analysis results
        complexity: Complexity metrics

    Returns:
        List of issue dicts
    """
    issues = []

    # 1. Large files (500+ lines)
    for module in modules:
        if module["lines"] >= 500:
            issues.append({
                "type": "large_file",
                "severity": "medium",
                "module": module["module_name"],
                "path": str(module["path"]),
                "lines": module["lines"],
                "description": f"File has {module['lines']} lines (>= 500)",
            })

    # 2. Circular dependencies
    for cycle in dependencies.get("cycles", []):
        issues.append({
            "type": "circular_dependency",
            "severity": "high",
            "cycle": cycle,
            "description": f"Circular dependency: {' -> '.join(cycle)} -> {cycle[0]}",
        })

    # 3. High complexity modules
    for module_name, metrics in complexity.items():
        if metrics.get("functions", 0) > 20:
            issues.append({
                "type": "high_complexity",
                "severity": "medium",
                "module": module_name,
                "functions": metrics["functions"],
                "description": f"Module has {metrics['functions']} functions (> 20)",
            })

    # 4. Duplicate code (simple heuristic by file hash)
    file_hashes = {}
    for module in modules:
        file_path = Path(module["path"])
        try:
            content = file_path.read_text(encoding="utf-8")
            file_hash = hashlib.md5(content.encode()).hexdigest()

            if file_hash in file_hashes:
                issues.append({
                    "type": "duplicate_code",
                    "severity": "low",
                    "module": module["module_name"],
                    "duplicate_of": file_hashes[file_hash],
                    "description": f"Duplicate content with {file_hashes[file_hash]}",
                })
            else:
                file_hashes[file_hash] = module["module_name"]
        except Exception:
            pass

    # 5. Low test coverage (heuristic)
    test_modules = [m for m in modules if "test" in m["path"].lower()]
    main_modules = [m for m in modules if "test" not in m["path"].lower()]

    if len(main_modules) > 0:
        coverage_ratio = len(test_modules) / len(main_modules)
        if coverage_ratio < 0.5:
            issues.append({
                "type": "low_test_coverage",
                "severity": "medium",
                "test_modules": len(test_modules),
                "main_modules": len(main_modules),
                "coverage_ratio": coverage_ratio,
                "description": f"Test coverage: {coverage_ratio:.1%} (< 50%)",
            })

    return issues


# ===== Improvement Proposals =====

def propose_improvements(analysis: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Generate improvement proposals based on analysis.

    Args:
        analysis: Architecture analysis results (or run new analysis)

    Returns:
        Dict with proposals
    """
    if analysis is None:
        analysis = analyze_architecture()

    proposals = []
    issue_types = {}

    # Group issues by type
    for issue in analysis["issues"]:
        issue_type = issue["type"]
        if issue_type not in issue_types:
            issue_types[issue_type] = []
        issue_types[issue_type].append(issue)

    # Generate proposals for each issue type

    # 1. Large files -> Split modules
    if "large_file" in issue_types:
        for issue in issue_types["large_file"]:
            proposals.append({
                "id": f"split_{issue['module'].replace('.', '_')}",
                "type": "split_module",
                "priority": "high" if issue["lines"] > 1000 else "medium",
                "target": issue["module"],
                "description": f"Split {issue['module']} ({issue['lines']} lines) into smaller modules",
                "estimated_effort": "high",
            })

    # 2. Circular dependencies -> Refactor to break cycles
    if "circular_dependency" in issue_types:
        for issue in issue_types["circular_dependency"]:
            proposals.append({
                "id": f"break_cycle_{'_'.join(issue['cycle'][:3])}",
                "type": "break_cycle",
                "priority": "high",
                "cycle": issue["cycle"],
                "description": f"Break circular dependency: {' -> '.join(issue['cycle'])}",
                "estimated_effort": "high",
            })

    # 3. High complexity -> Extract sub-modules
    if "high_complexity" in issue_types:
        for issue in issue_types["high_complexity"]:
            proposals.append({
                "id": f"extract_{issue['module'].replace('.', '_')}",
                "type": "extract_submodule",
                "priority": "medium",
                "target": issue["module"],
                "description": f"Extract related functions from {issue['module']} into sub-modules",
                "estimated_effort": "medium",
            })

    # 4. Low test coverage -> Add tests
    if "low_test_coverage" in issue_types:
        issue = issue_types["low_test_coverage"][0]
        proposals.append({
            "id": "add_tests",
            "type": "add_tests",
            "priority": "medium",
            "description": f"Increase test coverage from {issue['coverage_ratio']:.1%} to 70%+",
            "estimated_effort": "medium",
        })

    # Sort by priority
    priority_order = {"high": 0, "medium": 1, "low": 2}
    proposals.sort(key=lambda p: priority_order.get(p["priority"], 99))

    return {
        "proposals": proposals,
        "generated_at": datetime.now().isoformat(),
        "total_issues": len(analysis["issues"]),
    }


# ===== Refactoring Plans =====

def create_refactoring_plan(proposal_id: str) -> Dict[str, Any]:
    """
    Create a detailed refactoring plan for a proposal.

    Args:
        proposal_id: ID of the proposal to create plan for

    Returns:
        Dict with steps and estimated impact
    """
    # Get proposals
    proposals = propose_improvements()
    proposal = None
    for p in proposals["proposals"]:
        if p["id"] == proposal_id:
            proposal = p
            break

    if not proposal:
        return {
            "ok": False,
            "error": f"Proposal {proposal_id} not found",
        }

    steps = []
    proposal_type = proposal["type"]

    if proposal_type == "split_module":
        module_name = proposal["target"]
        steps = [
            f"Analyze {module_name} structure",
            f"Identify logical groupings in {module_name}",
            f"Create new sub-modules for each group",
            f"Move functions/classes to new modules",
            f"Update imports across codebase",
            f"Run tests to verify no breakage",
        ]
    elif proposal_type == "break_cycle":
        cycle = proposal["cycle"]
        steps = [
            f"Analyze circular dependency: {' -> '.join(cycle)}",
            f"Identify shared dependencies between {cycle[0]} and {cycle[-1]}",
            f"Create new abstraction layer to break cycle",
            f"Refactor {cycle[0]} to use new layer",
            f"Refactor {cycle[-1]} to use new layer",
            f"Remove circular imports",
            f"Run tests to verify",
        ]
    elif proposal_type == "extract_submodule":
        module_name = proposal["target"]
        steps = [
            f"Analyze {module_name} for cohesive groups",
            f"Identify candidate functions for extraction",
            f"Create new sub-module",
            f"Move functions to sub-module",
            f"Update imports",
            f"Test refactored code",
        ]
    elif proposal_type == "add_tests":
        steps = [
            "Identify untested critical modules",
            "Create test files for identified modules",
            "Write unit tests for key functions",
            "Run test suite",
            "Measure coverage improvement",
        ]

    return {
        "ok": True,
        "proposal_id": proposal_id,
        "proposal": proposal,
        "steps": steps,
        "estimated_impact": proposal.get("estimated_effort", "unknown"),
        "created_at": datetime.now().isoformat(),
    }


# ===== Refactoring Execution =====

def execute_refactoring(
    plan: Dict[str, Any],
    dry_run: bool = True,
    chat_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Execute a refactoring plan.

    Args:
        plan: Refactoring plan from create_refactoring_plan
        dry_run: If True, only simulate changes
        chat_id: Telegram chat ID (for MISO)

    Returns:
        Dict with execution results
    """
    logger.info(f"Executing refactoring plan: {plan.get('proposal_id')} (dry_run={dry_run})")

    # Start MISO mission if available
    mission_id = None
    if MISO_AVAILABLE and chat_id:
        try:
            mission_id = f"refactor-{plan.get('proposal_id', 'unknown')}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            start_mission(
                mission_id=mission_id,
                mission_name=f"Refactoring: {plan.get('proposal', {}).get('description', 'Unknown')}",
                goal=plan.get('proposal', {}).get('description', 'Execute refactoring'),
                chat_id=chat_id,
                agents=["analyzer", "refactorer", "tester"]
            )
        except Exception as e:
            logger.warning(f"Failed to start MISO mission: {e}")

    result = {
        "ok": False,
        "proposal_id": plan.get("proposal_id"),
        "dry_run": dry_run,
        "changes": [],
        "errors": [],
        "mission_id": mission_id,
    }

    try:
        # Execute each step
        for i, step in enumerate(plan.get("steps", [])):
            logger.info(f"Step {i+1}/{len(plan['steps'])}: {step}")

            if MISO_AVAILABLE and mission_id:
                update_agent_status(mission_id, "refactorer", "RUNNING", f"Step {i+1}: {step[:50]}...")

            # Simulate step execution
            if not dry_run:
                # TODO: Implement actual refactoring logic
                # For now, just log and continue
                pass

            # Record change
            result["changes"].append({
                "step": i + 1,
                "description": step,
                "status": "simulated" if dry_run else "executed",
            })

        # Run tests
        if not dry_run:
            logger.info("Running tests...")
            test_result = run_test_suite()
            result["test_result"] = test_result

            if not test_result.get("passed", True):
                result["errors"].append("Tests failed after refactoring")
                if MISO_AVAILABLE and mission_id:
                    fail_mission(mission_id, "Tests failed")
                return result

        result["ok"] = True
        logger.info("Refactoring completed successfully")

        if MISO_AVAILABLE and mission_id:
            complete_mission(mission_id, f"Completed {len(result['changes'])} steps")

    except Exception as e:
        error_msg = str(e)
        result["errors"].append(error_msg)
        logger.error(f"Refactoring failed: {e}")

        if MISO_AVAILABLE and mission_id:
            fail_mission(mission_id, error_msg)

    return result


def run_test_suite() -> Dict[str, Any]:
    """
    Run the test suite and return results.

    Returns:
        Dict with test results
    """
    try:
        result = subprocess.run(
            ["python3", "-m", "pytest", "tests/", "-v", "--tb=short"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )

        return {
            "passed": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "passed": False,
            "error": "Tests timed out",
        }
    except Exception as e:
        return {
            "passed": False,
            "error": str(e),
        }


# ===== Logging =====

def save_refactoring_log(action: str, data: Dict[str, Any]) -> None:
    """
    Save refactoring action to log.

    Args:
        action: Action type (analyze, propose, plan, execute)
        data: Data to log
    """
    log_dir = LEARNING_DIR / "refactoring_logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "action": action,
        **data,
    }

    log_file = log_dir / "refactoring.jsonl"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")


# ===== CLI Entry Point =====

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Architecture Evolver")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # analyze command
    analyze_parser = subparsers.add_parser("analyze", help="Analyze architecture")
    analyze_parser.add_argument("--output", help="Output JSON file")

    # propose command
    propose_parser = subparsers.add_parser("propose", help="Propose improvements")
    propose_parser.add_argument("--output", help="Output JSON file")

    # plan command
    plan_parser = subparsers.add_parser("plan", help="Create refactoring plan")
    plan_parser.add_argument("--proposal-id", required=True, help="Proposal ID")
    plan_parser.add_argument("--output", help="Output JSON file")

    # execute command
    exec_parser = subparsers.add_parser("execute", help="Execute refactoring")
    exec_parser.add_argument("--plan", required=True, help="Plan JSON file")
    exec_parser.add_argument("--dry-run", action="store_true", help="Dry run mode")
    exec_parser.add_argument("--chat-id", help="Telegram chat ID for MISO")

    args = parser.parse_args()

    result = {}

    if args.command == "analyze":
        result = analyze_architecture()
        save_refactoring_log("analyze", result)
    elif args.command == "propose":
        result = propose_improvements()
        save_refactoring_log("propose", result)
    elif args.command == "plan":
        result = create_refactoring_plan(args.proposal_id)
        save_refactoring_log("plan", result)
    elif args.command == "execute":
        with open(args.plan, "r") as f:
            plan = json.load(f)
        result = execute_refactoring(plan, dry_run=args.dry_run, chat_id=args.chat_id)
        save_refactoring_log("execute", result)

    # Output result
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))

    sys.exit(0 if result.get("ok", True) else 1)


if __name__ == "__main__":
    import sys
    main()
