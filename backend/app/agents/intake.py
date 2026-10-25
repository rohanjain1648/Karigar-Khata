"""Intake agent: turn a jeweller's voice/text note into a structured gold issue.

  "Ramesh ko 52.340g 22K, order 1045 haar, 12 Nov tak, ghatt 1.8%"

Lyzr extracts the fields when configured; a rule parser handles the same notes offline. Either
way the result is a *draft* the jeweller reviews, and any weight the model returns must appear
literally in the note: a model is never allowed to supply a gold weight.
"""
import difflib
import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from .. import config
from .llm import extract_json, lyzr

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}

WEIGHT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:g|gm|gms|gram|grams|ग्राम)(?![a-z])", re.I)
KARAT_RE = re.compile(r"\b(24|22|20|18|14)\s*(?:k|kt|ct|carat|karat|कैरेट)\b", re.I)
PPT_RE = re.compile(r"\b(999|995|916|875|833|750|585)\b")
WASTAGE_RE = re.compile(r"(?:wastage|ghatt?|ghat|घटत)\D{0,6}(\d+(?:\.\d+)?)\s*%|(\d+(?:\.\d+)?)\s*%\s*(?:wastage|ghatt?|ghat|घटत)", re.I)
MAKING_RE = re.compile(r"(?:making|majdoori|mazdoori|mazduri|मज़दूरी|मजदूरी)\D{0,6}(\d+)|₹\s*(\d+)\s*/\s*g", re.I)
ORDER_RE = re.compile(r"(?:order|ord|ऑर्डर|#)\s*#?\s*([A-Z]{0,3}-?\d{2,6})", re.I)
ISO_DATE_RE = re.compile(r"\b(20\d\d)-(\d\d)-(\d\d)\b")
DAY_MON_RE = re.compile(r"\b(\d{1,2})\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", re.I)
SLASH_DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b")
IN_DAYS_RE = re.compile(r"\b(\d{1,2})\s*(?:din|days?|दिन)\b", re.I)


def _to_mg(s: str) -> int | None:
    try:
        return int((Decimal(s) * 1000).to_integral_value())
    except InvalidOperation:
        return None


def _future(d: date, today: date) -> date:
    return d if d >= today else d.replace(year=d.year + 1)


def parse_due(text: str, today: date) -> str | None:
    t = text.lower()
    if m := ISO_DATE_RE.search(t):
        return date(int(m[1]), int(m[2]), int(m[3])).isoformat()
    if m := DAY_MON_RE.search(t):
        return _future(date(today.year, MONTHS[m[2][:3].lower()], int(m[1])), today).isoformat()
    if m := SLASH_DATE_RE.search(t):
        y = int(m[3]) if m[3] else today.year
        y = y + 2000 if y < 100 else y
        try:
            d = date(y, int(m[2]), int(m[1]))
        except ValueError:
            return None
        return (d if m[3] else _future(d, today)).isoformat()
    if m := IN_DAYS_RE.search(t):
        return (today + timedelta(days=int(m[1]))).isoformat()
    if re.search(r"\bparso\b|परसों", t):
        return (today + timedelta(days=2)).isoformat()
    if re.search(r"\bkal\b|tomorrow|कल", t):
        return (today + timedelta(days=1)).isoformat()
    return None


def match_karigar(name: str | None, karigars: list[dict]) -> dict | None:
    if not name:
        return None
    name = name.lower().strip()
    for k in karigars:
        full = k["name"].lower()
        if name == full or name in full.split():
            return k
    names = {k["name"].lower(): k for k in karigars}
    firsts = {k["name"].lower().split()[0]: k for k in karigars}
    hit = difflib.get_close_matches(name, list(names) + list(firsts), n=1, cutoff=0.75)
    return (names.get(hit[0]) or firsts.get(hit[0])) if hit else None


def find_karigar_in_text(text: str, karigars: list[dict]) -> dict | None:
    words = re.findall(r"[a-zA-Z]+", text.lower())
    for w in words:
        k = match_karigar(w, karigars)
        if k and len(w) >= 3:
            return k
    return None


def detect_category(text: str) -> str | None:
    t = f" {text.lower()} "
    for cat, words in config.CATEGORY_KEYWORDS.items():
        if any(w in t for w in words):
            return cat
    return None


def rules_parse(text: str, karigars: list[dict], orders: list[dict], today: date) -> dict:
    out: dict = {"source": "rules"}
    if m := WEIGHT_RE.search(text):
        out["gross_mg"] = _to_mg(m[1])
    if m := KARAT_RE.search(text):
        out["purity_ppt"] = config.PURITY_BY_KARAT[f"{m[1]}K"]
    elif m := PPT_RE.search(text):
        out["purity_ppt"] = int(m[1])
    if k := find_karigar_in_text(text, karigars):
        out["karigar_id"] = k["id"]
    if cat := detect_category(text):
        out["design_category"] = cat
    if m := WASTAGE_RE.search(text):
        out["agreed_wastage_bp"] = int(Decimal(m[1] or m[2]) * 100)
    if m := MAKING_RE.search(text):
        out["making_paise_per_g"] = int(m[1] or m[2]) * 100
    if m := ORDER_RE.search(text):
        out["order_id"] = _match_order(m[1], orders)
    out["due_date"] = parse_due(text, today)
    return out


def _match_order(token: str, orders: list[dict]) -> int | None:
    token = token.upper().replace(" ", "")
    for o in orders:
        code = o["code"].upper()
        if code == token or code.endswith(token.lstrip("#")) or code.replace("-", "").endswith(token.replace("-", "")):
            return o["id"]
    return None


def numbers_in(text: str) -> set[Decimal]:
    return {Decimal(n) for n in re.findall(r"\d+(?:\.\d+)?", text)}


def lyzr_parse(text: str, karigars: list[dict], orders: list[dict], today: date) -> dict | None:
    if not lyzr.enabled("intake"):
        return None
    brief = (
        "ROLE: Intake agent for a jewellery shop's karigar job-work ledger. The jeweller writes or speaks "
        "a note in Hindi, Hinglish or English about issuing gold to an artisan (karigar). Extract fields.\n"
        f"Today is {today.isoformat()}. Known karigars: {', '.join(k['name'] for k in karigars)}. "
        f"Open order codes: {', '.join(o['code'] for o in orders) or 'none'}.\n"
        f"Design categories: {', '.join(config.CATEGORIES)}.\n"
        "Return ONLY a JSON object with keys: karigar_name, weight_g (copy the number exactly as written, "
        "never compute or guess), karat (24K/22K/20K/18K/14K or null), item_type (short label), "
        "design_category, order_code, due_date (YYYY-MM-DD), wastage_pct, making_rs_per_g. Use null for "
        "anything not stated.\n"
        f"NOTE: {text}"
    )
    data = extract_json(lyzr.chat("intake", brief, "intake"))
    if not isinstance(data, dict):
        return None
    out: dict = {"source": "lyzr", "warnings": []}
    if data.get("weight_g") is not None:
        try:
            w = Decimal(str(data["weight_g"]))
        except InvalidOperation:
            w = None
        if w is not None and w in numbers_in(text):
            out["gross_mg"] = int((w * 1000).to_integral_value())
        else:
            out["warnings"].append("Model returned a weight that is not in the note; ignored.")
    if (kt := (data.get("karat") or "").upper().replace(" ", "")) in config.PURITY_BY_KARAT:
        out["purity_ppt"] = config.PURITY_BY_KARAT[kt]
    if k := match_karigar(data.get("karigar_name"), karigars):
        out["karigar_id"] = k["id"]
    if data.get("design_category") in config.CATEGORIES:
        out["design_category"] = data["design_category"]
    if data.get("item_type"):
        out["item_type"] = str(data["item_type"])[:60]
    if data.get("order_code"):
        out["order_id"] = _match_order(str(data["order_code"]), orders)
    if data.get("due_date") and ISO_DATE_RE.fullmatch(str(data["due_date"])):
        out["due_date"] = data["due_date"]
    for key, field, scale in (("wastage_pct", "agreed_wastage_bp", 100), ("making_rs_per_g", "making_paise_per_g", 100)):
        try:
            if data.get(key) is not None:
                out[field] = int(Decimal(str(data[key])) * scale)
        except InvalidOperation:
            pass
    return out


def parse(conn, text: str, today: date | None = None) -> dict:
    today = today or date.today()
    karigars = [dict(r) for r in conn.execute("SELECT id, name, skills FROM karigars WHERE active = 1")]
    orders = [dict(r) for r in conn.execute("SELECT id, code, design_category, item_type FROM orders WHERE status = 'open'")]

    rules = rules_parse(text, karigars, orders, today)
    llm = lyzr_parse(text, karigars, orders, today)
    draft = dict(rules)
    warnings: list[str] = []
    if llm:
        warnings += llm.pop("warnings", [])
        # Rules win on the weight when both found one (it was read straight from the text);
        # the model fills gaps and resolves names, dates and categories.
        for key, val in llm.items():
            if val is not None and (key != "gross_mg" or "gross_mg" not in draft):
                draft[key] = val
        draft["source"] = "lyzr+rules"

    if draft.get("order_id") and not draft.get("design_category"):
        o = next((o for o in orders if o["id"] == draft["order_id"]), None)
        if o:
            draft["design_category"] = o["design_category"]
            draft.setdefault("item_type", o["item_type"])
    cat = draft.get("design_category") or "other"
    draft["design_category"] = cat
    draft.setdefault("item_type", config.category_label(cat))
    defaults = config.CATEGORIES[cat]
    if draft.get("agreed_wastage_bp") is None:
        draft["agreed_wastage_bp"] = defaults[2]
        draft["wastage_defaulted"] = True
    if draft.get("making_paise_per_g") is None:
        draft["making_paise_per_g"] = defaults[3]
        draft["making_defaulted"] = True
    draft.setdefault("purity_ppt", 916)

    missing = [f for f in ("karigar_id", "gross_mg", "due_date") if not draft.get(f)]
    if missing:
        warnings.append("Please fill: " + ", ".join(missing))
    draft["missing"] = missing
    draft["warnings"] = warnings
    draft["text"] = text
    return draft
