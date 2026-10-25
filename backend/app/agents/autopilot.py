"""Autopilot: the manager agent that sweeps the ledger and acts.

Low-stakes actions run on their own (asking a karigar for a progress update). Anything that
changes who does the work, what a customer is told, or money, is queued for the jeweller to
approve. Every action lands in the activity feed with the reason behind it.
"""
import json
from datetime import date, timedelta

from .. import ledger, settlement
from .. import jobs as jobs_mod
from . import compliance, deadline, mediator, messenger, payments, wastage
from .messenger import rupees


def upsert_action(conn, *, key: str, agent: str, kind: str, severity: str, title: str, detail: str,
                  payload: dict | None = None, requires_approval: bool = False, status: str = "open",
                  source: str = "rules") -> bool:
    """Returns True if this is a new action (dedupe on key)."""
    existing = conn.execute("SELECT id, status FROM agent_actions WHERE dedupe_key = ?", (key,)).fetchone()
    if existing:
        if existing["status"] == "open":
            conn.execute("UPDATE agent_actions SET title = ?, detail = ?, payload = ?, severity = ? WHERE id = ?",
                         (title, detail, json.dumps(payload or {}), severity, existing["id"]))
        return False
    conn.execute(
        "INSERT INTO agent_actions(dedupe_key, agent, kind, severity, title, detail, payload, requires_approval,"
        " status, source, created_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (key, agent, kind, severity, title, detail, json.dumps(payload or {}), int(requires_approval), status,
         source, ledger.now_iso()))
    return True


def run(conn, today: date | None = None) -> dict:
    today = today or date.today()
    created = {"deadline": 0, "wastage": 0, "payments": 0, "compliance": 0, "disputes": 0, "messages": 0}
    bench = wastage.benchmarks(conn)

    # 1. Deadlines: nudge, warn, propose help
    live_keys: set[str] = set()
    for r in deadline.assess_all(conn, today):
        if r["risk"] in ("high", "late"):
            live_keys |= {f"risk:{r['job_id']}:{r['risk']}", f"split:{r['job_id']}", f"cust:{r['job_id']}:{r['risk']}"}
        job = jobs_mod.get(conn, r["job_id"])
        k = messenger.karigar(conn, job["karigar_id"])
        if r["stale"] and r["risk"] != "low":
            occ = f" ({r['customer_name']} — {r['occasion']} {r['occasion_date']})" if r["occasion"] else ""
            if k["language"] == "hi" and r["occasion"]:
                occ = f" ({r['customer_name']} जी की {r['occasion']} {r['occasion_date']})"
            text = messenger.render("nudge", k["language"], name=k["name"], code=job["code"],
                                    item=job["item_type"], due=r["hard_date"], occasion=occ)
            text, src = messenger.polish(text, k["language"], "friendly progress check, not pushy", f"nudge-{job['id']}")
            if upsert_action(conn, key=f"nudge:{job['id']}:{today}", agent="Deadline", kind="nudge_karigar",
                             severity="info", title=f"Asked {k['name']} for an update on {job['code']}",
                             detail=f"{'; '.join(r['reasons'])}. Basis: {r['basis']}.", payload={"job_id": job["id"], "message": text},
                             status="done", source=src):
                messenger.send(conn, audience="karigar", karigar_id=k["id"], to_name=k["name"], lang=k["language"],
                               text=text, job_id=job["id"], source=src)
                created["messages"] += 1
        if r["risk"] in ("high", "late"):
            target = date.fromisoformat(r["hard_date"])
            cands = deadline.reassign_candidates(conn, job, today, target)
            extra = [x for x in r["reasons"] if not x.startswith("expected ")]
            detail = (f"Expected finish {r['expected_finish']} vs needed by {r['hard_date']} — based on {r['basis']}."
                      + (f" Also: {'; '.join(extra)}." if extra else ""))
            if upsert_action(conn, key=f"risk:{job['id']}:{r['risk']}", agent="Deadline", kind="deadline_risk",
                             severity="high",
                             title=(f"{job['code']} {job['item_type']} is overdue since {r['hard_date']}" if r["risk"] == "late"
                                    else f"{job['code']} {job['item_type']} will likely miss {r['hard_date']}"),
                             detail=detail, payload={"job_id": job["id"], "assessment": r}):
                created["deadline"] += 1
            if cands:
                c = cands[0]
                upsert_action(conn, key=f"split:{job['id']}", agent="Deadline", kind="reassign_suggestion",
                              severity="high", requires_approval=True,
                              title=f"Split {job['code']}: ask {c['name']} to make part of it",
                              detail=f"{c['name']} has {c['load']} open job(s) and could finish half by {c['finish']}. "
                                     f"Approving sends {c['name']} a request; issue the gold from the Issue screen once he agrees.",
                              payload={"job_id": job["id"], "candidate": c})
            if r["customer_name"]:
                o_lang = "hi"
                text = messenger.render("customer_update", o_lang, customer=r["customer_name"], item=job["item_type"],
                                        order=r["order_code"], status="पर काम चल रहा है, हम समय पर देने की पूरी कोशिश कर रहे हैं",
                                        date=r["hard_date"])
                upsert_action(conn, key=f"cust:{job['id']}:{r['risk']}", agent="Deadline", kind="customer_update",
                              severity="medium", requires_approval=True,
                              title=f"Update {r['customer_name']} about order {r['order_code']}?",
                              detail="Draft message below. Nothing is sent until you approve.",
                              payload={"job_id": job["id"], "message": text, "to": r["customer_name"]})

    # risk warnings for jobs that recovered (or were received) close themselves
    for a in conn.execute("SELECT id, dedupe_key FROM agent_actions WHERE status = 'open'"
                          " AND kind IN ('deadline_risk', 'reassign_suggestion', 'customer_update')").fetchall():
        if a["dedupe_key"] not in live_keys:
            conn.execute("UPDATE agent_actions SET status = 'resolved', resolved_at = ? WHERE id = ?",
                         (ledger.now_iso(), a["id"]))

    # 2. Wastage: unfair agreements on open jobs, out-of-pattern losses on proposed settlements
    for job in jobs_mod.list_jobs(conn, open_only=True):
        flag = wastage.review_agreement(job, bench)
        if flag and upsert_action(conn, key=f"unfair:{job['id']}", agent="Wastage", kind="unfair_agreement",
                                  severity="medium", title=f"{job['code']}: wastage agreed with {job['karigar_name']} looks too low",
                                  detail=flag["text"], payload={"job_id": job["id"]}):
            created["wastage"] += 1
    for s in conn.execute("SELECT id FROM settlements WHERE status IN ('proposed','disputed')"):
        s = settlement.get(conn, s["id"])
        job = jobs_mod.get(conn, s["job_id"])
        for fl in wastage.review_settlement(conn, job, s["figures"], bench):
            if upsert_action(conn, key=f"wastage:{s['id']}:{fl['code']}", agent="Wastage", kind="wastage_flag",
                             severity=fl["severity"], title=f"{job['code']} ({job['karigar_name']}): {fl['code'].replace('_', ' ')}",
                             detail=fl["text"], payload={"settlement_id": s["id"], "job_id": job["id"]}):
                created["wastage"] += 1
        if s["status"] == "disputed":
            m = mediator.for_settlement(conn, s, wastage.review_settlement(conn, job, s["figures"], bench), bench)
            upsert_action(conn, key=f"sdispute:{s['id']}", agent="Mediator", kind="settlement_dispute", severity="high",
                          requires_approval=True, title=f"{job['karigar_name']} objected to settlement of {job['code']}",
                          detail=" · ".join(m["facts"]), payload={"settlement_id": s["id"], "job_id": job["id"], "mediation": m})

    # 3. Disputed ledger entries
    for e in conn.execute("SELECT * FROM entries WHERE state = 'active' AND (karigar_ack = 'disputed' OR jeweller_ack = 'disputed')"):
        e = dict(e)
        m = mediator.for_entry(conn, e)
        k = messenger.karigar(conn, e["karigar_id"])
        if upsert_action(conn, key=f"dispute:{e['id']}", agent="Mediator", kind="entry_dispute", severity="high",
                         requires_approval=True, title=f"{k['name']} disputes entry #{e['id']} ({e['kind'].lower()})",
                         detail=m["explanation"], source=m["source"],
                         payload={"entry_id": e["id"], "job_id": e["job_id"], "karigar_id": e["karigar_id"], "mediation": m}):
            created["disputes"] += 1

    # 4. Payments
    for d in payments.dues(conn, today):
        if d["status"] == "fresh":
            continue
        if upsert_action(conn, key=f"pay:{d['settlement_id']}:{d['status']}", agent="Payments", kind="payment_due",
                         severity="high" if d["status"] == "overdue" else "medium", requires_approval=True,
                         title=f"Pay {d['karigar_name']} ₹{rupees(d['due_paise'])} — waiting {d['days_waiting']} days",
                         detail=f"Settlement for {d['job_code']} was approved by both on {d['approved_at'][:10]}.",
                         payload=d):
            created["payments"] += 1

    # 5. Compliance
    for a in compliance.open_challan_alerts(conn, today):
        if upsert_action(conn, key=f"itc:{a['job_id']}:{a['severity']}", agent="Compliance", kind="challan_age",
                         severity=a["severity"], title=f"Challan {a['challan_no']} open {a['age_days']} days",
                         detail=f"Gold with {a['karigar']} since {(today - timedelta(days=a['age_days'])).isoformat()}. "
                                f"{a['days_left']} days left before Section 143's one-year limit treats it as a supply.",
                         payload=a):
            created["compliance"] += 1

    return {"ran_at": ledger.now_iso(), "today": today.isoformat(), "created": created}


def approve(conn, action_id: int) -> dict:
    a = conn.execute("SELECT * FROM agent_actions WHERE id = ?", (action_id,)).fetchone()
    if not a:
        raise LookupError("action not found")
    a = dict(a)
    p = json.loads(a["payload"] or "{}")
    result = "acknowledged"
    if a["kind"] == "customer_update":
        job = jobs_mod.get(conn, p["job_id"])
        messenger.send(conn, audience="customer", to_name=p["to"], lang="hi", text=p["message"], job_id=job["id"])
        result = "message sent to customer"
    elif a["kind"] == "reassign_suggestion":
        job = jobs_mod.get(conn, p["job_id"])
        c = p["candidate"]
        k = messenger.karigar(conn, c["karigar_id"])
        text = messenger.render("reassign_ask", k["language"], name=k["name"], code=job["code"], item=job["item_type"],
                                due=job["due_date"])
        messenger.send(conn, audience="karigar", karigar_id=k["id"], to_name=k["name"], lang=k["language"], text=text,
                       job_id=job["id"])
        result = f"request sent to {k['name']}"
    conn.execute("UPDATE agent_actions SET status = 'approved', resolved_at = ? WHERE id = ?", (ledger.now_iso(), action_id))
    return {"id": action_id, "result": result}


def dismiss(conn, action_id: int) -> None:
    conn.execute("UPDATE agent_actions SET status = 'dismissed', resolved_at = ? WHERE id = ?", (ledger.now_iso(), action_id))


def resolve_kind(conn, kind: str, key_prefix: str) -> None:
    conn.execute("UPDATE agent_actions SET status = 'resolved', resolved_at = ? WHERE kind = ? AND dedupe_key LIKE ?"
                 " AND status = 'open'", (ledger.now_iso(), kind, key_prefix + "%"))
