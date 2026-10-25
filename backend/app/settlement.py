"""Per-job settlement: deterministic arithmetic, approved by both parties before it posts.

Wastage allowance is computed on the fine gold issued for the job. Two policies:
  agreed        -> the full agreed allowance is written off; if the karigar used less, the saving
                   ("bachat") stays with him as gold credit. This is the common counter practice.
  actual_capped -> only the actual loss is written off, up to the agreed allowance.
Loss above the allowance stays on the karigar's gold balance as a shortfall to be squared up.
"""
import json

from . import ledger
from .ledger import round_div


def compute(*, issued_fine: int, piece_fine: int, scrap_fine: int, refiner_fine: int,
            piece_gross_mg: int, agreed_bp: int, policy: str, making_paise_per_g: int) -> dict:
    returned = piece_fine + scrap_fine + refiner_fine
    loss = issued_fine - returned
    allowance = round_div(issued_fine * agreed_bp, 10_000)
    if policy == "actual_capped":
        credit = min(max(loss, 0), allowance)
    else:
        credit = allowance
    gold_net = loss - credit  # > 0 karigar still owes gold; < 0 karigar keeps a gold credit
    return {
        "issued_fine_mg": issued_fine,
        "piece_fine_mg": piece_fine,
        "scrap_fine_mg": scrap_fine,
        "refiner_fine_mg": refiner_fine,
        "returned_fine_mg": returned,
        "loss_fine_mg": loss,
        "loss_bp": round_div(loss * 10_000, issued_fine) if issued_fine else 0,
        "agreed_bp": agreed_bp,
        "allowance_fine_mg": allowance,
        "wastage_credit_mg": credit,
        "gold_net_mg": gold_net,
        "policy": policy,
        "piece_gross_mg": piece_gross_mg,
        "making_paise_per_g": making_paise_per_g,
        "making_paise": round_div(making_paise_per_g * piece_gross_mg, 1000),
    }


def job_figures(conn, job_id: int) -> dict:
    job = dict(conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())
    es = [dict(r) for r in conn.execute(
        "SELECT * FROM entries WHERE job_id = ? AND state = 'active' AND settlement_id IS NULL",
        (job_id,))]
    unconfirmed = [e for e in es if not (e["jeweller_ack"] == "confirmed" and e["karigar_ack"] == "confirmed")]

    def total(kind):
        # stored fine is signed; undo the sign to get the positive weight moved
        return ledger.GOLD_KINDS[kind] * sum(e["fine_mg"] for e in es if e["kind"] == kind)

    figs = compute(
        issued_fine=total("ISSUE"),
        piece_fine=total("RETURN_PIECE"),
        scrap_fine=total("RETURN_SCRAP"),
        refiner_fine=total("REFINER_CREDIT"),
        piece_gross_mg=sum(e["gross_mg"] or 0 for e in es if e["kind"] == "RETURN_PIECE"),
        agreed_bp=job["agreed_wastage_bp"],
        policy=job["wastage_policy"],
        making_paise_per_g=job["making_paise_per_g"],
    )
    figs["unconfirmed_entry_ids"] = [e["id"] for e in unconfirmed]
    return figs


def propose(conn, job_id: int, actor: str, explanation: str = "") -> dict:
    job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not job:
        raise LookupError("job not found")
    if job["status"] not in ("returned", "settlement_disputed"):
        raise ValueError("job must be returned before it can be settled")
    figs = job_figures(conn, job_id)
    if figs["unconfirmed_entry_ids"]:
        raise ValueError(f"entries {figs['unconfirmed_entry_ids']} still need confirmation by both sides")
    conn.execute("UPDATE settlements SET status = 'withdrawn' WHERE job_id = ? AND status IN ('proposed','disputed')",
                 (job_id,))
    cur = conn.execute(
        "INSERT INTO settlements(karigar_id, job_id, computed_json, wastage_credit_mg, gold_net_mg,"
        " making_paise, status, jeweller_ok, karigar_ok, explanation, created_at)"
        " VALUES(?, ?, ?, ?, ?, ?, 'proposed', ?, ?, ?, ?)",
        (job["karigar_id"], job_id, json.dumps(figs), figs["wastage_credit_mg"], figs["gold_net_mg"],
         figs["making_paise"], 1 if actor == "jeweller" else 0, 1 if actor == "karigar" else 0,
         explanation, ledger.now_iso()),
    )
    sid = cur.lastrowid
    conn.execute("UPDATE jobs SET status = 'settlement_proposed' WHERE id = ?", (job_id,))
    ledger.audit(conn, actor, "settlement_propose", settlement_id=sid, detail=json.dumps(figs))
    return get(conn, sid)


def get(conn, sid: int) -> dict | None:
    r = conn.execute("SELECT * FROM settlements WHERE id = ?", (sid,)).fetchone()
    if not r:
        return None
    s = dict(r)
    s["figures"] = json.loads(s.pop("computed_json") or "{}")
    return s


def approve(conn, sid: int, party: str) -> dict:
    s = get(conn, sid)
    if not s:
        raise LookupError("settlement not found")
    if s["status"] not in ("proposed",):
        raise ValueError(f"settlement is {s['status']}")
    conn.execute(f"UPDATE settlements SET {party}_ok = 1 WHERE id = ?", (sid,))
    ledger.audit(conn, party, "settlement_approve", settlement_id=sid)
    s = get(conn, sid)
    if s["jeweller_ok"] and s["karigar_ok"]:
        _post(conn, s)
        s = get(conn, sid)
    return s


def dispute(conn, sid: int, party: str, comment: str) -> dict:
    s = get(conn, sid)
    if not s or s["status"] != "proposed":
        raise ValueError("only a proposed settlement can be disputed")
    conn.execute("UPDATE settlements SET status = 'disputed', karigar_comment = ? WHERE id = ?", (comment, sid))
    conn.execute("UPDATE jobs SET status = 'settlement_disputed' WHERE id = ?", (s["job_id"],))
    ledger.audit(conn, party, "settlement_dispute", settlement_id=sid, detail=comment)
    return get(conn, sid)


def _post(conn, s: dict) -> None:
    f = s["figures"]
    common = dict(karigar_id=s["karigar_id"], job_id=s["job_id"], settlement_id=s["id"], created_by="settlement")
    if f["wastage_credit_mg"]:
        ledger.post(conn, kind="WASTAGE_ALLOWANCE", fine_mg=f["wastage_credit_mg"],
                    note=f"Agreed wastage {f['agreed_bp'] / 100:.2f}% ({f['policy']})", **common)
    if f["making_paise"]:
        ledger.post(conn, kind="MAKING_CHARGE", amount_paise=f["making_paise"],
                    note=f"Making ₹{f['making_paise_per_g'] / 100:.0f}/g on {f['piece_gross_mg'] / 1000:.3f} g", **common)
    ts = ledger.now_iso()
    conn.execute("UPDATE settlements SET status = 'approved', approved_at = ? WHERE id = ?", (ts, s["id"]))
    conn.execute("UPDATE jobs SET status = 'settled', settled_at = ? WHERE id = ?", (ts, s["job_id"]))


def pay(conn, sid: int, amount_paise: int, upi_ref: str) -> dict:
    s = get(conn, sid)
    if not s or s["status"] != "approved":
        raise ValueError("only an approved settlement can be paid")
    if amount_paise <= 0:
        raise ValueError("amount must be positive")
    ledger.post(conn, karigar_id=s["karigar_id"], kind="PAYMENT", created_by="jeweller",
                job_id=s["job_id"], amount_paise=amount_paise, note=f"UPI {upi_ref}")
    conn.execute("UPDATE settlements SET paid_paise = paid_paise + ?, paid_at = ? WHERE id = ?",
                 (amount_paise, ledger.now_iso(), sid))
    return get(conn, sid)
