# CSP Solver - Map Colouring

A generic Constraint Satisfaction Problem solver written in Python, tested on
map colouring on two maps: India and the USA. It has a website to pick
a map and colours, watch the solver step by step, and compare the three methods.

## Run it

Needs Python 3.8 or newer. Nothing else to install.

- Windows: double-click `run.bat`
- Any OS: `python app.py`, then open http://localhost:8000

Command-line test (both maps, all methods, 4 / 3 / 2 colours):

    python test_map_colouring.py

## Deploy it

The site is one Python process, so any host that runs Python works.

- **Render**: New > Web Service > connect the repo. Start command `python app.py`
  (already in `render.yaml`). The app reads the `PORT` variable on its own.
- **Railway / Heroku-style hosts**: uses the `Procfile` (`web: python app.py`).
- **PythonAnywhere / a VPS**: run `python app.py 8000` behind the web server.

## Files

| Path | What it is |
|---|---|
| `csp/solver.py` | The generic CSP solver: `Constraint`, `CSP`, `Solver` (backtracking, forward checking, AC-3) |
| `csp/map_colouring.py` | Turns a map into a CSP and runs the comparison |
| `app.py` | Web server (Python standard library) and the JSON API |
| `web/` | The page: `index.html`, `style.css`, `app.js` (draws the map, replays the solver steps) |
| `data/maps/` | Ready-to-use maps: regions, SVG outlines, neighbour lists |
| `data/raw/` | Original GeoJSON datasets the maps were built from |
| `tools/build_maps.py` | Rebuilds `data/maps/` from `data/raw/` (needs `shapely`; not needed to run) |
| `test_map_colouring.py` | Command-line test |

## How the solver works

**Variables** are the regions, **domains** are the chosen colours, and each pair of
neighbouring regions has a **constraint** `colour(A) != colour(B)`. The solver
itself does not know about maps; any CSP with binary constraints can be given to it.

Regions are assigned in a fixed order (breadth-first from the region with the most
neighbours, so each region comes after one it touches). Colours are tried in the
order they were chosen.

1. **Backtracking** - give the next region a colour, check it against the neighbours
   that already have one. If it clashes try the next colour; if none fit, undo the
   previous region and try its next colour.
2. **Backtracking + Forward checking** - after each assignment, remove that colour
   from the domains of the uncoloured neighbours. If any neighbour is left with no
   colours, the assignment is undone straight away.
3. **Backtracking + Constraint propagation (AC-3)** - run AC-3 once before searching,
   then after every assignment. AC-3 keeps removing a colour from a region whenever
   some neighbour has no colour left that works with it, and repeats until nothing
   changes.

Measured for each run: assignments tried, backtracks, constraint checks,
values pruned and time. The comparison picks the best method for the chosen measure
(ties are broken by time).

## Failure case

With **2 colours** both maps have no solution, because each one has three
regions that all border each other (e.g. Uttar Pradesh, Bihar and Jharkhand).
All three methods search and correctly report "no solution".

## Map data

- India: udit-001/india-maps-data (districts joined into 28 states + 8 UTs)
- USA: PublicaMundi/MappingAPI (48 contiguous states)

Neighbours are worked out from shared borders; regions that only touch at a point
(like the Four Corners in the USA) are not neighbours.
