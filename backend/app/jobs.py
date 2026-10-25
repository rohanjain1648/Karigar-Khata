"""Job-work lifecycle: issue -> (progress) -> receive -> settle.

Each job carries a GST job-work challan number, since gold sent to a karigar must be reported
under Section 143 / ITC-04 and come back within a year.
"""
from datetime import date

from . import config, ledger


def _next_code(conn, prefix: str, table: str) -> str:
    n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] + 1
    return f"{prefix}{n:04d}"


def _fy(d: date) -> str:
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def issue(conn, *, karigar_id: int, design_category: str, item_type: str, purity_ppt: int,
          gross_mg: int, agreed_wastage_bp: int | None = None, making_paise_per_g: int | None = None,
          due_date: str | None = None, order_id: int | None = None, evidence: str | None = None,
          note: str = "", wastage_policy: str = "agreed", issued_at: str | None = None) -> dict:
    if gross_mg <= 0:
        raise ValueError("issued weight must be positive")
    if design_category not in config.CATEGORIES:
        design_category = "other"
    k = conn.execute("SELECT id FROM karigars WHERE id = ? AND active = 1", (karigar_id,)).fetchone()
    if not k:
        raise LookupError("karigar not found")
    cat = config.CATEGORIES[design_category]
    issued_at = issued_at or ledger.now_iso()
    code = _next_code(conn, "J-", "jobs")
    challan = f"CH/{_fy(date.fromisoformat(issued_at[:10]))}/{code[2:]}"
    cur = conn.execute(
        "INSERT INTO jobs(code, challan_no, order_id, karigar_id, item_type, design_category, purity_ppt,"
        " agreed_wastage_bp, wastage_policy, making_paise_per_g, due_date, status, issued_at)"
        " VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'issued', ?)",
        (code, challan, order_id, karigar_id, item_type or cat[0], design_category, purity_ppt,
         cat[2] if agreed_wastage_bp is None else agreed_wastage_bp, wastage_policy,
         cat[3] if making_paise_per_g is None else making_paise_per_g, due_date, issued_at),
    )
    job_id = cur.lastrowid
    ledger.post(conn, karigar_id=karigar_id, kind="ISSUE", created_by="jeweller", job_id=job_id,
                gross_mg=gross_mg, purity_ppt=purity_ppt, evidence=evidence,
                note=note or f"Issued for {item_type or cat[0]} ({challan})", created_at=issued_at)
    return get(conn, job_id)


def receive(conn, job_id: int, *, piece_gross_mg: int, piece_purity_ppt: int | None = None,
            scrap_gross_mg: int = 0, scrap_purity_ppt: int | None = None, evidence: str | None = None,
            note: str = "", received_at: str | None = None) -> dict:
    job = get(conn, job_id)
    if not job:
        raise LookupError("job not found")
    if job["status"] not in ("issued", "in_progress"):
        raise ValueError(f"job is {job['status']}")
    unconfirmed_issue = conn.execute(
        "SELECT COUNT(*) FROM entries WHERE job_id = ? AND kind = 'ISSUE' AND state = 'active'"
        " AND karigar_ack != 'confirmed'", (job_id,)).fetchone()[0]
    if unconfirmed_issue:
        raise ValueError("karigar has not confirmed the issued weight yet; resolve that first")
    if piece_gross_mg <= 0:
        raise ValueError("piece weight must be positive")
    at = received_at or ledger.now_iso()
    common = dict(karigar_id=job["karigar_id"], job_id=job_id, created_by="jeweller", evidence=evidence, created_at=at)
    ledger.post(conn, kind="RETURN_PIECE", gross_mg=piece_gross_mg,
                purity_ppt=piece_purity_ppt or job["purity_ppt"], note=note or "Finished piece received", **common)
    if scrap_gross_mg:
        ledger.post(conn, kind="RETURN_SCRAP", gross_mg=scrap_gross_mg,
                    purity_ppt=scrap_purity_ppt or job["purity_ppt"], note="Scrap / filings returned", **common)
    conn.execute("UPDATE jobs SET status = 'returned', returned_at = ?, progress_pct = 100 WHERE id = ?", (at, job_id))
    return get(conn, job_id)


def refiner_credit(conn, job_id: int, *, fine_mg: int, refiner_ref: str) -> dict:
    """Gold the refiner recovered from this karigar's sweepings, credited back to his account."""
    job = get(conn, job_id)
    if not job:
        raise LookupError("job not found")
    if fine_mg <= 0:
        raise ValueError("recovered fine weight must be positive")
    ledger.post(conn, karigar_id=job["karigar_id"], job_id=job_id, kind="REFINER_CREDIT",
                created_by="jeweller", fine_mg=fine_mg, note=f"Refiner recovery {refiner_ref}")
    return get(conn, job_id)


def record_progress(conn, job_id: int, pct: int, note: str = "", at: str | None = None) -> dict:
    pct = max(0, min(100, int(pct)))
    at = at or ledger.now_iso()
    conn.execute("INSERT INTO progress(job_id, pct, note, created_at) VALUES(?, ?, ?, ?)", (job_id, pct, note, at))
    conn.execute("UPDATE jobs SET progress_pct = ?, progress_at = ?,"
                 " status = CASE WHEN status = 'issued' THEN 'in_progress' ELSE status END WHERE id = ?",
                 (pct, at, job_id))
    return get(conn, job_id)


def get(conn, job_id: int) -> dict | None:
    r = conn.execute(
        "SELECT j.*, k.name AS karigar_name, o.code AS order_code, o.customer_name, o.occasion,"
        " o.occasion_date FROM jobs j JOIN karigars k ON k.id = j.karigar_id"
        " LEFT JOIN orders o ON o.id = j.order_id WHERE j.id = ?", (job_id,)).fetchone()
    if not r:
        return None
    j = dict(r)
    issued = conn.execute(
        "SELECT COALESCE(SUM(gross_mg), 0), COALESCE(SUM(fine_mg), 0) FROM entries"
        " WHERE job_id = ? AND kind = 'ISSUE' AND state = 'active'", (job_id,)).fetchone()
    j["issued_gross_mg"], j["issued_fine_mg"] = issued[0], issued[1]
    j["category_label"] = config.category_label(j["design_category"])
    j["karat"] = config.karat_label(j["purity_ppt"])
    return j


def list_jobs(conn, *, karigar_id: int | None = None, open_only: bool = False) -> list[dict]:
    sql = "SELECT id FROM jobs WHERE 1=1"
    args: list = []
    if karigar_id is not None:
        sql += " AND karigar_id = ?"
        args.append(karigar_id)
    if open_only:
        sql += " AND status IN ('issued', 'in_progress')"
    sql += " ORDER BY COALESCE(due_date, '9999') ASC, id DESC"
    return [get(conn, r[0]) for r in conn.execute(sql, args)]
