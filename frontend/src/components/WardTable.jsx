export default function WardTable({ wards }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-white/10">
      <table className="w-full text-left text-sm">
        <thead className="bg-white/5 text-[11px] uppercase tracking-wider text-slate-400">
          <tr>
            <th className="px-3 py-2">Pune demo zone</th>
            <th className="px-3 py-2">Critical</th>
            <th className="px-3 py-2">Moderate</th>
            <th className="px-3 py-2">Clear</th>
            <th className="px-3 py-2">Open</th>
            <th className="px-3 py-2">Avg mm</th>
          </tr>
        </thead>
        <tbody>
          {(wards || []).map((w) => (
            <tr key={w.ward_code} className="border-t border-white/5">
              <td className="px-3 py-2 text-slate-200">{w.ward_name}</td>
              <td className="px-3 py-2 font-mono text-red-300">{w.critical}</td>
              <td className="px-3 py-2 font-mono text-amber-200">{w.moderate}</td>
              <td className="px-3 py-2 font-mono text-cyan-200">{w.clear}</td>
              <td className="px-3 py-2 font-mono">{w.open_tickets}</td>
              <td className="px-3 py-2 font-mono text-slate-400">{w.avg_depth_mm}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
