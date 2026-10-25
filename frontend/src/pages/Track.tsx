import { useParams } from "react-router-dom";
import { day } from "../fmt";
import { Logo, useApi } from "../ui";

const STAGES = [["received", "Order received"], ["in_making", "With the karigar"], ["ready", "Ready at shop"]] as const;

export default function Track() {
  const { code } = useParams();
  const { data, error } = useApi<any>(`/api/public/track/${code}`);
  const idx = data ? STAGES.findIndex(([k]) => k === data.stage) : -1;
  return (
    <div className="min-h-full flex justify-center p-4 py-12">
      <div className="card p-6 w-full max-w-md">
        <div className="flex items-center gap-2 mb-6"><Logo /><span className="font-display">{data?.shop ?? "Karigar Khata"}</span></div>
        {error && <div className="text-bad">Order not found.</div>}
        {data && (
          <>
            <div className="label num">{data.code}</div>
            <h1 className="font-display text-2xl">{data.item_type}</h1>
            <div className="text-sm text-muted">For {data.customer_name}{data.occasion ? ` · ${data.occasion} on ${day(data.occasion_date)}` : ""}</div>
            <ol className="mt-6 space-y-4">
              {STAGES.map(([k, label], i) => (
                <li key={k} className="flex items-center gap-3">
                  <span className={`w-6 h-6 rounded-full grid place-items-center text-xs ${i <= idx ? "bg-gold text-ink" : "bg-ink-3 text-muted"}`}>{i < idx ? "✓" : i + 1}</span>
                  <span className={i <= idx ? "" : "text-muted"}>{label}</span>
                  {k === "in_making" && i === idx && <span className="num text-xs text-muted ml-auto">{data.progress_pct}%</span>}
                </li>
              ))}
            </ol>
            <div className={`mt-6 text-sm ${data.on_track ? "text-ok" : "text-warn"}`}>
              {data.on_track ? "On track for your date." : "The shop is working to keep your date and will contact you."}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
