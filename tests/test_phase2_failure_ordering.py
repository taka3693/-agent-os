from tools.lib.failure_policy import detect_failures_from_anomalies


def test_failures_are_ordered_by_type_priority_then_severity():
    failures = detect_failures_from_anomalies([
        "rate_limit",
        "deploy_not_executed",
        "snapshot_unavailable",
        "some_other_error",
    ])

    assert [x["type"] for x in failures] == [
        "snapshot_failure",
        "state_failure",
        "execution_failure",
        "rate_limit_failure",
    ]


def test_same_type_is_grouped_before_ordering():
    failures = detect_failures_from_anomalies([
        "missing_executed_action",
        "missing_deploy_artifact",
        "snapshot_unavailable",
    ])

    assert [x["type"] for x in failures] == [
        "snapshot_failure",
        "state_failure",
    ]
    assert failures[1]["severity"] == "high"
