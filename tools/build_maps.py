"""
Builds the map files in data/maps/ from the raw GeoJSON files in data/raw/.

You do NOT need to run this to use the website - the output files are already
included. It is kept so the datasets can be rebuilt or checked.

Needs: pip install shapely

For every map it writes one JSON file with:
  - regions:   id, name, SVG path, label position
  - neighbours (computed from shared borders, point contacts ignored)
"""

import json
import math
import os
from collections import deque

from shapely.geometry import shape, mapping
from shapely.ops import unary_union, transform

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "maps")

WIDTH = 1000  # every map is scaled to this SVG width


def load(name):
    with open(os.path.join(RAW, name), encoding="utf-8") as f:
        return json.load(f)["features"]


def albers(lon0, lat0, lat1, lat2):
    """Albers equal-area conic projection (returns a function lon,lat -> x,y)."""
    r = math.radians
    p1, p2, p0 = r(lat1), r(lat2), r(lat0)
    n = (math.sin(p1) + math.sin(p2)) / 2
    c = math.cos(p1) ** 2 + 2 * n * math.sin(p1)
    rho0 = math.sqrt(c - 2 * n * math.sin(p0)) / n

    def proj(lon, lat, z=None):
        rho = math.sqrt(c - 2 * n * math.sin(r(lat))) / n
        theta = n * r(lon - lon0)
        return rho * math.sin(theta), -(rho0 - rho * math.cos(theta))

    return proj


def clean(geom):
    # closes hairline gaps left between district polygons after a union
    return geom.buffer(0.0005).buffer(-0.0005)


def shared_border(a, b, eps):
    if not a.buffer(eps).intersects(b):
        return 0.0
    return a.boundary.intersection(b.buffer(eps)).length


def path_d(geom):
    parts = []
    polys = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
    for poly in polys:
        for ring in [poly.exterior, *poly.interiors]:
            pts = list(ring.coords)[:-1]
            if len(pts) < 3:
                continue
            s = "M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + "Z"
            parts.append(s)
    return "".join(parts)


def bfs_order(ids, nbrs):
    """Fixed variable order: breadth-first from the region with most neighbours,
    so each region (after the first) is next to one that came before it."""
    left = set(ids)
    order = []
    while left:
        start = max(sorted(left), key=lambda i: len(nbrs[i]))
        q = deque([start])
        left.discard(start)
        while q:
            v = q.popleft()
            order.append(v)
            for w in sorted(nbrs[v], key=lambda i: (-len(nbrs[i]), i)):
                if w in left:
                    left.discard(w)
                    q.append(w)
    return order


def build(map_id, title, regions, proj, eps=0.01, min_len=0.05, simplify=0.7, note=""):
    """regions: list of (id, name, shapely geometry in lon/lat)."""
    ids = [r[0] for r in regions]
    geo = {r[0]: r[2] for r in regions}
    names = {r[0]: r[1] for r in regions}

    nbrs = {i: set() for i in ids}
    for i_idx, a in enumerate(ids):
        for b in ids[i_idx + 1:]:
            if shared_border(geo[a], geo[b], eps) >= min_len:
                nbrs[a].add(b)
                nbrs[b].add(a)

    projected = {i: transform(proj, geo[i]) for i in ids}
    minx = min(g.bounds[0] for g in projected.values())
    miny = min(g.bounds[1] for g in projected.values())
    maxx = max(g.bounds[2] for g in projected.values())
    maxy = max(g.bounds[3] for g in projected.values())
    k = WIDTH / (maxx - minx)
    pad = 12
    height = (maxy - miny) * k

    def fit(x, y, z=None):
        return (x - minx) * k + pad, (y - miny) * k + pad

    out_regions = []
    for i in bfs_order(ids, nbrs):
        g = transform(fit, projected[i])
        g_s = g.simplify(simplify, preserve_topology=True)
        lab = g.representative_point()
        bx = g.bounds
        small = max(bx[2] - bx[0], bx[3] - bx[1]) < 14
        out_regions.append({
            "id": i,
            "name": names[i],
            "path": path_d(g_s),
            "label": [round(lab.x, 1), round(lab.y, 1)],
            "small": small,
            "area": round(g.area),
            "neighbours": sorted(nbrs[i]),
        })

    data = {
        "id": map_id,
        "title": title,
        "note": note,
        "viewBox": [0, 0, round(WIDTH + 2 * pad), round(height + 2 * pad)],
        "regions": out_regions,
    }
    with open(os.path.join(OUT, f"{map_id}.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    edges = sum(len(v) for v in nbrs.values()) // 2
    size = os.path.getsize(os.path.join(OUT, f"{map_id}.json")) // 1024
    print(f"{map_id}: {len(ids)} regions, {edges} borders, {size} KB")
    for r in out_regions:
        print(f"   {r['id']:4} {r['name'][:28]:28} {', '.join(r['neighbours'])}")


# ---------------------------------------------------------------- India
INDIA_CODES = {
    "Andaman and Nicobar Islands": "AN", "Andhra Pradesh": "AP", "Arunachal Pradesh": "AR",
    "Assam": "AS", "Bihar": "BR", "Chandigarh": "CH", "Chhattisgarh": "CG",
    "Dadra and Nagar Haveli and Daman and Diu": "DD", "Delhi": "DL", "Goa": "GA",
    "Gujarat": "GJ", "Haryana": "HR", "Himachal Pradesh": "HP", "Jammu and Kashmir": "JK",
    "Jharkhand": "JH", "Karnataka": "KA", "Kerala": "KL", "Ladakh": "LA", "Lakshadweep": "LD",
    "Madhya Pradesh": "MP", "Maharashtra": "MH", "Manipur": "MN", "Meghalaya": "ML",
    "Mizoram": "MZ", "Nagaland": "NL", "Odisha": "OD", "Puducherry": "PY", "Punjab": "PB",
    "Rajasthan": "RJ", "Sikkim": "SK", "Tamil Nadu": "TN", "Telangana": "TS", "Tripura": "TR",
    "Uttar Pradesh": "UP", "Uttarakhand": "UK", "West Bengal": "WB",
}
INDIA_NAMES = {"Dadra and Nagar Haveli and Daman and Diu": "Dadra & Nagar Haveli and Daman & Diu",
               "Andaman and Nicobar Islands": "Andaman & Nicobar Islands",
               "Jammu and Kashmir": "Jammu & Kashmir"}


def india():
    groups = {}
    for f in load("india_districts.geojson"):
        st = f["properties"]["st_nm"]
        groups.setdefault(st, []).append(shape(f["geometry"]).buffer(0))
    regions = []
    for st, geoms in groups.items():
        regions.append((INDIA_CODES[st], INDIA_NAMES.get(st, st), clean(unary_union(geoms))))
    build("india", "India - States & UTs", regions, albers(82, 22, 12, 30),
          note="28 states and 8 union territories. Islands have no land neighbours.")


# ---------------------------------------------------------------- USA
US_CODES = {
    "Alabama": "AL", "Arizona": "AZ", "Arkansas": "AR", "California": "CA", "Colorado": "CO",
    "Connecticut": "CT", "Delaware": "DE", "Florida": "FL", "Georgia": "GA", "Idaho": "ID",
    "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS", "Kentucky": "KY",
    "Louisiana": "LA", "Maine": "ME", "Maryland": "MD", "Massachusetts": "MA", "Michigan": "MI",
    "Minnesota": "MN", "Mississippi": "MS", "Missouri": "MO", "Montana": "MT", "Nebraska": "NE",
    "Nevada": "NV", "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM",
    "New York": "NY", "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH",
    "Oklahoma": "OK", "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI",
    "South Carolina": "SC", "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT",
    "Vermont": "VT", "Virginia": "VA", "Washington": "WA", "West Virginia": "WV",
    "Wisconsin": "WI", "Wyoming": "WY",
}


def usa():
    geoms = {}
    for f in load("us_states.geojson"):
        n = f["properties"]["name"]
        if n == "District of Columbia":
            n = "Maryland"
        if n not in US_CODES:
            continue  # Alaska, Hawaii, Puerto Rico
        geoms.setdefault(n, []).append(shape(f["geometry"]).buffer(0))
    regions = [(US_CODES[n], n, unary_union(g).buffer(0.001).buffer(-0.001)) for n, g in geoms.items()]
    build("usa", "USA - 48 States", regions, albers(-96, 37.5, 29.5, 45.5), simplify=0.6,
          note="The 48 contiguous states. States meeting only at a point (Four Corners) are not neighbours.")


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    india()
    usa()
