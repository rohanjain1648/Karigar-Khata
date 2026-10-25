import json
import uuid
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import auth, config, db, jobs, ledger, seed, settlement
from . import services as svc
from .agents import analyst, autopilot, compliance, deadline, intake, karigar_chat, mediator, payments, wastage
from .agents.llm import lyzr

app = FastAPI(title="Karigar Khata", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=config.UPLOAD_DIR), name="uploads")

if not config.DB_PATH.exists():
    seed.reset()


def conn_dep():
    c = db.connect()
    try:
        yield c
    finally:
        c.close()


def run_write(c, fn, *a, **kw):
    try:
        with db.write(c):
            return fn(*a, **kw)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


def today() -> date:
    return date.today()


# ---------- models ----------
class Login(BaseModel):
    role: str
    pin: str
    karigar_id: int | None = None


class IssueIn(BaseModel):
    karigar_id: int
    design_category: str
    item_type: str = ""
    purity_ppt: int = Field(916, gt=0, le=1000)
    gross_mg: int = Field(..., gt=0)
    agreed_wastage_bp: int | None = Field(None, ge=0, le=2000)
    making_paise_per_g: int | None = Field(None, ge=0)
    wastage_policy: str = "agreed"
    due_date: str | None = None
    order_id: int | None = None
    evidence: str | None = None
    note: str = ""


class ReceiveIn(BaseModel):
    piece_gross_mg: int = Field(..., gt=0)
    piece_purity_ppt: int | None = None
    scrap_gross_mg: int = Field(0, ge=0)
    scrap_purity_ppt: int | None = None
    evidence: str | None = None
    note: str = ""


class RefinerIn(BaseModel):
    fine_mg: int = Field(..., gt=0)
    refiner_ref: str


class TextIn(BaseModel):
    text: str


class DisputeIn(BaseModel):
    reason: str
    claimed_gross_mg: int | None = None


class ResolveIn(BaseModel):
    action: str
    gross_mg: int | None = None


class PayIn(BaseModel):
    amount_paise: int = Field(..., gt=0)
    upi_ref: str


class ProgressIn(BaseModel):
    pct: int = Field(..., ge=0, le=100)
    note: str = ""


class OrderIn(BaseModel):
    customer_name: str
    customer_phone: str = ""
    item_type: str
    design_category: str
    occasion: str = ""
    occasion_date: str | None = None


class CommentIn(BaseModel):
    comment: str


# ---------- public ----------
@app.get("/api/health")
def health():
    return {"ok": True, "shop": config.SHOP_NAME, "lyzr": lyzr.status()}


@app.post("/api/auth/login")
def login(body: Login, c=Depends(conn_dep)):
    if body.role == "jeweller":
        if body.pin != config.JEWELLER_PIN:
            raise HTTPException(401, "wrong PIN")
        return {"token": auth.issue("jeweller"), "role": "jeweller", "shop": config.SHOP_NAME}
    if body.role == "karigar":
        k = c.execute("SELECT id, name, pin FROM karigars WHERE id = ? AND active = 1", (body.karigar_id,)).fetchone()
        if not k or k["pin"] != body.pin:
            raise HTTPException(401, "wrong karigar or PIN")
        return {"token": auth.issue("karigar", k["id"]), "role": "karigar", "karigar_id": k["id"], "name": k["name"]}
    raise HTTPException(400, "role must be jeweller or karigar")


@app.get("/api/public/karigars")
def public_karigars(c=Depends(conn_dep)):
    return db.rows(c.execute("SELECT id, name, workshop FROM karigars WHERE active = 1 ORDER BY id"))


@app.get("/api/public/track/{code}")
def track(code: str, c=Depends(conn_dep)):
    o = db.one(c.execute("SELECT * FROM orders WHERE upper(code) = upper(?)", (code,)))
    if not o:
        raise HTTPException(404, "order not found")
    js = db.rows(c.execute("SELECT id, status, progress_pct, due_date FROM jobs WHERE order_id = ?", (o["id"],)))
    stage = "received"
    if js:
        st = {j["status"] for j in js}
        stage = ("ready" if st <= {"returned", "settlement_proposed", "settled", "settlement_disputed"}
                 else "in_making")
    risk = None
    for j in js:
        if j["status"] in ("issued", "in_progress"):
            a = deadline.assess_job(c, jobs.get(c, j["id"]), today())
            risk = a["risk"]
    return {"code": o["code"], "customer_name": o["customer_name"], "item_type": o["item_type"],
            "occasion": o["occasion"], "occasion_date": o["occasion_date"], "stage": stage,
            "progress_pct": max([j["progress_pct"] or 0 for j in js], default=0),
            "on_track": risk in (None, "low", "medium"), "shop": config.SHOP_NAME}


# ---------- jeweller ----------
J = Depends(auth.jeweller)


@app.get("/api/dashboard", dependencies=[J])
def dashboard(c=Depends(conn_dep)):
    t = today()
    ks = []
    for k in db.rows(c.execute("SELECT id, name, language, skills, workshop FROM karigars WHERE active = 1")):
        k["balance"] = ledger.balances(c, k["id"])
        k["open_jobs"] = deadline.open_load(c, k["id"])
        ks.append(k)
    risks = deadline.assess_all(c, t)
    dues = payments.dues(c, t)
    actions = db.rows(c.execute("SELECT * FROM agent_actions WHERE status = 'open' ORDER BY"
                                " CASE severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, id DESC"))
    for a in actions:
        a["payload"] = json.loads(a["payload"] or "{}")
    return {
        "today": t.isoformat(), "shop": config.SHOP_NAME,
        "kpis": {
            "fine_with_karigars_mg": sum(k["balance"]["fine_mg"] for k in ks),
            "unconfirmed_fine_mg": sum(k["balance"]["pending_fine_mg"] for k in ks),
            "open_jobs": len(risks),
            "at_risk": sum(1 for r in risks if r["risk"] in ("late", "high")),
            "disputes": sum(k["balance"]["disputed_count"] for k in ks),
            "unpaid_paise": sum(d["due_paise"] for d in dues),
            "oldest_unpaid_days": max([d["days_waiting"] for d in dues], default=0),
        },
        "karigars": ks, "risks": risks, "dues": dues, "actions": actions,
        "lyzr": lyzr.status(),
    }


@app.get("/api/karigars", dependencies=[J])
def karigars(c=Depends(conn_dep)):
    out = []
    for k in db.rows(c.execute("SELECT id FROM karigars WHERE active = 1 ORDER BY id")):
        p = svc.karigar_profile(c, k["id"])
        p["open_jobs"] = deadline.open_load(c, k["id"])
        out.append(p)
    return out


@app.get("/api/karigars/{kid}", dependencies=[J])
def karigar_detail(kid: int, c=Depends(conn_dep)):
    return _account(c, kid)


def _account(c, kid: int) -> dict:
    if not c.execute("SELECT 1 FROM karigars WHERE id = ?", (kid,)).fetchone():
        raise HTTPException(404, "karigar not found")
    p = svc.karigar_profile(c, kid)
    p["jobs"] = jobs.list_jobs(c, karigar_id=kid)
    p["entries"] = db.rows(c.execute("SELECT e.*, j.code AS job_code FROM entries e LEFT JOIN jobs j ON j.id = e.job_id"
                                     " WHERE e.karigar_id = ? ORDER BY e.created_at DESC, e.id DESC", (kid,)))
    p["settlements"] = [settlement.get(c, r["id"]) for r in c.execute(
        "SELECT id FROM settlements WHERE karigar_id = ? AND status != 'withdrawn' ORDER BY id DESC", (kid,))]
    for s in p["settlements"]:
        s["job_code"] = c.execute("SELECT code FROM jobs WHERE id = ?", (s["job_id"],)).fetchone()[0]
    p["messages"] = db.rows(c.execute("SELECT * FROM messages WHERE karigar_id = ? AND audience = 'karigar'"
                                      " ORDER BY created_at, id", (kid,)))
    return p


@app.get("/api/orders", dependencies=[J])
def orders(c=Depends(conn_dep)):
    return db.rows(c.execute("SELECT * FROM orders ORDER BY occasion_date"))


@app.post("/api/orders", dependencies=[J])
def create_order(body: OrderIn, c=Depends(conn_dep)):
    def go():
        n = c.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        code = f"SL-{1045 + n}"
        c.execute("INSERT INTO orders(code, customer_name, customer_phone, item_type, design_category, occasion,"
                  " occasion_date, created_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                  (code, body.customer_name, body.customer_phone, body.item_type, body.design_category, body.occasion,
                   body.occasion_date, ledger.now_iso()))
        return db.one(c.execute("SELECT * FROM orders WHERE code = ?", (code,)))
    return run_write(c, go)


@app.get("/api/jobs", dependencies=[J])
def list_jobs(open_only: bool = False, c=Depends(conn_dep)):
    return jobs.list_jobs(c, open_only=open_only)


@app.get("/api/jobs/{job_id}", dependencies=[J])
def job_detail(job_id: int, c=Depends(conn_dep)):
    j = jobs.get(c, job_id)
    if not j:
        raise HTTPException(404, "job not found")
    j["entries"] = db.rows(c.execute("SELECT * FROM entries WHERE job_id = ? ORDER BY id", (job_id,)))
    j["progress"] = db.rows(c.execute("SELECT * FROM progress WHERE job_id = ? ORDER BY id", (job_id,)))
    j["settlements"] = [settlement.get(c, r["id"]) for r in c.execute(
        "SELECT id FROM settlements WHERE job_id = ? ORDER BY id DESC", (job_id,))]
    if j["status"] in ("issued", "in_progress"):
        j["assessment"] = deadline.assess_job(c, j, today())
    if j["status"] in ("returned", "settlement_proposed", "settlement_disputed", "settled"):
        figs = settlement.job_figures(c, job_id)
        j["preview"] = figs
        j["flags"] = wastage.review_settlement(c, j, figs)
    j["benchmark"] = wastage.benchmarks(c).get(j["design_category"])
    return j


@app.post("/api/intake/parse", dependencies=[J])
def parse_note(body: TextIn, c=Depends(conn_dep)):
    return intake.parse(c, body.text, today())


@app.post("/api/jobs", dependencies=[J])
def create_job(body: IssueIn, c=Depends(conn_dep)):
    return run_write(c, svc.issue_job, c, **body.model_dump())


@app.post("/api/jobs/{job_id}/receive", dependencies=[J])
def receive(job_id: int, body: ReceiveIn, c=Depends(conn_dep)):
    return run_write(c, svc.receive_job, c, job_id, **body.model_dump())


@app.post("/api/jobs/{job_id}/refiner-credit", dependencies=[J])
def refiner(job_id: int, body: RefinerIn, c=Depends(conn_dep)):
    return run_write(c, jobs.refiner_credit, c, job_id, fine_mg=body.fine_mg, refiner_ref=body.refiner_ref)


@app.post("/api/jobs/{job_id}/settlement", dependencies=[J])
def propose(job_id: int, c=Depends(conn_dep)):
    return run_write(c, svc.propose_settlement, c, job_id, "jeweller")


@app.get("/api/settlements", dependencies=[J])
def list_settlements(c=Depends(conn_dep)):
    out = []
    for r in c.execute("SELECT s.id, k.name, j.code FROM settlements s JOIN karigars k ON k.id = s.karigar_id"
                       " JOIN jobs j ON j.id = s.job_id WHERE s.status != 'withdrawn' ORDER BY s.id DESC"):
        s = settlement.get(c, r["id"])
        s["karigar_name"], s["job_code"] = r["name"], r["code"]
        out.append(s)
    return out


@app.post("/api/settlements/{sid}/approve", dependencies=[J])
def approve_as_jeweller(sid: int, c=Depends(conn_dep)):
    return run_write(c, svc.approve_settlement, c, sid, "jeweller")


@app.post("/api/settlements/{sid}/resolve", dependencies=[J])
def resolve_settlement(sid: int, body: ResolveIn, c=Depends(conn_dep)):
    return run_write(c, svc.resolve_settlement_dispute, c, sid, body.action)


@app.get("/api/settlements/{sid}/mediate", dependencies=[J])
def mediate_settlement(sid: int, c=Depends(conn_dep)):
    s = settlement.get(c, sid)
    if not s:
        raise HTTPException(404, "settlement not found")
    job = jobs.get(c, s["job_id"])
    bench = wastage.benchmarks(c)
    return mediator.for_settlement(c, s, wastage.review_settlement(c, job, s["figures"], bench), bench)


@app.post("/api/settlements/{sid}/pay", dependencies=[J])
def pay(sid: int, body: PayIn, c=Depends(conn_dep)):
    return run_write(c, svc.pay, c, sid, body.amount_paise, body.upi_ref)


@app.get("/api/payments/dues", dependencies=[J])
def dues(c=Depends(conn_dep)):
    return payments.dues(c, today())


@app.post("/api/entries/{eid}/confirm", dependencies=[J])
def jeweller_confirm(eid: int, c=Depends(conn_dep)):
    return run_write(c, svc.confirm_entry, c, eid, "jeweller")


@app.get("/api/entries/{eid}/mediate", dependencies=[J])
def mediate_entry(eid: int, c=Depends(conn_dep)):
    e = ledger.get(c, eid)
    if not e:
        raise HTTPException(404, "entry not found")
    return mediator.for_entry(c, e)


@app.post("/api/entries/{eid}/resolve", dependencies=[J])
def resolve_entry(eid: int, body: ResolveIn, c=Depends(conn_dep)):
    return run_write(c, svc.resolve_entry, c, eid, body.action, body.gross_mg)


@app.post("/api/agents/run", dependencies=[J])
def run_agents(c=Depends(conn_dep)):
    return run_write(c, autopilot.run, c, today())


@app.get("/api/agents/actions", dependencies=[J])
def actions(status: str = "open", c=Depends(conn_dep)):
    rs = db.rows(c.execute("SELECT * FROM agent_actions WHERE status = ? ORDER BY id DESC LIMIT 200", (status,)))
    for a in rs:
        a["payload"] = json.loads(a["payload"] or "{}")
    return rs


@app.post("/api/agents/actions/{aid}/approve", dependencies=[J])
def approve_action(aid: int, c=Depends(conn_dep)):
    return run_write(c, autopilot.approve, c, aid)


@app.post("/api/agents/actions/{aid}/dismiss", dependencies=[J])
def dismiss_action(aid: int, c=Depends(conn_dep)):
    run_write(c, autopilot.dismiss, c, aid)
    return {"ok": True}


@app.get("/api/wastage/benchmarks", dependencies=[J])
def benchmarks(c=Depends(conn_dep)):
    b = wastage.benchmarks(c)
    b.pop("_by_karigar", None)
    return b


@app.get("/api/compliance/register", dependencies=[J])
def itc04(start: str | None = None, end: str | None = None, format: str = "json", c=Depends(conn_dep)):
    rows = compliance.register(c, start, end)
    if format == "csv":
        return PlainTextResponse(compliance.to_csv(rows), media_type="text/csv",
                                 headers={"Content-Disposition": "attachment; filename=job-work-register.csv"})
    return {"rows": rows, "alerts": compliance.open_challan_alerts(c, today())}


@app.get("/api/ledger/verify", dependencies=[J])
def verify(c=Depends(conn_dep)):
    return ledger.verify(c)


@app.get("/api/messages", dependencies=[J])
def messages(c=Depends(conn_dep)):
    return db.rows(c.execute("SELECT * FROM messages ORDER BY id DESC LIMIT 100"))


@app.post("/api/ask", dependencies=[J])
def ask(body: TextIn, c=Depends(conn_dep)):
    return analyst.answer(c, body.text, today())


@app.post("/api/uploads")
def upload(file: UploadFile = File(...), _s=Depends(auth.karigar_or_jeweller)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".heic"):
        raise HTTPException(400, "images only")
    name = f"{uuid.uuid4().hex}{ext}"
    (config.UPLOAD_DIR / name).write_bytes(file.file.read())
    return {"url": f"/uploads/{name}"}


@app.post("/api/admin/reset", dependencies=[J])
def reset_demo():
    seed.reset()
    return {"ok": True}


# ---------- karigar (scoped to the token's own id) ----------
@app.get("/api/me")
def me(s=Depends(auth.karigar), c=Depends(conn_dep)):
    return _account(c, s["kid"])


def _own_entry(c, eid: int, kid: int) -> dict:
    e = ledger.get(c, eid)
    if not e or e["karigar_id"] != kid:
        raise HTTPException(404, "entry not found")
    return e


def _own_settlement(c, sid: int, kid: int) -> dict:
    st = settlement.get(c, sid)
    if not st or st["karigar_id"] != kid:
        raise HTTPException(404, "settlement not found")
    return st


@app.post("/api/me/entries/{eid}/confirm")
def k_confirm(eid: int, s=Depends(auth.karigar), c=Depends(conn_dep)):
    _own_entry(c, eid, s["kid"])
    return run_write(c, svc.confirm_entry, c, eid, "karigar")


@app.post("/api/me/entries/{eid}/dispute")
def k_dispute(eid: int, body: DisputeIn, s=Depends(auth.karigar), c=Depends(conn_dep)):
    _own_entry(c, eid, s["kid"])

    def go():
        e = svc.dispute_entry(c, eid, "karigar", body.reason, body.claimed_gross_mg)
        autopilot.run(c, today())
        return e
    return run_write(c, go)


@app.post("/api/me/settlements/{sid}/approve")
def k_approve(sid: int, s=Depends(auth.karigar), c=Depends(conn_dep)):
    _own_settlement(c, sid, s["kid"])
    return run_write(c, svc.approve_settlement, c, sid, "karigar")


@app.post("/api/me/settlements/{sid}/dispute")
def k_dispute_settlement(sid: int, body: CommentIn, s=Depends(auth.karigar), c=Depends(conn_dep)):
    _own_settlement(c, sid, s["kid"])

    def go():
        st = svc.dispute_settlement(c, sid, "karigar", body.comment)
        autopilot.run(c, today())
        return st
    return run_write(c, go)


@app.post("/api/me/jobs/{job_id}/progress")
def k_progress(job_id: int, body: ProgressIn, s=Depends(auth.karigar), c=Depends(conn_dep)):
    j = jobs.get(c, job_id)
    if not j or j["karigar_id"] != s["kid"]:
        raise HTTPException(404, "job not found")
    return run_write(c, jobs.record_progress, c, job_id, body.pct, body.note)


@app.post("/api/me/messages")
def k_message(body: TextIn, s=Depends(auth.karigar), c=Depends(conn_dep)):
    return run_write(c, karigar_chat.handle, c, s["kid"], body.text)


# ---------- built frontend (production) ----------
DIST = config.BASE_DIR.parent / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = DIST / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
