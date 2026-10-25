"""Messages to karigars and customers (WhatsApp is simulated in-app; the outbox is real).

Transactional messages (issue, receipt, settlement, payment) are fixed templates so that the
numbers a karigar is asked to confirm are exactly the ledger's numbers. Softer messages (nudges,
customer updates) may be rewritten by the Lyzr messenger agent, and are kept only if every number
survives the rewrite.
"""
from .. import config, ledger
from .llm import lyzr, numbers_preserved


def g(mg: int) -> str:
    return f"{mg / 1000:.3f}"


def rupees(paise: int) -> str:
    return f"{paise / 100:,.0f}"


T = {
    "issue": {
        "hi": "नमस्ते {name} जी 🙏\n{shop} से सोना जारी हुआ:\nजॉब {code} · {item}\nवज़न: {gross} g ({karat})\nशुद्ध सोना: {fine} g\nडिलीवरी: {due}\nतय घटत: {wastage}%\nकृपया जाँचें — ✅ सही है / ❌ गलत है",
        "en": "Namaste {name} 🙏\nGold issued by {shop}:\nJob {code} · {item}\nWeight: {gross} g ({karat})\nFine gold: {fine} g\nDelivery: {due}\nAgreed wastage: {wastage}%\nPlease check — ✅ Correct / ❌ Wrong",
    },
    "receive": {
        "hi": "{name} जी, जॉब {code} का माल मिला:\nपीस: {piece} g · स्क्रैप: {scrap} g\nकृपया वज़न की पुष्टि करें — ✅ / ❌",
        "en": "{name}, received for job {code}:\nPiece: {piece} g · Scrap: {scrap} g\nPlease confirm the weights — ✅ / ❌",
    },
    "settlement": {
        "hi": "{name} जी, जॉब {code} का हिसाब तैयार है:\nजारी शुद्ध सोना: {issued} g\nवापस: {returned} g\nघटत: {loss} g ({loss_pct}%), तय: {agreed_pct}%\n{gold_line}\nमज़दूरी: ₹{making}\nकृपया मंज़ूर करें या आपत्ति दर्ज करें।",
        "en": "{name}, settlement for job {code} is ready:\nFine issued: {issued} g\nReturned: {returned} g\nLoss: {loss} g ({loss_pct}%), agreed: {agreed_pct}%\n{gold_line}\nMaking charge: ₹{making}\nPlease approve or raise an objection.",
    },
    "payment": {
        "hi": "{name} जी, ₹{amount} का भुगतान भेजा गया (UPI {ref})। मिलने पर ✅ दबाएँ।",
        "en": "{name}, ₹{amount} sent via UPI ({ref}). Tap ✅ once received.",
    },
    "nudge": {
        "hi": "{name} जी, जॉब {code} ({item}) की डिलीवरी {due} को है{occasion}। काम कितना हुआ? बस % लिख दें (जैसे 60%)।",
        "en": "{name}, job {code} ({item}) is due on {due}{occasion}. How far along is it? Just reply with a % (e.g. 60%).",
    },
    "reassign_ask": {
        "hi": "{name} जी, क्या आप {due} तक {item} (जॉब {code} का हिस्सा) बना सकते हैं? हाँ / ना",
        "en": "{name}, can you take part of job {code} ({item}) for delivery by {due}? Yes / No",
    },
    "customer_update": {
        "hi": "नमस्ते {customer} जी, {shop} से: आपका {item} (ऑर्डर {order}) {status}। अपेक्षित तारीख: {date}।",
        "en": "Hello {customer}, from {shop}: your {item} (order {order}) {status}. Expected date: {date}.",
    },
    "ack": {
        "hi": "धन्यवाद {name} जी, दर्ज कर लिया: {what}",
        "en": "Thanks {name}, noted: {what}",
    },
}


def render(key: str, lang: str, **kw) -> str:
    lang = lang if lang in ("hi", "en") else "en"
    kw.setdefault("shop", config.SHOP_NAME)
    return T[key][lang].format(**kw)


def send(conn, *, audience: str, text: str, karigar_id: int | None = None, to_name: str = "",
         lang: str = "hi", job_id: int | None = None, source: str = "template", direction: str = "out") -> int:
    cur = conn.execute(
        "INSERT INTO messages(karigar_id, audience, to_name, direction, lang, text, related_job_id, source, created_at)"
        " VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (karigar_id, audience, to_name, direction, lang, text, job_id, source, ledger.now_iso()),
    )
    return cur.lastrowid


def polish(text: str, lang: str, purpose: str, session: str) -> tuple[str, str]:
    """Ask the Lyzr messenger agent for a warmer rewrite; keep the template if any number moved."""
    if not lyzr.enabled("messenger"):
        return text, "template"
    brief = (
        "ROLE: You write short WhatsApp messages from a small-town jeweller to the artisan goldsmiths "
        "(karigars) and customers he works with. Be respectful and warm, plain words, at most 3 short lines. "
        f"Write in {'Hindi (Devanagari)' if lang == 'hi' else 'simple English'}. "
        "Copy every number, date, weight and code EXACTLY as given. Do not add facts. "
        f"Purpose: {purpose}.\nDraft:\n{text}\n\nReply with the message text only."
    )
    out = lyzr.chat("messenger", brief, session)
    if out and numbers_preserved(text, out):
        return out.strip(), "lyzr"
    return text, "template"


def karigar(conn, karigar_id: int) -> dict:
    return dict(conn.execute("SELECT * FROM karigars WHERE id = ?", (karigar_id,)).fetchone())


def issue_message(conn, job: dict) -> int:
    k = karigar(conn, job["karigar_id"])
    lang = k["language"]
    text = render("issue", lang, name=k["name"], code=job["code"],
                  item=job["item_type"] or config.category_label(job["design_category"], lang),
                  gross=g(job["issued_gross_mg"]), karat=job["karat"], fine=g(job["issued_fine_mg"]),
                  due=job["due_date"] or "-", wastage=f"{job['agreed_wastage_bp'] / 100:.2f}")
    return send(conn, audience="karigar", karigar_id=k["id"], to_name=k["name"], lang=lang, text=text, job_id=job["id"])


def receive_message(conn, job: dict, piece_mg: int, scrap_mg: int) -> int:
    k = karigar(conn, job["karigar_id"])
    text = render("receive", k["language"], name=k["name"], code=job["code"], piece=g(piece_mg), scrap=g(scrap_mg))
    return send(conn, audience="karigar", karigar_id=k["id"], to_name=k["name"], lang=k["language"], text=text, job_id=job["id"])


def settlement_text(k: dict, job: dict, f: dict) -> str:
    lang = k["language"]
    net = f["gold_net_mg"]
    if lang == "hi":
        gold_line = (f"आपकी बचत: {g(-net)} g शुद्ध सोना (आपके खाते में)" if net < 0 else
                     f"तय घटत से ज़्यादा: {g(net)} g शुद्ध सोना बाकी" if net > 0 else "सोने का हिसाब बराबर")
    else:
        gold_line = (f"Your saving: {g(-net)} g fine gold (credited to you)" if net < 0 else
                     f"Over agreed wastage: {g(net)} g fine gold outstanding" if net > 0 else "Gold account is square")
    return render("settlement", lang, name=k["name"], code=job["code"], issued=g(f["issued_fine_mg"]),
                  returned=g(f["returned_fine_mg"]), loss=g(f["loss_fine_mg"]), loss_pct=f"{f['loss_bp'] / 100:.2f}",
                  agreed_pct=f"{f['agreed_bp'] / 100:.2f}", gold_line=gold_line, making=rupees(f["making_paise"]))


def settlement_message(conn, job: dict, figures: dict) -> int:
    k = karigar(conn, job["karigar_id"])
    return send(conn, audience="karigar", karigar_id=k["id"], to_name=k["name"], lang=k["language"],
                text=settlement_text(k, job, figures), job_id=job["id"])


def payment_message(conn, karigar_id: int, amount_paise: int, ref: str, job_id: int | None) -> int:
    k = karigar(conn, karigar_id)
    text = render("payment", k["language"], name=k["name"], amount=rupees(amount_paise), ref=ref)
    return send(conn, audience="karigar", karigar_id=k["id"], to_name=k["name"], lang=k["language"], text=text, job_id=job_id)
