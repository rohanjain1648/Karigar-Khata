"""Compliance agent: GST job-work challans and the ITC-04 view.

Under CGST Section 143, inputs sent to a job worker must come back (or be supplied onward) within
one year, or the dispatch is treated as a supply on the day it left. ITC-04 reports the challans.
This produces a working register for the CA; it is not a filing.
"""
import csv
import io
from datetime import date, datetime

WARN_DAYS = 300
LIMIT_DAYS = 365


def register(conn, start: str | None = None, end: str | None = None) -> list[dict]:
    sql = ("SELECT j.*, k.name AS karigar_name FROM jobs j JOIN karigars k ON k.id = j.karigar_id WHERE 1=1")
    args = []
    if start:
        sql += " AND substr(j.issued_at, 1, 10) >= ?"
        args.append(start)
    if end:
        sql += " AND substr(j.issued_at, 1, 10) <= ?"
        args.append(end)
    out = []
    for j in conn.execute(sql + " ORDER BY j.issued_at", args):
        j = dict(j)

        def agg(kind):
            r = conn.execute("SELECT COALESCE(SUM(gross_mg),0), COALESCE(SUM(ABS(fine_mg)),0) FROM entries"
                             " WHERE job_id = ? AND kind = ? AND state = 'active'", (j["id"], kind)).fetchone()
            return r[0], r[1]

        ig, ifn = agg("ISSUE")
        pg, pf = agg("RETURN_PIECE")
        sg, sf = agg("RETURN_SCRAP")
        out.append({
            "challan_no": j["challan_no"], "job_code": j["code"], "issued_on": (j["issued_at"] or "")[:10],
            "karigar": j["karigar_name"], "description": f"{j['item_type']} ({j['design_category']})",
            "purity_ppt": j["purity_ppt"], "issued_gross_mg": ig, "issued_fine_mg": ifn,
            "returned_on": (j["returned_at"] or "")[:10], "piece_gross_mg": pg, "scrap_gross_mg": sg,
            "returned_fine_mg": pf + sf, "status": j["status"],
        })
    return out


def open_challan_alerts(conn, today: date) -> list[dict]:
    out = []
    for j in conn.execute("SELECT j.id, j.code, j.challan_no, j.issued_at, k.name FROM jobs j"
                          " JOIN karigars k ON k.id = j.karigar_id WHERE j.returned_at IS NULL"):
        age = (today - datetime.fromisoformat(j["issued_at"]).date()).days
        if age >= WARN_DAYS:
            out.append({"job_id": j["id"], "code": j["code"], "challan_no": j["challan_no"], "karigar": j["name"],
                        "age_days": age, "days_left": LIMIT_DAYS - age,
                        "severity": "high" if age >= LIMIT_DAYS - 30 else "medium"})
    return out


def to_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    if rows:
        w = csv.DictWriter(buf, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return buf.getvalue()
