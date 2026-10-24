import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import "./index.css";

class ApplicationErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, message: "" };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, message: error?.message || "An unexpected rendering error occurred." };
  }

  componentDidCatch(error, info) {
    console.error("PavePulse view rendering failed:", error, info?.componentStack || "");
  }

  render() {
    if (this.state.hasError) {
      return (
        <main className="flex min-h-screen items-center justify-center bg-ink-950 px-5 py-10 text-slate-100">
          <section className="w-full max-w-xl rounded-2xl border border-red-300/20 bg-white/[0.03] p-6 shadow-2xl sm:p-8">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-red-400/10 font-semibold text-red-200">!</div>
            <h1 className="mt-4 text-xl font-semibold tracking-tight">This view could not be displayed</h1>
            <p className="mt-2 text-sm leading-6 text-slate-400">PavePulse caught a UI error instead of leaving the page blank. Reload the dashboard. If the problem repeats, share the error below with the project maintainer.</p>
            <pre className="mt-4 max-h-32 overflow-auto whitespace-pre-wrap break-words rounded-xl border border-white/10 bg-black/20 p-3 text-xs text-red-100">{this.state.message}</pre>
            <button type="button" onClick={() => window.location.reload()} className="mt-5 rounded-xl bg-cyan-300 px-4 py-2.5 text-sm font-semibold text-ink-950">Reload PavePulse</button>
          </section>
        </main>
      );
    }
    return this.props.children;
  }
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <ApplicationErrorBoundary>
      <App />
    </ApplicationErrorBoundary>
  </React.StrictMode>,
);
