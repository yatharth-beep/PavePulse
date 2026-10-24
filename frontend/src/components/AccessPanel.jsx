import { useCallback, useEffect, useState } from "react";
import { api } from "../api";

export default function AccessPanel({ user, onNotify }) {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState("");
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      setError("");
      setUsers(await api.users());
    } catch (err) {
      setError(err.message || "Could not load user accounts.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  async function toggle(userToToggle) {
    setBusyId(userToToggle.id);
    setError("");
    try {
      const updated = await api.setUserActive(userToToggle.id, !userToToggle.is_active);
      setUsers((prev) => prev.map((item) => item.id === updated.id ? updated : item));
      onNotify?.(`${updated.username} ${updated.is_active ? "activated" : "deactivated"}.`);
    } catch (err) {
      setError(err.message || "Could not update the account.");
    } finally {
      setBusyId("");
    }
  }

  return <div className="space-y-5">
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div><h2 className="text-xl font-semibold text-white">Team access</h2><p className="mt-1 text-sm text-slate-400">Manage active Engineer and Worker access.</p></div>
      <button onClick={refresh} className="rounded-xl border border-white/10 px-3 py-2 text-sm text-slate-300 hover:bg-white/5">Refresh users</button>
    </div>

    {error ? <div role="alert" className="rounded-xl border border-red-400/20 bg-red-400/10 px-4 py-3 text-sm text-red-200">{error}</div> : null}

    <section className="overflow-hidden rounded-2xl border border-white/10 bg-white/[0.02]">
      <div className="flex items-center justify-between border-b border-white/10 px-4 py-3"><div className="text-sm font-medium text-white">Operational profiles</div><div className="text-xs text-slate-500">{users.length} profiles</div></div>
      {loading && users.length === 0 ? <div className="p-6 text-sm text-slate-400">Loading accounts…</div> : users.length === 0 ? <div className="p-8 text-sm text-slate-400">No operational profiles have been synced yet. Confirm the backend is connected to the same Supabase project and the configured role emails match your Auth users.</div> : <div className="divide-y divide-white/5">{users.map((item) => <div key={item.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-4">
        <div className="flex min-w-0 items-center gap-3"><div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/5 text-xs font-semibold text-cyan-200">{String(item.username || "??").slice(0, 2).toUpperCase()}</div><div className="min-w-0"><div className="text-sm font-medium text-slate-100">{item.username}{item.id === user.id ? <span className="ml-2 text-[10px] text-cyan-300">YOU</span> : null}</div><div className="mt-1 text-xs text-slate-500">{item.role === "engineer" ? "Municipal Engineer · full access" : "Field Crew Worker · assigned work orders"}</div></div></div>
        <div className="flex items-center gap-2"><span className={`rounded-full px-2.5 py-1 text-[10px] ${item.is_active ? "bg-emerald-400/10 text-emerald-200" : "bg-slate-500/10 text-slate-400"}`}>{item.is_active ? "Active" : "Disabled"}</span><button disabled={busyId === item.id || item.id === user.id} onClick={() => toggle(item)} className="rounded-lg border border-white/10 px-3 py-1.5 text-xs text-slate-300 hover:bg-white/5 disabled:opacity-30">{busyId === item.id ? "Saving…" : item.is_active ? "Deactivate" : "Activate"}</button></div>
      </div>)}</div>}
    </section>
    <p className="text-xs leading-5 text-slate-500">Deactivating a profile blocks it from using the PavePulse API. It does not delete or change its Supabase Auth identity. Do not deactivate the only Engineer; this screen prevents you from disabling your own account.</p>
  </div>;
}
