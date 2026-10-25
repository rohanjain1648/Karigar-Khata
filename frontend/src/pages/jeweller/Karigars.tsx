import { Link } from "react-router-dom";
import { g, rupees } from "../../fmt";
import { useApi } from "../../ui";

export default function Karigars() {
  const { data } = useApi<any[]>("/api/karigars");
  return (
    <div className="space-y-4">
      <h1 className="font-display text-3xl">Karigars</h1>
      <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-4">
        {data?.map((k) => (
          <Link key={k.id} to={`/j/karigars/${k.id}`} className="card p-5 hover:border-gold block">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-ink-3 grid place-items-center font-display text-gold">{k.name[0]}</div>
              <div>
                <div className="font-medium">{k.name}</div>
                <div className="text-xs text-muted">{k.workshop}</div>
              </div>
            </div>
            <div className="flex flex-wrap gap-1 mt-3">{k.skills_labels.map((s: string) => <span key={s} className="chip text-muted">{s}</span>)}</div>
            <div className="grid grid-cols-3 gap-2 mt-4 text-center">
              <div><div className="label">Gold held</div><div className="num text-gold-2">{g(k.balance.fine_mg)}</div></div>
              <div><div className="label">Owed</div><div className="num">{rupees(k.balance.money_paise)}</div></div>
              <div><div className="label">Open</div><div className="num">{k.open_jobs}</div></div>
            </div>
            {(k.balance.pending_count > 0 || k.balance.disputed_count > 0) && (
              <div className="text-xs mt-3">
                {k.balance.pending_count > 0 && <span className="text-warn">{k.balance.pending_count} awaiting confirmation </span>}
                {k.balance.disputed_count > 0 && <span className="text-bad">· {k.balance.disputed_count} disputed</span>}
              </div>
            )}
          </Link>
        ))}
      </div>
    </div>
  );
}
