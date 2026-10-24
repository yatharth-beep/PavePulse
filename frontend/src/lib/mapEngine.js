import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

// Pune, Maharashtra is the demo viewport. MapLibre and OpenStreetMap tiles require no API key.
// Demo coordinates are illustrative, not official municipal reports or bus GPS tracks.
// For higher-volume production workloads, configure an OSM-derived hosted/self-managed tile service.
export const CITY_CENTER = [73.8567, 18.5204];

const openStreetMapStyle = {
  version: 8,
  name: "PavePulse · OpenStreetMap",
  sources: {
    basemap: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© <a href=\"https://www.openstreetmap.org/copyright\" target=\"_blank\" rel=\"noopener noreferrer\">OpenStreetMap contributors</a>",
      maxzoom: 19,
    },
  },
  layers: [{ id: "basemap", type: "raster", source: "basemap", paint: { "raster-fade-duration": 0 } }],
};

// A separate open OSM-derived provider is a best-effort fallback, not an SLA-backed service.
const hotFallbackStyle = {
  version: 8,
  name: "PavePulse · HOT OpenStreetMap fallback",
  sources: {
    basemap: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.fr/hot/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© <a href=\"https://www.openstreetmap.org/copyright\" target=\"_blank\" rel=\"noopener noreferrer\">OpenStreetMap contributors</a> · HOT style",
      maxzoom: 19,
    },
  },
  layers: [{ id: "basemap", type: "raster", source: "basemap", paint: { "raster-fade-duration": 0 } }],
};

// If public tiles are blocked or offline, retain a useful canvas for operational overlays.
const offlineStyle = {
  version: 8,
  name: "PavePulse · offline canvas",
  sources: {},
  layers: [{ id: "offline-background", type: "background", paint: { "background-color": "#0b1220" } }],
};

export const CITY_STYLE = "Pune, Maharashtra · OpenStreetMap";
export { maplibregl };

export function createMap(container) {
  if (!container) throw new Error("Map container is not mounted.");
  return new maplibregl.Map({
    container,
    style: openStreetMapStyle,
    center: CITY_CENTER,
    zoom: 12,
    minZoom: 3,
    maxZoom: 19,
    pitch: 0,
    attributionControl: true,
    cooperativeGestures: true,
    trackResize: true,
    fadeDuration: 0,
    validateStyle: true,
  });
}

export function fallbackStyle() {
  return hotFallbackStyle;
}

export function offlineCanvasStyle() {
  return offlineStyle;
}
