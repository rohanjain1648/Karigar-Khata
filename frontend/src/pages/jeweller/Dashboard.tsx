import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api";
import { day, g, rupees } from "../../fmt";
import { Empty, Modal, Sev, SourceBadge, Stat, useApi } from "../../ui";
import { useRefresh } from "./Layout";

const AGENT_ICON: Record<string, string> = {
  Deadline: "⏱", Wastage: "⚖", Mediator: "🤝", Payments: "₹", Compliance: "§", Intake: "✉",
};

export default function Dashboard() {
  const { tick, bump } = useRefresh();
  const { data, reload } = useApi<any>("/api/dashboard");
  useEffect(() => { reload(); }, [tick, reload]);
  if (!data) return <div className="text-muted">Loading…</div>;
  const k = data.kpis;

  return (
    <div className="space-y-6">
      <div className="flex items-end gap-4 flex-wrap">
        <div>
          <div className="label">{new Date(data.today).toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" })}</div>
          <h1 className="font-display text-3xl">Today at the counter</h1>
        </div>
        <LyzrStatus lyzr={data.lyzr} />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-3">
        <Stat label="Fine gold with karigars" value={`${g(k.fine_with_karigars_mg)} g`} sub={k.unconfirmed_fine_mg ? `+${g(k.unconfirmed_fine_mg)} g awaiting confirmation` : "all confirmed by both sides"} tone="text-gold-2" />
        <Stat label="Open jobs" value={k.open_jobs} sub={`${k.at_risk} at risk of missing date`} tone={k.at_risk ? "text-warn" : undefined} />
        <Stat label="Open disputes" value={k.disputes} sub="weight entries contested" tone={k.disputes ? "text-bad" : undefined} />
        <Stat label="Owed to karigars" value={rupees(k.unpaid_paise)} sub={k.oldest_unpaid_days ? `oldest waiting ${k.oldest_unpaid_days} days` : "nobody waiting"} tone={k.oldest_unpaid_days > 7 ? "text-bad" : undefined} />
        <Stat label="Agent actions" value={data.actions.length} sub="need a look" />
      </div>

      <div className="grid lg:grid-cols-5 gap-6">
        <section className="lg:col-span-3">
          <h2 className="font-display text-xl mb-3">Agent feed</h2>
          <div className="space-y-2">
            {data.actions.length === 0 && <Empty>All clear. Press “Run agents” to sweep again.</Empty>}
            {data.actions.map((a: any) => <ActionCard key={a.id} a={a} onDone={bump} />)}
          </div>
        </section>
        <section className="lg:col-span-2 space-y-6">
          <div>
            <h2 className="font-display text-xl mb-3">Deadline radar</h2>
            <div className="card divide-y divide-line">
              {data.risks.map((r: any) => (
                <Link key={r.job_id} to={`/j/jobs/${r.job_id}`} className="flex items-center gap-3 p-3 hover:bg-ink-3">
                  <Sev level={r.risk} />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm truncate">{r.code} · {r.item_type}</div>
                    <div className="text-xs text-muted truncate">{r.karigar_name}{r.occasion ? ` · ${r.customer_name}'s ${r.occasion}` : ""}</div>
                  </div>
                  <div className="text-right">
                    <div className="num text-xs">need {day(r.hard_date)}</div>
                    <div className="num text-xs text-muted">exp. {day(r.expected_finish)}</div>
                  </div>
                </Link>
              ))}
            </div>
          </div>
          <div>
            <h2 className="font-display text-xl mb-3">Karigar balances</h2>
            <div className="card divide-y divide-line">
              {data.karigars.map((kk: any) => (
                <Link key={kk.id} to={`/j/karigars/${kk.id}`} className="flex items-center gap-3 p-3 hover:bg-ink-3">
                  <div className="flex-1">
                    <div className="text-sm">{kk.name}</div>
                    <div className="text-xs text-muted">{kk.open_jobs} open job{kk.open_jobs === 1 ? "" : "s"}{kk.balance.disputed_count ? " · ⚠ dispute" : ""}</div>
                  </div>
                  <div className="text-right">
                    <div className="num text-sm text-gold-2">{g(kk.balance.fine_mg)} g</div>
                    <div className="num text-xs text-muted">{kk.balance.money_paise ? `owed ${rupees(kk.balance.money_paise)}` : "money square"}</div>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

function LyzrStatus({ lyzr }: { lyzr: any }) {
  const on = lyzr?.configured && Object.values(lyzr.agents ?? {}).some(Boolean);
  return (
    <div className={`chip ml-auto ${on ? "text-gold" : "text-muted"}`} title={lyzr?.last_error ?? ""}>
      {on ? `⚡ Lyzr agents live · ${lyzr.calls} calls` : "Lyzr not configured — rules fallback"}
    </div>
  );
}

function ActionCard({ a, onDone }: { a: any; onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const [payOpen, setPayOpen] = useState(false);
  const p = a.payload ?? {};
  async function act(kind: "approve" | "dismiss") {
    setBusy(true);
    try {
      await api(`/api/agents/actions/${a.id}/${kind}`, { method: "POST" });
      onDone();
    } finally {
      setBusy(false);
    }
  }
  const jobId = p.job_id ?? p.assessment?.job_id;
  return (
    <div className="card p-4 fade-in">
      <div className="flex items-start gap-3">
        <div className="w-8 h-8 rounded-lg bg-ink-3 grid place-items-center text-gold shrink-0" title={`${a.agent} agent`}>{AGENT_ICON[a.agent] ?? "•"}</div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs text-muted">{a.agent} agent</span>
            <Sev level={a.severity} />
            <SourceBadge source={a.source} />
            {a.requires_approval ? <span className="chip text-gold-2">needs your OK</span> : null}
          </div>
          <div className="font-medium mt-1">{a.title}</div>
          <div className="text-sm text-muted mt-1 whitespace-pre-wrap">{a.detail}</div>
          {p.message && <div className="mt-2 text-sm bg-ink rounded-lg p-3 border border-line whitespace-pre-wrap">{p.message}</div>}
          {p.mediation?.options && (
            <ul className="mt-2 text-sm space-y-1">
              {p.mediation.options.map((o: any) => (
                <li key={o.action} className={o.recommended ? "text-gold-2" : "text-muted"}>{o.recommended ? "★ " : "· "}{o.label} — {o.why}</li>
              ))}
            </ul>
          )}
          <div className="flex gap-2 mt-3 flex-wrap">
            {a.kind === "payment_due" && <button className="btn btn-gold" onClick={() => setPayOpen(true)}>Pay {rupees(p.due_paise)} now</button>}
            {(a.kind === "customer_update" || a.kind === "reassign_suggestion") && (
              <button className="btn btn-gold" disabled={busy} onClick={() => act("approve")}>Approve & send</button>
            )}
            {jobId && (
              <Link className={`btn ${a.kind === "entry_dispute" || a.kind === "settlement_dispute" ? "btn-gold" : "btn-ghost"}`} to={`/j/jobs/${jobId}`}>
                {a.kind === "entry_dispute" || a.kind === "settlement_dispute" ? "Resolve on job page" : "Open job"}
              </Link>
            )}
            <button className="btn btn-ghost" disabled={busy} onClick={() => act("dismiss")}>
              {a.requires_approval && a.kind !== "payment_due" ? "Not now" : "Dismiss"}
            </button>
          </div>
        </div>
      </div>
      {payOpen && <PayModal due={p} onClose={() => setPayOpen(false)} onPaid={() => { setPayOpen(false); onDone(); }} />}
    </div>
  );
}

export function PayModal({ due, onClose, onPaid }: { due: any; onClose: () => void; onPaid: () => void }) {
  const [ref, setRef] = useState(`UPI${Date.now().toString().slice(-6)}`);
  const [busy, setBusy] = useState(false);
  return (
    <Modal open title={`Pay ${due.karigar_name}`} onClose={onClose}>
      <div className="num text-3xl text-gold-2 mb-1">{rupees(due.due_paise)}</div>
      <div className="text-xs text-muted mb-4">Making charges for {due.job_code}, approved by both sides.</div>
      <a className="btn btn-ghost w-full justify-center mb-3" href={due.upi_link}>Open UPI app</a>
      <label className="label">UPI reference</label>
      <input className="input num mb-4" value={ref} onChange={(e) => setRef(e.target.value)} />
      <button className="btn btn-gold w-full justify-center" disabled={busy}
        onClick={async () => {
          setBusy(true);
          try {
            await api(`/api/settlements/${due.settlement_id}/pay`, { body: { amount_paise: due.due_paise, upi_ref: ref } });
            onPaid();
          } finally {
            setBusy(false);
          }
        }}>
        Record payment
      </button>
      <div className="text-xs text-muted mt-2">The karigar confirms receipt on his phone before it counts as paid in the agreed balance.</div>
    </Modal>
  );
}
