import { useEffect, useRef, useState } from "react";
import { api, getToken, setToken } from "../../api";
import { dateTime, day, g, gramsToMg, KIND_LABEL, KIND_LABEL_HI, pct, rupees } from "../../fmt";
import { useApi } from "../../ui";

type Lang = "hi" | "en";
const S = {
  hi: {
    title: "मेरा खाता", tabs: ["खाता", "काम", "हिसाब", "चैट"], goldHeld: "आपके पास दुकान का शुद्ध सोना", owed: "दुकान से आपको मिलना है",
    goldSaving: "आपकी बचत — दुकान पर आपका सोना",
    confirm: "पुष्टि करें", correct: "✅ सही है", wrong: "❌ गलत है", why: "क्या गलत है?", myWeight: "मेरे कांटे पर वज़न (g)",
    send: "भेजें", nothing: "कुछ बाकी नहीं — सब पक्का है ✓", jobs: "चल रहे काम", due: "डिलीवरी", progress: "काम कितना हुआ",
    approve: "✅ मंज़ूर", object: "❌ आपत्ति", objection: "आपत्ति का कारण", waiting: "आपकी मंज़ूरी का इंतज़ार",
    history: "पूरा लेन-देन", type: "संदेश लिखें… (जैसे: हार 60% हो गया)", saving: "आपकी बचत", short: "कमी",
    disputed: "आपत्ति दर्ज", fineLabel: "शुद्ध", paidWait: "भुगतान मिला? ✅ दबाएँ", logout: "बाहर",
  },
  en: {
    title: "My khata", tabs: ["Account", "Work", "Settle", "Chat"], goldHeld: "Shop's fine gold with you", owed: "Shop owes you",
    goldSaving: "Your saving — your gold held by shop",
    confirm: "Please confirm", correct: "✅ Correct", wrong: "❌ Wrong", why: "What is wrong?", myWeight: "Weight on my scale (g)",
    send: "Send", nothing: "Nothing pending — all agreed ✓", jobs: "Open work", due: "Delivery", progress: "How much is done",
    approve: "✅ Approve", object: "❌ Object", objection: "Reason for objection", waiting: "Waiting for your approval",
    history: "All entries", type: "Type a message… (e.g. chain 60% done)", saving: "Your saving", short: "Shortfall",
    disputed: "Objection raised", fineLabel: "fine", paidWait: "Received the money? Tap ✅", logout: "Log out",
  },
};

export default function KarigarApp() {
  const embedded = new URLSearchParams(window.location.search).has("embedded");
  const [token, setTok] = useState(getToken("karigar"));
  if (!token) return <Phone embedded={embedded}><KarigarLogin onIn={() => setTok(getToken("karigar"))} /></Phone>;
  return <Phone embedded={embedded}><Inner onOut={() => { setToken("karigar", null); setTok(null); }} /></Phone>;
}

function Phone({ children, embedded }: { children: React.ReactNode; embedded: boolean }) {
  return (
    <div className={embedded ? "h-full" : "min-h-full flex justify-center sm:py-6"}>
      <div className={`phone w-full ${embedded ? "h-full" : "sm:max-w-[400px] sm:rounded-[28px] sm:shadow-2xl sm:border-8 sm:border-black min-h-[100dvh] sm:min-h-[780px]"} flex flex-col overflow-hidden`}>
        {children}
      </div>
    </div>
  );
}

function KarigarLogin({ onIn }: { onIn: () => void }) {
  const { data } = useApi<any[]>("/api/public/karigars", "karigar");
  const [err, setErr] = useState("");
  return (
    <div className="p-6 flex-1 flex flex-col justify-center gap-3">
      <div className="text-2xl font-bold text-wa">कारीगर खाता</div>
      <div className="text-sm text-gray-600 mb-2">अपना नाम चुनें (demo PIN: 1111…5555)</div>
      {data?.map((k) => (
        <button key={k.id} className="pcard pbtn text-left"
          onClick={async () => {
            try {
              const r = await api("/api/auth/login", { body: { role: "karigar", karigar_id: k.id, pin: String(k.id).repeat(4) }, role: "karigar" });
              setToken("karigar", r.token);
              onIn();
            } catch (e: any) {
              setErr(e.message);
            }
          }}>
          {k.name}<div className="text-xs font-normal text-gray-500">{k.workshop}</div>
        </button>
      ))}
      {err && <div className="text-red-600 text-sm">{err}</div>}
    </div>
  );
}

function Inner({ onOut }: { onOut: () => void }) {
  const { data: me, reload, error } = useApi<any>("/api/me", "karigar");
  const [tab, setTab] = useState(0);
  const [lang, setLang] = useState<Lang>("hi");
  useEffect(() => {
    const t = setInterval(reload, 4000);
    return () => clearInterval(t);
  }, [reload]);
  useEffect(() => {
    if (me?.language) setLang(me.language === "en" ? "en" : "hi");
  }, [me?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (error?.includes("session") || error?.includes("login")) onOut();
  }, [error, onOut]);
  if (!me) return <div className="p-6 text-gray-500">…</div>;
  const t = S[lang];
  const pending = me.entries.filter((e: any) => e.state === "active" && e.karigar_ack === "pending");
  const toApprove = me.settlements.filter((s: any) => s.status === "proposed" && !s.karigar_ok);

  return (
    <>
      <header className="bg-wa text-white px-4 pt-4 pb-3">
        <div className="flex items-center gap-2">
          <div className="w-9 h-9 rounded-full bg-white/20 grid place-items-center font-bold">{me.name[0]}</div>
          <div className="flex-1">
            <div className="font-semibold leading-tight">{me.name}</div>
            <div className="text-xs opacity-80">{t.title} · Shree Lakshmi Jewellers</div>
          </div>
          <button className="text-xs border border-white/40 rounded-full px-2 py-1" onClick={() => setLang(lang === "hi" ? "en" : "hi")}>{lang === "hi" ? "EN" : "हिं"}</button>
          <button className="text-xs opacity-80" onClick={onOut}>{t.logout}</button>
        </div>
        <nav className="flex mt-3 text-sm">
          {t.tabs.map((name, i) => {
            const badge = i === 0 ? pending.length : i === 2 ? toApprove.length : 0;
            return (
              <button key={name} onClick={() => setTab(i)} className={`flex-1 pb-1 border-b-2 ${tab === i ? "border-white font-semibold" : "border-transparent opacity-75"}`}>
                {name}{badge ? <span className="ml-1 bg-white text-wa rounded-full px-1.5 text-xs">{badge}</span> : null}
              </button>
            );
          })}
        </nav>
      </header>
      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {tab === 0 && <Account me={me} t={t} lang={lang} pending={pending} reload={reload} />}
        {tab === 1 && <Work me={me} t={t} reload={reload} />}
        {tab === 2 && <Settle me={me} t={t} lang={lang} reload={reload} />}
        {tab === 3 && <Chat me={me} t={t} reload={reload} />}
      </div>
    </>
  );
}

type T = (typeof S)["hi"];

function Account({ me, t, lang, pending, reload }: { me: any; t: T; lang: Lang; pending: any[]; reload: () => void }) {
  const b = me.balance;
  const kinds = lang === "hi" ? KIND_LABEL_HI : KIND_LABEL;
  return (
    <>
      <div className="pcard p-4 grid grid-cols-2 gap-3">
        <div>
          <div className="text-xs text-gray-500">{b.fine_mg < 0 ? t.goldSaving : t.goldHeld}</div>
          <div className={`num text-2xl font-bold ${b.fine_mg < 0 ? "text-green-700" : "text-amber-700"}`}>{g(Math.abs(b.fine_mg))} g</div>
        </div>
        <div>
          <div className="text-xs text-gray-500">{t.owed}</div>
          <div className="num text-2xl font-bold text-green-700">{rupees(b.money_paise)}</div>
        </div>
      </div>
      {pending.length === 0 && me.entries.every((e: any) => e.karigar_ack !== "disputed") && <div className="text-center text-sm text-green-700 py-2">{t.nothing}</div>}
      {pending.map((e: any) => <ConfirmCard key={e.id} e={e} t={t} kinds={kinds} reload={reload} />)}
      {me.entries.filter((e: any) => e.state === "active" && e.karigar_ack === "disputed").map((e: any) => (
        <div key={e.id} className="pcard p-3 border-l-4 border-red-500">
          <div className="text-xs text-red-600 font-semibold">{t.disputed} · {e.job_code}</div>
          <div className="text-sm">{kinds[e.kind]} <span className="num">{g(e.gross_mg)} g</span> → <span className="num">{g(e.claimed_gross_mg)} g</span></div>
          <div className="text-xs text-gray-500">“{e.dispute_reason}”</div>
        </div>
      ))}
      <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide pt-2">{t.history}</div>
      <div className="pcard divide-y">
        {me.entries.slice(0, 40).map((e: any) => (
          <div key={e.id} className={`p-3 flex items-center gap-2 text-sm ${e.state === "superseded" ? "opacity-40 line-through" : ""}`}>
            <div className="flex-1">
              <div>{kinds[e.kind]} <span className="text-xs text-gray-400 num">{e.job_code}</span></div>
              <div className="text-xs text-gray-400">{dateTime(e.created_at)}</div>
            </div>
            <div className="text-right num">
              {e.fine_mg ? <div className={e.fine_mg > 0 ? "text-amber-700" : ""}>{e.fine_mg > 0 ? "+" : ""}{g(e.fine_mg)} g</div> : null}
              {e.amount_paise ? <div className={e.amount_paise > 0 ? "text-green-700" : ""}>{rupees(e.amount_paise)}</div> : null}
            </div>
            <div className="w-5 text-center">{e.karigar_ack === "confirmed" ? "✓" : e.karigar_ack === "disputed" ? "✗" : "…"}</div>
          </div>
        ))}
      </div>
    </>
  );
}

function ConfirmCard({ e, t, kinds, reload }: { e: any; t: T; kinds: Record<string, string>; reload: () => void }) {
  const [wrong, setWrong] = useState(false);
  const [reason, setReason] = useState("");
  const [w, setW] = useState("");
  const [busy, setBusy] = useState(false);
  const isPayment = e.kind === "PAYMENT";
  async function go(path: string, body?: unknown) {
    setBusy(true);
    try {
      await api(path, { method: "POST", body, role: "karigar" });
      reload();
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="pcard p-4 border-l-4 border-amber-500 fade-in">
      <div className="text-xs text-amber-700 font-semibold">{t.confirm} · {e.job_code}</div>
      <div className="text-lg font-semibold mt-1">{kinds[e.kind]}</div>
      {e.gross_mg && <div className="num text-3xl font-bold mt-1">{g(e.gross_mg)} g</div>}
      {e.fine_mg !== 0 && <div className="num text-sm text-gray-500">{g(Math.abs(e.fine_mg))} g {t.fineLabel}{e.purity_ppt ? ` · ${e.purity_ppt}` : ""}</div>}
      {e.amount_paise !== 0 && <div className="num text-3xl font-bold mt-1 text-green-700">{rupees(Math.abs(e.amount_paise))}</div>}
      {isPayment && <div className="text-xs text-gray-500">{t.paidWait}</div>}
      <div className="text-xs text-gray-500 mt-1">{e.note}</div>
      {e.evidence && <img src={e.evidence} alt="" className="mt-2 h-24 rounded-lg" />}
      {!wrong ? (
        <div className="grid grid-cols-2 gap-2 mt-3">
          <button disabled={busy} className="pbtn bg-green-600 text-white" onClick={() => go(`/api/me/entries/${e.id}/confirm`)}>{t.correct}</button>
          <button disabled={busy} className="pbtn bg-red-50 text-red-700 border border-red-200" onClick={() => setWrong(true)}>{t.wrong}</button>
        </div>
      ) : (
        <div className="mt-3 space-y-2">
          <input className="w-full border rounded-lg p-3" placeholder={t.why} value={reason} onChange={(ev) => setReason(ev.target.value)} />
          {e.gross_mg && <input className="w-full border rounded-lg p-3 num" inputMode="decimal" placeholder={t.myWeight} value={w} onChange={(ev) => setW(ev.target.value)} />}
          <button disabled={busy || !reason} className="pbtn w-full bg-red-600 text-white"
            onClick={() => go(`/api/me/entries/${e.id}/dispute`, { reason, claimed_gross_mg: w ? gramsToMg(w) : null })}>{t.send}</button>
        </div>
      )}
    </div>
  );
}

function Work({ me, t, reload }: { me: any; t: T; reload: () => void }) {
  const open = me.jobs.filter((j: any) => ["issued", "in_progress"].includes(j.status));
  return (
    <>
      <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide">{t.jobs}</div>
      {open.map((j: any) => <WorkCard key={j.id} j={j} t={t} reload={reload} />)}
    </>
  );
}

function WorkCard({ j, t, reload }: { j: any; t: T; reload: () => void }) {
  const [p, setP] = useState(j.progress_pct ?? 0);
  return (
    <div className="pcard p-4">
      <div className="flex items-center">
        <div className="font-semibold flex-1">{j.item_type}</div>
        <div className="num text-xs text-gray-400">{j.code}</div>
      </div>
      <div className="text-sm text-gray-600 num">{g(j.issued_gross_mg)} g · {j.karat} · {t.due} {day(j.due_date)}</div>
      {j.customer_name && <div className="text-xs text-amber-700 mt-1">{j.customer_name} · {j.occasion} {day(j.occasion_date)}</div>}
      <div className="text-xs text-gray-500 mt-3">{t.progress}: <b className="num">{p}%</b></div>
      <input type="range" min={0} max={100} step={10} value={p} className="w-full accent-green-700" onChange={(e) => setP(+e.target.value)}
        onMouseUp={() => api(`/api/me/jobs/${j.id}/progress`, { body: { pct: p }, role: "karigar" }).then(reload)}
        onTouchEnd={() => api(`/api/me/jobs/${j.id}/progress`, { body: { pct: p }, role: "karigar" }).then(reload)} />
    </div>
  );
}

function Settle({ me, t, lang, reload }: { me: any; t: T; lang: Lang; reload: () => void }) {
  return (
    <>
      {me.settlements.map((s: any) => <SettleCard key={s.id} s={s} t={t} lang={lang} reload={reload} />)}
    </>
  );
}

function SettleCard({ s, t, lang, reload }: { s: any; t: T; lang: Lang; reload: () => void }) {
  const [objecting, setObjecting] = useState(false);
  const [comment, setComment] = useState("");
  const f = s.figures;
  const waiting = s.status === "proposed" && !s.karigar_ok;
  const go = async (path: string, body?: unknown) => { await api(path, { method: "POST", body, role: "karigar" }); reload(); };
  return (
    <div className={`pcard p-4 ${waiting ? "border-l-4 border-amber-500" : ""}`}>
      <div className="flex items-center">
        <div className="font-semibold flex-1 num">{s.job_code}</div>
        <span className={`text-xs px-2 py-0.5 rounded-full ${s.status === "approved" ? "bg-green-100 text-green-800" : s.status === "disputed" ? "bg-red-100 text-red-800" : "bg-amber-100 text-amber-800"}`}>
          {waiting ? t.waiting : s.status}
        </span>
      </div>
      <table className="w-full text-sm mt-2 numcol">
        <tbody>
          <tr><td>{lang === "hi" ? "जारी शुद्ध सोना" : "Fine issued"}</td><td className="text-right">{g(f.issued_fine_mg)} g</td></tr>
          <tr><td>{lang === "hi" ? "वापस (पीस+स्क्रैप)" : "Returned (piece+scrap)"}</td><td className="text-right">{g(f.returned_fine_mg)} g</td></tr>
          <tr><td>{lang === "hi" ? "घटत" : "Loss"}</td><td className="text-right">{g(f.loss_fine_mg)} g ({pct(f.loss_bp)})</td></tr>
          <tr><td>{lang === "hi" ? "तय घटत" : "Agreed"}</td><td className="text-right">{pct(f.agreed_bp)}</td></tr>
          <tr className="font-semibold border-t"><td>{f.gold_net_mg <= 0 ? t.saving : t.short}</td><td className={`text-right ${f.gold_net_mg > 0 ? "text-red-600" : "text-green-700"}`}>{g(Math.abs(f.gold_net_mg))} g</td></tr>
          <tr className="font-semibold"><td>{lang === "hi" ? "मज़दूरी" : "Making charge"}</td><td className="text-right text-green-700">{rupees(f.making_paise)}</td></tr>
          {s.status === "approved" && <tr><td>{lang === "hi" ? "मिला" : "Paid"}</td><td className="text-right">{rupees(s.paid_paise)}</td></tr>}
        </tbody>
      </table>
      {waiting && !objecting && (
        <div className="grid grid-cols-2 gap-2 mt-3">
          <button className="pbtn bg-green-600 text-white" onClick={() => go(`/api/me/settlements/${s.id}/approve`)}>{t.approve}</button>
          <button className="pbtn bg-red-50 text-red-700 border border-red-200" onClick={() => setObjecting(true)}>{t.object}</button>
        </div>
      )}
      {objecting && (
        <div className="mt-3 space-y-2">
          <input className="w-full border rounded-lg p-3" placeholder={t.objection} value={comment} onChange={(e) => setComment(e.target.value)} />
          <button className="pbtn w-full bg-red-600 text-white" disabled={!comment} onClick={() => go(`/api/me/settlements/${s.id}/dispute`, { comment })}>{t.send}</button>
        </div>
      )}
      {s.status === "disputed" && <div className="text-xs text-red-700 mt-2">“{s.karigar_comment}”</div>}
    </div>
  );
}

function Chat({ me, t, reload }: { me: any; t: T; reload: () => void }) {
  const [text, setText] = useState("");
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView(); }, [me.messages.length]);
  return (
    <div className="flex flex-col min-h-full">
      <div className="text-center text-[11px] text-gray-500 mb-2">WhatsApp (simulated in demo) · messages are real ledger notifications</div>
      <div className="space-y-2 flex-1">
        {me.messages.slice(-30).map((m: any) => (
          <div key={m.id} className={`max-w-[85%] rounded-xl px-3 py-2 text-sm whitespace-pre-wrap shadow-sm ${m.direction === "in" ? "ml-auto bg-wa-2" : "bg-white"}`}>
            {m.text}
            <div className="text-[10px] text-gray-400 text-right mt-1">{dateTime(m.created_at)}{m.source === "lyzr" ? " · ⚡" : ""}</div>
          </div>
        ))}
        <div ref={end} />
      </div>
      <form className="sticky bottom-0 flex gap-2 pt-3 bg-[#ece5dd]" onSubmit={async (e) => {
        e.preventDefault();
        if (!text.trim()) return;
        await api("/api/me/messages", { body: { text }, role: "karigar" });
        setText("");
        reload();
      }}>
        <input className="flex-1 rounded-full px-4 py-3 bg-white" value={text} onChange={(e) => setText(e.target.value)} placeholder={t.type} />
        <button className="w-12 h-12 rounded-full bg-wa text-white">➤</button>
      </form>
    </div>
  );
}
