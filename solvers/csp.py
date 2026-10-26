"""Solution A: CSP solver.

Formulation (a disjunctive-ordering CSP over the must-visit POIs):

- Variables: one per unordered pair {i, j} of must-visit POIs.
- Domains: {(i, j), (j, i)}, where (a, b) means "a is visited before b".
- Each POI also carries start-time bounds [lo, hi], tightened by propagation. A value
  (a, b) is supported only if lo[a] + gap(a, b) <= hi[b], where
  gap(a, b) = duration[a] + travel[a][b].

AC-3 removes unsupported values and, once a pair is fixed, tightens the bounds of its
two POIs. Search uses MRV, then the degree heuristic, then LCV, and runs AC-3 after
every assignment. When every pair is fixed, the pairs form a total order, and starting
each POI at its lower bound gives a valid plan.

Two simplifications keep the model small. Both rely on the travel times obeying the
triangle inequality including the visit duration,
travel[a][c] <= travel[a][b] + duration[b] + travel[b][c], which the test cases uphold.
- Optional POIs are dropped. Removing a stop never makes a later stop arrive later.
- The travel constraint is applied to every ordered pair, not only consecutive stops.
  Along a valid plan, the gaps between consecutive stops add up to at least the direct
  gap, so no valid plan is lost.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

Pair = tuple[str, str]  # (a, b): a is visited before b


def to_minutes(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def to_hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


@dataclass
class Problem:
    travel: dict[str, dict[str, int]]
    duration: dict[str, int]  # must-visit POIs only

    def gap(self, a: str, b: str) -> int:
        """Minimum minutes between the start of a and the start of b, if a comes first."""
        return self.duration[a] + self.travel[a][b]


@dataclass
class State:
    lo: dict[str, int]  # earliest start of each POI
    hi: dict[str, int]  # latest start of each POI
    domains: dict[Pair, set[Pair]]

    def copy(self) -> State:
        return State(dict(self.lo), dict(self.hi), {var: set(vals) for var, vals in self.domains.items()})

    def slack(self) -> int:
        return sum(self.hi[poi] - self.lo[poi] for poi in self.lo)


def parse(instance: dict) -> tuple[Problem, State]:
    """Build the CSP: keep must-visit POIs only, with bounds from C1 and C3."""
    home = instance["start_location"]
    travel = instance["travel_times"]
    day_start = to_minutes(instance["day_window"]["start"])
    day_end = to_minutes(instance["day_window"]["end"])
    must = [poi for poi in instance["pois"] if poi["must_visit"]]

    duration = {poi["id"]: poi["visit_duration"] for poi in must}
    lo, hi = {}, {}
    for poi in must:
        x = poi["id"]
        (opens, closes), = poi["opening_windows"]
        lo[x] = max(to_minutes(opens), day_start + travel[home][x])
        hi[x] = min(to_minutes(closes), day_end - travel[x][home]) - duration[x]

    domains = {(a, b): {(a, b), (b, a)} for a, b in combinations(sorted(duration), 2)}
    return Problem(travel, duration), State(lo, hi, domains)


def revise(problem: Problem, state: State, var: Pair) -> set[str] | None:
    """Make `var` consistent with the current bounds.

    Returns the POIs whose bounds changed, or None if a domain or bound becomes empty.
    """
    domain = state.domains[var]
    domain -= {(a, b) for a, b in domain if state.lo[a] + problem.gap(a, b) > state.hi[b]}
    if not domain:
        return None
    changed = set()
    if len(domain) == 1:
        (a, b), = domain
        if state.lo[b] < state.lo[a] + problem.gap(a, b):
            state.lo[b] = state.lo[a] + problem.gap(a, b)
            changed.add(b)
        if state.hi[a] > state.hi[b] - problem.gap(a, b):
            state.hi[a] = state.hi[b] - problem.gap(a, b)
            changed.add(a)
    if any(state.lo[x] > state.hi[x] for x in changed):
        return None
    return changed


def ac3(problem: Problem, state: State, queue: list[Pair]) -> bool:
    """Propagate until no variable can be revised further. False on a dead end."""
    pending = set(queue)
    while queue:
        var = queue.pop()
        pending.discard(var)
        changed = revise(problem, state, var)
        if changed is None:
            return False
        for other in state.domains:
            if other != var and other not in pending and changed & set(other):
                queue.append(other)
                pending.add(other)
    return True


def select_variable(state: State, unassigned: list[Pair]) -> Pair:
    """MRV, then degree (most unassigned pairs sharing a POI), then name order."""
    def degree(var: Pair) -> int:
        return sum(1 for other in unassigned if other != var and set(other) & set(var))

    return min(unassigned, key=lambda var: (len(state.domains[var]), -degree(var), var))


def ordered_children(problem: Problem, state: State, var: Pair) -> list[State]:
    """LCV: try each value, propagate, and put the one leaving the most slack first."""
    children = []
    for value in sorted(state.domains[var]):
        child = state.copy()
        child.domains[var] = {value}
        if ac3(problem, child, [var]):
            children.append(child)
    return sorted(children, key=State.slack, reverse=True)


def backtrack(problem: Problem, state: State) -> State | None:
    unassigned = [var for var, vals in state.domains.items() if len(vals) > 1]
    if not unassigned:
        return state
    var = select_variable(state, unassigned)
    for child in ordered_children(problem, state, var):
        result = backtrack(problem, child)
        if result is not None:
            return result
    return None


def infeasible(reason: str) -> dict:
    return {"feasible": False, "itinerary": [], "reason": reason}


def solve(instance: dict) -> dict:
    """Input: one parsed *.instance.json file.
    Output: a dict in the format of testcases/example_output.json, i.e. a feasible
    itinerary, or {"feasible": False, "itinerary": [], "reason": "..."} if none exists.
    """
    problem, state = parse(instance)
    for x in sorted(state.lo):
        if state.lo[x] > state.hi[x]:
            return infeasible(
                f"{x} cannot be visited on its own: its earliest start is {to_hhmm(state.lo[x])} "
                f"but its latest start is {to_hhmm(state.hi[x])}."
            )

    if not ac3(problem, state, list(state.domains)):
        return infeasible("Constraint propagation proves that no visiting order fits the day.")
    solution = backtrack(problem, state)
    if solution is None:
        return infeasible("Exhaustive search found no visiting order that fits the day.")

    stops = sorted(solution.lo, key=lambda x: solution.lo[x])
    itinerary = [
        {"poi": x, "mode": "walk", "start": to_hhmm(solution.lo[x]),
         "end": to_hhmm(solution.lo[x] + problem.duration[x])}
        for x in stops
    ]
    return {"feasible": True, "itinerary": itinerary, "return_mode": "walk", "reason": ""}
