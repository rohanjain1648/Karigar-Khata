# Karigar Khata — साझा बही

**A shared, two-sided job-work ledger for jewellers and karigars, kept honest by AI agents.**
Tech4Bharat × GAVS Hackathon · Problem 2.2 — *Gold given to karigars for job-work is tracked on trust, and disputes follow.*

Gold goes out to a karigar by weight and comes back as jewellery. Today that is a notebook entry,
a verbal wastage figure, phone calls about deadlines, and a month-end argument. Karigar Khata replaces it with:

- **One ledger, two signatures.** Every issue, return, scrap, refiner credit, settlement and payment is
  weighed to the **milligram** and only counts once **both** the jeweller and the karigar confirm it.
  Either side can dispute any entry with their own figure.
- **Tamper-evident history.** Entries and every confirmation/dispute are SHA-256 hash-chained. Edit one
  past row and the chain breaks visibly (`/j/ledger`).
- **Agents that do the chasing.** Deadlines, wastage fairness, dispute mediation, payments and GST
  compliance are watched by agents that act, explain why, and ask before anything consequential.
- **No number ever comes from a model.** Weights, fine gold, wastage, money are integer arithmetic in code.
  LLMs (Lyzr) parse notes, write messages and explain — and are rejected if they alter a number.

## Brief → how we meet it

| Brief says | What we built |
|---|---|
| Accuracy has to hold at the level of weight | Integer mg, purity in ppt, banker's rounding; float never touches the ledger; weights typed as strings → mg without float |
| An audit trail both parties accept | Every entry needs both acks; disputes keep the original (superseded, struck through) and add a corrected entry the other side re-confirms; hash chain + verify |
| Fairness matters most to the artisan | Karigar's own phone view in Hindi; mediator tilts to his figure within scale tolerance; wastage agent flags agreements *below* what the design really loses; payment agent counts his waiting days |
| Settlements go to both parties for approval | Settlement = proposal → jeweller ✓ + karigar ✓ → only then posted; objection → mediation → fresh proposal |
| Each karigar has full access to his own account | `/api/me/*` is bound to the token's karigar id; he sees every entry, settlement, message — and nobody else's (tested) |

## The agents

| Agent | Watches | Does on its own | Asks the jeweller first |
|---|---|---|---|
| **Intake** | Jeweller's voice/typed note (Hindi/Hinglish/English); karigar's WhatsApp replies | Drafts the gold issue; records "haar 60% ho gaya" as progress; "taiyar hai" → piece ready | — (jeweller reviews every drafted field) |
| **Deadline** | Every open job vs due date *and the customer's occasion date*, using the karigar's own pace and current load | Nudges a karigar who has gone quiet | Split the job to a skilled, free karigar; message the wedding customer |
| **Wastage** | Shop's own settled history per design (median, p90) | Flags losses above p90, losses above agreed, and **unfair agreements** | — |
| **Mediator** | Disputed weights and settlement objections | Proposes resolution: accept karigar within scale noise, re-weigh together, refiner recovery, or settle at actual loss | Jeweller picks; karigar re-confirms |
| **Payments** | Days since both approved a settlement | — | Pay now (UPI link); karigar confirms receipt |
| **Compliance** | GST Section 143 job-work challans | Flags gold out > 300 days; builds the ITC-04 working register (CSV) | — |
| **Analyst ("Ask Khata")** | Live ledger snapshot | Answers the jeweller in Hindi or English | — |

Each agent runs on **Lyzr Agent Studio** when configured (intake extraction, message writing, mediation
explanation, Q&A) and falls back to deterministic rules otherwise, so the demo never breaks. The UI marks
which produced each output (`⚡ Lyzr` / `rules`).

## Run it

Requirements: Python 3.12 (+ `uv`), Node 20+.

```powershell
./run.ps1          # installs, seeds demo data, starts API :8000 and web :5173
```

or manually:

```bash
cd backend && uv venv .venv && uv pip install -r requirements.txt --python .venv/Scripts/python.exe
.venv/Scripts/python -m app.seed                       # wipes & rebuilds demo data
.venv/Scripts/python -m uvicorn app.main:app --port 8000
cd ../frontend && npm install && npx vite --host 127.0.0.1
```

Open **http://127.0.0.1:5173/demo** for the pitch split view (counter left, karigar phone right).
Jeweller PIN `1234`; karigars `1111` … `5555`. Customer tracking: `/track/SL-1045`.

### Connect Lyzr (credits from the hackathon)

1. In Lyzr Agent Studio create **one** agent (any GPT-4o-class model). System prompt:
   *"Follow the ROLE given in each message exactly. Output only what is asked, no preamble. Never change numbers."*
2. Copy `backend/.env.example` → `backend/.env`, set `LYZR_API_KEY` and `LYZR_AGENT_ID`.
3. Restart the API. The dashboard chip turns to **⚡ Lyzr agents live**.
   Optionally give each role its own agent via `LYZR_AGENT_INTAKE`, `…_MESSENGER`, `…_MEDIATOR`, `…_ANALYST`.

The client calls `POST https://agent-prod.studio.lyzr.ai/v3/inference/chat/` with
`{user_id, agent_id, session_id, message}` and header `x-api-key` (configurable via `LYZR_CHAT_URL`).

## 3-minute demo script

1. **Today at the counter** (`/demo`). ~137 g fine gold out with 5 karigars (+10 g still awaiting confirmation); the agent feed has already flagged six kinds of problem.
2. **Wedding at risk.** J-0047 Rani haar for the Sharma wedding: Suresh is 20% done after 5 days → Deadline agent predicts 13 Nov vs needed 3 Nov → proposes splitting with Prakash and drafts a Hindi update for the family. Approve.
3. **Weight dispute.** Abdul says the 31.500 g issue was 31.420 g on his scale. Mediator: gap > scale noise → re-weigh together. Record 31.460 → switch phone to Abdul → he taps ✅ → balance updates live; the old entry stays, struck through.
4. **Unfair wastage.** Same job: 1.20% agreed for filigree that really loses ~2.5% in this shop → flagged before the karigar pays for normal process loss.
5. **Wastage outlier + objection.** Ramesh's kada pair lost 2.80% vs 1.08% median. On his phone he objects ("jhadan refiner ko bheja hai"). Jeweller credits 0.600 g refiner recovery → Ramesh ✅ → re-proposed at 1.49% → he approves.
6. **Paid today.** Suresh has waited 20 days for ₹6,380 → Pay → UPI → he confirms receipt on his phone.
7. **Proof.** Challans/ITC-04 register CSV for the CA; Ledger proof shows the chain intact.

## What is real vs simulated

- Real: ledger, arithmetic, two-party confirmation, hash chain, all agents' logic, Lyzr calls (when keyed), voice input (browser speech API, `hi-IN`), photo evidence upload, CSV register.
- Simulated in the demo: WhatsApp delivery (messages are stored and shown in the karigar's in-app chat; plugging in WhatsApp Business API is a transport swap), UPI (a `upi://` deep link + reference capture, no payment gateway). Demo data is generated history, clearly not real shops.

## Following the money

- **Karigar working capital:** an approved settlement is a receivable both parties have signed → invoice discounting so the artisan is paid the same day; his verified work history → MUDRA / micro-loans.
- **Refiners:** sweepings recovery credited per karigar → refiners get a clean intake record.
- **Jewellers:** SaaS for ITC-04/Section-143 compliance and loss control; fewer disputes, on-time wedding deliveries.
- **Insurers:** gold-in-transit/at-workshop cover priced on actual, verified exposure.

## Code map

```
backend/app/
  ledger.py        two-sided hash-chained ledger, integer mg arithmetic, verify()
  jobs.py          issue → progress → receive → refiner credit (GST challan numbering)
  settlement.py    deterministic settlement maths + two-party approval + pay
  services.py      use-cases shared by API and seeder (ledger + messages + feed upkeep)
  agents/
    llm.py         Lyzr client, JSON extraction, number-preservation guard
    intake.py      note → issue draft (Lyzr + rules; weight must appear in the note)
    deadline.py    pace/load-based finish prediction, occasion-aware, reassignment candidates
    wastage.py     per-design benchmarks from shop history; outlier + unfair-agreement flags
    mediator.py    dispute options (tolerance-aware), Lyzr explanation
    payments.py    dues and waiting days
    compliance.py  Section 143 ageing, ITC-04 working register
    analyst.py     "Ask Khata" over a computed snapshot
    karigar_chat.py  understands karigar replies (progress / ready / message)
    autopilot.py   manager agent: sweeps, acts, queues approvals, self-resolves stale warnings
  main.py          FastAPI routes (jeweller, karigar-scoped /api/me, public tracking)
  seed.py          4 months of history replayed through the real code paths
frontend/src/pages/  jeweller dashboard & screens, karigar phone app, demo split view, tracking
```

Tests: `cd backend && .venv/Scripts/python -m pytest` (ledger maths, settlement, intake parsing, API scoping and flows).
