import pytest
from fastapi.testclient import TestClient

from app import config, seed


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "khata.db")
    seed.reset()
    from app.main import app
    return TestClient(app)


def login(client, **body):
    r = client.post("/api/auth/login", json=body)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_jeweller_dashboard_and_chain(client):
    h = login(client, role="jeweller", pin="1234")
    d = client.get("/api/dashboard", headers=h).json()
    assert d["kpis"]["open_jobs"] >= 5
    assert d["kpis"]["disputes"] == 1
    kinds = {a["kind"] for a in d["actions"]}
    assert {"deadline_risk", "entry_dispute", "payment_due", "challan_age", "unfair_agreement", "wastage_flag"} <= kinds
    assert client.get("/api/ledger/verify", headers=h).json()["ok"]


def test_karigar_sees_only_his_account(client):
    h1 = login(client, role="karigar", karigar_id=1, pin="1111")
    me = client.get("/api/me", headers=h1).json()
    assert me["id"] == 1 and all(e["karigar_id"] == 1 for e in me["entries"])
    other = client.get("/api/karigars/2", headers=h1)
    assert other.status_code == 403
    abdul_entry = next(e for e in client.get("/api/me", headers=login(client, role="karigar", karigar_id=2, pin="2222")).json()["entries"])
    assert client.post(f"/api/me/entries/{abdul_entry['id']}/confirm", headers=h1).status_code == 404


def test_wrong_pin_rejected(client):
    assert client.post("/api/auth/login", json={"role": "karigar", "karigar_id": 1, "pin": "0000"}).status_code == 401


def test_dispute_resolution_flow(client):
    hj = login(client, role="jeweller", pin="1234")
    hk = login(client, role="karigar", karigar_id=2, pin="2222")
    disputed = next(e for e in client.get("/api/me", headers=hk).json()["entries"] if e["karigar_ack"] == "disputed")
    m = client.get(f"/api/entries/{disputed['id']}/mediate", headers=hj).json()
    assert m["options"][0]["action"] == "reweigh"  # 80 mg gap > scale tolerance
    new = client.post(f"/api/entries/{disputed['id']}/resolve", headers=hj,
                      json={"action": "reweigh", "gross_mg": 31_460}).json()
    assert new["gross_mg"] == 31_460 and new["karigar_ack"] == "pending"
    assert client.post(f"/api/me/entries/{new['id']}/confirm", headers=hk).json()["karigar_ack"] == "confirmed"
    assert client.get("/api/dashboard", headers=hj).json()["kpis"]["disputes"] == 0


def test_settle_and_pay_live(client):
    hj = login(client, role="jeweller", pin="1234")
    hk = login(client, role="karigar", karigar_id=5, pin="5555")
    job = next(j for j in client.get("/api/jobs", headers=hj).json() if j["status"] == "returned")
    s = client.post(f"/api/jobs/{job['id']}/settlement", headers=hj).json()
    assert s["status"] == "proposed"
    s = client.post(f"/api/me/settlements/{s['id']}/approve", headers=hk).json()
    assert s["status"] == "approved"
    p = client.post(f"/api/settlements/{s['id']}/pay", headers=hj,
                    json={"amount_paise": s["making_paise"], "upi_ref": "TEST1"}).json()
    assert p["paid_paise"] == s["making_paise"]


def test_intake_and_issue(client):
    hj = login(client, role="jeweller", pin="1234")
    d = client.post("/api/intake/parse", headers=hj, json={"text": "Suresh ko 12.500g 22K chain 5 din"}).json()
    assert d["karigar_id"] == 3 and d["gross_mg"] == 12_500 and not d["missing"]
    body = {k: d[k] for k in ("karigar_id", "design_category", "item_type", "purity_ppt", "gross_mg",
                              "agreed_wastage_bp", "making_paise_per_g", "due_date")}
    job = client.post("/api/jobs", headers=hj, json=body).json()
    assert job["issued_gross_mg"] == 12_500 and job["challan_no"].startswith("CH/")


def test_karigar_chat_progress(client):
    hk = login(client, role="karigar", karigar_id=3, pin="3333")
    r = client.post("/api/me/messages", headers=hk, json={"text": "haar 60% ho gaya"}).json()
    assert r["understood"] == "progress" and r["pct"] == 60


def test_public_tracking_hides_ledger(client):
    r = client.get("/api/public/track/SL-1045").json()
    assert r["stage"] == "in_making" and "gross_mg" not in str(r)
