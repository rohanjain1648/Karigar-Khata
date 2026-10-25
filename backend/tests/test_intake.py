from datetime import date

import pytest

from app import db
from app.agents import intake

TODAY = date(2026, 10, 25)


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.init(c)
    c.executemany("INSERT INTO karigars(id, name, pin) VALUES (?, ?, '1')",
                  [(1, "Ramesh Soni"), (2, "Abdul Karim"), (3, "Suresh Verma")])
    c.execute("INSERT INTO orders(id, code, item_type, design_category, status) VALUES (7, 'SL-1045', 'Rani haar', 'necklace_haar', 'open')")
    return c


def test_hinglish_note(conn):
    d = intake.parse(conn, "Ramesh ko 52.340g 22K, order 1045 haar, 12 Nov tak, ghatt 1.8%", TODAY)
    assert d["karigar_id"] == 1
    assert d["gross_mg"] == 52_340
    assert d["purity_ppt"] == 916
    assert d["order_id"] == 7
    assert d["design_category"] == "necklace_haar"
    assert d["due_date"] == "2026-11-12"
    assert d["agreed_wastage_bp"] == 180
    assert d["missing"] == []


def test_defaults_and_missing(conn):
    d = intake.parse(conn, "abdul jhumka 18k 8 din me", TODAY)
    assert d["karigar_id"] == 2 and d["purity_ppt"] == 750
    assert d["design_category"] == "jhumka_earring"
    assert d["due_date"] == "2026-11-02"
    assert d["wastage_defaulted"] and "gross_mg" in d["missing"]


def test_past_date_rolls_to_next_year():
    assert intake.parse_due("5 jan", TODAY) == "2027-01-05"
