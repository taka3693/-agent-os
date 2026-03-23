from tools.pr_gate import has_deletion_justification


def test_has_deletion_justification_accepts_deletion_approved():
    assert has_deletion_justification("cleanup [deletion-approved]")


def test_has_deletion_justification_accepts_migration():
    assert has_deletion_justification("refactor with [migration] plan")


def test_has_deletion_justification_accepts_replace_marker():
    assert has_deletion_justification("replace old module [replace:tools/new_entrypoint.py]")


def test_has_deletion_justification_rejects_plain_text():
    assert not has_deletion_justification("remove obsolete file without justification")
