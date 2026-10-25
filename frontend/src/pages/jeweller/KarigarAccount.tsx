import { useEffect } from "react";
import { Link, useParams } from "react-router-dom";
import { dateTime, g, KIND_LABEL, rupees } from "../../fmt";
import { Ack, useApi } from "../../ui";
import { StatusChip } from "./Jobs";
import { useRefresh } from "./Layout";

export default function KarigarAccount() {
  const { id } = useParams();
  const { tick } = useRefresh();
  const { data: k, reload } = useApi<any>(`/api/karigars/${id}`);
  useEffect(() => { reload(); }, [tick, reload]);
  if (!k) return <div className="text-muted">Loading…</div>;
  const b = k.balance;
  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex items-end gap-4 flex-wrap">
        <div>
          <div className="label">Karigar account · exactly what he sees on his phone</div>
          <h1 className="font-display text-3xl">{k.name}</h1>
          <div className="text-sm text-muted">{k.workshop} · {k.phone}</div>
        </div>
        <div className="ml-auto grid grid-cols-3 gap-4 text-right">
          <div><div className="label">Gold held (agreed)</div><div className="num text-2xl text-gold-2">{g(b.fine_mg)} g</div></div>
          <div><div className="label">Shop owes him</div><div className="num text-2xl">{rupees(b.money_paise)}</div></div>
          <div><div className="label">Unconfirmed</div><div className="num text-2xl text-warn">{b.pending_count + b.disputed_count}</div></div>
        </div>
      </div>

      <section>
        <h2 className="font-display text-xl mb-2">Jobs</h2>
        <div className="card divide-y divide-line">
          {k.jobs.slice(0, 12).map((j: any) => (
            <Link key={j.id} to={`/j/jobs/${j.id}`} className="flex items-center gap-3 p-3 hover:bg-ink-3 text-sm">
              <span className="num text-gold w-16">{j.code}</span>
              <span className="flex-1 truncate">{j.item_type}</span>
              <span className="num text-muted">{g(j.issued_gross_mg)} g</span>
              <StatusChip s={j.status} />
            </Link>
          ))}
        </div>
      </section>

      <section>
        <h2 className="font-display text-xl mb-2">Full ledger</h2>
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted"><tr className="border-b border-line">
              <th className="p-3">When</th><th>Job</th><th>Entry</th><th className="text-right">Fine g</th><th className="text-right">Money</th><th className="pl-4">Acks</th>
            </tr></thead>
            <tbody>
              {k.entries.map((e: any) => (
                <tr key={e.id} className={`border-b border-line ${e.state === "superseded" ? "opacity-40 line-through" : ""}`}>
                  <td className="p-3 text-xs text-muted whitespace-nowrap">{dateTime(e.created_at)}</td>
                  <td className="num text-xs">{e.job_code}</td>
                  <td>{KIND_LABEL[e.kind]}</td>
                  <td className={`num text-right ${e.fine_mg > 0 ? "text-gold-2" : ""}`}>{e.fine_mg ? (e.fine_mg > 0 ? "+" : "") + g(e.fine_mg) : ""}</td>
                  <td className="num text-right">{e.amount_paise ? rupees(e.amount_paise) : ""}</td>
                  <td className="pl-4 space-x-1 whitespace-nowrap"><Ack who="J" state={e.jeweller_ack} /><Ack who="K" state={e.karigar_ack} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
