"""
Map colouring written as a CSP.

    variables   = regions of the map (states / countries)
    domains     = the colours the user picked (same list for every region)
    constraints = for every pair of neighbouring regions: colours must differ
"""

import json
import os

from .solver import CSP, METHODS, different, solve

MAP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "maps")
MAP_ORDER = ["india", "usa"]

_cache = {}


def load_map(map_id):
    if map_id not in MAP_ORDER:
        raise KeyError(map_id)
    if map_id not in _cache:
        with open(os.path.join(MAP_DIR, map_id + ".json"), encoding="utf-8") as f:
            _cache[map_id] = json.load(f)
    return _cache[map_id]


def list_maps():
    out = []
    for m in MAP_ORDER:
        data = load_map(m)
        borders = sum(len(r["neighbours"]) for r in data["regions"]) // 2
        out.append({"id": m, "title": data["title"], "regions": len(data["regions"]), "borders": borders})
    return out


def build_csp(map_data, colours):
    variables = [r["id"] for r in map_data["regions"]]
    domains = {v: list(colours) for v in variables}
    constraints = []
    seen = set()
    for r in map_data["regions"]:
        for n in r["neighbours"]:
            pair = tuple(sorted((r["id"], n)))
            if pair not in seen:
                seen.add(pair)
                constraints.append(different(*pair))
    return CSP(variables, domains, constraints)


def solve_map(map_id, colours, method, record_trace=True):
    csp = build_csp(load_map(map_id), colours)
    result = solve(csp, method, record_trace)
    if result["status"] == "solved":
        result["valid"] = csp.is_solution(result["assignment"])
    return result


CRITERIA = {
    "nodes": "assignments tried",
    "backtracks": "backtracks",
    "checks": "constraint checks",
    "time_ms": "time",
}


def compare(map_id, colours, runs=3):
    """Runs every method on the same problem and picks the best one for each
    criterion. Time is the fastest of `runs` runs (to reduce noise)."""
    results = []
    for m in METHODS:
        best = None
        for _ in range(runs):
            r = solve_map(map_id, colours, m, record_trace=False)
            if best is None or r["stats"]["time_ms"] < best["stats"]["time_ms"]:
                best = r
        best.pop("trace", None)
        best.pop("assignment", None)
        results.append(best)

    finished = [r for r in results if r["status"] != "stopped"]
    best = {}
    for key in CRITERIA:
        if finished:
            # ties on the main number are broken by time
            winner = min(finished, key=lambda r: (r["stats"][key], r["stats"]["time_ms"]))
            best[key] = winner["method"]
    return {"results": results, "best": best, "criteria": CRITERIA}
