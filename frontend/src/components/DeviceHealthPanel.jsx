import { useCallback, useEffect, useState } from "react";
import { api } from "../api";

function StateChip({ value }) {
  const good = ["connected", "on"].includes(value);
  const warning = ["degraded", "unknown"].includes(value);
  const style = good ? "border-emerald-400/20 bg-emerald-400/10 text-emerald-200" : warning ? "border-amber-400/20 bg-amber-400/10 text-amber-200" : "border-red-400/20 bg-red-400/10 text-red-200";
  return <span className={`inline-flex rounded-full border px-2.5 py-1 text-[11px] capitalize ${style}`}>{value || "unknown"}</span>;
}
const when = (value) => value ? new Date(value).toLocaleString() : "Never reported";

export default function DeviceHealthPanel({ user, onNotify }) {
  const [devices, setDevices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [rotating, setRotating] = useState("");
  const [issuedKey, setIssuedKey] = useState(null);
  const [keyMessage, setKeyMessage] = useState("");
  const [routes, setRoutes] = useState([]);
  const [registering, setRegistering] = useState(false);
  const [newDevice, setNewDevice] = useState({ vehicle_label: "", fleet_id: "TRANSIT-01", route_id: "R12", software_version: "edge-0.1.0" });
  const refresh = useCallback(async () => {
    try { setError(""); setDevices(await api.telemetryDevices()); }
    catch (err) { setError(err.message || "Could not load device health."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => {
    refresh();
    api.meta().then((result) => setRoutes(result.routes || [])).catch(() => {});
    const id = window.setInterval(refresh, 10000);
    return () => window.clearInterval(id);
  }, [refresh]);

  async function register(event) {
    event.preventDefault();
    setRegistering(true); setError("");
    try {
      const result = await api.registerDevice({ ...newDevice, vehicle_label: newDevice.vehicle_label.trim().toUpperCase(), fleet_id: newDevice.fleet_id.trim().toUpperCase() });
      setNewDevice((prev) => ({ ...prev, vehicle_label: "" }));
      await refresh();
      onNotify?.(`Device ${result.vehicle_label} registered. Issue its device credential before connecting it.`);
    } catch (err) { setError(err.message || "Could not register this device."); }
    finally { setRegistering(false); }
  }

  const connected = devices.filter((item) => item.connectivity_status === "connected").length;
  const offline = devices.filter((item) => item.connectivity_status === "offline").length;

  async function rotate(label) {
    setRotating(label); setError(""); setKeyMessage(""); setIssuedKey(null);
    try { const result = await api.rotateDeviceCredential(label); setIssuedKey(result); }
    catch (err) { setError(err.message || "Could not rotate the device credential."); }
    finally { setRotating(""); }
  }

  async function copyKey() {
    try { await navigator.clipboard.writeText(issuedKey.device_key); setKeyMessage("Credential copied to clipboard."); }
    catch { setKeyMessage("Clipboard access was blocked. Select and copy the key manually."); }
  }

  return <div className="space-y-5">
    <div className="flex flex-wrap items-end justify-between gap-3"><div><h2 className="text-xl font-semibold text-white">Edge device health</h2><p className="mt-1 text-sm text-slate-400">Last transmission, power state, connectivity and deployed software version.</p></div><button onClick={refresh} className="rounded-xl border border-white/10 px-3 py-2 text-sm text-slate-300 hover:bg-white/5">Refresh devices</button></div>
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3"><div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4"><div className="text-xs uppercase tracking-wider text-slate-500">Registered devices</div><div className="mt-2 font-mono text-3xl text-white">{devices.length}</div></div><div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4"><div className="text-xs uppercase tracking-wider text-slate-500">Connected</div><div className="mt-2 font-mono text-3xl text-emerald-200">{connected}</div></div><div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4"><div className="text-xs uppercase tracking-wider text-slate-500">Offline</div><div className="mt-2 font-mono text-3xl text-red-200">{offline}</div></div></div>
    {error ? <div role="alert" className="rounded-xl border border-red-400/20 bg-red-400/10 px-4 py-3 text-sm text-red-200">{error}</div> : null}
    {user?.role === "engineer" ? <form onSubmit={register} className="grid grid-cols-1 gap-3 rounded-2xl border border-white/10 bg-white/[0.025] p-4 sm:grid-cols-2 xl:grid-cols-[1.1fr_1fr_0.8fr_1fr_auto] xl:items-end">
      <div className="sm:col-span-2 xl:col-span-1"><h3 className="text-sm font-semibold text-white">Register edge device</h3><p className="mt-1 text-xs text-slate-500">Register the vehicle first, then issue its unique secret.</p></div>
      <label className="block text-xs text-slate-400">Device label<input required minLength={2} maxLength={64} pattern="[A-Za-z0-9_-]+" value={newDevice.vehicle_label} onChange={(event) => setNewDevice((prev) => ({ ...prev, vehicle_label: event.target.value }))} placeholder="BUS-701" className="mt-1 w-full rounded-lg border border-white/10 bg-ink-950 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400/40" /></label>
      <label className="block text-xs text-slate-400">Fleet ID<input required minLength={1} maxLength={32} pattern="[A-Za-z0-9_-]+" value={newDevice.fleet_id} onChange={(event) => setNewDevice((prev) => ({ ...prev, fleet_id: event.target.value }))} className="mt-1 w-full rounded-lg border border-white/10 bg-ink-950 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400/40" /></label>
      <label className="block text-xs text-slate-400">Route<select value={newDevice.route_id} onChange={(event) => setNewDevice((prev) => ({ ...prev, route_id: event.target.value }))} className="mt-1 w-full rounded-lg border border-white/10 bg-ink-950 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400/40">{(routes.length ? routes : ["R12", "R18", "R22", "R31"]).map((route) => <option key={route} value={route}>{route}</option>)}</select></label>
      <button disabled={registering || !newDevice.vehicle_label.trim()} className="rounded-lg bg-cyan-300 px-4 py-2 text-sm font-semibold text-ink-950 disabled:opacity-50">{registering ? "Registering…" : "Register device"}</button>
    </form> : null}
    {issuedKey ? <div className="rounded-2xl border border-amber-400/20 bg-amber-400/[0.06] p-4"><div className="text-sm font-semibold text-amber-100">New credential for {issuedKey.vehicle_label}</div><p className="mt-1 text-xs text-amber-100/70">This secret is displayed once. Copy it to the device configuration now; the previous key has been invalidated.</p><div className="mt-3 flex flex-wrap items-center gap-2"><code className="min-w-0 flex-1 break-all rounded-lg bg-ink-950 px-3 py-2 font-mono text-xs text-amber-50">{issuedKey.device_key}</code><button onClick={copyKey} className="rounded-lg border border-amber-100/20 px-3 py-2 text-xs text-amber-50">Copy key</button><button onClick={() => { setIssuedKey(null); setKeyMessage(""); }} className="rounded-lg border border-white/10 px-3 py-2 text-xs text-slate-300">Dismiss</button></div>{keyMessage ? <div className="mt-2 text-xs text-amber-100">{keyMessage}</div> : null}</div> : null}
    <div className="overflow-hidden rounded-2xl border border-white/10">
      <div className="overflow-x-auto"><table className="w-full min-w-[840px] text-left text-sm"><thead className="bg-white/5 text-[11px] uppercase tracking-wider text-slate-500"><tr>{["Device / fleet", "Route", "Power", "Connectivity", "Last transmission", "Software", "Last error", ...(user?.role === "engineer" ? ["Credential"] : [])].map((x) => <th key={x} className="px-4 py-3 font-medium">{x}</th>)}</tr></thead><tbody>{devices.map((device) => <tr key={device.vehicle_label} className="border-t border-white/5"><td className="px-4 py-3"><div className="font-mono text-cyan-200">{device.vehicle_label}</div><div className="mt-1 text-xs text-slate-500">{device.fleet_id}</div></td><td className="px-4 py-3 font-mono text-slate-300">{device.route_id}</td><td className="px-4 py-3"><StateChip value={device.power_status} /></td><td className="px-4 py-3"><StateChip value={device.connectivity_status} /></td><td className="px-4 py-3 text-xs text-slate-300">{when(device.last_seen_at)}</td><td className="px-4 py-3 font-mono text-xs text-slate-400">{device.software_version}</td><td className="max-w-[200px] px-4 py-3 text-xs text-slate-500">{device.last_error || "—"}</td>{user?.role === "engineer" ? <td className="px-4 py-3"><button disabled={Boolean(rotating)} onClick={() => rotate(device.vehicle_label)} className="whitespace-nowrap rounded-lg border border-white/10 px-2.5 py-1.5 text-xs text-slate-300 hover:bg-white/5 disabled:opacity-50">{rotating === device.vehicle_label ? "Working…" : device.credential_configured ? "Rotate key" : "Issue key"}</button></td> : null}</tr>)}</tbody></table></div>
      {loading && devices.length === 0 ? <div className="p-6 text-sm text-slate-400">Loading fleet device status…</div> : null}
      {!loading && devices.length === 0 ? <div className="p-6 text-sm text-slate-400">No registered devices found.</div> : null}
    </div>
    <p className="text-xs leading-5 text-slate-500">A device is considered offline after five minutes without a telemetry record. The demo simulator reports version edge-0.1.0; production devices should publish authenticated firmware and diagnostic fields.</p>
  </div>;
}
