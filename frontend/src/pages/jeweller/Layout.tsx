import { createContext, useContext, useState } from "react";
import { Navigate, NavLink, Outlet, useNavigate } from "react-router-dom";
import { api, getToken, setToken } from "../../api";
import { Logo, SourceBadge } from "../../ui";

const Refresh = createContext<{ tick: number; bump: () => void }>({ tick: 0, bump: () => {} });
export const useRefresh = () => useContext(Refresh);

const NAV = [
  ["/j", "Today", true],
  ["/j/issue", "Issue gold"],
  ["/j/jobs", "Jobs"],
  ["/j/karigars", "Karigars"],
  ["/j/settlements", "Settlements & pay"],
  ["/j/compliance", "Challans / ITC-04"],
  ["/j/ledger", "Ledger proof"],
] as const;

export default function JewellerLayout() {
  const nav = useNavigate();
  const [tick, setTick] = useState(0);
  const [running, setRunning] = useState(false);
  const [last, setLast] = useState<string | null>(null);
  const [askOpen, setAskOpen] = useState(false);
  if (!getToken("jeweller")) return <Navigate to="/" />;

  async function runAgents() {
    setRunning(true);
    try {
      const r = await api("/api/agents/run", { method: "POST" });
      const n = Object.values(r.created as Record<string, number>).reduce((a, b) => a + b, 0);
      setLast(n ? `${n} new action${n > 1 ? "s" : ""}` : "nothing new");
      setTick((t) => t + 1);
    } finally {
      setRunning(false);
    }
  }

  return (
    <Refresh.Provider value={{ tick, bump: () => setTick((t) => t + 1) }}>
      <div className="min-h-full flex flex-col md:flex-row">
        <aside className="md:w-56 md:min-h-full border-b md:border-b-0 md:border-r border-line p-4 flex md:flex-col gap-1 overflow-x-auto">
          <div className="flex items-center gap-2 mb-0 md:mb-6 mr-4 md:mr-0 shrink-0">
            <Logo />
            <div className="leading-tight">
              <div className="font-display">Karigar Khata</div>
              <div className="text-[10px] text-muted">Shree Lakshmi Jewellers</div>
            </div>
          </div>
          {NAV.map(([to, label, end]) => (
            <NavLink key={to} to={to} end={!!end}
              className={({ isActive }) => `px-3 py-2 rounded-lg text-sm whitespace-nowrap ${isActive ? "bg-ink-3 text-gold-2" : "text-muted hover:text-paper"}`}>
              {label}
            </NavLink>
          ))}
          <div className="md:mt-auto flex md:flex-col gap-1 shrink-0">
            <a href="/k" target="_blank" className="px-3 py-2 text-sm text-muted hover:text-paper whitespace-nowrap">Karigar view ↗</a>
            <button className="px-3 py-2 text-sm text-muted hover:text-paper text-left" onClick={() => { setToken("jeweller", null); nav("/"); }}>Log out</button>
          </div>
        </aside>
        <main className="flex-1 min-w-0">
          <div className="flex items-center gap-2 px-4 md:px-8 py-3 border-b border-line sticky top-0 bg-ink/85 backdrop-blur z-20">
            <button className="btn btn-gold" disabled={running} onClick={runAgents}>
              {running ? "Agents working…" : "▶ Run agents"}
            </button>
            {last && <span className="text-xs text-muted">{last}</span>}
            <button className="btn btn-ghost ml-auto" onClick={() => setAskOpen(true)}>Ask Khata</button>
          </div>
          <div className="px-4 md:px-8 py-6">
            <Outlet />
          </div>
        </main>
      </div>
      {askOpen && <AskDrawer onClose={() => setAskOpen(false)} />}
    </Refresh.Provider>
  );
}

function AskDrawer({ onClose }: { onClose: () => void }) {
  const [q, setQ] = useState("");
  const [log, setLog] = useState<{ q: string; a: string; source: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const suggestions = ["Which jobs will miss a wedding date?", "Kis karigar ke paas kitna sona hai?", "Who is still waiting for payment?"];

  async function ask(text: string) {
    if (!text.trim()) return;
    setBusy(true);
    try {
      const r = await api("/api/ask", { body: { text } });
      setLog((l) => [...l, { q: text, a: r.answer, source: r.source }]);
      setQ("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/50" onClick={onClose}>
      <div className="w-full max-w-md h-full bg-ink-2 border-l border-line p-5 flex flex-col fade-in" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center mb-4">
          <h3 className="font-display text-lg">Ask Khata</h3>
          <button className="ml-auto text-muted" onClick={onClose}>✕</button>
        </div>
        <div className="flex-1 overflow-y-auto space-y-4">
          {log.length === 0 && (
            <div className="space-y-2">
              {suggestions.map((s) => (
                <button key={s} className="btn btn-ghost w-full justify-start text-left" onClick={() => ask(s)}>{s}</button>
              ))}
            </div>
          )}
          {log.map((m, i) => (
            <div key={i} className="fade-in">
              <div className="text-sm text-gold-2 mb-1">{m.q}</div>
              <div className="card p-3 text-sm whitespace-pre-wrap">{m.a}</div>
              <div className="mt-1"><SourceBadge source={m.source} /></div>
            </div>
          ))}
        </div>
        <form className="flex gap-2 mt-4" onSubmit={(e) => { e.preventDefault(); ask(q); }}>
          <input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask in Hindi or English…" />
          <button className="btn btn-gold" disabled={busy}>{busy ? "…" : "Ask"}</button>
        </form>
      </div>
    </div>
  );
}
