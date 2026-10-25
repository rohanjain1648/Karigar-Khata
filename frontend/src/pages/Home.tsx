import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, setToken } from "../api";
import { ErrorNote, Logo, useApi } from "../ui";

export default function Home() {
  const nav = useNavigate();
  const [pin, setPin] = useState("1234");
  const [kid, setKid] = useState(1);
  const [kpin, setKpin] = useState("1111");
  const [order, setOrder] = useState("SL-1045");
  const [err, setErr] = useState<string | null>(null);
  const { data: karigars } = useApi<any[]>("/api/public/karigars");

  async function loginJeweller() {
    try {
      const r = await api("/api/auth/login", { body: { role: "jeweller", pin } });
      setToken("jeweller", r.token);
      nav("/j");
    } catch (e: any) {
      setErr(e.message);
    }
  }
  async function loginKarigar() {
    try {
      const r = await api("/api/auth/login", { body: { role: "karigar", karigar_id: kid, pin: kpin }, role: "karigar" });
      setToken("karigar", r.token);
      nav("/k");
    } catch (e: any) {
      setErr(e.message);
    }
  }

  return (
    <div className="min-h-full px-4 py-10 max-w-5xl mx-auto">
      <header className="flex items-center gap-3 mb-12">
        <Logo size={36} />
        <div>
          <div className="font-display text-xl">Karigar Khata</div>
          <div className="text-xs text-muted">साझा बही · one ledger both sides sign</div>
        </div>
        <Link to="/demo" className="btn btn-ghost ml-auto">Open demo split view →</Link>
      </header>

      <section className="mb-12 fade-in">
        <h1 className="font-display text-4xl sm:text-5xl leading-tight max-w-3xl">
          Gold goes out by weight. <span className="text-gold">It should come back by proof.</span>
        </h1>
        <p className="text-muted mt-4 max-w-2xl">
          Every issue, return and settlement is weighed to the milligram, confirmed by both the jeweller and the karigar,
          and sealed in a tamper-evident chain. AI agents chase deadlines, flag unfair wastage, mediate disputes and make
          sure artisans get paid — but no number ever comes from a model.
        </p>
      </section>

      <ErrorNote error={err} />
      <div className="grid md:grid-cols-3 gap-4">
        <div className="card p-5">
          <div className="label">Jeweller / counter</div>
          <div className="font-display text-lg mb-3">Shop dashboard</div>
          <input className="input num mb-3" type="password" value={pin} onChange={(e) => setPin(e.target.value)} placeholder="PIN" />
          <button className="btn btn-gold w-full justify-center" onClick={loginJeweller}>Enter shop</button>
          <div className="text-xs text-muted mt-2">Demo PIN 1234</div>
        </div>
        <div className="card p-5">
          <div className="label">Karigar · कारीगर</div>
          <div className="font-display text-lg mb-3">My own khata</div>
          <select className="input mb-2" value={kid} onChange={(e) => { const v = +e.target.value; setKid(v); setKpin(String(v).repeat(4)); }}>
            {karigars?.map((k) => <option key={k.id} value={k.id}>{k.name}</option>)}
          </select>
          <input className="input num mb-3" type="password" value={kpin} onChange={(e) => setKpin(e.target.value)} placeholder="PIN" />
          <button className="btn btn-gold w-full justify-center" onClick={loginKarigar}>Open my phone view</button>
          <div className="text-xs text-muted mt-2">Demo PINs 1111 … 5555</div>
        </div>
        <div className="card p-5">
          <div className="label">Customer</div>
          <div className="font-display text-lg mb-3">Track my order</div>
          <input className="input num mb-3" value={order} onChange={(e) => setOrder(e.target.value)} />
          <button className="btn btn-ghost w-full justify-center" onClick={() => nav(`/track/${order}`)}>Track</button>
          <div className="text-xs text-muted mt-2">Shows stage only — never the shop's ledger.</div>
        </div>
      </div>
    </div>
  );
}
