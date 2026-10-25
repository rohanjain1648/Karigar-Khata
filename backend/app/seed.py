"""Demo data: ~4 months of realistic history replayed through the real code paths, plus a
scripted 'today' with every situation the demo needs (wedding order at risk, weight dispute,
unfair wastage agreement, wastage outlier, overdue payment, ageing challan).

Run:  python -m app.seed      (wipes and rebuilds data/khata.db)
"""
import random
from datetime import date, datetime, time, timedelta
from pathlib import Path

from . import config, db, jobs, ledger, settlement
from . import services as svc

KARIGARS = [
    # id, name, phone, lang, pin, skills, workshop
    (1, "Ramesh Soni", "9829012345", "hi", "1111", "plain_bangle,chain,ring", "Johari Bazaar, Jaipur"),
    (2, "Abdul Karim", "9829023456", "hi", "2222", "filigree,jhumka_earring,necklace_haar", "Ramganj (home workshop)"),
    (3, "Suresh Verma", "9829034567", "hi", "3333", "necklace_haar,mangalsutra,chain", "Chandpol, Jaipur"),
    (4, "Meena Devi", "9829045678", "hi", "4444", "ring,jhumka_earring,plain_bangle", "Sanganer (home workshop)"),
    (5, "Prakash Ghosh", "9829056789", "en", "5555", "filigree,necklace_haar,chain", "Gopalji ka Rasta, Jaipur"),
]

# what each design really loses in this shop, in basis points (mean)
TRUE_LOSS_BP = {"plain_bangle": 95, "chain": 140, "filigree": 245, "necklace_haar": 170, "ring": 115,
                "jhumka_earring": 190, "mangalsutra": 150, "other": 140}


class Timeline:
    def __init__(self):
        self.events = []

    def at(self, when: datetime, fn):
        self.events.append((when, len(self.events), fn))

    def play(self, conn, until: datetime):
        for when, _, fn in sorted(self.events, key=lambda e: (e[0], e[1])):
            if when > until:
                continue
            ledger.set_clock(when)
            fn(conn)
        ledger.set_clock(None)


def _history(tl: Timeline, rng: random.Random, now: datetime):
    for kid, _, _, _, _, skills, _ in KARIGARS:
        cats = skills.split(",")
        for _ in range(8):
            cat = rng.choice(cats)
            d0 = now - timedelta(days=rng.randint(35, 125), hours=rng.randint(0, 6))
            purity = 750 if rng.random() < 0.2 else 916
            gross = rng.randint(800, 6000) * 10
            dur = max(2, config.CATEGORIES[cat][4] + rng.randint(-2, 3))
            loss_bp = max(30, int(rng.gauss(TRUE_LOSS_BP[cat], 28)))
            scrap_bp = rng.randint(40, 120)
            pay_lag = rng.choice([1, 2, 3, 4, 6, 9, 12])
            _schedule_job(tl, kid, cat, purity, gross, d0, dur, loss_bp, scrap_bp, pay_lag)


def _schedule_job(tl, kid, cat, purity, gross, d0, dur, loss_bp, scrap_bp, pay_lag, *, stop_after=None,
                  agreed_bp=None, order_code=None, due=None, item=None, confirm_issue=True):
    """stop_after: None = full lifecycle; 'issued' | 'returned' | 'proposed' | 'approved'."""
    st: dict = {}
    fine = ledger.fine_of(gross, purity)
    loss = ledger.round_div(fine * loss_bp, 10_000)
    scrap_fine = ledger.round_div(fine * scrap_bp, 10_000)
    piece_gross = ledger.round_div((fine - loss - scrap_fine) * 1000, purity)
    scrap_gross = ledger.round_div(scrap_fine * 1000, purity)

    def issue(conn):
        oid = None
        if order_code:
            oid = conn.execute("SELECT id FROM orders WHERE code = ?", (order_code,)).fetchone()[0]
        st["job"] = svc.issue_job(conn, karigar_id=kid, design_category=cat, item_type=item or config.category_label(cat),
                                  purity_ppt=purity, gross_mg=gross, agreed_wastage_bp=agreed_bp,
                                  due_date=(due or (d0 + timedelta(days=dur + 2))).date().isoformat(), order_id=oid)

    def ack_all(conn):
        for (eid,) in conn.execute("SELECT id FROM entries WHERE job_id = ? AND karigar_ack = 'pending' AND state = 'active'",
                                   (st["job"]["id"],)).fetchall():
            ledger.acknowledge(conn, eid, "karigar")

    def receive(conn):
        svc.receive_job(conn, st["job"]["id"], piece_gross_mg=piece_gross, scrap_gross_mg=scrap_gross)

    def propose(conn):
        st["s"] = svc.propose_settlement(conn, st["job"]["id"], "jeweller")

    def approve(conn):
        svc.approve_settlement(conn, st["s"]["id"], "karigar")

    def pay(conn):
        s = settlement.get(conn, st["s"]["id"])
        svc.pay(conn, s["id"], s["making_paise"], f"UPI{rng_ref(s['id'])}")

    def ack_pay(conn):
        for (eid,) in conn.execute("SELECT id FROM entries WHERE job_id = ? AND kind = 'PAYMENT' AND karigar_ack = 'pending'",
                                   (st["job"]["id"],)).fetchall():
            ledger.acknowledge(conn, eid, "karigar")

    steps = [(d0, issue)] + ([(d0 + timedelta(hours=3), ack_all)] if confirm_issue else [])
    if stop_after != "issued":
        r = d0 + timedelta(days=dur)
        steps += [(r, receive), (r + timedelta(hours=2), ack_all)]
        if stop_after != "returned":
            steps.append((r + timedelta(days=1), propose))
            if stop_after != "proposed":
                a = r + timedelta(days=1, hours=4)
                steps.append((a, approve))
                if stop_after != "approved":
                    steps += [(a + timedelta(days=pay_lag), pay), (a + timedelta(days=pay_lag, hours=2), ack_pay)]
    for when, fn in steps:
        tl.at(when, fn)
    return st


def rng_ref(n: int) -> str:
    return f"{(n * 7919) % 1_000_000:06d}"


def build(conn, today: date | None = None) -> None:
    today = today or date.today()
    now = datetime.combine(today, time(10, 30))
    rng = random.Random(42)

    conn.executemany("INSERT INTO karigars(id, name, phone, language, pin, skills, workshop) VALUES(?, ?, ?, ?, ?, ?, ?)",
                     KARIGARS)
    d = lambda n: (today + timedelta(days=n)).isoformat()  # noqa: E731
    conn.executemany(
        "INSERT INTO orders(code, customer_name, customer_phone, item_type, design_category, occasion, occasion_date, created_at)"
        " VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
        [("SL-1045", "Sharma family", "9414011111", "Rani haar", "necklace_haar", "wedding", d(11), d(-8)),
         ("SL-1046", "Priya Mehta", "9414022222", "Filigree jhumka", "filigree", "engagement", d(19), d(-5)),
         ("SL-1047", "Gupta ji", "9414033333", "Set of 4 bangles", "plain_bangle", "anniversary", d(9), d(-3))])

    tl = Timeline()
    _history(tl, rng, now)

    H = lambda days, hours=0: now + timedelta(days=days, hours=hours)  # noqa: E731

    # Suresh: settled 19 days ago, still unpaid -> overdue payment
    _schedule_job(tl, 3, "mangalsutra", 916, 18_640, H(-27), 6, 150, 70, 0, stop_after="approved")
    # Meena: settled 4 days ago, unpaid -> due
    _schedule_job(tl, 4, "ring", 916, 9_870, H(-10), 4, 110, 60, 0, stop_after="approved")

    # Wedding order at risk: Suresh's Rani haar, slow progress
    haar = _schedule_job(tl, 3, "necklace_haar", 916, 72_500, H(-6), 12, 170, 80, 0, stop_after="issued",
                         order_code="SL-1045", due=H(9), item="Rani haar")
    tl.at(H(-1, -2), lambda c: jobs.record_progress(c, haar["job"]["id"], 20, "Kundan setting pending"))

    # Abdul: filigree jhumka, wastage agreed far below normal, and he disputes the issued weight
    jh = _schedule_job(tl, 2, "filigree", 916, 31_500, H(-3), 14, 245, 80, 0, stop_after="issued",
                       order_code="SL-1046", agreed_bp=120, due=H(16), item="Filigree jhumka", confirm_issue=False)
    tl.at(H(-3, 4), lambda c: ledger.dispute(
        c, c.execute("SELECT id FROM entries WHERE job_id = ? AND kind = 'ISSUE'", (jh["job"]["id"],)).fetchone()[0],
        "karigar", "Mere kaante par 31.420 g aaya, 80 mg kam", 31_420))

    # Ramesh: bangle set for anniversary (fine), and a chain gone quiet
    _schedule_job(tl, 1, "plain_bangle", 916, 40_000, H(-2), 5, 95, 60, 0, stop_after="issued",
                  order_code="SL-1047", due=H(6), item="Set of 4 bangles")
    ch = _schedule_job(tl, 1, "chain", 916, 22_350, H(-9), 7, 140, 60, 0, stop_after="issued", due=H(1),
                       item="Rope chain")
    tl.at(H(-6), lambda c: jobs.record_progress(c, ch["job"]["id"], 50, "aadha ho gaya"))

    # Ramesh: plain bangle returned with 2.8% loss (normal ~1%) -> settlement proposed, awaiting him
    _schedule_job(tl, 1, "plain_bangle", 916, 50_000, H(-8), 6, 280, 50, 0, stop_after="proposed", item="Plain kada pair")

    # Prakash: chain returned yesterday, normal loss, ready to settle live in the demo
    _schedule_job(tl, 5, "chain", 916, 28_400, H(-8), 7, 135, 70, 0, stop_after="returned", item="Box chain")

    # Meena: ring issued this morning, waiting for her confirmation
    tl.at(H(0, -2), lambda c: svc.issue_job(c, karigar_id=4, design_category="ring", item_type="Ladies ring (2 pcs)",
                                            purity_ppt=916, gross_mg=11_230, due_date=d(5)))

    # Prakash: remodel job issued 340 days ago and never closed -> Section 143 alert
    _schedule_job(tl, 5, "other", 916, 14_200, H(-340), 20, 0, 0, 0, stop_after="issued", due=H(-320),
                  item="Old mangalsutra remodel")

    tl.play(conn, until=now)
    conn.execute("UPDATE jobs SET status = 'in_progress' WHERE item_type = 'Old mangalsutra remodel'")
    conn.commit()


def reset(path=None, today: date | None = None) -> None:
    path = path or config.DB_PATH
    with db.WRITE_LOCK:
        for suffix in ("", "-wal", "-shm"):
            p = Path(str(path) + suffix)
            if p.exists():
                p.unlink()
        conn = db.connect(path)
        db.init(conn)
        build(conn, today)
        from .agents import autopilot
        autopilot.run(conn, today)
        conn.commit()
        conn.close()


if __name__ == "__main__":
    reset()
    print(f"seeded {config.DB_PATH}")
