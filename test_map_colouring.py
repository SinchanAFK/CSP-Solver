"""
Command-line test of the CSP solver on map colouring.

    python test_map_colouring.py

For every map it runs all three methods with 4, 3 and 2 colours, checks that
every solution found is valid, and that 2 colours is reported as impossible.
"""

from csp.map_colouring import MAP_ORDER, compare, load_map, solve_map

COLOURS = ["Red", "Green", "Blue", "Yellow"]


def main():
    failures = 0
    for map_id in MAP_ORDER:
        title = load_map(map_id)["title"]
        print(f"\n=== {title} ===")
        print(f"{'colours':>7}  {'method':<46} {'result':<12} {'assign':>7} {'backtr':>7} {'checks':>8} {'ms':>8}")
        for k in (4, 3, 2):
            colours = COLOURS[:k]
            for r in compare(map_id, colours, runs=1)["results"]:
                s = r["stats"]
                print(f"{k:>7}  {r['method_name']:<46} {r['status']:<12} {s['nodes']:>7} "
                      f"{s['backtracks']:>7} {s['checks']:>8} {s['time_ms']:>8.2f}")
            # every solution must actually satisfy all constraints
            for m in ("bt", "fc", "mac"):
                full = solve_map(map_id, colours, m, record_trace=False)
                if full["status"] == "solved" and not full["valid"]:
                    print("   !! invalid solution from", m)
                    failures += 1
                if k == 2 and full["status"] != "no_solution":
                    print("   !! 2 colours should have no solution, got", full["status"])
                    failures += 1

    print("\nAll checks passed." if failures == 0 else f"\n{failures} check(s) FAILED.")
    return failures


if __name__ == "__main__":
    raise SystemExit(1 if main() else 0)
