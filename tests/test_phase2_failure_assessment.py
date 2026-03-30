from tools.lib.failure_policy import detect_failures_from_anomalies


def test_failure_assessment_fields_exist():
    failures = detect_failures_from_anomalies([
        "snapshot_unavailable",
        "deploy_not_executed",
        "rate_limit",
        "some_other_error",
    ])

    for failure in failures:
        assert "confidence" in failure
        assert "risk" in failure
        assert isinstance(failure["confidence"], float)
        assert failure["risk"] in {"low", "mid", "high"}


def test_failure_assessment_grouping_keeps_max_confidence_and_risk():
    failures = detect_failures_from_anomalies([
        "missing_executed_action",
        "missing_deploy_artifact",
    ])

    assert len(failures) == 1
    failure = failures[0]
    assert failure["type"] == "state_failure"
    assert failure["severity"] == "high"
    assert failure["confidence"] >= 0.90
    assert failure["risk"] in {"mid", "high"}
