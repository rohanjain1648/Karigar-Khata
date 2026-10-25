"""Wastage agent: fair benchmarks per design, built from this shop's own settled jobs.

It flags in both directions: a karigar losing far more than the design normally loses, and an
agreement that allows far less wastage than the design normally needs (which quietly makes the
artisan pay for gold the process itself consumes).
"""
import json
from statistics import median

from .. import config


def _p90(xs: list[int]) -> int:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(0.9 * (len(xs) - 1))))]


def benchmarks(conn) -> dict:
    by_cat: dict[str, list[int]] = {}
    by_kar: dict[tuple[int, str], list[int]] = {}
    for r in conn.execute("SELECT s.karigar_id, s.computed_json, j.design_category FROM settlements s"
                          " JOIN jobs j ON j.id = s.job_id WHERE s.status = 'approved'"):
        loss_bp = json.loads(r["computed_json"])["loss_bp"]
        by_cat.setdefault(r["design_category"], []).append(loss_bp)
        by_kar.setdefault((r["karigar_id"], r["design_category"]), []).append(loss_bp)
    out = {}
    for cat in config.CATEGORIES:
        xs = by_cat.get(cat, [])
        out[cat] = {
            "label": config.category_label(cat), "n": len(xs),
            "median_bp": int(median(xs)) if xs else None, "p90_bp": _p90(xs) if xs else None,
            "default_bp": config.CATEGORIES[cat][2],
        }
    out["_by_karigar"] = {f"{k}:{c}": {"n": len(v), "median_bp": int(median(v))} for (k, c), v in by_kar.items()}
    return out


def review_settlement(conn, job: dict, figures: dict, bench: dict | None = None) -> list[dict]:
    bench = bench or benchmarks(conn)
    b = bench.get(job["design_category"], {})
    flags = []
    loss_bp, agreed = figures["loss_bp"], figures["agreed_bp"]
    label = config.category_label(job["design_category"])
    if figures["loss_fine_mg"] < 0:
        flags.append({"severity": "high", "code": "negative_loss",
                      "text": f"More fine gold came back ({figures['returned_fine_mg']} mg) than was issued "
                              f"({figures['issued_fine_mg']} mg). Check the purity used on the return or re-weigh."})
    if loss_bp > agreed:
        flags.append({"severity": "medium", "code": "over_agreed",
                      "text": f"Loss {loss_bp / 100:.2f}% is above the agreed {agreed / 100:.2f}%."})
    if b.get("n", 0) >= 3 and loss_bp > b["p90_bp"]:
        flags.append({"severity": "high", "code": "above_p90",
                      "text": f"Loss {loss_bp / 100:.2f}% is above 90% of past {label} jobs "
                              f"(median {b['median_bp'] / 100:.2f}%, p90 {b['p90_bp'] / 100:.2f}%, n={b['n']}). "
                              "Ask for scrap/sweepings to go to the refiner before settling."})
    return flags


def review_agreement(job: dict, bench: dict) -> dict | None:
    b = bench.get(job["design_category"], {})
    if b.get("n", 0) >= 3 and b["median_bp"] and job["agreed_wastage_bp"] < 0.7 * b["median_bp"]:
        label = config.category_label(job["design_category"])
        return {"severity": "medium", "code": "unfair_agreement",
                "text": f"Agreed wastage {job['agreed_wastage_bp'] / 100:.2f}% for {label} is well below what this "
                        f"design actually loses in your shop (median {b['median_bp'] / 100:.2f}% over {b['n']} jobs). "
                        "The karigar will likely end up paying for normal process loss."}
    return None
