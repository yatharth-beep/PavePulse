import { useCallback, useEffect, useRef, useState } from "react";
import { CITY_STYLE, createMap, fallbackStyle, offlineCanvasStyle } from "../lib/mapEngine";

const SOURCE = "incidents";

function toGeoJSON(incidents) {
  return {
    type: "FeatureCollection",
    features: (Array.isArray(incidents) ? incidents : []).filter((row) => Number.isFinite(Number(row.lon)) && Number.isFinite(Number(row.lat))).map((row) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [Number(row.lon), Number(row.lat)] },
      properties: {
        id: row.id,
        severity: row.severity,
        status: row.status,
        depth_mm: Number(row.depth_mm || 0),
        hit_count: Number(row.hit_count || 1),
        weight: { critical: 3, moderate: 2, clear: 0.7 }[row.severity] || 1,
      },
    })),
  };
}


function addOperationalLayers(map, incidents, onSelect) {
  if (!map.getSource(SOURCE)) map.addSource(SOURCE, { type: "geojson", data: toGeoJSON(incidents) });

  if (!map.getLayer("heat")) {
    map.addLayer({
      id: "heat", type: "heatmap", source: SOURCE, maxzoom: 15,
      paint: {
        "heatmap-weight": ["get", "weight"],
        "heatmap-intensity": 1.15,
        "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 8, 10, 12, 24, 15, 36],
        "heatmap-opacity": 0.72,
        "heatmap-color": ["interpolate", ["linear"], ["heatmap-density"], 0, "rgba(0,0,0,0)", 0.2, "#164e63", 0.45, "#22d3ee", 0.7, "#f59e0b", 0.9, "#ef4444"],
      },
    });
  }
  if (!map.getLayer("dots")) {
    map.addLayer({
      id: "dots", type: "circle", source: SOURCE,
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["get", "depth_mm"], 5, 4, 90, 11],
        "circle-color": ["match", ["get", "status"],
          "awaiting_verification", "#a78bfa",
          "verified_fixed", "#34d399",
          ["match", ["get", "severity"], "critical", "#ef4444", "moderate", "#f59e0b", "#22d3ee"]],
        "circle-stroke-width": 1.4,
        "circle-stroke-color": "#070b12",
        "circle-opacity": 0.92,
      },
    });
  }


  // Register only once; these handlers survive map.setStyle() during tile fallback.
  if (!map.__pavePulseHandlers) {
    map.on("click", "dots", (event) => {
      const id = event.features?.[0]?.properties?.id;
      if (id) onSelect(id);
    });
    map.on("mouseenter", "dots", () => { map.getCanvas().style.cursor = "pointer"; });
    map.on("mouseleave", "dots", () => { map.getCanvas().style.cursor = ""; });
    map.__pavePulseHandlers = true;
  }
}

export default function MapView({ incidents = [], selectedId, onSelect }) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const readyRef = useRef(false);
  const fallbackStageRef = useRef(0);
  const handlersRef = useRef({ incidents, onSelect });
  const [mapError, setMapError] = useState("");
  const [loading, setLoading] = useState(true);

  handlersRef.current = { incidents, onSelect };
  const currentSelect = useCallback((id) => handlersRef.current.onSelect?.(id), []);

  useEffect(() => {
    if (!containerRef.current) return undefined;
    let disposed = false;
    let observer;
    let map;
    try {
      map = createMap(containerRef.current);
      mapRef.current = map;
      map.on("style.load", () => {
        if (disposed) return;
        try {
          addOperationalLayers(map, handlersRef.current.incidents, currentSelect);
          readyRef.current = true;
          setLoading(false);
          if (fallbackStageRef.current === 0) setMapError("");
          map.resize();
          map.getSource(SOURCE)?.setData(toGeoJSON(handlersRef.current.incidents));
        } catch (error) {
          setMapError(error.message || "Map layers could not be initialized.");
          setLoading(false);
        }
      });
      map.on("error", (event) => {
        if (disposed) return;
        const status = event?.error?.status;
        const message = event?.error?.message || "";
        const looksLikeTileFailure = status === 401 || status === 403 || status === 429 || status >= 500 || /api key|required|tile|style|failed to fetch|network/i.test(message);
        if (!looksLikeTileFailure || fallbackStageRef.current >= 2) return;
        try {
          if (fallbackStageRef.current === 0) {
            fallbackStageRef.current = 1;
            setMapError("OpenStreetMap tiles are unavailable. Trying the alternate open tile source…");
            map.setStyle(fallbackStyle());
          } else {
            fallbackStageRef.current = 2;
            setMapError("Public map tiles are unavailable. Incident overlays remain active on the offline map canvas.");
            map.setStyle(offlineCanvasStyle());
          }
        } catch {
          fallbackStageRef.current = 2;
          setMapError("Map tiles could not load. Check connectivity; incident overlays remain available when the map initializes.");
          try { map.setStyle(offlineCanvasStyle()); } catch { /* keep the map instance alive for cleanup */ }
        }
      });
      map.once("load", () => {
        if (!disposed) {
          setLoading(false);
          requestAnimationFrame(() => map.resize());
        }
      });
      if (typeof ResizeObserver !== "undefined") {
        observer = new ResizeObserver(() => map.resize());
        observer.observe(containerRef.current);
      }
      // Some dashboards reveal the map from hidden/animated layouts. Force a size pass once mounted.
      requestAnimationFrame(() => { if (!disposed) map.resize(); });
    } catch (error) {
      setLoading(false);
      setMapError(error.message || "Map initialization failed.");
    }

    return () => {
      disposed = true;
      readyRef.current = false;
      observer?.disconnect();
      map?.remove();
      mapRef.current = null;
    };
  }, [currentSelect]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !readyRef.current || !map.getSource(SOURCE)) return;
    map.getSource(SOURCE).setData(toGeoJSON(incidents));
  }, [incidents]);



  useEffect(() => {
    const map = mapRef.current;
    if (!map || !selectedId || !readyRef.current) return;
    const hit = incidents.find((row) => row.id === selectedId);
    if (hit) map.flyTo({ center: [Number(hit.lon), Number(hit.lat)], zoom: 14.6, speed: 0.8, essential: true });
  }, [selectedId, incidents]);

  return (
    <div className="relative h-full min-h-[420px] w-full overflow-hidden rounded-2xl border border-white/10 bg-slate-900">
      <div ref={containerRef} className="map-shell absolute inset-0 h-full w-full" aria-label="Interactive road condition map" />
      {loading ? <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center bg-slate-950/35 text-sm text-slate-300"><span className="mr-2 h-2 w-2 animate-pulse rounded-full bg-cyan-300" />Loading map tiles…</div> : null}
      {mapError ? <div role="status" className="absolute bottom-3 left-3 z-20 max-w-[min(420px,calc(100%-1.5rem))] rounded-lg border border-amber-300/20 bg-ink-950/90 px-3 py-2 text-xs text-amber-100">{mapError}</div> : null}
      <div className="pointer-events-none absolute left-3 top-3 z-10 rounded-xl border border-white/10 bg-ink-950/85 px-3 py-2 text-xs text-slate-300 backdrop-blur">
        <div className="mb-1 font-medium text-white">Road condition legend</div>
        <div className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-red-500" />Critical damage</div>
        <div className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-amber-400" />Moderate wear</div>
        <div className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-cyan-400" />Other reports</div>
        <div className="mt-1 flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-violet-400" />Awaiting verification</div>
        <div className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-emerald-400" />Verified fixed</div>
      </div>
      <div className="pointer-events-none absolute right-3 top-3 z-10 rounded-lg bg-ink-950/80 px-2 py-1 font-mono text-[10px] text-slate-300">{CITY_STYLE} · {Array.isArray(incidents) ? incidents.length : 0} reports</div>
      {!loading && Array.isArray(incidents) && incidents.length === 0 ? <div className="pointer-events-none absolute bottom-14 left-1/2 z-10 w-[min(420px,calc(100%-2rem))] -translate-x-1/2 rounded-xl border border-white/10 bg-ink-950/90 px-4 py-3 text-center backdrop-blur"><div className="text-sm font-medium text-white">No road reports yet</div><p className="mt-1 text-xs leading-5 text-slate-400">The map is ready. Check the API/database connection or ingest road-event records to display incident markers.</p></div> : null}
    </div>
  );
}
