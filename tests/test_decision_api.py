from fastapi.testclient import TestClient
from tools.decision_api import app

client = TestClient(app)

def test_decision_api_health_and_post():
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"ok": True}

    res = client.post("/decision", json={"request": "月額 or 受託で迷う。継続収益を重視"})
    assert res.status_code == 200

    body = res.json()
    assert body["ok"] is True
    assert body["result"]["goal"] == "recurring"
    assert body["result"]["recommendation"]["option"] == "サブスク"
    assert "why_not_second" in body["result"]["proposal"]
    assert "kpi" in body["result"]["proposal"]
    assert "first_month" in body["result"]["proposal"]
