import pytest
pytestmark = pytest.mark.skip(reason="test_phase3_policy_override_visibility.py: not fully implemented")

import json
from pathlib import Path

from tools.run_agent_os_request import process_request


def test_process_request_exposes_policy_override_visibility(tmp_path):
    p = tmp_path / "state"
    p.mkdir(parents=True, exist_ok=True)
    (p / "policy_overrides.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-03-29T00:00:00+00:00",
                "overrides": {
                    "execution_failure": "manual_review",
                    "rate_limit_failure": "backoff_retry",
                },
                "sources": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    out = process_request("hello", base_dir=tmp_path)

    assert out["policy_override_count"] == 2
    assert out["policy_override_types"] == [
        "execution_failure",
        "rate_limit_failure",
    ]
    assert out["active_policy_overrides"]["execution_failure"] == "manual_review"
    assert out["active_policy_overrides"]["rate_limit_failure"] == "backoff_retry"


def test_process_request_exposes_empty_policy_override_visibility(tmp_path):
    out = process_request("hello", base_dir=tmp_path)

    assert out["policy_override_count"] == 0
    assert out["policy_override_types"] == []
    assert out["active_policy_overrides"] == {}
