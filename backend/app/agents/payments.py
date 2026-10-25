"""Payment agent: how long each karigar has been waiting since both sides approved his settlement."""
from datetime import date, datetime

PROMPT_AFTER_DAYS = 3
OVERDUE_AFTER_DAYS = 7


def dues(conn, today: date) -> list[dict]:
    out = []
    for r in conn.execute(
            "SELECT s.*, k.name AS karigar_name, k.phone, j.code AS job_code FROM settlements s"
            " JOIN karigars k ON k.id = s.karigar_id LEFT JOIN jobs j ON j.id = s.job_id"
            " WHERE s.status = 'approved' AND s.making_paise > s.paid_paise ORDER BY s.approved_at"):
        r = dict(r)
        waiting = (today - datetime.fromisoformat(r["approved_at"]).date()).days
        out.append({
            "settlement_id": r["id"], "karigar_id": r["karigar_id"], "karigar_name": r["karigar_name"],
            "job_code": r["job_code"], "due_paise": r["making_paise"] - r["paid_paise"],
            "approved_at": r["approved_at"], "days_waiting": waiting,
            "status": "overdue" if waiting >= OVERDUE_AFTER_DAYS else "due" if waiting >= PROMPT_AFTER_DAYS else "fresh",
            "upi_link": f"upi://pay?pa={(r['phone'] or 'karigar')}@upi&pn={r['karigar_name'].replace(' ', '%20')}"
                        f"&am={(r['making_paise'] - r['paid_paise']) / 100:.2f}&tn={r['job_code']}",
        })
    return out
