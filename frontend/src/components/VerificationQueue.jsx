import { severityMeta } from "../lib/severity";

function formatDate(value) {
  if (!value) return "Waiting for first inspection";
  return new Date(value).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

export default function VerificationQueue({ incidents = [], onOpen, requiredBuses = 2 }) {
  const rows = [...incidents]
    .filter((incident) => incident.status === "awaiting_verification")
    .sort((a, b) => new Date(a.verification_last_at || a.updated_at || a.observed_at) - new Date(b.verification_last_at || b.updated_at || b.observed_at));

  return (
    <section className="overflow-hidden rounded-2xl border border-violet-300/15 bg-gradient-to-br from-violet-300/[0.06] via-white/[0.02] to-transparent">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-white/[0.06] px-4 py-4 sm:px-5">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-violet-300/20 bg-violet-300/10 text-violet-200">
            <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" className="h-5 w-5" stroke="currentColor" strokeWidth="1.7"><path d="M4 12a8 8 0 1 0 2.34-5.66L4 8.5" strokeLinecap="round" strokeLinejoin="round"/><path d="M4 4v4.5h4.5M8.5 12l2.2 2.2 4.8-5" strokeLinecap="round" strokeLinejoin="round"/></svg>
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2"><h2 className="text-sm font-semibold text-white">Awaiting verification</h2><span className="rounded-full border border-violet-300/20 bg-violet-300/10 px-2 py-0.5 text-[10px] font-semibold text-violet-100">{rows.length} pending</span></div>
            <p className="mt-1 max-w-2xl text-xs leading-5 text-slate-400">A repair is not considered verified until independent buses report a clear surface at the same location. A new defect automatically reopens the incident.</p>
          </div>
        </div>
        <div className="rounded-lg border border-white/[0.07] bg-ink-950/70 px-3 py-2 text-right"><div className="font-mono text-lg font-semibold text-violet-100">{requiredBuses} buses</div><div className="text-[10px] uppercase tracking-wider text-slate-500">Independent checks required</div></div>
      </div>
      {rows.length === 0 ? (
        <div className="flex items-center gap-3 px-5 py-5">
          <span className="flex h-7 w-7 items-center justify-center rounded-full bg-emerald-400/10 text-emerald-200">✓</span>
          <div><div className="text-sm font-medium text-slate-200">No repairs waiting for a road check</div><div className="mt-1 text-xs text-slate-500">Completed repairs will appear here until two different buses verify the location.</div></div>
        </div>
      ) : (
        <div className="grid gap-2 p-3 sm:grid-cols-2 xl:grid-cols-3">
          {rows.map((incident) => {
            const severity = severityMeta(incident.severity);
            const required = Math.max(1, Number(incident.verification_required || requiredBuses || 2));
            const passes = Math.min(required, Number(incident.verification_passes || 0));
            const percentage = Math.min(100, Math.round((passes / required) * 100));
            return (
              <article key={`${incident.id}:${incident.verification_cycle || 0}`} className="rounded-xl border border-white/[0.07] bg-ink-950/60 p-3 transition hover:border-violet-300/25 hover:bg-ink-950/90">
                <div className="flex items-start justify-between gap-2"><span className={`rounded-full px-2 py-1 text-[10px] ring-1 ${severity.chip}`}>{severity.label}</span><span className="text-[10px] text-slate-500">Cycle {incident.verification_cycle || 1}</span></div>
                <div className="mt-3 text-sm font-semibold text-white">{incident.ward_name || incident.ward_code || "Unassigned demo zone"}</div>
                <div className="mt-1 text-xs text-slate-400">Route {incident.route_id} · {Number(incident.lat).toFixed(5)}, {Number(incident.lon).toFixed(5)}</div>
                <div className="mt-4 flex items-center justify-between gap-2"><span className="text-xs font-medium text-violet-100">{passes} of {required} independent bus checks</span><span className="font-mono text-[10px] text-slate-500">{percentage}%</span></div>
                <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/[0.07]"><div className="h-full rounded-full bg-gradient-to-r from-violet-400 to-emerald-300 transition-all" style={{ width: `${percentage}%` }} /></div>
                <div className="mt-3 flex items-center justify-between gap-2"><span className="text-[10px] text-slate-500">Last check · {formatDate(incident.verification_last_at)}</span><button type="button" onClick={() => onOpen?.(incident)} className="shrink-0 rounded-lg border border-violet-300/20 bg-violet-300/10 px-2.5 py-1.5 text-xs font-semibold text-violet-100 transition hover:bg-violet-300/15 focus:outline-none focus:ring-2 focus:ring-violet-300/50">Inspect</button></div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
