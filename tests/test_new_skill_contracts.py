#!/usr/bin/env python3
from skills.execution.execution_impl import run_execution
from skills.critique.critique_impl import run_critique
from skills.retrospective.retrospective_impl import run_retrospective


def assert_keys(d, keys):
    missing = [k for k in keys if k not in d]
    if missing:
        raise AssertionError(f"missing keys: {missing} in {d}")


def main():
    ex = run_execution("build sample feature")
    cr = run_critique("review sample output")
    rt = run_retrospective("reflect on sample run")

    assert_keys(ex, ["summary", "status", "artifacts", "next_inputs"])
    assert_keys(cr, ["summary", "status", "issues", "decision"])
    assert_keys(rt, ["summary", "status", "lessons", "actions"])

    assert ex["status"] == "ok"
    assert cr["status"] == "ok"
    assert rt["status"] == "ok"

    assert isinstance(ex["artifacts"], list)
    assert isinstance(ex["next_inputs"], list)
    assert isinstance(cr["issues"], list)
    assert isinstance(rt["lessons"], list)
    assert isinstance(rt["actions"], list)

    print("OK: new skill contracts are valid")


if __name__ == "__main__":
    main()
