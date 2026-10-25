import pytest

from app import db, jobs, ledger, settlement


def test_compute_worked_example_within_allowance():
    # 50.000 g 22K issued, 48.900 g piece + 0.600 g scrap back, 1.5% agreed
    f = settlement.compute(issued_fine=45_800, piece_fine=44_792, scrap_fine=550, refiner_fine=0,
                           piece_gross_mg=48_900, agreed_bp=150, policy="agreed", making_paise_per_g=30_000)
    assert f["loss_fine_mg"] == 458
    assert f["loss_bp"] == 100
    assert f["allowance_fine_mg"] == 687
    assert f["wastage_credit_mg"] == 687
    assert f["gold_net_mg"] == -229          # karigar keeps 229 mg fine as saving
    assert f["making_paise"] == 1_467_000     # Rs 300/g x 48.9 g = Rs 14,670


def test_compute_actual_capped_policy():
    f = settlement.compute(issued_fine=45_800, piece_fine=44_792, scrap_fine=550, refiner_fine=0,
                           piece_gross_mg=48_900, agreed_bp=150, policy="actual_capped", making_paise_per_g=0)
    assert f["wastage_credit_mg"] == 458 and f["gold_net_mg"] == 0


def test_compute_over_allowance_leaves_shortfall():
    f = settlement.compute(issued_fine=10_000, piece_fine=9_700, scrap_fine=0, refiner_fine=0,
                           piece_gross_mg=10_590, agreed_bp=100, policy="agreed", making_paise_per_g=0)
    assert f["loss_fine_mg"] == 300 and f["wastage_credit_mg"] == 100 and f["gold_net_mg"] == 200


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.init(c)
    c.execute("INSERT INTO karigars(id, name, pin, language) VALUES (1, 'Ramesh', '1111', 'hi')")
    return c


def test_full_job_lifecycle_requires_both_parties(conn):
    job = jobs.issue(conn, karigar_id=1, design_category="chain", item_type="Chain", purity_ppt=916,
                     gross_mg=50_000, agreed_wastage_bp=150, making_paise_per_g=30_000, due_date="2026-11-01")
    with pytest.raises(ValueError):
        jobs.receive(conn, job["id"], piece_gross_mg=48_900, scrap_gross_mg=600, scrap_purity_ppt=916)  # not confirmed yet

    issue_entry = conn.execute("SELECT id FROM entries WHERE job_id = ?", (job["id"],)).fetchone()[0]
    ledger.acknowledge(conn, issue_entry, "karigar")
    jobs.receive(conn, job["id"], piece_gross_mg=48_900, scrap_gross_mg=600, scrap_purity_ppt=916)

    with pytest.raises(ValueError):  # returns not yet confirmed by karigar
        settlement.propose(conn, job["id"], "jeweller")
    for (eid,) in conn.execute("SELECT id FROM entries WHERE job_id = ? AND karigar_ack = 'pending'", (job["id"],)).fetchall():
        ledger.acknowledge(conn, eid, "karigar")

    s = settlement.propose(conn, job["id"], "jeweller")
    assert s["jeweller_ok"] == 1 and s["status"] == "proposed"
    s = settlement.approve(conn, s["id"], "karigar")
    assert s["status"] == "approved"

    b = ledger.balances(conn, 1)
    assert b["fine_mg"] == -229
    assert b["money_paise"] == 1_467_000

    settlement.pay(conn, s["id"], 1_467_000, "UPI123")
    assert ledger.balances(conn, 1)["pending_money_paise"] == -1_467_000  # until karigar confirms receipt
    assert ledger.verify(conn)["ok"]
