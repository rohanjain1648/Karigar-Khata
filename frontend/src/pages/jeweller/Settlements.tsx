import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { day, g, pct, rupees } from "../../fmt";
import { Empty, Sev, useApi } from "../../ui";
import { PayModal } from "./Dashboard";
import { useRefresh } from "./Layout";

export default function Settlements() {
  const { tick, bump } = useRefresh();
  const { data: dues, reload: r1 } = useApi<any[]>("/api/payments/dues");
  const { data: list, reload: r2 } = useApi<any[]>("/api/settlements");
  const [paying, setPaying] = useState<any>(null);
  useEffect(() => { r1(); r2(); }, [tick, r1, r2]);

  return (
    <div className="space-y-6 max-w-5xl">
      <h1 className="font-display text-3xl">Settlements & payments</h1>
      <section>
        <h2 className="font-display text-xl mb-2">Waiting to be paid</h2>
        <div className="card divide-y divide-line">
          {dues?.length === 0 && <Empty>No karigar is waiting for money.</Empty>}
          {dues?.map((d) => (
            <div key={d.settlement_id} className="flex items-center gap-3 p-3">
              <Sev level={d.status === "overdue" ? "high" : d.status === "due" ? "medium" : "low"}>{d.days_waiting} days</Sev>
              <div className="flex-1">
                <div className="text-sm">{d.karigar_name}</div>
                <div className="text-xs text-muted">{d.job_code} · approved {day(d.approved_at)}</div>
              </div>
              <div className="num text-lg">{rupees(d.due_paise)}</div>
              <button className="btn btn-gold" onClick={() => setPaying(d)}>Pay</button>
            </div>
          ))}
        </div>
      </section>
      <section>
        <h2 className="font-display text-xl mb-2">All settlements</h2>
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs text-muted text-left"><tr className="border-b border-line">
              <th className="p-3">#</th><th>Job</th><th>Karigar</th><th className="text-right">Loss</th><th className="text-right">Agreed</th>
              <th className="text-right">Gold net</th><th className="text-right">Making</th><th className="pl-4">Status</th>
            </tr></thead>
            <tbody>
              {list?.map((s) => (
                <tr key={s.id} className="border-b border-line">
                  <td className="p-3 num text-xs text-muted">{s.id}</td>
                  <td><Link className="num text-gold" to={`/j/jobs/${s.job_id}`}>{s.job_code}</Link></td>
                  <td>{s.karigar_name}</td>
                  <td className={`num text-right ${s.figures.loss_bp > s.figures.agreed_bp ? "text-warn" : ""}`}>{pct(s.figures.loss_bp)}</td>
                  <td className="num text-right text-muted">{pct(s.figures.agreed_bp)}</td>
                  <td className="num text-right">{g(s.figures.gold_net_mg)}</td>
                  <td className="num text-right">{rupees(s.making_paise)}</td>
                  <td className="pl-4"><span className={`chip ${s.status === "approved" ? "text-ok" : s.status === "disputed" ? "text-bad" : "text-warn"}`}>{s.status}{s.status === "approved" && s.paid_paise >= s.making_paise ? " · paid" : ""}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      {paying && <PayModal due={paying} onClose={() => setPaying(null)} onPaid={() => { setPaying(null); bump(); }} />}
    </div>
  );
}
