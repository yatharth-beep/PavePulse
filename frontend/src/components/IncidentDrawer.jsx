import { useState } from "react";
import { api } from "../api";
import { severityMeta, statusLabel } from "../lib/severity";

function Row({ k, v, mono }) {
  return <div className="flex items-start justify-between gap-4 border-b border-white/5 py-2"><div className="text-xs uppercase tracking-wider text-slate-500">{k}</div><div className={`${mono ? "font-mono" : ""} max-w-[65%] break-words text-right text-sm text-slate-100`}>{v}</div></div>;
}

function distanceMeters(a, b) {
  const radians = (degrees) => degrees * Math.PI / 180;
  const dLat = radians(b.lat - a.lat);
  const dLon = radians(b.lon - a.lon);
  const lat1 = radians(a.lat);
  const lat2 = radians(b.lat);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return 6371000 * 2 * Math.asin(Math.min(1, Math.sqrt(h)));
}

export default function IncidentDrawer({ incident, incidents, onClose, onReviewed, onDispatched, onMerged, onStatusChanged, canReview }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [selectedDuplicate, setSelectedDuplicate] = useState("");
  if (!incident) return null;
  const sev = severityMeta(incident.severity);
  const dispatched = ["dispatched", "in_progress", "awaiting_verification", "verified_fixed", "resolved"].includes(incident.status);
  const reviewable = ["open", "reviewing"].includes(incident.status) && !incident.merged_into_id;
  const candidates = (incidents || []).filter((item) => {
    if (item.id === incident.id || item.severity !== incident.severity || !["open", "reviewing"].includes(item.status)) return false;
    return distanceMeters(incident, item) <= 100;
  }).sort((a, b) => distanceMeters(incident, a) - distanceMeters(incident, b));

  async function review() {
    setBusy(true); setError("");
    try { onReviewed(await api.reviewIncident(incident.id)); }
    catch (err) { setError(err.message || "Could not mark this defect as reviewed."); }
    finally { setBusy(false); }
  }

  async function dispatch() {
    setBusy(true); setError("");
    try { onDispatched(await api.dispatch(incident.id)); }
    catch (err) { setError(err.message || "Dispatch failed."); }
    finally { setBusy(false); }
  }

  async function merge() {
    if (!selectedDuplicate) return;
    setBusy(true); setError("");
    try { onMerged(await api.mergeIncident(incident.id, selectedDuplicate)); }
    catch (err) { setError(err.message || "Could not merge reports."); }
    finally { setBusy(false); }
  }

  async function quickStatus(status) {
    setBusy(true); setError("");
    try {
      const note = status === "resolved" ? "Engineer quick action from incident review panel." : "Engineer started repair from incident review panel.";
      onStatusChanged(await api.setIncidentStatus(incident.id, status, note));
    } catch (err) { setError(err.message || "Could not update incident status."); }
    finally { setBusy(false); }
  }

  return (
    <div className="absolute inset-y-0 right-0 z-20 flex w-full max-w-md flex-col border-l border-white/10 bg-ink-900/95 shadow-2xl backdrop-blur">
      <div className="flex items-start justify-between gap-3 border-b border-white/10 p-5"><div><div className="text-xs uppercase tracking-[0.2em] text-slate-500">Incident review</div><h2 className="mt-1 text-xl font-semibold text-white">Surface defect</h2><div className="mt-1 font-mono text-[10px] text-slate-600">{incident.id}</div></div><button type="button" onClick={onClose} className="rounded-lg px-2 py-1 text-slate-400 hover:bg-white/5">Close</button></div>
      <div className="scrollbar-thin flex-1 overflow-y-auto p-5">
        <div className={`inline-flex rounded-full px-3 py-1 text-xs ring-1 ${sev.chip}`}>{sev.label}</div><div className="mt-2 text-xs capitalize text-slate-400">Status · {statusLabel(incident.status)}</div>
        <div className="mt-4"><Row k="GPS" v={`${Number(incident.lat).toFixed(6)}, ${Number(incident.lon).toFixed(6)}`} mono /><Row k="Timestamp" v={new Date(incident.observed_at).toLocaleString()} /><Row k="Depth estimate" v={`${Number(incident.depth_mm).toFixed(1)} mm`} mono /><Row k="Est. volume" v={`${Number(incident.estimated_volume_m3).toFixed(4)} m³`} mono /><Row k="Reports clustered" v={incident.hit_count} /><Row k="Pune demo zone" v={incident.ward_name || "Unassigned zone"} /><Row k="Route / reporting vehicle" v={`${incident.route_id} · ${incident.vehicle_label || "unknown"}`} /><Row k="Ticket" v={incident.work_order_ticket || "Not dispatched"} mono /><Row k="Reviewed at" v={incident.reviewed_at ? new Date(incident.reviewed_at).toLocaleString() : "Not reviewed"} />{incident.status === "awaiting_verification" || incident.status === "verified_fixed" ? <Row k="Independent bus checks" v={`${incident.verification_passes || 0} / ${incident.verification_required || 2}`} /> : null}{incident.verified_at ? <Row k="Fix verified at" v={new Date(incident.verified_at).toLocaleString()} /> : null}</div>
        {incident.sensor_log ? <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-400">{Object.entries(incident.sensor_log).map(([key, val]) => <div key={key} className="min-w-0 rounded-lg bg-white/5 px-2 py-1"><div className="truncate text-[10px] text-slate-500">{key}</div><div className="break-words font-mono text-slate-200">{String(val ?? "—")}</div></div>)}</div> : null}
        {canReview && reviewable && candidates.length > 0 ? <div className="mt-5 rounded-xl border border-white/10 p-3"><div className="text-sm font-medium text-slate-200">Possible duplicate reports</div><p className="mt-1 text-xs leading-5 text-slate-500">Same severity and within 100 m. A merge combines eligible nearby reports into one primary incident.</p><select value={selectedDuplicate} onChange={(e) => setSelectedDuplicate(e.target.value)} className="mt-3 w-full rounded-lg border border-white/10 bg-ink-800 px-3 py-2 text-sm text-slate-200 outline-none focus:border-cyan-400/40"><option value="">Choose a nearby report</option>{candidates.map((item) => <option key={item.id} value={item.id}>{item.ward_code || "No zone"} · {Math.round(distanceMeters(incident, item))} m · {item.hit_count} hit(s) · {item.id.slice(0, 8)}</option>)}</select><button disabled={!selectedDuplicate || busy} onClick={merge} className="mt-2 w-full rounded-lg border border-white/10 px-3 py-2 text-sm text-slate-200 hover:bg-white/5 disabled:opacity-40">{busy ? "Merging…" : "Merge selected report"}</button></div> : null}
        {error ? <div role="alert" className="mt-4 rounded-lg border border-red-400/20 bg-red-400/10 px-3 py-2 text-sm text-red-200">{error}</div> : null}
      </div>
      <div className="space-y-2 border-t border-white/10 bg-ink-900/90 p-5">
        {canReview && incident.status === "open" ? <button type="button" disabled={busy} onClick={review} className="w-full rounded-xl border border-cyan-300/30 bg-cyan-300/10 px-4 py-3 text-sm font-semibold text-cyan-100 hover:bg-cyan-300/15 disabled:opacity-50">{busy ? "Saving review…" : "Mark defect as reviewed"}</button> : null}
        {canReview && incident.status === "reviewing" ? <button type="button" disabled={busy} onClick={dispatch} className="w-full rounded-xl bg-gradient-to-r from-cyan-300 to-sky-400 px-4 py-3 text-sm font-semibold text-ink-950 disabled:opacity-50">{busy ? "Routing crew…" : "Create & dispatch work order"}</button> : null}
        {incident.status === "open" && canReview ? <div className="text-center text-[11px] text-slate-500">Dispatch stays disabled until the defect is reviewed.</div> : null}
        {canReview && ["dispatched", "in_progress"].includes(incident.status) ? <div className="rounded-xl border border-white/10 bg-ink-950/70 p-3"><div className="text-xs font-semibold text-slate-200">Quick status actions</div><div className="mt-2 grid grid-cols-2 gap-2">{incident.status === "dispatched" ? <button type="button" disabled={busy} onClick={() => quickStatus("in_progress")} className="rounded-lg border border-amber-300/20 bg-amber-300/10 px-3 py-2 text-xs font-semibold text-amber-100 disabled:opacity-50">Start repair</button> : <span className="rounded-lg border border-amber-300/15 px-3 py-2 text-center text-xs text-amber-100">In progress</span>}<button type="button" disabled={busy} onClick={() => quickStatus("resolved")} className="rounded-lg border border-emerald-300/20 bg-emerald-300/10 px-3 py-2 text-xs font-semibold text-emerald-100 disabled:opacity-50">Mark resolved</button></div><p className="mt-2 text-[10px] leading-4 text-slate-500">Status changes are reflected on the incident and its work order. Engineer resolution without field evidence is explicitly noted.</p></div> : null}
        {dispatched ? <div className={`rounded-xl border px-3 py-3 text-center ${incident.status === "awaiting_verification" ? "border-violet-400/20 bg-violet-400/[0.06] text-violet-100" : "border-emerald-400/15 bg-emerald-400/[0.06] text-emerald-100"}`}><div className="text-sm font-semibold">{incident.status === "awaiting_verification" ? "Repair complete · awaiting verification" : incident.status === "verified_fixed" ? "Repair verified fixed" : incident.status === "resolved" ? "Repair marked resolved" : `Work order ${incident.work_order_ticket || "created"} is ${statusLabel(incident.status)}`}</div>{incident.status === "awaiting_verification" ? <div className="mt-1 text-xs text-violet-200/75">{incident.verification_passes || 0} of {incident.verification_required || 2} independent buses have reported a clear surface.</div> : null}</div> : null}
        {!canReview ? <div className="text-center text-xs text-slate-500">Workers access only their assigned work orders; incident review is restricted to Engineers.</div> : null}
      </div>
    </div>
  );
}
