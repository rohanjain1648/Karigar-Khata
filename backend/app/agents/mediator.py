"""Mediator agent: proposes how to close a dispute from the evidence; humans decide.

The rule set is deliberately tilted toward the weaker party on tiny differences: when the two
numbers are within scale noise, the karigar's figure is recommended, because the cost to the shop
is a few milligrams and the cost to the relationship of arguing over it is not.
"""
import json

from .. import config
from .llm import lyzr, numbers_preserved
from .messenger import g


def for_entry(conn, entry: dict) -> dict:
    k = dict(conn.execute("SELECT * FROM karigars WHERE id = ?", (entry["karigar_id"],)).fetchone())
    recorded, claimed = entry["gross_mg"], entry["claimed_gross_mg"]
    tolerance = 2 * config.SCALE_RESOLUTION_MG
    past = conn.execute("SELECT COUNT(*) FROM audit a JOIN entries e ON e.id = a.entry_id"
                        " WHERE a.action = 'dispute' AND e.karigar_id = ? AND e.id != ?",
                        (entry["karigar_id"], entry["id"])).fetchone()[0]
    facts = [f"Recorded by shop: {g(recorded)} g", f"Karigar says: {g(claimed) if claimed else 'not given'} g"]
    options = []
    if claimed is not None:
        diff = claimed - recorded
        fine_diff = abs(diff) * (entry["purity_ppt"] or 1000) // 1000
        facts.append(f"Difference: {g(abs(diff))} g ({g(fine_diff)} g fine)")
        if abs(diff) <= tolerance:
            options.append({"action": "accept_karigar", "recommended": True,
                            "label": f"Accept {k['name']}'s {g(claimed)} g",
                            "why": f"Within scale tolerance (±{g(tolerance)} g). Not worth a dispute."})
            options.append({"action": "reweigh", "recommended": False, "label": "Re-weigh together",
                            "why": "Only if either side insists."})
        else:
            options.append({"action": "reweigh", "recommended": True, "label": "Re-weigh together on the shop scale",
                            "why": "Gap is larger than scale noise. Weigh in front of both, photo the display, record that number."})
            options.append({"action": "accept_karigar", "recommended": False,
                            "label": f"Accept {k['name']}'s {g(claimed)} g", "why": "If the shop's own weighing can't be shown."})
    else:
        options.append({"action": "reweigh", "recommended": True, "label": "Re-weigh together", "why": "No counter-figure given."})
    if entry.get("evidence"):
        facts.append("Shop has a photo of the scale display for this entry.")
    if past:
        facts.append(f"{past} earlier dispute(s) with this karigar.")

    summary = " · ".join(facts)
    explanation, source = summary, "rules"
    if lyzr.enabled("mediator"):
        brief = ("ROLE: Neutral mediator between a jeweller and an artisan goldsmith (karigar) over a gold "
                 "weight entry. The karigar has less power; be fair and plain. In 2-3 sentences explain the "
                 "situation and the recommended next step. Copy all numbers exactly.\n"
                 f"FACTS: {summary}\nREASON GIVEN BY KARIGAR: {entry.get('dispute_reason') or '-'}\n"
                 f"OPTIONS: {json.dumps(options)}")
        out = lyzr.chat("mediator", brief, f"dispute-{entry['id']}")
        if out and numbers_preserved(summary, out):
            explanation, source = out.strip(), "lyzr"
    return {"entry_id": entry["id"], "facts": facts, "options": options, "explanation": explanation, "source": source}


def for_settlement(conn, s: dict, flags: list[dict], bench: dict) -> dict:
    f = s["figures"]
    job = dict(conn.execute("SELECT * FROM jobs WHERE id = ?", (s["job_id"],)).fetchone())
    b = bench.get(job["design_category"], {})
    facts = [f"Loss {f['loss_bp'] / 100:.2f}% vs agreed {f['agreed_bp'] / 100:.2f}%"]
    if b.get("median_bp") is not None:
        facts.append(f"Shop median for this design {b['median_bp'] / 100:.2f}% (n={b['n']})")
    options = []
    if f["loss_bp"] > f["agreed_bp"] and b.get("median_bp") is not None and f["loss_bp"] <= b["p90_bp"]:
        options.append({"action": "raise_allowance", "recommended": True,
                        "label": f"Settle at actual loss {f['loss_bp'] / 100:.2f}%",
                        "why": "Loss is within the normal range for this design in your own shop."})
    options.append({"action": "refiner", "recommended": f["loss_bp"] > (b.get("p90_bp") or 10_000),
                    "label": "Send workshop sweepings to refiner, credit recovery, then settle",
                    "why": "Recovered gold goes back to the karigar's account before the shortfall is counted."})
    options.append({"action": "keep", "recommended": False, "label": "Keep proposal as is",
                    "why": "Karigar's objection: " + (s.get("karigar_comment") or "-")})
    return {"settlement_id": s["id"], "facts": facts + [fl["text"] for fl in flags], "options": options}
