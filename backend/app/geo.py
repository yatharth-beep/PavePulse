"""Illustrative Pune, Maharashtra geometry used by the PavePulse demo.

These are rectangular demo zones around known Pune-area localities, not official
Pune Municipal Corporation ward boundaries. Real deployments should import
validated ward polygons from the relevant municipal GIS authority.
"""

# Coarse demo zones cover the Pune urban area from Baner/Aundh in the west to
# Viman Nagar/Kharadi in the east, and from the northern suburbs to Hadapsar.
WARDS = [
    {
        "code": "W01",
        "name": "Baner–Aundh Corridor",
        "bounds": (73.730, 18.550, 73.820, 18.620),
    },
    {
        "code": "W02",
        "name": "University–North Pune",
        "bounds": (73.820, 18.550, 73.890, 18.620),
    },
    {
        "code": "W03",
        "name": "Viman Nagar–Kharadi",
        "bounds": (73.890, 18.550, 73.970, 18.620),
    },
    {
        "code": "W04",
        "name": "Pashan–Bavdhan Corridor",
        "bounds": (73.730, 18.500, 73.820, 18.550),
    },
    {
        "code": "W05",
        "name": "Deccan–Shivajinagar Core",
        "bounds": (73.820, 18.500, 73.890, 18.550),
    },
    {
        "code": "W06",
        "name": "Koregaon Park–Yerawada",
        "bounds": (73.890, 18.500, 73.970, 18.550),
    },
    {
        "code": "W07",
        "name": "Kothrud–Warje Corridor",
        "bounds": (73.730, 18.460, 73.820, 18.500),
    },
    {
        "code": "W08",
        "name": "Swargate–Hadapsar Corridor",
        "bounds": (73.820, 18.460, 73.970, 18.500),
    },
]

# MapLibre expects [longitude, latitude]. Pune city centre is approximately
# 18.5204 N, 73.8567 E.
CITY_CENTER = (73.8567, 18.5204)

# Synthetic demo routes through well-known Pune localities. These are not
# representations of official PMPML routes or surveyed bus GPS tracks.
ROUTES = {
    # Baner / Aundh → Shivajinagar → Camp → Hadapsar
    "R12": [
        (73.7850, 18.5600),
        (73.8080, 18.5520),
        (73.8360, 18.5370),
        (73.8490, 18.5290),
        (73.8660, 18.5160),
        (73.8920, 18.5090),
        (73.9250, 18.5070),
    ],
    # Wakad / Aundh → Pashan → Kothrud → Swargate
    "R18": [
        (73.7630, 18.5990),
        (73.7780, 18.5700),
        (73.7970, 18.5570),
        (73.8110, 18.5400),
        (73.8070, 18.5160),
        (73.8280, 18.4980),
        (73.8580, 18.4800),
    ],
    # Kharadi / Viman Nagar → Koregaon Park → Camp → south Pune
    "R22": [
        (73.9360, 18.5670),
        (73.9180, 18.5550),
        (73.9130, 18.5430),
        (73.8960, 18.5360),
        (73.8790, 18.5220),
        (73.8620, 18.5070),
        (73.8660, 18.4650),
    ],
    # Kothrud → Deccan → Shivajinagar → Yerawada → Viman Nagar
    "R31": [
        (73.7920, 18.5070),
        (73.8120, 18.5150),
        (73.8350, 18.5230),
        (73.8510, 18.5310),
        (73.8720, 18.5390),
        (73.8960, 18.5500),
        (73.9250, 18.5660),
    ],
}


def box_wkt(bounds: tuple[float, float, float, float]) -> str:
    minx, miny, maxx, maxy = bounds
    return f"POLYGON(({minx} {miny}, {maxx} {miny}, {maxx} {maxy}, {minx} {maxy}, {minx} {miny}))"


def parse_box_wkt(wkt: str) -> tuple[float, float, float, float]:
    body = wkt.replace("POLYGON((", "").replace("))", "").strip()
    xs, ys = [], []
    for pair in body.split(","):
        lon_s, lat_s = pair.strip().split()
        xs.append(float(lon_s))
        ys.append(float(lat_s))
    return min(xs), min(ys), max(xs), max(ys)


def point_in_bounds(lon: float, lat: float, bounds: tuple[float, float, float, float]) -> bool:
    minx, miny, maxx, maxy = bounds
    return minx <= lon <= maxx and miny <= lat <= maxy


def assign_ward(lon: float, lat: float) -> str | None:
    for ward in WARDS:
        if point_in_bounds(lon, lat, ward["bounds"]):
            return ward["code"]
    # Keep an explicit fallback for events just outside the simplified demo grid.
    return "W05"


def interpolate_route(route_id: str, t: float) -> tuple[float, float]:
    pts = ROUTES[route_id]
    t = t % 1.0
    total_seg = len(pts) - 1
    scaled = t * total_seg
    i = min(int(scaled), total_seg - 1)
    frac = scaled - i
    lon = pts[i][0] + (pts[i + 1][0] - pts[i][0]) * frac
    lat = pts[i][1] + (pts[i + 1][1] - pts[i][1]) * frac
    return lon, lat
