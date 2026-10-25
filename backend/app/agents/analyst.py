"""'Ask Khata' — the jeweller's questions answered over a live snapshot of the ledger.

The snapshot is computed by code; the Lyzr analyst only reads it and answers in plain words.
Offline, a few common questions are answered directly from the same snapshot.
"""
import json
from datetime import date

from .. import ledger
from . import deadline, payments
from .llm import lyzr


def snapshot(conn, today: date) -> dict:
    ks = []
    for k in conn.execute("SELECT id, name FROM karigars WHERE active = 1"):
        b = ledger.balances(conn, k["id"])
        ks.append({"name": k["name"], "fine_gold_held_g": round(b["fine_mg"] / 1000, 3),
                   "unconfirmed_g": round(b["pending_fine_mg"] / 1000, 3), "disputes": b["disputed_count"],
                   "owed_to_karigar_rs": round(b["money_paise"] / 100)})
    risks = [{k: r[k] for k in ("code", "karigar_name", "item_type", "risk", "hard_date", "expected_finish",
                                "progress_pct", "customer_name", "occasion")}
             for r in deadline.assess_all(conn, today)]
    dues = [{"karigar": d["karigar_name"], "job": d["job_code"], "rs": round(d["due_paise"] / 100),
             "days_waiting": d["days_waiting"]} for d in payments.dues(conn, today)]
    return {"today": today.isoformat(), "karigars": ks, "open_jobs": risks, "unpaid": dues}


def answer(conn, question: str, today: date) -> dict:
    snap = snapshot(conn, today)
    if lyzr.enabled("analyst"):
        brief = ("ROLE: You are 'Khata', assistant to a small-town jeweller who gives gold to karigars for "
                 "job-work. Answer the question ONLY from the JSON snapshot below, in the same language as the "
                 "question, in 1-4 short lines. Quote numbers exactly. If the snapshot doesn't cover it, say so.\n"
                 f"SNAPSHOT: {json.dumps(snap, ensure_ascii=False)}\nQUESTION: {question}")
        out = lyzr.chat("analyst", brief, "ask")
        if out:
            return {"answer": out.strip(), "source": "lyzr"}
    return {"answer": _rules_answer(question.lower(), snap), "source": "rules"}


def _rules_answer(q: str, snap: dict) -> str:
    if any(w in q for w in ("late", "risk", "der", "deadline", "wedding", "shaadi", "delay")):
        bad = [j for j in snap["open_jobs"] if j["risk"] in ("late", "high", "medium")]
        if not bad:
            return "All open jobs are on track."
        return "\n".join(f"{j['code']} {j['item_type']} ({j['karigar_name']}): {j['risk']}, needed by {j['hard_date']}, "
                         f"expected {j['expected_finish']}" + (f" — {j['customer_name']}'s {j['occasion']}" if j['occasion'] else "")
                         for j in bad)
    if any(w in q for w in ("pay", "paise", "dues", "baaki", "bakaya", "owe", "payment")):
        if not snap["unpaid"]:
            return "No unpaid settlements."
        return "\n".join(f"{d['karigar']}: ₹{d['rs']:,} for {d['job']}, waiting {d['days_waiting']} days" for d in snap["unpaid"])
    if any(w in q for w in ("gold", "sona", "kitna", "balance", "held")):
        total = sum(k["fine_gold_held_g"] for k in snap["karigars"])
        lines = [f"{k['name']}: {k['fine_gold_held_g']:.3f} g fine" + (f" (+{k['unconfirmed_g']:.3f} g unconfirmed)" if k['unconfirmed_g'] else "")
                 for k in snap["karigars"]]
        return f"Total fine gold with karigars: {total:.3f} g\n" + "\n".join(lines)
    return ("I can answer about late/at-risk jobs, gold held by each karigar, and unpaid dues. "
            "Connect a Lyzr agent for open questions.")
