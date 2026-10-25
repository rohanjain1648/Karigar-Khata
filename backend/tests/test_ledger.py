import pytest

from app import db, ledger


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.init(c)
    c.execute("INSERT INTO karigars(id, name, pin) VALUES (1, 'Ramesh', '1111')")
    return c


def test_fine_of_22k_is_exact_integer_mg():
    assert ledger.fine_of(50_000, 916) == 45_800
    assert ledger.fine_of(52_340, 916) == 47_943  # 47943.44 -> 47943


def test_fine_of_uses_bankers_rounding():
    assert ledger.round_div(5, 2) == 2
    assert ledger.round_div(7, 2) == 4
    assert ledger.round_div(-5, 2) == -2


def test_fine_of_rejects_bad_purity():
    with pytest.raises(ValueError):
        ledger.fine_of(1000, 0)
    with pytest.raises(ValueError):
        ledger.fine_of(1000, 1001)


def test_issue_counts_only_after_both_sides_confirm(conn):
    eid = ledger.post(conn, karigar_id=1, kind="ISSUE", created_by="jeweller",
                      gross_mg=50_000, purity_ppt=916)
    b = ledger.balances(conn, 1)
    assert b["fine_mg"] == 0 and b["pending_fine_mg"] == 45_800

    ledger.acknowledge(conn, eid, "karigar")
    b = ledger.balances(conn, 1)
    assert b["fine_mg"] == 45_800 and b["pending_count"] == 0


def test_return_reduces_karigar_balance(conn):
    a = ledger.post(conn, karigar_id=1, kind="ISSUE", created_by="jeweller", gross_mg=50_000, purity_ppt=916)
    r = ledger.post(conn, karigar_id=1, kind="RETURN_PIECE", created_by="jeweller", gross_mg=48_900, purity_ppt=916)
    for e in (a, r):
        ledger.acknowledge(conn, e, "karigar")
    assert ledger.balances(conn, 1)["fine_mg"] == 45_800 - 44_792


def test_dispute_is_excluded_then_superseded(conn):
    eid = ledger.post(conn, karigar_id=1, kind="ISSUE", created_by="jeweller", gross_mg=31_500, purity_ppt=916)
    ledger.dispute(conn, eid, "karigar", "I weighed 31.42 g", claimed_gross_mg=31_420)
    b = ledger.balances(conn, 1)
    assert b["disputed_count"] == 1 and b["fine_mg"] == 0

    new_id = ledger.supersede(conn, eid, "jeweller", gross_mg=31_420, note="re-weighed together")
    ledger.acknowledge(conn, new_id, "karigar")
    b = ledger.balances(conn, 1)
    assert b["disputed_count"] == 0 and b["fine_mg"] == ledger.fine_of(31_420, 916)
    assert ledger.get(conn, eid)["state"] == "superseded"


def test_cannot_dispute_after_confirming(conn):
    eid = ledger.post(conn, karigar_id=1, kind="ISSUE", created_by="jeweller", gross_mg=1000, purity_ppt=916)
    ledger.acknowledge(conn, eid, "karigar")
    with pytest.raises(ValueError):
        ledger.dispute(conn, eid, "karigar", "late complaint")


def test_money_signs(conn):
    ledger.post(conn, karigar_id=1, kind="MAKING_CHARGE", created_by="settlement", amount_paise=1_200_000)
    pid = ledger.post(conn, karigar_id=1, kind="PAYMENT", created_by="jeweller", amount_paise=500_000)
    ledger.acknowledge(conn, pid, "karigar")
    assert ledger.balances(conn, 1)["money_paise"] == 700_000


def test_chain_verifies_and_detects_tampering(conn):
    ids = [ledger.post(conn, karigar_id=1, kind="ISSUE", created_by="jeweller", gross_mg=g, purity_ppt=916)
           for g in (10_000, 20_000, 30_000)]
    assert ledger.verify(conn)["ok"]

    conn.execute("UPDATE entries SET gross_mg = 19000 WHERE id = ?", (ids[1],))
    v = ledger.verify(conn)
    assert not v["ok"] and v["entries"]["first_broken_id"] == ids[1]
