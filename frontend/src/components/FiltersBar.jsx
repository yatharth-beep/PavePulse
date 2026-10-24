import { statusLabel } from "../lib/severity";

const selectClass =
  "rounded-xl border border-white/10 bg-ink-800 px-3 py-2 text-sm text-slate-100 outline-none focus:border-cyan-400/40";

export default function FiltersBar({ meta, filters, onChange }) {
  const set = (key, value) => onChange({ ...filters, [key]: value });

  return (
    <div className="flex flex-wrap items-end gap-3 rounded-2xl border border-white/10 bg-white/[0.03] p-3">
      <label className="flex min-w-[140px] flex-1 flex-col gap-1 text-[11px] uppercase tracking-wider text-slate-400">
        Pune demo zone
        <select className={selectClass} value={filters.ward} onChange={(e) => set("ward", e.target.value)}>
          <option value="">All demo zones</option>
          {(meta?.wards || []).map((w) => (
            <option key={w.code} value={w.code}>
              {w.name}
            </option>
          ))}
        </select>
      </label>
      <label className="flex min-w-[120px] flex-col gap-1 text-[11px] uppercase tracking-wider text-slate-400">
        Route
        <select className={selectClass} value={filters.route} onChange={(e) => set("route", e.target.value)}>
          <option value="">All routes</option>
          {(meta?.routes || []).map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
      </label>
      <label className="flex min-w-[120px] flex-col gap-1 text-[11px] uppercase tracking-wider text-slate-400">
        Status
        <select className={selectClass} value={filters.status} onChange={(e) => set("status", e.target.value)}>
          <option value="">All statuses</option>
          {(meta?.statuses || []).map((s) => (
            <option key={s} value={s}>
              {statusLabel(s)}
            </option>
          ))}
        </select>
      </label>
      <label className="flex min-w-[140px] flex-col gap-1 text-[11px] uppercase tracking-wider text-slate-400">
        Condition
        <select className={selectClass} value={filters.severity} onChange={(e) => set("severity", e.target.value)}>
          <option value="">All conditions</option>
          <option value="critical">Critical Damage</option>
          <option value="moderate">Moderate Wear</option>
          <option value="clear">Clear Roads</option>
        </select>
      </label>
      <label className="flex min-w-[140px] flex-col gap-1 text-[11px] uppercase tracking-wider text-slate-400">
        From
        <input type="date" className={selectClass} value={filters.date_from} onChange={(e) => set("date_from", e.target.value)} />
      </label>
      <label className="flex min-w-[140px] flex-col gap-1 text-[11px] uppercase tracking-wider text-slate-400">
        To
        <input type="date" className={selectClass} value={filters.date_to} onChange={(e) => set("date_to", e.target.value)} />
      </label>
      <button
        type="button"
        className="rounded-xl border border-white/10 px-3 py-2 text-sm text-slate-300 hover:bg-white/5"
        onClick={() =>
          onChange({ ward: "", route: "", status: "", severity: "", date_from: "", date_to: "" })
        }
      >
        Reset
      </button>
    </div>
  );
}
