import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, upload } from "../../api";
import { CATEGORIES, g, gramsToMg, pct } from "../../fmt";
import { ErrorNote, SourceBadge, useApi } from "../../ui";

const PURITIES = [[916, "22K (916)"], [750, "18K (750)"], [999, "24K (999)"], [833, "20K (833)"], [585, "14K (585)"]] as const;

type Form = {
  karigar_id: string; order_id: string; design_category: string; item_type: string; purity_ppt: number;
  grams: string; wastage_pct: string; making_rs: string; due_date: string; wastage_policy: string; evidence: string | null;
};

const blank: Form = {
  karigar_id: "", order_id: "", design_category: "chain", item_type: "", purity_ppt: 916, grams: "",
  wastage_pct: "1.50", making_rs: "300", due_date: "", wastage_policy: "agreed", evidence: null,
};

export default function IssueGold() {
  const nav = useNavigate();
  const { data: karigars } = useApi<any[]>("/api/karigars");
  const { data: orders } = useApi<any[]>("/api/orders");
  const { data: bench } = useApi<any>("/api/wastage/benchmarks");
  const [note, setNote] = useState("Ramesh ko 18.450g 22K rope chain, 6 din, ghatt 1.5%");
  const [draft, setDraft] = useState<any>(null);
  const [f, setF] = useState<Form>(blank);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const rec = useRef<any>(null);
  const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

  const set = (k: keyof Form, v: any) => setF((x) => ({ ...x, [k]: v }));

  useEffect(() => {
    if (!f.design_category) return;
    const b = bench?.[f.design_category];
    if (b && !draft) set("wastage_pct", (b.default_bp / 100).toFixed(2));
  }, [f.design_category, bench]); // eslint-disable-line react-hooks/exhaustive-deps

  async function parse() {
    setBusy(true);
    setErr(null);
    try {
      const d = await api("/api/intake/parse", { body: { text: note } });
      setDraft(d);
      setF({
        karigar_id: d.karigar_id ? String(d.karigar_id) : "",
        order_id: d.order_id ? String(d.order_id) : "",
        design_category: d.design_category ?? "other",
        item_type: d.item_type ?? "",
        purity_ppt: d.purity_ppt ?? 916,
        grams: d.gross_mg ? (d.gross_mg / 1000).toFixed(3) : "",
        wastage_pct: (d.agreed_wastage_bp / 100).toFixed(2),
        making_rs: String(Math.round(d.making_paise_per_g / 100)),
        due_date: d.due_date ?? "",
        wastage_policy: "agreed",
        evidence: f.evidence,
      });
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  function listen() {
    if (!SR) return;
    if (listening) {
      rec.current?.stop();
      return;
    }
    const r = new SR();
    r.lang = "hi-IN";
    r.interimResults = false;
    r.onresult = (e: any) => setNote(e.results[0][0].transcript);
    r.onend = () => setListening(false);
    rec.current = r;
    setListening(true);
    r.start();
  }

  async function submit() {
    const gross = gramsToMg(f.grams);
    if (!f.karigar_id) return setErr("Choose a karigar");
    if (!gross) return setErr("Enter the weight in grams, up to 3 decimals (e.g. 18.450)");
    const wastageBp = Math.round(parseFloat(f.wastage_pct || "0") * 100);
    setBusy(true);
    setErr(null);
    try {
      const job = await api("/api/jobs", {
        body: {
          karigar_id: +f.karigar_id, order_id: f.order_id ? +f.order_id : null, design_category: f.design_category,
          item_type: f.item_type || CATEGORIES[f.design_category], purity_ppt: f.purity_ppt, gross_mg: gross,
          agreed_wastage_bp: wastageBp, making_paise_per_g: Math.round(parseFloat(f.making_rs || "0") * 100),
          due_date: f.due_date || null, wastage_policy: f.wastage_policy, evidence: f.evidence,
        },
      });
      nav(`/j/jobs/${job.id}`);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  const gross = gramsToMg(f.grams);
  const fine = gross ? Math.round((gross * f.purity_ppt) / 1000) : null;
  const b = bench?.[f.design_category];
  const wbp = Math.round(parseFloat(f.wastage_pct || "0") * 100);
  const unfair = b?.n >= 3 && b.median_bp && wbp < 0.7 * b.median_bp;
  const karigar = karigars?.find((k) => String(k.id) === f.karigar_id);
  const skilled = karigar && !(karigar.skills ?? "").split(",").includes(f.design_category);

  return (
    <div className="max-w-4xl space-y-6">
      <div>
        <div className="label">Gold out · सोना जारी करें</div>
        <h1 className="font-display text-3xl">Issue gold to a karigar</h1>
      </div>

      <div className="card p-5">
        <label className="label">Say it or type it — the intake agent drafts the entry</label>
        <div className="flex gap-2">
          <textarea className="input min-h-[64px]" value={note} onChange={(e) => setNote(e.target.value)} />
          {SR && (
            <button className={`btn ${listening ? "btn-gold" : "btn-ghost"} self-start`} onClick={listen} title="Speak in Hindi or English">
              {listening ? "● Listening" : "🎙"}
            </button>
          )}
        </div>
        <div className="flex items-center gap-2 mt-3">
          <button className="btn btn-gold" disabled={busy} onClick={parse}>Draft entry</button>
          {draft && <SourceBadge source={draft.source} />}
          {draft?.warnings?.map((w: string) => <span key={w} className="text-xs text-warn">{w}</span>)}
        </div>
        <div className="text-xs text-muted mt-2">The agent never supplies a weight: any weight it returns must appear in your note, and you confirm every field below.</div>
      </div>

      <ErrorNote error={err} />

      <div className="card p-5 grid sm:grid-cols-2 gap-4">
        <div>
          <label className="label">Karigar</label>
          <select className="input" value={f.karigar_id} onChange={(e) => set("karigar_id", e.target.value)}>
            <option value="">Choose…</option>
            {karigars?.map((k) => <option key={k.id} value={k.id}>{k.name} — {k.open_jobs} open</option>)}
          </select>
          {skilled && <div className="text-xs text-warn mt-1">{karigar.name} doesn't usually make {CATEGORIES[f.design_category]}.</div>}
        </div>
        <div>
          <label className="label">Customer order (optional)</label>
          <select className="input" value={f.order_id} onChange={(e) => set("order_id", e.target.value)}>
            <option value="">Stock / no order</option>
            {orders?.filter((o) => o.status === "open").map((o) => (
              <option key={o.id} value={o.id}>{o.code} · {o.customer_name} · {o.occasion} {o.occasion_date}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="label">Design</label>
          <select className="input" value={f.design_category} onChange={(e) => set("design_category", e.target.value)}>
            {Object.entries(CATEGORIES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </div>
        <div>
          <label className="label">Item description</label>
          <input className="input" value={f.item_type} onChange={(e) => set("item_type", e.target.value)} placeholder="e.g. Rope chain 20 inch" />
        </div>
        <div>
          <label className="label">Weight on scale (g)</label>
          <input className={`input num text-lg ${f.grams && !gross ? "border-bad" : ""}`} inputMode="decimal" value={f.grams}
            onChange={(e) => set("grams", e.target.value)} placeholder="0.000" />
        </div>
        <div>
          <label className="label">Purity</label>
          <select className="input" value={f.purity_ppt} onChange={(e) => set("purity_ppt", +e.target.value)}>
            {PURITIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <div className="text-xs text-muted mt-1">Fine gold: <span className="num text-gold-2">{fine ? `${g(fine)} g` : "—"}</span></div>
        </div>
        <div>
          <label className="label">Agreed wastage (%)</label>
          <input className="input num" inputMode="decimal" value={f.wastage_pct} onChange={(e) => set("wastage_pct", e.target.value)} />
          {b?.n ? (
            <div className={`text-xs mt-1 ${unfair ? "text-warn" : "text-muted"}`}>
              {unfair ? "⚠ Well below what this design really loses — " : ""}your shop: median {pct(b.median_bp)}, p90 {pct(b.p90_bp)} over {b.n} jobs
            </div>
          ) : null}
        </div>
        <div>
          <label className="label">Making charge (₹ / g)</label>
          <input className="input num" inputMode="numeric" value={f.making_rs} onChange={(e) => set("making_rs", e.target.value)} />
        </div>
        <div>
          <label className="label">Deliver by</label>
          <input className="input num" type="date" value={f.due_date} onChange={(e) => set("due_date", e.target.value)} />
        </div>
        <div>
          <label className="label">If he uses less than agreed</label>
          <select className="input" value={f.wastage_policy} onChange={(e) => set("wastage_policy", e.target.value)}>
            <option value="agreed">Saving stays with karigar (bachat)</option>
            <option value="actual_capped">Allow only actual loss</option>
          </select>
        </div>
        <div className="sm:col-span-2">
          <label className="label">Photo of scale display (evidence for both sides)</label>
          <input type="file" accept="image/*" capture="environment" className="text-sm"
            onChange={async (e) => { const file = e.target.files?.[0]; if (file) set("evidence", await upload(file)); }} />
          {f.evidence && <img src={f.evidence} alt="scale" className="mt-2 h-24 rounded-lg border border-line" />}
        </div>
        <div className="sm:col-span-2 flex items-center gap-3">
          <button className="btn btn-gold" disabled={busy} onClick={submit}>Issue & send for confirmation</button>
          <span className="text-xs text-muted">The karigar gets this on his phone and must tap ✅ before it counts in the agreed balance.</span>
        </div>
      </div>
    </div>
  );
}
