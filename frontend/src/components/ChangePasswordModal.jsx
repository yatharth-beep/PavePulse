import { useState } from "react";
import { api } from "../api";

export default function ChangePasswordModal({ onClose, onNotify }) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setError("");
    if (newPassword !== confirmPassword) { setError("New passwords do not match."); return; }
    if (newPassword.length < 14) { setError("Use at least 14 characters for the new password."); return; }
    setBusy(true);
    try {
      const result = await api.changePassword({ current_password: currentPassword, new_password: newPassword });
      if (result.access_token) api.setToken(result.access_token);
      onNotify?.("Password changed successfully.");
      onClose();
    } catch (err) { setError(err.message || "Could not change password."); }
    finally { setBusy(false); }
  }

  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><section role="dialog" aria-modal="true" aria-labelledby="change-password-title" className="w-full max-w-md rounded-2xl border border-white/10 bg-ink-900 p-6 shadow-2xl"><div className="flex items-start justify-between gap-3"><div><h2 id="change-password-title" className="text-lg font-semibold text-white">Change password</h2><p className="mt-1 text-xs text-slate-500">Use a unique passphrase with at least 14 characters.</p></div><button onClick={onClose} className="rounded-lg px-2 py-1 text-slate-400 hover:bg-white/5">Close</button></div><form onSubmit={submit} className="mt-5 space-y-4"><label className="block text-xs text-slate-400">Current password<input type="password" autoComplete="current-password" required className="mt-1 w-full rounded-xl border border-white/10 bg-ink-950 px-3 py-2.5 text-sm text-white outline-none focus:border-cyan-400/40" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} /></label><label className="block text-xs text-slate-400">New password<input type="password" autoComplete="new-password" required minLength={14} className="mt-1 w-full rounded-xl border border-white/10 bg-ink-950 px-3 py-2.5 text-sm text-white outline-none focus:border-cyan-400/40" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} /></label><label className="block text-xs text-slate-400">Confirm new password<input type="password" autoComplete="new-password" required minLength={14} className="mt-1 w-full rounded-xl border border-white/10 bg-ink-950 px-3 py-2.5 text-sm text-white outline-none focus:border-cyan-400/40" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} /></label>{error ? <div role="alert" className="rounded-lg border border-red-400/20 bg-red-400/10 px-3 py-2 text-xs text-red-200">{error}</div> : null}<button disabled={busy} className="w-full rounded-xl bg-cyan-300 px-4 py-3 text-sm font-semibold text-ink-950 disabled:opacity-50">{busy ? "Updating…" : "Update password"}</button></form></section></div>;
}
