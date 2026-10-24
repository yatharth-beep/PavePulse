export const SEVERITY = {
  critical: {
    label: "Critical Damage",
    color: "#ef4444",
    chip: "bg-red-500/15 text-red-300 ring-red-500/30",
  },
  moderate: {
    label: "Moderate Wear",
    color: "#f59e0b",
    chip: "bg-amber-500/15 text-amber-200 ring-amber-500/30",
  },
  clear: {
    label: "Clear Roads",
    color: "#22d3ee",
    chip: "bg-cyan-500/15 text-cyan-200 ring-cyan-500/30",
  },
};

export function severityMeta(key) {
  return SEVERITY[key] || SEVERITY.moderate;
}

const STATUS_LABELS = {
  open: "Open",
  reviewing: "In review",
  dispatched: "Dispatched",
  in_progress: "In progress",
  awaiting_verification: "Awaiting verification",
  verified_fixed: "Verified fixed",
  resolved: "Resolved",
  cancelled: "Cancelled",
};

export function statusLabel(status) {
  return STATUS_LABELS[status] || (status || "open").replaceAll("_", " ");
}
