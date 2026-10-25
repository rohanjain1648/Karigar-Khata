import { useState } from "react";
import { getToken } from "../../api";
import { g } from "../../fmt";
import { Sev, useApi } from "../../ui";

export default function Compliance() {
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const qs = new URLSearchParams({ ...(start && { start }), ...(end && { end }) }).toString();
  const { data } = useApi<any>(`/api/compliance/register?${qs}`);

  async function downloadCsv() {
    const res = await fetch(`/api/compliance/register?${qs}&format=csv`, { headers: { Authorization: `Bearer ${getToken("jeweller")}` } });
    const url = URL.createObjectURL(await res.blob());
    const a = Object.assign(document.createElement("a"), { href: url, download: "job-work-register.csv" });
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="label">GST · CGST Section 143 / ITC-04</div>
        <h1 className="font-display text-3xl">Job-work challan register</h1>
        <p className="text-sm text-muted mt-1 max-w-2xl">Every issue to a karigar is a job-work challan. Gold not back within a year is treated as a supply on the day it left. This register is generated from the ledger for your CA — it is a working record, not a filing.</p>
      </div>
      {data?.alerts?.length > 0 && (
        <div className="space-y-2">
          {data.alerts.map((a: any) => (
            <div key={a.job_id} className="card p-3 flex items-center gap-3 border-bad">
              <Sev level={a.severity}>{a.days_left} days left</Sev>
              <div className="text-sm">Challan <span className="num">{a.challan_no}</span> with {a.karigar} has been open {a.age_days} days.</div>
            </div>
          ))}
        </div>
      )}
      <div className="flex gap-3 items-end flex-wrap">
        <div><label className="label">From</label><input type="date" className="input num" value={start} onChange={(e) => setStart(e.target.value)} /></div>
        <div><label className="label">To</label><input type="date" className="input num" value={end} onChange={(e) => setEnd(e.target.value)} /></div>
        <button className="btn btn-gold" onClick={downloadCsv}>Download CSV</button>
      </div>
      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-xs text-muted text-left"><tr className="border-b border-line">
            <th className="p-3">Challan</th><th>Issued</th><th>Karigar</th><th>Description</th><th className="text-right">Issued g</th>
            <th className="text-right">Fine g</th><th>Returned</th><th className="text-right">Back fine g</th>
          </tr></thead>
          <tbody>
            {data?.rows?.map((r: any) => (
              <tr key={r.challan_no} className="border-b border-line">
                <td className="p-3 num text-xs">{r.challan_no}</td>
                <td className="num text-xs">{r.issued_on}</td>
                <td>{r.karigar}</td>
                <td className="text-xs text-muted">{r.description}</td>
                <td className="num text-right">{g(r.issued_gross_mg)}</td>
                <td className="num text-right">{g(r.issued_fine_mg)}</td>
                <td className="num text-xs">{r.returned_on || <span className="text-warn">open</span>}</td>
                <td className="num text-right">{r.returned_fine_mg ? g(r.returned_fine_mg) : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
