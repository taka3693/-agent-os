import importlib.util

def load_module():
    path = "/home/milky/agent-os/skills/decision/generate_decision.py"
    spec = importlib.util.spec_from_file_location("gd", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

def test_recurring_prefers_subscription_over_service():
    m = load_module()
    r = m.generate_decision("月額 or 受託で迷う。継続収益を重視")
    assert r["goal"] == "recurring"
    assert r["recommendation"]["option"] == "サブスク"
    assert r["scores"]["サブスク"] > r["scores"]["受託"]
    assert "why_not_second" in r["proposal"]
    assert "kpi" in r["proposal"]
    assert "first_month" in r["proposal"]
