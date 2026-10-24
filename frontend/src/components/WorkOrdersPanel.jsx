import { useCallback, useEffect, useState } from "react";
import { api } from "../api";

const STATUS = {
  dispatched: "border-sky-400/20 bg-sky-400/10 text-sky-200",
  in_progress: "border-amber-400/20 bg-amber-400/10 text-amber-200",
  resolved: "border-emerald-400/20 bg-emerald-400/10 text-emerald-200",
  cancelled: "border-slate-500/30 bg-slate-500/10 text-slate-300",
};
const VERIFICATION = {
  awaiting_verification: "border-violet-300/20 bg-violet-300/10 text-violet-100",
  verified_fixed: "border-emerald-300/20 bg-emerald-300/10 text-emerald-100",
};
const nice = (value) => (value || "—").replaceAll("_", " ");
const dateText = (value) => value ? new Date(value).toLocaleString() : "—";

function StatusBadge({ status }) {
  return <span className={`inline-flex rounded-full border px-2.5 py-1 text-[11px] font-medium capitalize ${STATUS[status] || STATUS.dispatched}`}>{nice(status)}</span>;
}

export default function WorkOrdersPanel({ user, onNotify }) {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [drafts, setDrafts] = useState({});
  const [evidenceFiles, setEvidenceFiles] = useState({});
  const [workers, setWorkers] = useState([]);
  const canAdminister = user.role === "engineer";

  const refresh = useCallback(async () => {
    try {
      setError("");
      const rows = await api.workOrders();
      setOrders(rows);
      if (canAdminister) api.workers().then(setWorkers).catch(() => {});
      setDrafts((prev) => {
        const next = { ...prev };
        rows.forEach((row) => {
          if (!next[row.id]) next[row.id] = { evidence_url: row.evidence_url || "", completion_notes: row.completion_notes || "" };
          if (next[`${row.id}:assigned`] === undefined) next[`${row.id}:assigned`] = row.assigned_to_id || "";
          if (next[`${row.id}:crew`] === undefined) next[`${row.id}:crew`] = row.crew;
        });
        return next;
      });
    } catch (err) {
      setError(err.message || "Could not load work orders.");
    } finally {
      setLoading(false);
    }
  }, [canAdminister]);

  useEffect(() => {
    refresh();
    const id = window.setInterval(refresh, 15000);
    return () => window.clearInterval(id);
  }, [refresh]);

  async function changeStatus(order, status) {
    setBusy(order.id);
    setError("");
    try {
      const payload = { status };
      if (status === "resolved") {
        const draft = drafts[order.id] || {};
        payload.completion_notes = draft.completion_notes || order.completion_notes || (canAdminister ? "Engineer quick action: marked resolved; field evidence was not submitted through this action." : "");
        payload.evidence_url = draft.evidence_url || order.evidence_url || null;
        if (!payload.completion_notes.trim() && !payload.evidence_url && !(order.evidence_files || []).length) {
          setError("Add completion notes, an evidence URL, or upload a completion evidence file before resolving this work order.");
          setBusy("");
          return;
        }
      }
      const result = await api.updateWorkOrder(order.id, payload);
      setOrders((prev) => prev.map((row) => row.id === order.id ? { ...row, ...result } : row));
      onNotify?.(`${order.ticket_no} updated to ${nice(result.status)}.`);
    } catch (err) {
      setError(err.message || "Status update failed.");
    } finally {
      setBusy("");
    }
  }

  async function saveEvidence(order) {
    const draft = drafts[order.id] || {};
    setBusy(order.id);
    setError("");
    try {
      const payload = {
        evidence_url: draft.evidence_url || null,
        completion_notes: draft.completion_notes || "",
      };
      if (canAdminister) {
        payload.crew = drafts[`${order.id}:crew`] || order.crew;
        payload.assigned_to_id = drafts[`${order.id}:assigned`] || null;
      }
      const result = await api.updateWorkOrder(order.id, payload);
      setOrders((prev) => prev.map((row) => row.id === order.id ? { ...row, ...result } : row));
      setDrafts((prev) => ({ ...prev, [`${order.id}:assigned`]: result.assigned_to_id || "", [`${order.id}:crew`]: result.crew }));
      onNotify?.(`Work order ${order.ticket_no} saved.`);
    } catch (err) {
      setError(err.message || "Could not save the repair evidence.");
    } finally {
      setBusy("");
    }
  }

  async function uploadEvidence(order) {
    const file = evidenceFiles[order.id];
    if (!file) return;
    setBusy(order.id); setError("");
    try {
      const result = await api.uploadWorkOrderEvidence(order.id, file);
      setOrders((prev) => prev.map((row) => row.id === order.id ? { ...row, ...result } : row));
      setEvidenceFiles((prev) => { const next = { ...prev }; delete next[order.id]; return next; });
      onNotify?.(`Evidence uploaded for ${order.ticket_no}.`);
    } catch (err) { setError(err.message || "Evidence upload failed."); }
    finally { setBusy(""); }
  }

  async function downloadEvidence(order, evidence) {
    setBusy(`evidence:${evidence.id}`); setError("");
    try {
      const blob = await api.downloadWorkOrderEvidence(order.id, evidence.id);
      const objectUrl = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = evidence.original_filename || "repair-evidence";
      document.body.appendChild(anchor); anchor.click(); anchor.remove();
      window.URL.revokeObjectURL(objectUrl);
    } catch (err) { setError(err.message || "Evidence download failed."); }
    finally { setBusy(""); }
  }

  const transitionsFor = (order) => {
    const allowed = {
      dispatched: ["dispatched", "in_progress", "cancelled"],
      in_progress: ["in_progress", "resolved", "cancelled"],
      resolved: ["resolved"],
      cancelled: ["cancelled"],
    }[order.status] || [];
    return canAdminister ? allowed : allowed.filter((status) => ["in_progress", "resolved"].includes(status));
  };
  const active = orders.filter((item) => !["resolved", "cancelled"].includes(item.status)).length;
  const completed = orders.filter((item) => item.status === "resolved").length;

  return (
    <div className="space-y-5">
      <section className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4"><div className="text-xs uppercase tracking-wider text-slate-500">Total work orders</div><div className="mt-2 font-mono text-3xl text-white">{orders.length}</div></div>
        <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4"><div className="text-xs uppercase tracking-wider text-slate-500">Active repairs</div><div className="mt-2 font-mono text-3xl text-amber-200">{active}</div></div>
        <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4"><div className="text-xs uppercase tracking-wider text-slate-500">Resolved</div><div className="mt-2 font-mono text-3xl text-emerald-200">{completed}</div></div>
      </section>

      <div className="flex flex-wrap items-end justify-between gap-3"><div><h2 className="text-xl font-semibold text-white">Repair work orders</h2><p className="mt-1 text-sm text-slate-400">Timestamped dispatch, field progress and close-out evidence.</p></div><button onClick={refresh} className="rounded-xl border border-white/10 px-3 py-2 text-sm text-slate-300 hover:bg-white/5">Refresh list</button></div>
      {error ? <div role="alert" className="rounded-xl border border-red-400/20 bg-red-400/10 px-4 py-3 text-sm text-red-200">{error}</div> : null}
      {loading ? <div className="rounded-2xl border border-white/10 p-8 text-sm text-slate-400">Loading work orders…</div> : orders.length === 0 ? <div className="rounded-2xl border border-dashed border-white/15 p-10 text-center"><div className="text-white">No work orders yet</div><p className="mt-2 text-sm text-slate-500">Review a defect on the dashboard and dispatch a repair crew to create the first ticket.</p></div> : (
        <div className="grid grid-cols-1 gap-4 2xl:grid-cols-2">
          {orders.map((order) => (
            <article key={order.id} className="rounded-2xl border border-white/10 bg-white/[0.025] p-4 sm:p-5">
              <div className="flex flex-wrap items-start justify-between gap-3"><div><div className="font-mono text-sm text-cyan-200">{order.ticket_no}</div><h3 className="mt-1 text-base font-semibold capitalize text-white">{nice(order.severity)} road repair</h3><div className="mt-1 text-xs text-slate-500">{order.ward_name || "Unassigned demo zone"} · Route {order.incident_route || "—"}</div><div className="mt-1 text-xs text-slate-500">Assigned to <span className="text-slate-300">{order.assigned_to_username || "Unassigned worker"}</span></div></div><div className="flex flex-col items-end gap-1.5"><StatusBadge status={order.status} />{order.incident_status && VERIFICATION[order.incident_status] ? <span className={`rounded-full border px-2.5 py-1 text-[10px] font-medium ${VERIFICATION[order.incident_status]}`}>{order.incident_status === "awaiting_verification" ? `Awaiting verification · ${order.verification_passes || 0}/${order.verification_required || 2}` : "Verified fixed"}</span> : null}</div></div>
              {order.incident_status === "awaiting_verification" ? <div className="mt-3 rounded-xl border border-violet-300/15 bg-violet-300/[0.06] px-3 py-2.5 text-xs leading-5 text-violet-100">Repair close-out recorded. Waiting for {Math.max(0, (order.verification_required || 2) - (order.verification_passes || 0))} more independent bus check(s) to verify the road is fixed.</div> : null}
              {order.incident_status === "verified_fixed" ? <div className="mt-3 rounded-xl border border-emerald-300/15 bg-emerald-300/[0.06] px-3 py-2.5 text-xs leading-5 text-emerald-100">Independent fleet verification complete{order.verified_at ? ` · ${dateText(order.verified_at)}` : ""}.</div> : null}
              <div className="mt-4 grid grid-cols-1 gap-2 rounded-xl bg-ink-950/70 p-3 text-xs sm:grid-cols-2"><div><span className="text-slate-500">Crew</span><div className="mt-1 text-slate-200">{order.crew}</div></div><div><span className="text-slate-500">Dispatched</span><div className="mt-1 text-slate-200">{dateText(order.dispatched_at)}</div></div><div><span className="text-slate-500">Last updated</span><div className="mt-1 text-slate-200">{dateText(order.updated_at)}</div></div><div><span className="text-slate-500">Completed</span><div className="mt-1 text-slate-200">{dateText(order.completed_at)}</div></div></div>
              <label className="mt-4 block text-xs text-slate-400">Work-order notes<textarea rows="2" className="mt-1 w-full resize-y rounded-lg border border-white/10 bg-ink-950 px-3 py-2 text-sm text-slate-200 outline-none focus:border-cyan-400/40" value={drafts[order.id]?.completion_notes ?? order.completion_notes ?? ""} onChange={(e) => setDrafts((prev) => ({ ...prev, [order.id]: { ...prev[order.id], completion_notes: e.target.value } }))} placeholder="Repair outcome, materials used, inspection notes…" /></label>
              <label className="mt-3 block text-xs text-slate-400">External evidence URL (optional)<input type="url" className="mt-1 w-full rounded-lg border border-white/10 bg-ink-950 px-3 py-2 text-sm text-slate-200 outline-none focus:border-cyan-400/40" value={drafts[order.id]?.evidence_url ?? order.evidence_url ?? ""} onChange={(e) => setDrafts((prev) => ({ ...prev, [order.id]: { ...prev[order.id], evidence_url: e.target.value } }))} placeholder="https://…" /></label>
              <div className="mt-3 rounded-xl border border-white/10 bg-ink-950/65 p-3">
                <label className="block text-xs text-slate-400">Upload repair evidence <span className="text-slate-600">PNG, JPEG or PDF · max 5 MB</span><input type="file" accept="image/png,image/jpeg,application/pdf" disabled={busy === order.id || (user.role === "worker" && ["resolved", "cancelled"].includes(order.status))} onChange={(event) => setEvidenceFiles((prev) => ({ ...prev, [order.id]: event.target.files?.[0] || null }))} className="mt-2 block w-full text-xs text-slate-300 file:mr-3 file:rounded-lg file:border-0 file:bg-white/10 file:px-3 file:py-2 file:text-xs file:text-slate-100 hover:file:bg-white/15" /></label>
                {evidenceFiles[order.id] ? <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-cyan-100"><span className="break-all">{evidenceFiles[order.id].name} · {(evidenceFiles[order.id].size / 1024).toFixed(0)} KB</span><button type="button" disabled={busy === order.id} onClick={() => uploadEvidence(order)} className="rounded-lg bg-cyan-300 px-3 py-2 font-semibold text-ink-950 disabled:opacity-50">{busy === order.id ? "Uploading…" : "Upload evidence"}</button></div> : null}
                {(order.evidence_files || []).length ? <div className="mt-3 space-y-2 border-t border-white/5 pt-3">{order.evidence_files.map((evidence) => <div key={evidence.id} className="flex flex-wrap items-center justify-between gap-2 text-xs"><div className="min-w-0"><div className="break-all text-slate-200">{evidence.original_filename}</div><div className="mt-0.5 text-slate-500">{(evidence.size_bytes / 1024).toFixed(0)} KB · {dateText(evidence.created_at)}</div></div><button type="button" disabled={busy === `evidence:${evidence.id}`} onClick={() => downloadEvidence(order, evidence)} className="rounded-lg border border-white/10 px-2.5 py-1.5 text-slate-300 hover:bg-white/5 disabled:opacity-50">{busy === `evidence:${evidence.id}` ? "Opening…" : "Download"}</button></div>)}</div> : <div className="mt-2 text-[10px] text-slate-600">No files attached yet. Uploaded files are private and require an authorized account to download.</div>}
              </div>
              <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-white/5 pt-4">
                {order.status === "dispatched" ? <button type="button" disabled={busy === order.id} onClick={() => changeStatus(order, "in_progress")} className="rounded-lg border border-amber-300/20 bg-amber-300/10 px-3 py-2 text-xs font-semibold text-amber-100 disabled:opacity-50">Start work</button> : null}
                {(order.status === "in_progress" || (canAdminister && order.status === "dispatched")) ? <button type="button" disabled={busy === order.id} onClick={() => changeStatus(order, "resolved")} className="rounded-lg border border-emerald-300/20 bg-emerald-300/10 px-3 py-2 text-xs font-semibold text-emerald-100 disabled:opacity-50">Mark resolved</button> : null}
                <select aria-label={`Update status for ${order.ticket_no}`} disabled={busy === order.id || ["resolved", "cancelled"].includes(order.status)} value={order.status} onChange={(e) => changeStatus(order, e.target.value)} className="min-w-[150px] flex-1 rounded-lg border border-white/10 bg-ink-800 px-3 py-2 text-sm capitalize text-slate-200 outline-none focus:border-cyan-400/40">
                  {!transitionsFor(order).includes(order.status) ? <option value={order.status} disabled>{nice(order.status)}</option> : null}
                  {transitionsFor(order).map((status) => <option key={status} value={status}>{nice(status)}</option>)}
                </select>
                {canAdminister ? <label className="min-w-[140px] flex-1 text-xs text-slate-500">Assigned crew<input className="mt-1 w-full rounded-lg border border-white/10 bg-ink-800 px-3 py-2 text-sm text-slate-200 outline-none focus:border-cyan-400/40" value={drafts[`${order.id}:crew`] ?? order.crew} onChange={(e) => setDrafts((prev) => ({ ...prev, [`${order.id}:crew`]: e.target.value }))} /></label> : null}
                {canAdminister ? <label className="min-w-[170px] flex-1 text-xs text-slate-500">Assign worker<select className="mt-1 w-full rounded-lg border border-white/10 bg-ink-800 px-3 py-2 text-sm text-slate-200 outline-none focus:border-cyan-400/40" value={drafts[`${order.id}:assigned`] ?? ""} onChange={(e) => setDrafts((prev) => ({ ...prev, [`${order.id}:assigned`]: e.target.value }))}><option value="">Unassigned</option>{workers.map((worker) => <option key={worker.id} value={worker.id}>{worker.username}</option>)}</select></label> : null}
                <button disabled={busy === order.id || (user.role === "worker" && ["resolved", "cancelled"].includes(order.status))} onClick={() => saveEvidence(order)} className="rounded-lg bg-cyan-300 px-3 py-2 text-sm font-semibold text-ink-950 disabled:opacity-50">{busy === order.id ? "Saving…" : "Save updates"}</button>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
