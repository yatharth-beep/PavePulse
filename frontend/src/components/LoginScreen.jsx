import { useState } from "react";

const DEMO_ACCOUNTS = [
  {
    role: "Engineer",
    username: "engineer",
    password: "engineer123",
    description: "Explore the Pune dashboard, review incidents, dispatch work and manage the demo team.",
  },
  {
    role: "Worker",
    username: "worker",
    password: "worker123",
    description: "View assigned work, update repair progress and submit completion notes or evidence.",
  },
];

export default function LoginScreen({ onLogin }) {
  const [username, setUsername] = useState("engineer");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function selectDemoAccount(account) {
    setUsername(account.username);
    setPassword(account.password);
    setError("");
  }

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await onLogin(username.trim(), password);
    } catch (err) {
      setError(err.message || "Sign-in failed. Check the account and try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen px-4 py-6 sm:px-6 sm:py-10">
      <div className="mx-auto grid w-full max-w-6xl overflow-hidden rounded-3xl border border-white/10 bg-ink-900/90 shadow-2xl lg:grid-cols-[0.95fr_1.05fr]">
        <section className="relative flex min-h-[310px] flex-col justify-between overflow-hidden border-b border-white/10 p-6 sm:p-9 lg:min-h-[760px] lg:border-b-0 lg:border-r lg:p-10">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_25%_20%,rgba(34,211,238,0.20),transparent_44%),radial-gradient(ellipse_at_80%_90%,rgba(14,165,233,0.14),transparent_40%)]" />
          <div className="relative flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-cyan-300 text-base font-bold text-ink-950">PP</div>
            <div><div className="text-lg font-semibold text-white">PavePulse</div><div className="text-xs text-slate-400">Road intelligence platform</div></div>
          </div>
          <div className="relative mt-10 max-w-md lg:mt-0">
            <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-cyan-400/20 bg-cyan-400/10 px-3 py-1.5 text-xs text-cyan-200"><span className="h-1.5 w-1.5 rounded-full bg-cyan-300" /> PUNE · PROTOTYPE DEMO</div>
            <h1 className="text-3xl font-semibold leading-tight tracking-tight text-white sm:text-4xl">Find road defects earlier. Move repairs forward.</h1>
            <p className="mt-4 text-sm leading-6 text-slate-400">Explore the road-condition workflow, from incident review and repair assignment to independent verification after a repair.</p>
            <div className="mt-7 grid grid-cols-3 gap-2 sm:gap-3">
              {[['01', 'Detect'], ['02', 'Dispatch'], ['03', 'Verify']].map(([number, label]) => <div key={number} className="rounded-xl border border-white/10 bg-white/[0.035] p-3"><div className="font-mono text-xs text-cyan-300">{number}</div><div className="mt-2 text-sm text-slate-200">{label}</div></div>)}
            </div>
          </div>
          <div className="relative mt-8 text-xs leading-5 text-slate-500 lg:mt-0">Prototype for review and workflow testing. Pune incidents and map locations are illustrative, not official PMC reports.</div>
        </section>

        <section className="min-w-0 p-5 sm:p-8 lg:p-10">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div><div className="text-xs font-semibold uppercase tracking-[0.22em] text-cyan-300">Reviewer access</div><h2 className="mt-2 text-2xl font-semibold text-white">Welcome to PavePulse</h2><p className="mt-2 text-sm leading-6 text-slate-400">Choose a demo role below or enter the assigned credentials.</p></div>
            <a href="/reviewer-guide.pdf" target="_blank" rel="noreferrer" className="inline-flex shrink-0 items-center gap-2 rounded-xl border border-cyan-300/30 bg-cyan-300/10 px-3 py-2.5 text-xs font-semibold text-cyan-100 transition hover:bg-cyan-300/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300"><span aria-hidden="true">↗</span> Open reviewer guide (PDF)</a>
          </div>

          <div className="mt-6 rounded-2xl border border-amber-300/25 bg-amber-300/[0.07] p-4">
            <div className="flex items-start gap-3"><div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-amber-200/10 text-lg text-amber-100" aria-hidden="true">i</div><div><h3 className="text-sm font-semibold text-amber-100">Quick start for reviewers</h3><p className="mt-1 text-xs leading-5 text-amber-100/75">The PDF includes step-by-step instructions and illustrated screens. Demo accounts are shared for evaluation only; do not enter personal or sensitive information.</p></div></div>
          </div>

          <div className="mt-5 grid gap-3 sm:grid-cols-2">
            {DEMO_ACCOUNTS.map((account) => <article key={account.role} className="flex min-w-0 flex-col rounded-2xl border border-white/10 bg-white/[0.025] p-4 transition hover:border-cyan-300/25 hover:bg-white/[0.04]">
              <div className="flex items-center justify-between gap-2"><h3 className="text-sm font-semibold text-white">{account.role}</h3><span className="rounded-full border border-white/10 bg-white/[0.04] px-2 py-1 text-[10px] text-slate-400">Demo account</span></div>
              <p className="mt-2 min-h-[54px] text-xs leading-5 text-slate-400">{account.description}</p>
              <dl className="mt-3 space-y-2 rounded-xl bg-ink-950/70 p-3 text-xs">
                <div className="flex items-center justify-between gap-2"><dt className="text-slate-500">Username</dt><dd className="font-mono font-medium text-slate-100">{account.username}</dd></div>
                <div className="flex items-center justify-between gap-2"><dt className="text-slate-500">Password</dt><dd className="font-mono font-medium text-cyan-100">{account.password}</dd></div>
              </dl>
              <button type="button" onClick={() => selectDemoAccount(account)} className="mt-3 w-full rounded-xl border border-cyan-300/20 px-3 py-2.5 text-xs font-semibold text-cyan-100 transition hover:bg-cyan-300/10">Use {account.role} account</button>
            </article>)}
          </div>

          <form onSubmit={submit} className="mt-6 space-y-4 border-t border-white/10 pt-6">
            <div><div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Sign in</div><p className="mt-1 text-xs text-slate-500">You can enter a username or its registered email.</p></div>
            <label className="block text-sm text-slate-300">Username or email<input autoComplete="username" autoFocus className="mt-2 w-full rounded-xl border border-white/10 bg-ink-950 px-4 py-3 text-sm text-white outline-none transition placeholder:text-slate-600 focus:border-cyan-400/60" value={username} onChange={(e) => setUsername(e.target.value)} placeholder="engineer or engineer@pavepulse.local" required /></label>
            <label className="block text-sm text-slate-300">Password<input autoComplete="current-password" type="password" className="mt-2 w-full rounded-xl border border-white/10 bg-ink-950 px-4 py-3 text-sm text-white outline-none transition placeholder:text-slate-600 focus:border-cyan-400/60" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Enter the demo password" required /></label>
            {error ? <div role="alert" className="rounded-xl border border-red-400/20 bg-red-400/10 px-3 py-2.5 text-sm leading-5 text-red-200">{error}</div> : null}
            <button type="submit" disabled={busy || !username.trim() || !password} className="w-full rounded-xl bg-cyan-300 px-4 py-3 font-semibold text-ink-950 transition hover:bg-cyan-200 disabled:cursor-not-allowed disabled:opacity-50">{busy ? "Signing in…" : "Sign in to PavePulse"}</button>
          </form>
          <div className="mt-4 flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-500"><span>Engineer + Worker access</span><a href="/reviewer-guide.pdf" target="_blank" rel="noreferrer" className="text-cyan-200 underline decoration-cyan-200/30 underline-offset-4 hover:text-cyan-100">Need help? Read the guide</a></div>
        </section>
      </div>
    </main>
  );
}
