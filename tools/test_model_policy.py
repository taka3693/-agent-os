#!/usr/bin/env python3
"""Test model policy resolution.

Validates:
1. resolve_role_for_skill() - skill → role mapping
2. resolve_model_for_skill() - skill → role → model resolution
3. OpenClaw roles follow - config changes reflect without code changes
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from router.model_policy import (
    resolve_role_for_skill,
    resolve_model_for_skill,
    list_skill_role_mappings,
    list_role_model_mappings,
    _clear_cache,
)


def test_skill_role_mapping():
    """Test skill → role resolution."""
    expected = {
        "research": "primary",
        "decision": "primary",
        "execution": "subagent",
        "critique": "reviewer",
        "retrospective": "deep_reviewer",
    }
    actual = list_skill_role_mappings()

    if actual != expected:
        print(json.dumps({
            "ok": False,
            "test": "skill_role_mapping",
            "expected": expected,
            "actual": actual
        }, indent=2))
        return False

    # Test individual resolutions
    for skill, expected_role in expected.items():
        actual_role = resolve_role_for_skill(skill)
        if actual_role != expected_role:
            print(json.dumps({
                "ok": False,
                "test": "resolve_role_for_skill",
                "skill": skill,
                "expected": expected_role,
                "actual": actual_role
            }, indent=2))
            return False

    return True


def test_role_model_from_openclaw():
    """Test role → model resolution from OpenClaw config."""
    expected_roles = {
        "primary": "zai/glm-5",
        "subagent": "openrouter/moonshotai/kimi-k2.5",
        "reviewer": "anthropic/claude-sonnet-4-6",
        "deep_reviewer": "anthropic/claude-opus-4-6",
    }
    actual = list_role_model_mappings()

    for role, expected_model in expected_roles.items():
        if actual.get(role) != expected_model:
            print(json.dumps({
                "ok": False,
                "test": "role_model_from_openclaw",
                "role": role,
                "expected": expected_model,
                "actual": actual.get(role)
            }, indent=2))
            return False

    return True


def test_skill_model_resolution():
    """Test full skill → role → model resolution."""
    expected = {
        "research": ("primary", "zai/glm-5"),
        "decision": ("primary", "zai/glm-5"),
        "execution": ("subagent", "openrouter/moonshotai/kimi-k2.5"),
        "critique": ("reviewer", "anthropic/claude-sonnet-4-6"),
        "retrospective": ("deep_reviewer", "anthropic/claude-opus-4-6"),
    }

    for skill, (expected_role, expected_model) in expected.items():
        actual_role = resolve_role_for_skill(skill)
        actual_model = resolve_model_for_skill(skill)

        if actual_role != expected_role or actual_model != expected_model:
            print(json.dumps({
                "ok": False,
                "test": "skill_model_resolution",
                "skill": skill,
                "expected_role": expected_role,
                "actual_role": actual_role,
                "expected_model": expected_model,
                "actual_model": actual_model
            }, indent=2))
            return False

    return True


def test_openclaw_roles_follow():
    """Test that changing OpenClaw roles reflects without code changes."""
    config_path = Path.home() / ".openclaw" / "openclaw.json"

    # Save original
    config = json.loads(config_path.read_text())
    original_reviewer = config["agents"]["defaults"]["roles"]["reviewer"]

    try:
        # Clear cache
        _clear_cache()

        # Get before
        before = resolve_model_for_skill("critique")

        # Change config
        config["agents"]["defaults"]["roles"]["reviewer"] = "test-model-xxx"
        config_path.write_text(json.dumps(config, indent=2))

        # Clear cache and get after
        _clear_cache()
        after = resolve_model_for_skill("critique")

        # Verify change
        if after != "test-model-xxx":
            print(json.dumps({
                "ok": False,
                "test": "openclaw_roles_follow",
                "before": before,
                "expected_after": "test-model-xxx",
                "actual_after": after
            }, indent=2))
            return False

        # Restore and verify
        config["agents"]["defaults"]["roles"]["reviewer"] = original_reviewer
        config_path.write_text(json.dumps(config, indent=2))
        _clear_cache()

        restored = resolve_model_for_skill("critique")
        if restored != original_reviewer:
            print(json.dumps({
                "ok": False,
                "test": "openclaw_roles_follow_restore",
                "expected": original_reviewer,
                "actual": restored
            }, indent=2))
            return False

        return True

    except Exception as e:
        # Ensure restore on error
        config["agents"]["defaults"]["roles"]["reviewer"] = original_reviewer
        config_path.write_text(json.dumps(config, indent=2))
        _clear_cache()
        raise


def test_unknown_skill_fallback():
    """Test that unknown skills fall back to default."""
    role = resolve_role_for_skill("unknown_skill_xyz")
    model = resolve_model_for_skill("unknown_skill_xyz")

    if role != "primary":
        print(json.dumps({
            "ok": False,
            "test": "unknown_skill_fallback_role",
            "expected": "primary",
            "actual": role
        }, indent=2))
        return False

    if model != "zai/glm-5":
        print(json.dumps({
            "ok": False,
            "test": "unknown_skill_fallback_model",
            "expected": "zai/glm-5",
            "actual": model
        }, indent=2))
        return False

    return True


def main():
    tests = [
        ("skill_role_mapping", test_skill_role_mapping),
        ("role_model_from_openclaw", test_role_model_from_openclaw),
        ("skill_model_resolution", test_skill_model_resolution),
        ("openclaw_roles_follow", test_openclaw_roles_follow),
        ("unknown_skill_fallback", test_unknown_skill_fallback),
    ]

    results = []
    all_passed = True

    for name, fn in tests:
        _clear_cache()
        try:
            passed = fn()
            results.append({"name": name, "passed": passed})
            if not passed:
                all_passed = False
        except Exception as e:
            results.append({"name": name, "passed": False, "error": str(e)})
            all_passed = False

    print(json.dumps({
        "ok": all_passed,
        "test_count": len(tests),
        "passed": sum(1 for r in results if r["passed"]),
        "failed": sum(1 for r in results if not r["passed"]),
        "results": results
    }, indent=2))

    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
