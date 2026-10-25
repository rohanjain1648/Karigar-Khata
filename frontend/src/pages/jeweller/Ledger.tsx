import { useState } from "react";
import { api } from "../../api";
import { useApi } from "../../ui";

export default function Ledger() {
  const { data, reload } = useApi<any>("/api/ledger/verify");
  const [busy, setBusy] = useState(false);
  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <div className="label">Proof · प्रमाण</div>
        <h1 className="font-display text-3xl">Is the khata untouched?</h1>
        <p className="text-sm text-muted mt-1">Every entry carries the SHA-256 hash of the one before it. Editing, deleting or inserting any past row — by anyone, including the shop — breaks every link after it. Confirmations and disputes are chained the same way, so who agreed to what, and when, can be replayed.</p>
      </div>
      {data && (
        <div className={`card p-6 ${data.ok ? "border-ok" : "border-bad"}`}>
          <div className={`font-display text-2xl ${data.ok ? "text-ok" : "text-bad"}`}>{data.ok ? "✓ Chain intact" : "✗ Chain broken"}</div>
          <div className="grid sm:grid-cols-2 gap-4 mt-4">
            {(["entries", "audit"] as const).map((t) => (
              <div key={t}>
                <div className="label">{t === "entries" ? "Ledger entries" : "Confirmations & disputes"}</div>
                <div className="num text-xl">{data[t].rows} rows</div>
                {!data[t].ok && <div className="text-bad text-sm">first broken at row #{data[t].first_broken_id}</div>}
                <div className="num text-[11px] text-muted break-all mt-1">head {data[t].head}</div>
              </div>
            ))}
          </div>
        </div>
      )}
      <div className="flex gap-2">
        <button className="btn btn-gold" disabled={busy} onClick={async () => { setBusy(true); await reload(); setBusy(false); }}>Re-verify now</button>
        <button className="btn btn-bad" onClick={async () => { if (window.confirm("Reset all demo data?")) { await api("/api/admin/reset", { method: "POST" }); location.href = "/j"; } }}>
          Reset demo data
        </button>
      </div>
      <div className="text-xs text-muted">Share the head hash with the karigar (e.g. on WhatsApp at month end). If anyone later shows a different history, the hashes won't match.</div>
    </div>
  );
}
