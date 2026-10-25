"""Deadline agent: predicts which jobs will miss their date before they do.

Expected finish comes from the karigar's own reported progress rate when he has sent one,
otherwise from his historical turnaround for this design category, stretched by how many jobs he
is carrying right now. Jobs tied to a customer occasion (wedding, engagement) are checked against
that date, not just the internal due date.
"""
from datetime import date, datetime, timedelta
from statistics import median

from .. import config

OCCASION_BUFFER_DAYS = 2
STALE_UPDATE_DAYS = 3


def _d(s: str | None) -> date | None:
    return datetime.fromisoformat(s).date() if s else None


def typical_days(conn, karigar_id: int, category: str) -> tuple[float, str]:
    def durations(sql, args):
        out = []
        for a, b in conn.execute(sql, args):
            if a and b:
                out.append(max((datetime.fromisoformat(b) - datetime.fromisoformat(a)).days, 1))
        return out

    own = durations("SELECT issued_at, returned_at FROM jobs WHERE karigar_id = ? AND design_category = ?"
                    " AND returned_at IS NOT NULL", (karigar_id, category))
    if len(own) >= 2:
        return float(median(own)), f"his median over {len(own)} past {config.category_label(category)} jobs"
    shop = durations("SELECT issued_at, returned_at FROM jobs WHERE design_category = ? AND returned_at IS NOT NULL",
                     (category,))
    if len(shop) >= 2:
        return float(median(shop)), f"shop median over {len(shop)} past jobs"
    return float(config.CATEGORIES.get(category, config.CATEGORIES["other"])[4]), "category default"


def open_load(conn, karigar_id: int) -> int:
    return conn.execute("SELECT COUNT(*) FROM jobs WHERE karigar_id = ? AND status IN ('issued','in_progress')",
                        (karigar_id,)).fetchone()[0]


def assess_job(conn, job: dict, today: date) -> dict:
    issued = _d(job["issued_at"]) or today
    due = _d(job["due_date"])
    reasons: list[str] = []
    load = open_load(conn, job["karigar_id"])
    base_days, basis = typical_days(conn, job["karigar_id"], job["design_category"])

    pct = job.get("progress_pct") or 0
    progress_at = _d(job.get("progress_at"))
    if 0 < pct < 100 and progress_at:
        elapsed = max((progress_at - issued).days, 1)
        remaining = elapsed * (100 - pct) / pct
        expected = progress_at + timedelta(days=round(remaining))
        basis = f"his update: {pct}% done after {elapsed} days"
    else:
        stretch = 1 + 0.15 * max(load - 1, 0)
        expected = issued + timedelta(days=round(base_days * stretch))
        if load > 1:
            basis += f", stretched ×{stretch:.2f} for {load} open jobs"

    stale = (today - (progress_at or issued)).days >= STALE_UPDATE_DAYS
    if stale:
        reasons.append(f"no progress update for {(today - (progress_at or issued)).days} days")

    occasion = _d(job.get("occasion_date"))
    hard_date = due
    if occasion:
        latest = occasion - timedelta(days=OCCASION_BUFFER_DAYS)
        if not hard_date or latest < hard_date:
            hard_date = latest
            reasons.append(f"customer's {job.get('occasion') or 'occasion'} on {occasion.isoformat()}")

    slack = (hard_date - expected).days if hard_date else None
    if hard_date and today > hard_date:
        risk = "late"
    elif slack is not None and slack < 0:
        risk = "high"
    elif slack is not None and (slack <= 1 or (stale and (hard_date - today).days <= 4)):
        risk = "medium"
    else:
        risk = "low"
    if slack is not None and slack < 0:
        reasons.append(f"expected {expected.isoformat()} is {-slack} day(s) after {hard_date.isoformat()}")

    return {
        "job_id": job["id"], "code": job["code"], "karigar_id": job["karigar_id"],
        "karigar_name": job.get("karigar_name"), "item_type": job["item_type"],
        "design_category": job["design_category"], "due_date": job["due_date"],
        "hard_date": hard_date.isoformat() if hard_date else None,
        "expected_finish": expected.isoformat(), "slack_days": slack, "risk": risk,
        "progress_pct": pct, "stale": stale, "basis": basis, "reasons": reasons, "karigar_load": load,
        "order_code": job.get("order_code"), "customer_name": job.get("customer_name"),
        "occasion": job.get("occasion"), "occasion_date": job.get("occasion_date"),
    }


def reassign_candidates(conn, job: dict, today: date, target: date) -> list[dict]:
    """Other karigars skilled in this category who could finish *half* the work by `target`."""
    out = []
    for k in conn.execute("SELECT id, name, skills FROM karigars WHERE active = 1 AND id != ?", (job["karigar_id"],)):
        skills = [s.strip() for s in (k["skills"] or "").split(",")]
        if job["design_category"] not in skills:
            continue
        load = open_load(conn, k["id"])
        days, _ = typical_days(conn, k["id"], job["design_category"])
        finish = today + timedelta(days=round(days * 0.5 * (1 + 0.15 * load)))
        if finish <= target:
            out.append({"karigar_id": k["id"], "name": k["name"], "load": load, "finish": finish.isoformat()})
    return sorted(out, key=lambda c: (c["finish"], c["load"]))


def assess_all(conn, today: date) -> list[dict]:
    from .. import jobs as jobs_mod
    order = {"late": 0, "high": 1, "medium": 2, "low": 3}
    res = [assess_job(conn, j, today) for j in jobs_mod.list_jobs(conn, open_only=True)]
    return sorted(res, key=lambda r: (order[r["risk"]], r["hard_date"] or "9999"))
