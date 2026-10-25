import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, getToken, setToken } from "../api";
import { Logo } from "../ui";

/** Pitch view: the jeweller's counter and a karigar's phone side by side, live. */
export default function Demo() {
  const [ready, setReady] = useState(false);
  const [kid, setKid] = useState(1);
  const [key, setKey] = useState(0);

  useEffect(() => {
    (async () => {
      if (!getToken("jeweller")) {
        const r = await api("/api/auth/login", { body: { role: "jeweller", pin: "1234" } });
        setToken("jeweller", r.token);
      }
      setReady(true);
    })();
  }, []);

  async function switchKarigar(id: number) {
    const r = await api("/api/auth/login", { body: { role: "karigar", karigar_id: id, pin: String(id).repeat(4) }, role: "karigar" });
    setToken("karigar", r.token);
    setKid(id);
    setKey((k) => k + 1);
  }
  useEffect(() => { if (ready) switchKarigar(kid); }, [ready]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!ready) return null;
  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center gap-3 px-4 py-2 border-b border-line">
        <Logo size={22} /><Link to="/" className="font-display whitespace-nowrap">Karigar Khata</Link>
        <span className="text-xs text-muted hidden lg:inline">· live split view — counter on the left, karigar's phone on the right</span>
        <span className="text-xs text-muted ml-auto">Phone:</span>
        <select className="input py-1" style={{ width: 180 }} value={kid} onChange={(e) => switchKarigar(+e.target.value)}>
          <option value={1}>Ramesh Soni</option><option value={2}>Abdul Karim</option><option value={3}>Suresh Verma</option>
          <option value={4}>Meena Devi</option><option value={5}>Prakash Ghosh</option>
        </select>
      </div>
      <div className="flex-1 flex min-h-0">
        <iframe title="jeweller" src="/j" className="flex-1 min-w-0 border-0" />
        <div className="w-[400px] shrink-0 border-l border-line hidden md:block bg-black p-3">
          <iframe key={key} title="karigar" src="/k?embedded=1" className="w-full h-full rounded-[22px] border-0 bg-white" />
        </div>
      </div>
    </div>
  );
}
