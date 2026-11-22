"""
A generic CSP (Constraint Satisfaction Problem) solver.

A CSP has three parts:
    variables    - the things we have to give a value to
    domains      - the values each variable is allowed to take
    constraints  - rules that say which value combinations are allowed

The solver supports three search methods:
    "bt"   plain backtracking
    "fc"   backtracking + forward checking
    "mac"  backtracking + constraint propagation (AC-3, run before the
           search and again after every assignment)

Nothing here knows about maps. Map colouring is only one CSP that is built
on top of this file (see map_colouring.py).
"""

import time
from collections import deque


# --------------------------------------------------------------------------
# Problem definition
# --------------------------------------------------------------------------

class Constraint:
    """A binary constraint between variables x and y.

    `relation(a, b)` returns True when x = a and y = b is allowed.
    Any rule can be used, e.g. lambda a, b: a != b  for "must be different".
    """

    def __init__(self, x, y, relation, name="custom"):
        self.x = x
        self.y = y
        self.relation = relation
        self.name = name

    def allows(self, var, value, other_value):
        """Is var = value allowed when the other variable has other_value?"""
        if var == self.x:
            return self.relation(value, other_value)
        return self.relation(other_value, value)

    def other(self, var):
        return self.y if var == self.x else self.x

    def __repr__(self):
        return f"{self.name}({self.x}, {self.y})"


def different(x, y):
    """The map colouring constraint: neighbours must not share a colour."""
    return Constraint(x, y, lambda a, b: a != b, name="different")


class CSP:
    def __init__(self, variables, domains, constraints):
        self.variables = list(variables)
        self.domains = {v: list(domains[v]) for v in self.variables}
        self.constraints = list(constraints)

        # neighbours[v] = variables that share a constraint with v
        # between[(a, b)] = constraints linking a and b
        self.neighbours = {v: [] for v in self.variables}
        self.between = {}
        for c in self.constraints:
            for a, b in ((c.x, c.y), (c.y, c.x)):
                if b not in self.neighbours[a]:
                    self.neighbours[a].append(b)
                self.between.setdefault((a, b), []).append(c)

    def is_solution(self, assignment):
        if len(assignment) != len(self.variables):
            return False
        for c in self.constraints:
            if not c.relation(assignment[c.x], assignment[c.y]):
                return False
        return True


# --------------------------------------------------------------------------
# Solver
# --------------------------------------------------------------------------

METHODS = {
    "bt": "Backtracking",
    "fc": "Backtracking + Forward checking",
    "mac": "Backtracking + Constraint propagation (AC-3)",
}


class Solver:
    def __init__(self, csp, method="bt", record_trace=True,
                 max_nodes=300000, max_seconds=10.0, max_trace=25000):
        if method not in METHODS:
            raise ValueError(f"unknown method {method!r}")
        self.csp = csp
        self.method = method
        self.record_trace = record_trace
        self.max_nodes = max_nodes
        self.max_seconds = max_seconds
        self.max_trace = max_trace

        self.trace = []
        self.trace_cut = False
        self.nodes = 0        # assignments tried
        self.backtracks = 0   # times a variable ran out of values
        self.checks = 0       # constraint checks
        self.pruned = 0       # values removed from domains
        self.stopped = False  # hit max_nodes / max_seconds

    # ---------------------------------------------------------------- helpers
    def log(self, **event):
        if not self.record_trace:
            return
        if len(self.trace) >= self.max_trace:
            self.trace_cut = True
            return
        self.trace.append(event)

    def compatible(self, x, vx, y, vy):
        """Do all constraints between x and y allow x = vx, y = vy?"""
        for c in self.csp.between.get((x, y), ()):
            self.checks += 1
            if not c.allows(x, vx, vy):
                return False
        return True

    def next_variable(self, assignment):
        # fixed order: the order the variables were given in
        for v in self.csp.variables:
            if v not in assignment:
                return v
        return None

    def out_of_budget(self):
        if self.nodes >= self.max_nodes or time.perf_counter() - self.start > self.max_seconds:
            self.stopped = True
        return self.stopped

    # ---------------------------------------------------------------- entry
    def solve(self):
        self.start = time.perf_counter()
        domains = {v: list(d) for v, d in self.csp.domains.items()}
        assignment = {}

        ok = True
        if self.method == "mac":
            # constraint propagation once before the search starts
            removed = []
            ok = self.ac3(domains, deque((x, y) for x in self.csp.variables
                                         for y in self.csp.neighbours[x]), removed, by="AC-3")

        result = self.search(assignment, domains) if ok else None
        elapsed = (time.perf_counter() - self.start) * 1000

        if result is not None:
            status = "solved"
            self.log(e="done")
        elif self.stopped:
            status = "stopped"
            self.log(e="stopped")
        else:
            status = "no_solution"
            self.log(e="fail")

        return {
            "method": self.method,
            "method_name": METHODS[self.method],
            "status": status,
            "assignment": dict(result) if result else None,
            "stats": {
                "nodes": self.nodes,
                "backtracks": self.backtracks,
                "checks": self.checks,
                "pruned": self.pruned,
                "time_ms": round(elapsed, 3),
            },
            "trace": self.trace,
            "trace_cut": self.trace_cut,
        }

    # ---------------------------------------------------------------- search
    def search(self, assignment, domains):
        """Recursive backtracking. Returns a full assignment or None."""
        var = self.next_variable(assignment)
        if var is None:
            return assignment

        for value in list(domains[var]):
            if self.out_of_budget():
                return None
            self.nodes += 1
            self.log(e="try", v=var, c=value)

            if self.method == "bt":
                # plain backtracking: check the value against assigned neighbours
                clash = None
                for n in self.csp.neighbours[var]:
                    if n in assignment and not self.compatible(var, value, n, assignment[n]):
                        clash = n
                        break
                if clash is not None:
                    self.log(e="reject", v=var, c=value, w=clash)
                    continue
                assignment[var] = value
                result = self.search(assignment, domains)
                if result is not None:
                    return result
                del assignment[var]
                self.log(e="undo", v=var, c=value, r=[])
                continue

            # fc / mac: the domains already only hold values that fit the
            # assigned neighbours, so we just assign and look ahead
            assignment[var] = value
            removed = []  # (variable, value) pairs taken out, to put back on undo
            if self.method == "fc":
                ok = self.forward_check(var, value, assignment, domains, removed)
            else:
                ok = self.propagate(var, value, assignment, domains, removed)

            if ok:
                result = self.search(assignment, domains)
                if result is not None:
                    return result

            # undo the assignment and everything it pruned
            del assignment[var]
            for v, val in reversed(removed):
                domains[v].append(val)
            for v in domains:  # keep the original value order
                domains[v].sort(key=self.csp.domains[v].index)
            self.log(e="undo", v=var, c=value, r=[[v, val] for v, val in removed])

        self.backtracks += 1
        self.log(e="back", v=var)
        return None

    # ---------------------------------------------------------------- forward checking
    def forward_check(self, var, value, assignment, domains, removed):
        """Remove values from unassigned neighbours that clash with var = value.
        Returns False if some neighbour has no values left."""
        for n in self.csp.neighbours[var]:
            if n in assignment:
                continue
            for val in list(domains[n]):
                if not self.compatible(n, val, var, value):
                    domains[n].remove(val)
                    removed.append((n, val))
                    self.pruned += 1
                    self.log(e="prune", v=n, c=val, by=var)
            if not domains[n]:
                self.log(e="wipe", v=n)
                return False
        return True

    # ---------------------------------------------------------------- constraint propagation
    def propagate(self, var, value, assignment, domains, removed):
        """MAC: fix var's domain to {value}, then run AC-3 from var's neighbours."""
        for val in list(domains[var]):
            if val != value:
                domains[var].remove(val)
                removed.append((var, val))
        queue = deque((n, var) for n in self.csp.neighbours[var] if n not in assignment)
        return self.ac3(domains, queue, removed, by=var, assignment=assignment)

    def ac3(self, domains, queue, removed, by, assignment=None):
        """AC-3 arc consistency. An arc (x, y) is consistent when every value
        left for x has at least one value left for y that it works with.
        Returns False if a domain becomes empty."""
        assignment = assignment or {}
        while queue:
            x, y = queue.popleft()
            if self.revise(domains, x, y, removed, by):
                if not domains[x]:
                    self.log(e="wipe", v=x)
                    return False
                for z in self.csp.neighbours[x]:
                    if z != y and z not in assignment:
                        queue.append((z, x))
        return True

    def revise(self, domains, x, y, removed, by):
        changed = False
        for vx in list(domains[x]):
            if not any(self.compatible(x, vx, y, vy) for vy in domains[y]):
                domains[x].remove(vx)
                removed.append((x, vx))
                self.pruned += 1
                self.log(e="prune", v=x, c=vx, by=by)
                changed = True
        return changed


def solve(csp, method="bt", record_trace=True, **limits):
    return Solver(csp, method, record_trace, **limits).solve()
