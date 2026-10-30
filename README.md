# CS4263 Group 10: Tourist Trip Design as a CSP

We compare two planners for a one-day tourist itinerary, given the same
deterministic input:

- **Solution A:** a CSP solver (MRV, degree and LCV heuristics with AC-3).
- **Solution B:** an LLM planner, tested with safeguards added one at a time
  (chain-of-thought, self-verification, verifier-in-the-loop, self-consistency).

## Problem

A solver gets one `*.instance.json` file. The fields it needs:

| Field | Meaning |
|---|---|
| `day_window.start`, `day_window.end` | The day window *S* and *E*, as `HH:MM`. |
| `start_location` | The hotel `H`. The day starts and ends there. |
| `travel_times[a][b]` | Walking minutes from `a` to `b`, for every pair of locations, including `H`. |
| `pois[].id` | The POI's ID, used in the output. |
| `pois[].opening_windows` | One `[open, close]` window. |
| `pois[].visit_duration` | Minutes spent at the POI. |
| `pois[].must_visit` | `true` if the POI must be visited, `false` if it is optional. |

The other fields (`date`, `weekday`, `name`, `entry_fee`, `allow_waiting`) are
informational.

The solver returns a plan in the format of
[`testcases/example_output.json`](testcases/example_output.json): an
`itinerary` list of `{"poi", "mode": "walk", "start", "end"}`, plus
`"return_mode": "walk"`. The checker accepts the plan only if every rule below
holds. Its violation code is in brackets.

1. **Valid stops.** Each `poi` is a real POI ID and appears at most once
   (`unknown_poi`, `duplicate_visit`). Every `mode` is `"walk"` (`unknown_mode`).
2. **Times.** `start` and `end` are 24-hour `HH:MM` (`bad_time_format`), and
   `end − start = visit_duration` (`wrong_duration`).
3. **C1 Opening hours.** `open ≤ start` and `end ≤ close` (`outside_opening_hours`).
4. **C2 Travel time.** The first stop starts no earlier than
   *S* + `travel_times[H][first]`. Each later stop starts no earlier than the
   previous stop's `end` + `travel_times[prev][next]` (`insufficient_travel`).
   Arriving early and waiting is allowed.
5. **C3 Day window.** The last stop's `end` + `travel_times[last][H]` ≤ *E*
   (`exceeds_day_window`).
6. **C4 Must-visit.** Every POI with `must_visit: true` is in the itinerary
   (`missing_must_visit`). Optional POIs may be visited or skipped.

If no plan satisfies all six rules, return
`{"feasible": false, "itinerary": [], "reason": "..."}`.

**Correct output:** an itinerary the checker accepts on a feasible instance,
or `"feasible": false` on an infeasible one. Anything else is wrong.

## Test cases

`testcases/testcase_N/` holds `testcase_N`, a feasible instance, and
`testcase_N-X`, its infeasible near-miss twin, which differs in one
parameter. All cases are walk-only, with one opening window per POI and
symmetric travel times. They differ in scale:

| Level | Cases | POIs (must-visit) |
|---|---|---|
| Easy | `testcase_1`, `testcase_5` | 5 (4), 4 (4) |
| Medium | `testcase_2`, `testcase_6` | 7 (5), 7 (5) |
| Hard | `testcase_3`, `testcase_4`, `testcase_7` | 10 (7), 13 (9), 10 (7) |

`testcase_7` has exactly one valid visiting order, and it includes a forced
wait.

The twins fail in one of four ways:

- **`testcase_1-X`, `testcase_2-X`:** one POI's window can't be met.
- **`testcase_3-X`, `testcase_4-X`, `testcase_5-X`:** no visiting order gets
  back to the hotel in time.
- **`testcase_6-X`:** two POIs each fit alone, but their windows can't both
  be met in either order.
- **`testcase_7-X`:** every POI fits alone, every pair fits together and the
  shortest loop fits in the day, yet no full order works. Proving it takes a
  chain of deductions across several POIs.

`<ID>.answer.json` is the ground truth. **Never give it to a solver.**

## Solution A: CSP solver

`solvers/csp.py` models the problem as a disjunctive-ordering CSP:

- **Variables:** one per pair of must-visit POIs.
- **Domain:** "i before j" or "j before i".
- **Bounds:** each POI keeps a start-time interval `[lo, hi]` from its opening window
  and the day window, including the hotel legs.

AC-3 removes orderings that the bounds rule out and tightens the bounds once a pair is
fixed. Backtracking search picks a pair by MRV and then the degree heuristic, orders
its values by LCV (most slack left first), and runs AC-3 after every choice. Each POI
in the final order starts as early as possible.

It relies on two simplifications, both exact when travel times obey the triangle
inequality **including the visit duration**:
`travel[a][c] ≤ travel[a][b] + visit_duration[b] + travel[b][c]`.
**All test cases must satisfy this.**

- Optional POIs are dropped, since visiting one can never help.
- Travel time is enforced between every ordered pair of stops, not only between
  consecutive ones.

Its unit tests cover the 10 test cases, boundary edge cases, and 300 random instances
cross-checked against the exhaustive search in `ttdp_tool.py`:

```bash
python3 -m unittest discover tests -v
```

## Testing your solver

The solvers are stubs in `solvers/`:

- `csp.py` is Solution A.
- `llm.py` is Solution B.

To implement one, fill in its `solve(instance)`. It takes the parsed instance
(a dict) and returns a dict in the format of
[`testcases/example_output.json`](testcases/example_output.json). To test more
solvers, such as one per safeguard, add them to `SOLVERS` in
`solvers/__init__.py`.

Then run:

```bash
python run_tests.py
```

The runner runs every implemented solver on every test case, easy first, and
stops at the first failure with the reason. Solvers that are still stubs are
skipped. To run one solver only, name it, for example
`python run_tests.py llm`. On a Mac without `python`, use `python3`.

To check one output:

```bash
python ttdp_tool.py check <instance.json> <output.json>
```
