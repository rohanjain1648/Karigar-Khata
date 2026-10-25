"""Use-cases shared by the API and the demo seeder: domain change + message + feed upkeep."""
from . import config, jobs, ledger, settlement
from .agents import messenger
from .agents.autopilot import resolve_kind


def issue_job(conn, **kw) -> dict:
    job = jobs.issue(conn, **kw)
    messenger.issue_message(conn, job)
    return job


def receive_job(conn, job_id: int, **kw) -> dict:
    job = jobs.receive(conn, job_id, **kw)
    messenger.receive_message(conn, job, kw["piece_gross_mg"], kw.get("scrap_gross_mg") or 0)
    resolve_kind(conn, "piece_ready", f"ready:{job_id}")
    resolve_kind(conn, "deadline_risk", f"risk:{job_id}:")
    return job


def confirm_entry(conn, entry_id: int, party: str) -> dict:
    e = ledger.acknowledge(conn, entry_id, party)
    return e


def dispute_entry(conn, entry_id: int, party: str, reason: str, claimed_gross_mg: int | None) -> dict:
    return ledger.dispute(conn, entry_id, party, reason, claimed_gross_mg)


def resolve_entry(conn, entry_id: int, action: str, gross_mg: int | None = None) -> dict:
    e = ledger.get(conn, entry_id)
    if not e:
        raise LookupError("entry not found")
    if action == "accept_karigar":
        if e["claimed_gross_mg"] is None:
            raise ValueError("karigar gave no figure to accept")
        new_id = ledger.supersede(conn, entry_id, "jeweller", gross_mg=e["claimed_gross_mg"],
                                  note=f"Accepted karigar's figure (dispute on #{entry_id})")
    elif action == "reweigh":
        if not gross_mg:
            raise ValueError("enter the re-weighed figure")
        new_id = ledger.supersede(conn, entry_id, "jeweller", gross_mg=gross_mg,
                                  note=f"Re-weighed together (dispute on #{entry_id})")
    else:
        raise ValueError("unknown resolution")
    resolve_kind(conn, "entry_dispute", f"dispute:{entry_id}")
    new = ledger.get(conn, new_id)
    k = messenger.karigar(conn, e["karigar_id"])
    hi = k["language"] == "hi"
    text = (f"{k['name']} जी, एंट्री #{entry_id} सुधारी गई: नया वज़न {messenger.g(new['gross_mg'])} g। कृपया ✅ करें।" if hi else
            f"{k['name']}, entry #{entry_id} corrected: new weight {messenger.g(new['gross_mg'])} g. Please confirm ✅.")
    messenger.send(conn, audience="karigar", karigar_id=k["id"], to_name=k["name"], lang=k["language"], text=text,
                   job_id=e["job_id"])
    return new


def propose_settlement(conn, job_id: int, actor: str = "jeweller") -> dict:
    s = settlement.propose(conn, job_id, actor)
    job = jobs.get(conn, job_id)
    k = messenger.karigar(conn, job["karigar_id"])
    s_text = messenger.settlement_text(k, job, s["figures"])
    conn.execute("UPDATE settlements SET explanation = ? WHERE id = ?", (s_text, s["id"]))
    messenger.send(conn, audience="karigar", karigar_id=k["id"], to_name=k["name"], lang=k["language"],
                   text=s_text, job_id=job_id)
    return settlement.get(conn, s["id"])


def approve_settlement(conn, sid: int, party: str) -> dict:
    s = settlement.approve(conn, sid, party)
    if s["status"] == "approved":
        resolve_kind(conn, "wastage_flag", f"wastage:{sid}:")
        resolve_kind(conn, "settlement_dispute", f"sdispute:{sid}")
    return s


def dispute_settlement(conn, sid: int, party: str, comment: str) -> dict:
    return settlement.dispute(conn, sid, party, comment)


def resolve_settlement_dispute(conn, sid: int, action: str) -> dict:
    s = settlement.get(conn, sid)
    if not s or s["status"] != "disputed":
        raise ValueError("settlement is not disputed")
    if action == "raise_allowance":
        conn.execute("UPDATE jobs SET agreed_wastage_bp = ?, wastage_policy = 'actual_capped' WHERE id = ?",
                     (max(s["figures"]["loss_bp"], 0), s["job_id"]))
        ledger.audit(conn, "jeweller", "allowance_raised", settlement_id=sid,
                     detail=f"to actual loss {s['figures']['loss_bp']} bp")
    elif action not in ("refiner", "keep"):
        raise ValueError("unknown resolution")
    resolve_kind(conn, "settlement_dispute", f"sdispute:{sid}")
    resolve_kind(conn, "wastage_flag", f"wastage:{sid}:")
    return propose_settlement(conn, s["job_id"], "jeweller")


def pay(conn, sid: int, amount_paise: int, upi_ref: str) -> dict:
    s = settlement.pay(conn, sid, amount_paise, upi_ref)
    messenger.payment_message(conn, s["karigar_id"], amount_paise, upi_ref, s["job_id"])
    if s["paid_paise"] >= s["making_paise"]:
        resolve_kind(conn, "payment_due", f"pay:{sid}:")
    return s


def karigar_profile(conn, kid: int) -> dict:
    k = dict(conn.execute("SELECT id, name, phone, language, skills, workshop FROM karigars WHERE id = ?", (kid,)).fetchone())
    k["balance"] = ledger.balances(conn, kid)
    k["skills_labels"] = [config.category_label(s.strip()) for s in (k["skills"] or "").split(",") if s.strip()]
    return k
