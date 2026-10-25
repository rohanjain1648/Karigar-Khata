import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../../api";
import { dateTime, day, g, gramsToMg, karat, KIND_LABEL, pct, rupees } from "../../fmt";
import { Ack, ErrorNote, Sev, SourceBadge, useApi } from "../../ui";
import { StatusChip } from "./Jobs";
import { PayModal } from "./Dashboard";
import { useRefresh } from "./Layout";

export default function JobDetail() {
  const { id } = useParams();
  const { tick, bump } = useRefresh();
  const { data: j, reload } = useApi<any>(`/api/jobs/${id}`);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { reload(); }, [tick, reload]);
  if (!j) return <div className="text-muted">Loading…</div>;

  const call = async (path: string, body?: unknown) => {
    setErr(null);
    try {
      await api(path, { method: "POST", body });
      bump();
    } catch (e: any) {
      setErr(e.message);
    }
  };
  const open = ["issued", "in_progress"].includes(j.status);
  const issueConfirmed = j.entries.some((e: any) => e.kind === "ISSUE" && e.state === "active" && e.karigar_ack === "confirmed");
  const current = j.settlements.find((s: any) => s.status !== "withdrawn");

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex items-start gap-4 flex-wrap">
        <div>
          <div className="label num">{j.code} · {j.challan_no}</div>
          <h1 className="font-display text-3xl">{j.item_type}</h1>
          <div className="text-sm text-muted mt-1">
            <Link className="text-gold-2 hover:underline" to={`/j/karigars/${j.karigar_id}`}>{j.karigar_name}</Link>
            {" · "}{j.category_label} · {karat(j.purity_ppt)} · wastage {pct(j.agreed_wastage_bp)} · making {rupees(j.making_paise_per_g)}/g
          </div>
          {j.customer_name && <div className="text-sm mt-1">For <b>{j.customer_name}</b> · {j.occasion} on <span className="num">{day(j.occasion_date)}</span> ({j.order_code})</div>}
        </div>
        <div className="ml-auto text-right">
          <StatusChip s={j.status} />
          <div className="num text-2xl text-gold-2 mt-2">{g(j.issued_gross_mg)} g</div>
          <div className="num text-xs text-muted">{g(j.issued_fine_mg)} g fine · due {day(j.due_date)}</div>
        </div>
      </div>

      <ErrorNote error={err} />

      {j.assessment && <Assessment a={j.assessment} />}

      <section>
        <h2 className="font-display text-xl mb-2">Ledger entries for this job</h2>
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-muted text-xs">
              <tr className="border-b border-line">
                <th className="p-3">When</th><th>Entry</th><th className="text-right">Gross g</th><th className="text-right">Fine g</th>
                <th className="text-right">Money</th><th className="pl-4">Both sides</th><th>Note</th>
              </tr>
            </thead>
            <tbody>
              {j.entries.map((e: any) => (
                <EntryRow key={e.id} e={e} onResolved={bump} setErr={setErr} />
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {open && (
        <ReceiveForm job={j} disabled={!issueConfirmed} onDone={bump} setErr={setErr} />
      )}

      {j.preview && (
        <SettlementPanel j={j} current={current} call={call} onDone={bump} />
      )}

      {j.progress?.length > 0 && (
        <section>
          <h2 className="font-display text-xl mb-2">Karigar's updates</h2>
          <div className="card divide-y divide-line">
            {j.progress.map((p: any) => (
              <div key={p.id} className="p-3 flex gap-3 text-sm">
                <span className="num text-gold-2 w-12">{p.pct}%</span>
                <span className="flex-1">{p.note}</span>
                <span className="text-xs text-muted">{dateTime(p.created_at)}</span>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function Assessment({ a }: { a: any }) {
  return (
    <div className={`card p-4 ${a.risk === "high" || a.risk === "late" ? "border-bad" : ""}`}>
      <div className="flex items-center gap-3 flex-wrap">
        <span className="text-xs text-muted">⏱ Deadline agent</span>
        <Sev level={a.risk}>{a.risk} risk</Sev>
        <span className="text-sm">Needed by <b className="num">{day(a.hard_date)}</b> · expected <b className="num">{day(a.expected_finish)}</b>
          {a.slack_days !== null && <> · slack <span className="num">{a.slack_days}</span> d</>}</span>
      </div>
      <div className="h-1.5 bg-ink-3 rounded mt-3"><div className="h-1.5 bg-gold rounded" style={{ width: `${a.progress_pct}%` }} /></div>
      <div className="text-xs text-muted mt-2">{a.progress_pct}% done · basis: {a.basis}{a.reasons.length ? ` · ${a.reasons.join("; ")}` : ""}</div>
    </div>
  );
}

function EntryRow({ e, onResolved, setErr }: { e: any; onResolved: () => void; setErr: (s: string | null) => void }) {
  const disputed = e.state === "active" && (e.karigar_ack === "disputed" || e.jeweller_ack === "disputed");
  const [m, setM] = useState<any>(null);
  const [grams, setGrams] = useState("");
  useEffect(() => {
    if (disputed) api(`/api/entries/${e.id}/mediate`).then(setM).catch(() => {});
  }, [disputed, e.id]);
  const superseded = e.state === "superseded";

  async function resolve(action: string) {
    const gross_mg = action === "reweigh" ? gramsToMg(grams) : undefined;
    if (action === "reweigh" && !gross_mg) return setErr("Enter the re-weighed figure in grams");
    try {
      await api(`/api/entries/${e.id}/resolve`, { body: { action, gross_mg } });
      onResolved();
    } catch (er: any) {
      setErr(er.message);
    }
  }

  return (
    <>
      <tr className={`border-b border-line ${superseded ? "opacity-40 line-through" : ""}`}>
        <td className="p-3 text-xs text-muted whitespace-nowrap">{dateTime(e.created_at)}</td>
        <td className="whitespace-nowrap">{KIND_LABEL[e.kind] ?? e.kind}</td>
        <td className="num text-right">{e.gross_mg ? g(e.gross_mg) : ""}</td>
        <td className={`num text-right ${e.fine_mg > 0 ? "text-gold-2" : e.fine_mg < 0 ? "text-paper" : "text-muted"}`}>{e.fine_mg ? (e.fine_mg > 0 ? "+" : "") + g(e.fine_mg) : ""}</td>
        <td className="num text-right">{e.amount_paise ? rupees(e.amount_paise) : ""}</td>
        <td className="pl-4 whitespace-nowrap space-x-1"><Ack who="J" state={e.jeweller_ack} /><Ack who="K" state={e.karigar_ack} /></td>
        <td className="text-xs text-muted pr-3">
          {e.note}{e.evidence && <> · <a className="text-gold-2" href={e.evidence} target="_blank">photo</a></>}
          <span className="num block opacity-60" title={e.hash}>#{e.id} · {e.hash.slice(0, 10)}…</span>
        </td>
      </tr>
      {disputed && (
        <tr className="border-b border-line bg-[#2a1712]">
          <td colSpan={7} className="p-4">
            <div className="flex items-center gap-2 mb-2"><span className="text-xs text-muted">🤝 Mediator agent</span>{m && <SourceBadge source={m.source} />}</div>
            <div className="text-sm"><b>Karigar's objection:</b> “{e.dispute_reason}”{e.claimed_gross_mg && <> — he weighed <span className="num">{g(e.claimed_gross_mg)} g</span></>}</div>
            {m && (
              <>
                <div className="text-sm text-muted mt-2">{m.explanation}</div>
                <div className="flex flex-wrap gap-2 mt-3 items-center">
                  {m.options.map((o: any) => o.action === "reweigh" ? (
                    <div key={o.action} className="flex gap-2 items-center">
                      <input className="input num w-28" placeholder="g" value={grams} onChange={(ev) => setGrams(ev.target.value)} />
                      <button className={`btn ${o.recommended ? "btn-gold" : "btn-ghost"}`} onClick={() => resolve("reweigh")}>{o.recommended ? "★ " : ""}Record re-weigh</button>
                    </div>
                  ) : (
                    <button key={o.action} className={`btn ${o.recommended ? "btn-gold" : "btn-ghost"}`} onClick={() => resolve(o.action)} title={o.why}>
                      {o.recommended ? "★ " : ""}{o.label}
                    </button>
                  ))}
                </div>
                <div className="text-xs text-muted mt-2">Either way, the original entry stays in the chain marked superseded, and the karigar confirms the new one.</div>
              </>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

function ReceiveForm({ job, disabled, onDone, setErr }: { job: any; disabled: boolean; onDone: () => void; setErr: (s: string | null) => void }) {
  const [piece, setPiece] = useState("");
  const [scrap, setScrap] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit() {
    const p = gramsToMg(piece);
    const s = scrap ? gramsToMg(scrap) : 0;
    if (!p || s === null) return setErr("Enter weights in grams, up to 3 decimals");
    setBusy(true);
    try {
      await api(`/api/jobs/${job.id}/receive`, { body: { piece_gross_mg: p, scrap_gross_mg: s } });
      onDone();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="card p-4">
      <h2 className="font-display text-xl mb-1">Receive piece back</h2>
      {disabled ? (
        <div className="text-sm text-warn">The karigar hasn't confirmed the issued weight yet. Settle that first — both sides must agree on what went out.</div>
      ) : (
        <div className="flex gap-3 flex-wrap items-end">
          <div><label className="label">Finished piece (g)</label><input className="input num w-36" inputMode="decimal" value={piece} onChange={(e) => setPiece(e.target.value)} /></div>
          <div><label className="label">Scrap / filings (g)</label><input className="input num w-36" inputMode="decimal" value={scrap} onChange={(e) => setScrap(e.target.value)} /></div>
          <button className="btn btn-gold" disabled={busy} onClick={submit}>Record & send to karigar</button>
        </div>
      )}
    </section>
  );
}

function SettlementPanel({ j, current, call, onDone }: { j: any; current: any; call: (p: string, b?: unknown) => Promise<void>; onDone: () => void }) {
  const f = current?.figures ?? j.preview;
  const [refiner, setRefiner] = useState("");
  const [med, setMed] = useState<any>(null);
  const [payOpen, setPayOpen] = useState(false);
  useEffect(() => {
    if (current?.status === "disputed") api(`/api/settlements/${current.id}/mediate`).then(setMed).catch(() => {});
  }, [current?.status, current?.id]);
  const b = j.benchmark;
  const rows: [string, number, string?][] = [
    ["Fine gold issued", f.issued_fine_mg],
    ["− in finished piece", f.piece_fine_mg],
    ["− in scrap returned", f.scrap_fine_mg],
    ...(f.refiner_fine_mg ? [["− recovered by refiner", f.refiner_fine_mg] as [string, number]] : []),
    ["= Actual loss", f.loss_fine_mg, pct(f.loss_bp)],
    ["Agreed allowance", f.allowance_fine_mg, pct(f.agreed_bp)],
    ["Wastage written off", f.wastage_credit_mg, f.policy === "agreed" ? "full allowance" : "actual, capped"],
  ];
  const unconfirmed = j.preview?.unconfirmed_entry_ids?.length;
  return (
    <section className="card p-5">
      <div className="flex items-center gap-3 flex-wrap mb-3">
        <h2 className="font-display text-xl">Settlement</h2>
        {current && <span className="chip text-muted">#{current.id} · {current.status}</span>}
        {current && <><span className={`chip ${current.jeweller_ok ? "text-ok" : "text-muted"}`}>Jeweller {current.jeweller_ok ? "✓" : "…"}</span>
          <span className={`chip ${current.karigar_ok ? "text-ok" : "text-muted"}`}>Karigar {current.karigar_ok ? "✓" : "…"}</span></>}
      </div>
      <div className="grid md:grid-cols-2 gap-6">
        <table className="text-sm w-full">
          <tbody>
            {rows.map(([label, mg, note]) => (
              <tr key={label} className={label.startsWith("=") ? "border-t border-line font-semibold" : ""}>
                <td className="py-1">{label}</td>
                <td className="num text-right">{g(mg)} g</td>
                <td className="text-xs text-muted pl-3">{note}</td>
              </tr>
            ))}
            <tr className="border-t border-line font-semibold">
              <td className="py-1">{f.gold_net_mg < 0 ? "Karigar's saving (gold credit)" : f.gold_net_mg > 0 ? "Shortfall on karigar" : "Gold balance"}</td>
              <td className={`num text-right ${f.gold_net_mg > 0 ? "text-bad" : "text-ok"}`}>{g(Math.abs(f.gold_net_mg))} g</td>
              <td />
            </tr>
            <tr><td className="py-1">Making charge</td><td className="num text-right">{rupees(f.making_paise)}</td><td className="text-xs text-muted pl-3">{rupees(f.making_paise_per_g)}/g × {g(f.piece_gross_mg)} g</td></tr>
          </tbody>
        </table>
        <div className="space-y-3">
          <div className="text-xs text-muted">⚖ Wastage agent</div>
          {b?.n ? (
            <BenchBar loss={f.loss_bp} agreed={f.agreed_bp} median={b.median_bp} p90={b.p90_bp} n={b.n} label={b.label} />
          ) : <div className="text-sm text-muted">Not enough history for this design yet.</div>}
          {j.flags.map((fl: any) => (
            <div key={fl.code} className="text-sm flex gap-2 items-start"><span className="shrink-0"><Sev level={fl.severity} /></span><span>{fl.text}</span></div>
          ))}
          {!j.flags.length && <div className="text-sm text-ok">Loss is within the normal range for this design.</div>}
        </div>
      </div>

      {current?.status === "disputed" && (
        <div className="mt-4 p-4 rounded-xl bg-[#2a1712] border border-[#6b2b22]">
          <div className="text-sm"><b>{j.karigar_name} objected:</b> “{current.karigar_comment}”</div>
          {med && (
            <div className="flex gap-2 flex-wrap mt-3">
              {med.options.map((o: any) => (
                <button key={o.action} className={`btn ${o.recommended ? "btn-gold" : "btn-ghost"}`} title={o.why}
                  onClick={() => call(`/api/settlements/${current.id}/resolve`, { action: o.action })}>
                  {o.recommended ? "★ " : ""}{o.label}
                </button>
              ))}
            </div>
          )}
          <div className="text-xs text-muted mt-2">Each option produces a fresh proposal that the karigar approves again.</div>
        </div>
      )}

      <div className="flex gap-2 flex-wrap mt-5 items-end">
        {j.status === "returned" && (
          <button className="btn btn-gold" disabled={!!unconfirmed} onClick={() => call(`/api/jobs/${j.id}/settlement`)}>
            Propose settlement to {j.karigar_name}
          </button>
        )}
        {unconfirmed ? <span className="text-xs text-warn">Waiting for the karigar to confirm the returned weights.</span> : null}
        {current?.status === "proposed" && !current.jeweller_ok && (
          <button className="btn btn-gold" onClick={() => call(`/api/settlements/${current.id}/approve`)}>Approve as jeweller</button>
        )}
        {current?.status === "proposed" && current.jeweller_ok && !current.karigar_ok && (
          <span className="text-sm text-muted">Sent to {j.karigar_name}'s phone — waiting for his approval.</span>
        )}
        {current?.status === "approved" && current.making_paise > current.paid_paise && (
          <button className="btn btn-gold" onClick={() => setPayOpen(true)}>Pay {rupees(current.making_paise - current.paid_paise)}</button>
        )}
        {current?.status === "approved" && current.making_paise <= current.paid_paise && <span className="chip text-ok">Paid {day(current.paid_at)}</span>}
        {["returned", "settlement_proposed", "settlement_disputed"].includes(j.status) && (
          <div className="flex gap-2 items-end ml-auto">
            <div><label className="label">Refiner recovered (fine g)</label><input className="input num w-32" value={refiner} onChange={(e) => setRefiner(e.target.value)} /></div>
            <button className="btn btn-ghost" onClick={async () => { const mg = gramsToMg(refiner); if (mg) { await call(`/api/jobs/${j.id}/refiner-credit`, { fine_mg: mg, refiner_ref: `RF-${Date.now().toString().slice(-5)}` }); setRefiner(""); } }}>
              Credit to karigar
            </button>
          </div>
        )}
      </div>
      {payOpen && current && (
        <PayModal due={{ settlement_id: current.id, karigar_name: j.karigar_name, job_code: j.code, due_paise: current.making_paise - current.paid_paise, upi_link: "upi://pay" }}
          onClose={() => setPayOpen(false)} onPaid={() => { setPayOpen(false); onDone(); }} />
      )}
    </section>
  );
}

function BenchBar({ loss, agreed, median, p90, n, label }: { loss: number; agreed: number; median: number; p90: number; n: number; label: string }) {
  const max = Math.max(loss, agreed, p90) * 1.25 || 1;
  const x = (v: number) => `${Math.max(0, Math.min(100, (v / max) * 100))}%`;
  return (
    <div>
      <div className="relative h-8 rounded-lg bg-ink-3 mt-5">
        <div className="absolute top-0 bottom-0 bg-ok/20 rounded-lg" style={{ left: 0, width: x(p90) }} />
        <Mark at={x(median)} label="median" cls="bg-muted" />
        <Mark at={x(agreed)} label="agreed" cls="bg-info" above />
        <Mark at={x(loss)} label="this job" cls={loss > p90 ? "bg-bad" : "bg-gold"} thick />
      </div>
      <div className="text-xs text-muted mt-5">{label} in your shop: median {pct(median)}, 90% of jobs under {pct(p90)} (n={n}). This job: <b className="text-paper">{pct(loss)}</b>.</div>
    </div>
  );
}

function Mark({ at, label, cls, thick, above }: { at: string; label: string; cls: string; thick?: boolean; above?: boolean }) {
  return (
    <div className="absolute top-0 bottom-0" style={{ left: at }}>
      <div className={`${cls} ${thick ? "w-1" : "w-0.5"} h-full`} />
      <div className={`absolute ${above ? "bottom-full mb-0.5" : "top-full mt-0.5"} -translate-x-1/2 text-[10px] text-muted whitespace-nowrap`}>{label}</div>
    </div>
  );
}
