import { useState } from "react";
import { Link } from "react-router-dom";
import { day, g, karat } from "../../fmt";
import { useApi } from "../../ui";

const COLUMNS: [string, string[]][] = [
  ["With karigar", ["issued", "in_progress"]],
  ["Back, to settle", ["returned", "settlement_proposed", "settlement_disputed"]],
  ["Settled", ["settled"]],
];

export default function Jobs() {
  const { data } = useApi<any[]>("/api/jobs");
  const [q, setQ] = useState("");
  const jobs = (data ?? []).filter((j) => !q || `${j.code} ${j.item_type} ${j.karigar_name} ${j.customer_name ?? ""}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <div className="space-y-4">
      <div className="flex items-end gap-4 flex-wrap">
        <h1 className="font-display text-3xl">Jobs</h1>
        <input className="input max-w-xs ml-auto" placeholder="Search code, karigar, customer…" value={q} onChange={(e) => setQ(e.target.value)} />
        <Link to="/j/issue" className="btn btn-gold">+ Issue gold</Link>
      </div>
      <div className="grid lg:grid-cols-3 gap-4">
        {COLUMNS.map(([title, statuses]) => {
          const list = jobs.filter((j) => statuses.includes(j.status));
          return (
            <div key={title}>
              <div className="label mb-2">{title} · {list.length}</div>
              <div className="space-y-2 max-h-[75vh] overflow-y-auto pr-1">
                {list.map((j) => (
                  <Link key={j.id} to={`/j/jobs/${j.id}`} className="card p-3 block hover:border-gold">
                    <div className="flex items-center gap-2">
                      <span className="num text-xs text-gold">{j.code}</span>
                      <span className="text-sm truncate flex-1">{j.item_type}</span>
                      <StatusChip s={j.status} />
                    </div>
                    <div className="flex text-xs text-muted mt-1 gap-2">
                      <span>{j.karigar_name}</span>
                      <span className="num ml-auto">{g(j.issued_gross_mg)} g {karat(j.purity_ppt)}</span>
                    </div>
                    {j.status !== "settled" && (
                      <div className="flex text-xs text-muted mt-1 gap-2">
                        {j.customer_name && <span className="truncate">{j.customer_name} · {j.occasion}</span>}
                        <span className="num ml-auto">due {day(j.due_date)}</span>
                      </div>
                    )}
                    {["issued", "in_progress"].includes(j.status) && (
                      <div className="h-1 bg-ink-3 rounded mt-2"><div className="h-1 bg-gold rounded" style={{ width: `${j.progress_pct ?? 0}%` }} /></div>
                    )}
                  </Link>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function StatusChip({ s }: { s: string }) {
  const map: Record<string, [string, string]> = {
    issued: ["issued", "text-info"],
    in_progress: ["in progress", "text-info"],
    returned: ["returned", "text-warn"],
    settlement_proposed: ["awaiting approval", "text-warn"],
    settlement_disputed: ["objection", "text-bad"],
    settled: ["settled", "text-ok"],
  };
  const [label, cls] = map[s] ?? [s, "text-muted"];
  return <span className={`chip ${cls}`}>{label}</span>;
}
