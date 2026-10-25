"""Understands what a karigar types back on WhatsApp: progress, 'piece ready', or a question.

  "haar 60% ho gaya"   -> progress 60% on his matching open job
  "J-0012 taiyar hai"  -> tells the jeweller the piece is ready for pickup/weighing
Anything else is passed to the jeweller as-is. Confirmations and disputes of weights are never
inferred from free text; they need the explicit ✅ / ❌ buttons on the entry.
"""
import re

from .. import config
from .. import jobs as jobs_mod
from . import messenger
from .autopilot import upsert_action

PCT_RE = re.compile(r"(\d{1,3})\s*(?:%|percent|pratishat|प्रतिशत)", re.I)
CODE_RE = re.compile(r"\bJ-?(\d{1,5})\b", re.I)
READY_RE = re.compile(r"\b(ready|taiyar|tayyar|ho gaya hai|bann? gaya|complete|तैयार)\b", re.I)


def pick_job(conn, karigar_id: int, text: str) -> dict | None:
    open_jobs = jobs_mod.list_jobs(conn, karigar_id=karigar_id, open_only=True)
    if not open_jobs:
        return None
    if m := CODE_RE.search(text):
        code = f"J-{int(m[1]):04d}"
        for j in open_jobs:
            if j["code"] == code:
                return j
    t = f" {text.lower()} "
    for j in open_jobs:
        words = config.CATEGORY_KEYWORDS.get(j["design_category"], []) + [(j["item_type"] or "").lower()]
        if any(w and w in t for w in words):
            return j
    return open_jobs[0]  # nearest due date


def handle(conn, karigar_id: int, text: str) -> dict:
    k = messenger.karigar(conn, karigar_id)
    messenger.send(conn, audience="karigar", karigar_id=karigar_id, to_name=k["name"], direction="in",
                   lang=k["language"], text=text)
    job = pick_job(conn, karigar_id, text)
    what, result = None, {"understood": "message"}
    if job and (m := PCT_RE.search(text)):
        pct = int(m[1])
        jobs_mod.record_progress(conn, job["id"], pct, note=text)
        what = f"{job['code']} — {pct}%"
        result = {"understood": "progress", "job_id": job["id"], "pct": pct}
    elif job and READY_RE.search(text):
        jobs_mod.record_progress(conn, job["id"], 100, note=text)
        upsert_action(conn, key=f"ready:{job['id']}", agent="Intake", kind="piece_ready", severity="info",
                      title=f"{k['name']} says {job['code']} {job['item_type']} is ready",
                      detail="Weigh the piece and scrap on receipt (Receive on the job page).", payload={"job_id": job["id"]})
        what = f"{job['code']} ready" if k["language"] != "hi" else f"{job['code']} तैयार"
        result = {"understood": "ready", "job_id": job["id"]}
    else:
        upsert_action(conn, key=f"msg:{karigar_id}:{text[:40]}", agent="Intake", kind="karigar_message", severity="info",
                      title=f"Message from {k['name']}", detail=text, payload={"karigar_id": karigar_id})
    if what:
        messenger.send(conn, audience="karigar", karigar_id=karigar_id, to_name=k["name"], lang=k["language"],
                       text=messenger.render("ack", k["language"], name=k["name"], what=what),
                       job_id=job["id"] if job else None)
    return result
