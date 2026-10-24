import { createClient } from "@supabase/supabase-js";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;
if (!supabaseUrl || !supabaseAnonKey) {
  // Don't let Supabase throw an opaque initialization error during the React render.
  console.error("PavePulse configuration is incomplete: set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY.");
}
const supabase = createClient(supabaseUrl || "https://missing-project.supabase.co", supabaseAnonKey || "missing-anon-key");
const API = String(import.meta.env.VITE_API_BASE || "").trim().replace(/\/+$/, "");
let accessToken = typeof window === "undefined" ? "" : window.sessionStorage.getItem("pavepulse_token") || "";

function setAccessToken(token) {
  accessToken = token || "";
  if (typeof window !== "undefined") {
    if (accessToken) window.sessionStorage.setItem("pavepulse_token", accessToken);
    else window.sessionStorage.removeItem("pavepulse_token");
  }
}

// Keep the API bearer token aligned with Supabase's automatic token refresh.
supabase.auth.onAuthStateChange((event, session) => {
  if (session?.access_token) setAccessToken(session.access_token);
  else if (event === "SIGNED_OUT") setAccessToken("");
});

function apiUrl(path) {
  if (import.meta.env.PROD && !API) {
    throw new Error("PavePulse API URL is not configured. In Vercel, set VITE_API_BASE to your deployed FastAPI service URL, then redeploy the frontend.");
  }
  return `${API}${path}`;
}

function headers(extra = {}) {
  return {
    ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    ...extra,
  };
}

async function request(path, options = {}) {
  const url = apiUrl(path);
  let res;
  try {
    res = await fetch(url, {
      ...options,
      headers: headers({ ...(options.body && !(options.body instanceof FormData) ? { "Content-Type": "application/json" } : {}), ...(options.headers || {}) }),
    });
  } catch (error) {
    throw new Error(`Could not reach the PavePulse API at ${API || "the local API proxy"}. Check the backend deployment and its URL. ${error?.message || ""}`.trim());
  }

  const contentType = res.headers.get("content-type") || "";
  let data;
  if (contentType.includes("application/json")) {
    try { data = await res.json(); }
    catch { throw new Error(`The API returned invalid JSON for ${path}. Check the backend logs.`); }
  } else {
    const text = await res.text();
    if (res.ok) {
      throw new Error(`The request ${path} returned a webpage instead of JSON. VITE_API_BASE must point to the FastAPI backend, not the Vercel frontend.`);
    }
    // Avoid showing a full HTML error page inside the dashboard when the API host is wrong.
    throw new Error(`The API request ${path} returned HTTP ${res.status} without a JSON response. Check VITE_API_BASE and the backend deployment. ${text.slice(0, 160).replace(/\s+/g, " ")}`);
  }

  if (!res.ok) {
    const message = typeof data === "object" && data !== null ? data.detail || data.message : data;
    const error = new Error(message || `${path} failed (${res.status})`);
    error.status = res.status;
    throw error;
  }
  return data;
}

async function requestArray(path, options = {}) {
  const result = await request(path, options);
  if (!Array.isArray(result)) {
    throw new Error(`The API returned an unexpected data format for ${path}. Expected a list. Check the backend URL and server logs.`);
  }
  return result;
}

export const api = {
  setToken(token) {
    setAccessToken(token);
  },
  authHeaders: () => headers(),
  signOut: async () => {
    api.setToken("");
    try { await supabase.auth.signOut(); } catch { /* local UI is signed out regardless */ }
  },
  health: () => request("/api/v1/health"),
  meta: () => request("/api/v1/meta"),
  login: async (username, password) => {
    if (!supabaseUrl || !supabaseAnonKey) throw new Error("Supabase frontend configuration is missing. Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY in Vercel, then redeploy.");
    const input = username.trim();
    const email = input.includes("@") ? input.toLowerCase() : `${input.toLowerCase()}@pavepulse.local`;
    const { data, error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) throw error;
    const token = data?.session?.access_token;
    if (!token) {
      await supabase.auth.signOut();
      throw new Error("Supabase did not return an active session. Check the account and password.");
    }
    api.setToken(token);
    try {
      // The API is authoritative for active status and role-based access.
      const user = await request("/api/v1/auth/me");
      if (!user || !["engineer", "worker"].includes(user.role)) throw new Error("This account does not have an authorized PavePulse role.");
      return { access_token: token, user };
    } catch (apiError) {
      await api.signOut();
      throw apiError;
    }
  },
  me: () => request("/api/v1/auth/me"),
  changePassword: async ({ current_password, new_password }) => {
    const { data: currentData, error: currentError } = await supabase.auth.getUser();
    if (currentError || !currentData?.user?.email) throw new Error("Your Supabase session has expired. Sign in again.");
    const { error: verifyError } = await supabase.auth.signInWithPassword({ email: currentData.user.email, password: current_password });
    if (verifyError) throw new Error("Current password is incorrect.");
    const { error } = await supabase.auth.updateUser({ password: new_password });
    if (error) throw error;
    const { data: sessionData } = await supabase.auth.getSession();
    if (sessionData?.session?.access_token) api.setToken(sessionData.session.access_token);
    return { ok: true, access_token: sessionData?.session?.access_token };
  },
  users: () => requestArray("/api/v1/auth/users"),
  workers: () => requestArray("/api/v1/auth/workers"),
  // Public application accounts are provisioned in Supabase Auth. A local SQL user alone
  // cannot authenticate with Supabase, so the UI must not report it as a created account.
  createUser: async () => {
    throw new Error("Create the account in Supabase Dashboard → Authentication → Users, then authorize its email in SUPABASE_WORKER_EMAILS or assign a server-controlled app_metadata.role and redeploy the API.");
  },
  setUserActive: (id, isActive) => request(`/api/v1/auth/users/${id}/active?is_active=${isActive}`, { method: "PATCH" }),
  summary: () => request("/api/v1/analytics/summary"),
  wards: () => requestArray("/api/v1/analytics/wards"),
  incidents: async (params = {}) => {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params || {})) {
      if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
    }
    return requestArray(`/api/v1/incidents${query.size ? `?${query.toString()}` : ""}`);
  },
  incident: (id) => request(`/api/v1/incidents/${encodeURIComponent(id)}`),
  reviewIncident: (id, note = "") => request(`/api/v1/incidents/${id}/review`, { method: "POST", body: JSON.stringify({ status: "reviewing", note }) }),
  setIncidentStatus: (id, status, note = "") => request(`/api/v1/incidents/${id}/status`, { method: "PATCH", body: JSON.stringify({ status, note }) }),
  mergeIncident: (id, duplicateId) => request(`/api/v1/incidents/${id}/merge`, { method: "POST", body: JSON.stringify({ duplicate_id: duplicateId, note: "Merged by municipal dashboard" }) }),
  dispatch: (id) => request(`/api/v1/incidents/${id}/dispatch`, { method: "POST" }),
  workOrders: () => requestArray("/api/v1/work-orders"),
  updateWorkOrder: (id, payload) => request(`/api/v1/work-orders/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  uploadWorkOrderEvidence: async (id, file) => {
    const form = new FormData();
    form.append("file", file);
    return request(`/api/v1/work-orders/${id}/evidence`, { method: "POST", body: form });
  },
  downloadWorkOrderEvidence: async (id, evidenceId) => {
    const response = await fetch(apiUrl(`/api/v1/work-orders/${id}/evidence/${evidenceId}`), { headers: headers() });
    if (!response.ok) {
      const contentType = response.headers.get("content-type") || "";
      const data = contentType.includes("application/json") ? await response.json() : await response.text();
      throw new Error(typeof data === "object" && data !== null ? data.detail || data.message : data || "Evidence download failed.");
    }
    return response.blob();
  },
  telemetryDevices: () => requestArray("/api/v1/telemetry/devices"),
  registerDevice: (payload) => request("/api/v1/telemetry/devices", { method: "POST", body: JSON.stringify(payload) }),
  rotateDeviceCredential: (label) => request(`/api/v1/telemetry/devices/${encodeURIComponent(label)}/credentials`, { method: "POST" }),
};
