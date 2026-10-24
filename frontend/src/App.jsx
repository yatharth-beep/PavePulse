import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import AccessPanel from "./components/AccessPanel.jsx";
import ChangePasswordModal from "./components/ChangePasswordModal.jsx";
import DeviceHealthPanel from "./components/DeviceHealthPanel.jsx";
import FiltersBar from "./components/FiltersBar.jsx";
import IncidentDrawer from "./components/IncidentDrawer.jsx";
import KpiRow from "./components/KpiRow.jsx";
import LoginScreen from "./components/LoginScreen.jsx";
import MapView from "./components/MapView.jsx";
import WardTable from "./components/WardTable.jsx";
import WorkOrdersPanel from "./components/WorkOrdersPanel.jsx";
import VerificationQueue from "./components/VerificationQueue.jsx";

const EMPTY_FILTERS = { ward: "", route: "", status: "", severity: "", date_from: "", date_to: "" };
const ROLE_LABEL = {
  engineer: "Municipal Engineer",
  worker: "Field Crew Worker",
};

function homeTabForRole(role) {
  return role === "worker" ? "work-orders" : "dashboard";
}

function NavButton({ active, children, onClick }) {
  return <button type="button" onClick={onClick} className={`rounded-lg px-3 py-2 text-sm transition ${active ? "bg-cyan-300 text-ink-950" : "text-slate-400 hover:bg-white/5 hover:text-white"}`}>{children}</button>;
}

export default function App() {
  const [user, setUser] = useState(null);
  const [authChecking, setAuthChecking] = useState(true);
  const [meta, setMeta] = useState(null);
  const [summary, setSummary] = useState(null);
  const [wards, setWards] = useState([]);
  const [incidents, setIncidents] = useState([]);
  const [verificationQueue, setVerificationQueue] = useState([]);
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [selected, setSelected] = useState(null);
  const [toast, setToast] = useState("");
  const [globalError, setGlobalError] = useState("");
  const [lastRefreshAt, setLastRefreshAt] = useState(null);
  const [activeTab, setActiveTab] = useState("dashboard");
  const [passwordModal, setPasswordModal] = useState(false);
  const canSeeDashboard = Boolean(user && user.role === "engineer");
  const canSeeWorkOrders = Boolean(user && ["engineer", "worker"].includes(user.role));

  const query = useMemo(() => {
    const params = { ...filters };
    if (params.date_from) params.date_from = `${params.date_from}T00:00:00Z`;
    if (params.date_to) params.date_to = `${params.date_to}T23:59:59Z`;
    return params;
  }, [filters]);

  const signOut = useCallback(() => {
    void api.signOut();
    setUser(null);
    setSelected(null);
    setActiveTab("dashboard");
  }, []);

  const notify = useCallback((message) => {
    setToast(message);
    window.setTimeout(() => setToast(""), 4500);
  }, []);

  useEffect(() => {
    if (!user) return;
    if (user.role === "worker") setActiveTab("work-orders");
  }, [user]);

  useEffect(() => {
    api.meta().then(setMeta).catch((err) => setGlobalError(err.message || "Could not connect to the PavePulse API."));
    if (!window.sessionStorage.getItem("pavepulse_token")) {
      setAuthChecking(false);
      return undefined;
    }
    api.me().then(setUser).catch(() => signOut()).finally(() => setAuthChecking(false));
    return undefined;
  }, [signOut]);

  const refresh = useCallback(async () => {
    if (!user || user.role !== "engineer") return;
    try {
      setGlobalError("");
      const [nextSummary, nextWards, rows, verificationRows] = await Promise.all([
        api.summary(), api.wards(), api.incidents(query), api.incidents({ status: "awaiting_verification" }),
      ]);
      setSummary(nextSummary);
      setWards(nextWards);
      setIncidents(rows);
      setVerificationQueue(verificationRows);
      setLastRefreshAt(new Date());
      setSelected((current) => {
        if (!current) return null;
        return rows.find((row) => row.id === current.id) || null;
      });
    } catch (err) {
      if (err.status === 401) signOut();
      else setGlobalError(err.message || "Could not refresh the dashboard data.");
    }
  }, [query, signOut, user]);

  useEffect(() => {
    if (!user || user.role !== "engineer") return undefined;
    refresh();
    const id = window.setInterval(refresh, 10000);
    return () => window.clearInterval(id);
  }, [refresh, user]);

  async function login(username, password) {
    const result = await api.login(username, password);
    api.setToken(result.access_token);
    setUser(result.user);
    setGlobalError("");
    setActiveTab(homeTabForRole(result.user.role));
  }

  function onReviewed(result) {
    setSelected(result);
    notify("Defect reviewed. It is now eligible for repair dispatch.");
    refresh();
  }

  function onDispatched(result) {
    setSelected(result.incident);
    notify(`Work order ${result.work_order.ticket_no} dispatched to ${result.work_order.crew}.`);
    refresh();
  }

  function onMerged(result) {
    setSelected(result);
    notify("Duplicate report merged. The primary incident has been updated.");
    refresh();
  }

  function onStatusChanged(result) {
    setSelected(result);
    notify(`Incident status updated to ${String(result.status).replaceAll("_", " ")}.`);
    refresh();
  }

  const canReview = canSeeDashboard;
  const canSeeDevices = Boolean(user && user.role === "engineer");
  const canManageUsers = Boolean(user && user.role === "engineer");

  if (authChecking) {
    return <div className="flex min-h-screen items-center justify-center text-sm text-slate-400"><span className="mr-3 h-2 w-2 animate-pulse rounded-full bg-cyan-300" />Checking session…</div>;
  }
  if (!user) return <><LoginScreen onLogin={login} />{globalError ? <div role="alert" className="fixed inset-x-4 top-4 z-[100] mx-auto max-w-2xl rounded-xl border border-red-400/25 bg-ink-900/95 px-4 py-3 text-sm text-red-100 shadow-2xl">{globalError}</div> : null}</>;

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 border-b border-white/10 bg-ink-950/90 px-4 backdrop-blur-xl sm:px-6">
        <div className="mx-auto flex min-h-[72px] max-w-[1800px] flex-wrap items-center justify-between gap-3 py-3">
          <div className="flex items-center gap-3"><div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-300 text-sm font-bold text-ink-950">PP</div><div><div className="text-lg font-semibold tracking-tight text-white">PavePulse</div><div className="text-[10px] uppercase tracking-[0.18em] text-slate-500">Road intelligence operations</div></div></div>
          <nav aria-label="Main navigation" className="order-3 flex w-full flex-wrap gap-1 border-t border-white/5 pt-3 sm:order-none sm:w-auto sm:border-0 sm:pt-0">
            {canSeeDashboard ? <NavButton active={activeTab === "dashboard"} onClick={() => setActiveTab("dashboard")}>Dashboard</NavButton> : null}
            {canSeeWorkOrders ? <NavButton active={activeTab === "work-orders"} onClick={() => setActiveTab("work-orders")}>Work orders</NavButton> : null}
            {canSeeDevices ? <NavButton active={activeTab === "devices"} onClick={() => setActiveTab("devices")}>Devices</NavButton> : null}
            {canManageUsers ? <NavButton active={activeTab === "access"} onClick={() => setActiveTab("access")}>Team access</NavButton> : null}
          </nav>
          <div className="flex items-center gap-2"><div className="hidden text-right sm:block"><div className="text-xs font-medium text-slate-200">{user.username}</div><div className="mt-0.5 text-[10px] text-slate-500">{ROLE_LABEL[user.role] || user.role}</div></div><button onClick={() => setPasswordModal(true)} className="rounded-lg border border-white/10 px-3 py-2 text-xs text-slate-300 hover:bg-white/5">Password</button><div className="h-8 w-px bg-white/10" /><button onClick={signOut} className="rounded-lg border border-white/10 px-3 py-2 text-xs text-slate-300 hover:bg-white/5">Sign out</button></div>
        </div>
      </header>

      <main className="mx-auto max-w-[1800px] space-y-5 px-4 py-5 sm:px-6 sm:py-6">
        {globalError ? <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-red-400/20 bg-red-400/10 px-4 py-3 text-sm text-red-200">{globalError}<button onClick={() => setGlobalError("")} className="text-xs underline">Dismiss</button></div> : null}
        {activeTab !== "dashboard" && meta?.demo_data_enabled ? <div role="note" className="flex flex-wrap items-center gap-2 rounded-xl border border-amber-300/20 bg-amber-300/[0.07] px-4 py-3 text-xs text-amber-100"><span className="rounded-md border border-amber-200/25 px-2 py-1 font-semibold tracking-wide">PUNE DEMO · ILLUSTRATIVE ONLY</span><span>Sample incidents and work orders are synthetic workflow examples, not official PMC records or verified road defects.</span></div> : null}
        {activeTab === "dashboard" && canSeeDashboard ? <>
          <div className="flex flex-wrap items-end justify-between gap-3"><div><div className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">Municipal control room</div><h1 className="mt-1 text-2xl font-semibold tracking-tight text-white sm:text-3xl">Road condition overview</h1><p className="mt-1 text-sm text-slate-400">Pune, Maharashtra · illustrative road reports for demo and workflow testing, not official PMC records.</p></div><div className="flex flex-wrap items-center gap-2">{meta?.demo_data_enabled ? <span className="rounded-xl border border-amber-300/25 bg-amber-300/10 px-3 py-2 text-[10px] font-semibold tracking-wide text-amber-100">PUNE DEMO · ILLUSTRATIVE ONLY</span> : null}<div className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.025] px-3 py-2"><span className={`h-2 w-2 rounded-full ${lastRefreshAt ? "bg-emerald-300" : "bg-amber-300"}`} /><span className="text-xs text-slate-300">{lastRefreshAt ? "Dashboard connected" : "Connecting to data service"}</span><span className="mx-1 h-4 w-px bg-white/10"/><span className="font-mono text-[10px] text-slate-500">{lastRefreshAt ? `Updated ${lastRefreshAt.toLocaleTimeString()}` : "Waiting for API"}</span></div></div></div>
          <KpiRow summary={summary} />
          <FiltersBar meta={meta} filters={filters} onChange={setFilters} />
          <VerificationQueue incidents={verificationQueue} requiredBuses={meta?.verification_required_buses || 2} onOpen={(incident) => { setFilters(EMPTY_FILTERS); setSelected(incident); }} />
          <section className="relative">
            <div className="h-[58vh] min-h-[460px] max-h-[760px]"><MapView incidents={incidents} selectedId={selected?.id} onSelect={(id) => setSelected(incidents.find((row) => row.id === id) || null)} /></div>
            {selected ? <IncidentDrawer incident={selected} incidents={incidents} canReview={canReview} onClose={() => setSelected(null)} onReviewed={onReviewed} onDispatched={onDispatched} onMerged={onMerged} onStatusChanged={onStatusChanged} /> : null}
          </section>
          <section className="rounded-2xl border border-white/10 bg-white/[0.02] p-3 sm:p-4"><div className="mb-3 flex flex-wrap items-center justify-between gap-2"><div><h2 className="text-sm font-semibold text-slate-200">Pune demo-zone road condition</h2><p className="mt-1 text-xs text-slate-500">Counts exclude reports merged into a canonical incident. Zones are illustrative and are not official PMC ward boundaries.</p></div><span className="text-xs text-slate-500">Spatial store · {meta?.spatial_dedup_meters || 30} m dedup radius</span></div><div className="overflow-x-auto"><WardTable wards={wards} /></div></section>
        </> : null}
        {activeTab === "work-orders" && canSeeWorkOrders ? <WorkOrdersPanel user={user} onNotify={notify} /> : null}
        {activeTab === "devices" && canSeeDevices ? <DeviceHealthPanel user={user} onNotify={notify} /> : null}
        {activeTab === "access" && canManageUsers ? <AccessPanel user={user} onNotify={notify} /> : null}
        <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-white/5 pt-4 text-[10px] text-slate-600"><span>PavePulse · Road condition intelligence</span><span>Engineer / Worker access · Repair verification · Pune prototype</span></footer>
      </main>

      {passwordModal ? <ChangePasswordModal onClose={() => setPasswordModal(false)} onNotify={notify} /> : null}
      {toast ? <div role="status" aria-live="polite" className="fixed bottom-5 left-1/2 z-50 max-w-[calc(100%-2rem)] -translate-x-1/2 rounded-xl border border-cyan-400/20 bg-ink-900 px-4 py-3 text-sm text-cyan-100 shadow-glow">{toast}</div> : null}
    </div>
  );
}
