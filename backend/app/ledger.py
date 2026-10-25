"""Two-sided, hash-chained gold & money ledger.

Sign convention (karigar's account, as both parties see it):
  fine_mg     > 0  -> karigar holds that much of the jeweller's fine gold
  amount_paise > 0 -> jeweller owes the karigar that much money

Entry content is immutable once written and covered by a SHA-256 chain. Acknowledgements,
disputes and supersession are state changes, recorded in a second chain (`audit`), so the
full history of who agreed to what, and when, can be replayed and verified by either side.
"""
import hashlib
import json
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal

GENESIS = "0" * 64

# kind -> sign applied to the fine weight of the gross/purity given
GOLD_KINDS = {
    "ISSUE": +1,              # gold handed to karigar
    "RETURN_PIECE": -1,       # finished piece received back
    "RETURN_SCRAP": -1,       # filings/cut pieces returned
    "REFINER_CREDIT": -1,     # gold recovered by refiner from karigar's workshop sweepings
    "WASTAGE_ALLOWANCE": -1,  # agreed wastage written off at settlement
    "GOLD_ADJUSTMENT": +1,    # signed correction, fine given directly
}
MONEY_KINDS = {"MAKING_CHARGE": +1, "PAYMENT": -1, "MONEY_ADJUSTMENT": +1}
ALL_KINDS = set(GOLD_KINDS) | set(MONEY_KINDS)

HASHED_FIELDS = (
    "karigar_id", "job_id", "settlement_id", "kind", "gross_mg", "purity_ppt", "fine_mg",
    "amount_paise", "note", "evidence", "created_by", "created_at", "prev_hash",
)
AUDIT_FIELDS = ("entry_id", "settlement_id", "actor", "action", "detail", "created_at", "prev_hash")


_clock: datetime | None = None


def set_clock(dt: datetime | None) -> None:
    """Pin 'now' (used only by the demo seeder to replay a realistic history)."""
    global _clock
    _clock = dt


def now_iso() -> str:
    return (_clock or datetime.now()).replace(microsecond=0).isoformat()


def round_div(numerator: int, denominator: int) -> int:
    """Integer division with banker's rounding; exact for any int sizes we use."""
    if denominator == 0:
        raise ZeroDivisionError("denominator is zero")
    q = Decimal(numerator) / Decimal(denominator)
    return int(q.quantize(Decimal(1), rounding=ROUND_HALF_EVEN))


def fine_of(gross_mg: int, purity_ppt: int) -> int:
    """Pure-gold content in mg of `gross_mg` at `purity_ppt` (e.g. 916 for 22K)."""
    if gross_mg < 0 or not (0 < purity_ppt <= 1000):
        raise ValueError("gross must be >= 0 and purity in (0, 1000]")
    return round_div(gross_mg * purity_ppt, 1000)


def _digest(record: dict, fields) -> str:
    payload = json.dumps({k: record.get(k) for k in fields}, sort_keys=True,
                         separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _last_hash(conn, table: str) -> str:
    row = conn.execute(f"SELECT hash FROM {table} ORDER BY id DESC LIMIT 1").fetchone()
    return row[0] if row else GENESIS


def audit(conn, actor: str, action: str, *, entry_id=None, settlement_id=None, detail="") -> None:
    rec = {
        "entry_id": entry_id, "settlement_id": settlement_id, "actor": actor, "action": action,
        "detail": detail, "created_at": now_iso(), "prev_hash": _last_hash(conn, "audit"),
    }
    rec["hash"] = _digest(rec, AUDIT_FIELDS)
    conn.execute(
        "INSERT INTO audit(entry_id, settlement_id, actor, action, detail, created_at, prev_hash, hash)"
        " VALUES(:entry_id, :settlement_id, :actor, :action, :detail, :created_at, :prev_hash, :hash)",
        rec,
    )


def post(conn, *, karigar_id: int, kind: str, created_by: str, job_id=None, settlement_id=None,
         gross_mg=None, purity_ppt=None, fine_mg=None, amount_paise=0, note="", evidence=None,
         created_at=None) -> int:
    """Append an entry. Gold kinds take gross+purity (fine is derived) or, for allowances and
    adjustments, a fine weight directly. The creator's side is acknowledged automatically;
    entries produced by an approved settlement are acknowledged by both parties."""
    if kind not in ALL_KINDS:
        raise ValueError(f"unknown entry kind {kind}")
    if created_by not in ("jeweller", "karigar", "settlement"):
        raise ValueError("created_by must be jeweller, karigar or settlement")

    if kind in GOLD_KINDS:
        if gross_mg is not None:
            if purity_ppt is None:
                raise ValueError("purity is required with a gross weight")
            signed_fine = GOLD_KINDS[kind] * fine_of(int(gross_mg), int(purity_ppt))
        elif fine_mg is not None:
            signed_fine = GOLD_KINDS[kind] * int(fine_mg)
        else:
            raise ValueError("gold entry needs gross_mg+purity_ppt or fine_mg")
        signed_amount = 0
    else:
        signed_fine = 0
        signed_amount = MONEY_KINDS[kind] * int(amount_paise)

    rec = {
        "karigar_id": karigar_id, "job_id": job_id, "settlement_id": settlement_id, "kind": kind,
        "gross_mg": gross_mg, "purity_ppt": purity_ppt, "fine_mg": signed_fine,
        "amount_paise": signed_amount, "note": note or "", "evidence": evidence,
        "created_by": created_by, "created_at": created_at or now_iso(),
        "prev_hash": _last_hash(conn, "entries"),
    }
    rec["hash"] = _digest(rec, HASHED_FIELDS)
    rec["jeweller_ack"] = "confirmed" if created_by in ("jeweller", "settlement") else "pending"
    rec["karigar_ack"] = "confirmed" if created_by in ("karigar", "settlement") else "pending"
    cur = conn.execute(
        "INSERT INTO entries(karigar_id, job_id, settlement_id, kind, gross_mg, purity_ppt, fine_mg,"
        " amount_paise, note, evidence, created_by, created_at, prev_hash, hash, jeweller_ack, karigar_ack)"
        " VALUES(:karigar_id, :job_id, :settlement_id, :kind, :gross_mg, :purity_ppt, :fine_mg,"
        " :amount_paise, :note, :evidence, :created_by, :created_at, :prev_hash, :hash,"
        " :jeweller_ack, :karigar_ack)",
        rec,
    )
    entry_id = cur.lastrowid
    audit(conn, created_by, "post", entry_id=entry_id, detail=kind)
    return entry_id


def get(conn, entry_id: int) -> dict | None:
    r = conn.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
    return dict(r) if r else None


def acknowledge(conn, entry_id: int, party: str) -> dict:
    """`party` ('jeweller' | 'karigar') confirms an entry the other side wrote."""
    e = _require_active(conn, entry_id)
    col = f"{party}_ack"
    if e[col] == "confirmed":
        return e
    conn.execute(f"UPDATE entries SET {col} = 'confirmed' WHERE id = ?", (entry_id,))
    audit(conn, party, "confirm", entry_id=entry_id)
    return get(conn, entry_id)


def dispute(conn, entry_id: int, party: str, reason: str, claimed_gross_mg: int | None = None) -> dict:
    e = _require_active(conn, entry_id)
    col = f"{party}_ack"
    if e[col] == "confirmed":
        raise ValueError("entry already confirmed by this party; raise a correction instead")
    conn.execute(
        f"UPDATE entries SET {col} = 'disputed', dispute_reason = ?, claimed_gross_mg = ? WHERE id = ?",
        (reason, claimed_gross_mg, entry_id),
    )
    audit(conn, party, "dispute", entry_id=entry_id,
          detail=json.dumps({"reason": reason, "claimed_gross_mg": claimed_gross_mg}))
    return get(conn, entry_id)


def supersede(conn, entry_id: int, actor: str, *, gross_mg: int, note: str) -> int:
    """Resolve a disputed gold entry by replacing it with a corrected one. The original stays in
    the ledger (and the chain) marked superseded; the replacement needs the other side's ack."""
    old = _require_active(conn, entry_id)
    if old["kind"] not in GOLD_KINDS or old["gross_mg"] is None:
        raise ValueError("only gross-weight gold entries can be superseded")
    new_id = post(conn, karigar_id=old["karigar_id"], kind=old["kind"], created_by=actor,
                  job_id=old["job_id"], gross_mg=gross_mg, purity_ppt=old["purity_ppt"],
                  note=note, evidence=old["evidence"])
    conn.execute("UPDATE entries SET state = 'superseded', superseded_by = ? WHERE id = ?",
                 (new_id, entry_id))
    audit(conn, actor, "supersede", entry_id=entry_id, detail=f"replaced by {new_id}")
    return new_id


def _require_active(conn, entry_id: int) -> dict:
    e = get(conn, entry_id)
    if not e:
        raise LookupError("entry not found")
    if e["state"] != "active":
        raise ValueError("entry is superseded")
    return e


def balances(conn, karigar_id: int) -> dict:
    """Agreed balance counts only entries both sides confirmed. Everything else is shown
    separately so neither side's unconfirmed number silently becomes the truth."""
    rs = [dict(r) for r in conn.execute(
        "SELECT * FROM entries WHERE karigar_id = ? AND state = 'active'", (karigar_id,))]
    agreed = [e for e in rs if e["jeweller_ack"] == "confirmed" and e["karigar_ack"] == "confirmed"]
    disputed = [e for e in rs if "disputed" in (e["jeweller_ack"], e["karigar_ack"])]
    pending = [e for e in rs if e not in agreed and e not in disputed]
    return {
        "fine_mg": sum(e["fine_mg"] for e in agreed),
        "money_paise": sum(e["amount_paise"] for e in agreed),
        "pending_fine_mg": sum(e["fine_mg"] for e in pending),
        "pending_money_paise": sum(e["amount_paise"] for e in pending),
        "disputed_fine_mg": sum(e["fine_mg"] for e in disputed),
        "pending_count": len(pending),
        "disputed_count": len(disputed),
    }


def verify(conn) -> dict:
    """Recompute both chains. Any edited, inserted or deleted row breaks the link after it."""
    out = {}
    for table, fields in (("entries", HASHED_FIELDS), ("audit", AUDIT_FIELDS)):
        prev, broken = GENESIS, None
        count = 0
        for r in conn.execute(f"SELECT * FROM {table} ORDER BY id"):
            r = dict(r)
            count += 1
            if r["prev_hash"] != prev or _digest(r, fields) != r["hash"]:
                broken = r["id"]
                break
            prev = r["hash"]
        out[table] = {"ok": broken is None, "rows": count, "first_broken_id": broken, "head": prev}
    out["ok"] = all(v["ok"] for v in out.values() if isinstance(v, dict))
    return out
