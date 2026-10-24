function Card({ label, value, hint, accent }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3 shadow-glow">
      <div className="text-[11px] uppercase tracking-[0.16em] text-slate-400">{label}</div>
      <div className={`mt-1 font-mono text-2xl font-medium ${accent || "text-white"}`}>{value}</div>
      {hint ? <div className="mt-1 text-xs text-slate-500">{hint}</div> : null}
    </div>
  );
}

export default function KpiRow({ summary }) {
  if (!summary) {
    return <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">{Array.from({ length: 6 }).map((_, i) => <div key={i} className="h-20 animate-pulse rounded-2xl bg-white/5" />)}</div>;
  }
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
      <Card label="Defects logged" value={summary.incidents} hint={`${summary.open} open`} />
      <Card label="Critical" value={summary.critical} accent="text-red-300" hint="Immediate patching" />
      <Card label="Moderate wear" value={summary.moderate} accent="text-amber-200" />
      <Card label="Clear roads" value={summary.clear} accent="text-cyan-300" />
      <Card label="Work orders" value={summary.work_orders} hint={`${summary.dispatched} dispatched`} />
      <Card label="Fleet online" value={summary.fleet_online} hint={`avg depth ${summary.avg_depth_mm} mm`} />
    </div>
  );
}
