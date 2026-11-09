# CS4263 Group 10: Tourist Trip Design as a CSP

We compare two planners for a one-day tourist itinerary, given the same
deterministic input:

- **Solution A:** a CSP solver (MRV, degree and LCV heuristics with AC-3).
- **Solution B:** an LLM planner (`gemini-3.5-flash-lite`), tested with six safeguards added one at a time.

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

Its unit tests cover the 14 test cases, boundary edge cases, and 300 random instances
cross-checked against the exhaustive search in `ttdp_tool.py`:

```bash
python3 -m unittest discover tests -v
```

## Solution B: LLM planner and safeguards

`solvers/llm.py` implements all Solution B variants. The baseline calls
`gemini-3.5-flash-lite` with a structured-output schema and no reasoning
elicitation. Each safeguard builds on top of it.

### Safeguards

| Solver | Safeguard | Description |
|---|---|---|
| `llm` | Baseline | Single-pass structured output, no reasoning elicited. |
| `llm_cot` | Chain-of-Thought (Wei et al., 2022) | Adds a `reasoning` field placed first in the schema, forcing the model to reason step-by-step before committing to an answer. |
| `llm_ltm` | Least-to-Most (Zhou et al., 2023) | Two sequential calls: (1) check each must-visit POI's individual feasibility in isolation; (2) find a valid ordering given the pre-analysis. Prevents the model from skipping unary constraint checks. *Excluded from the report as it did not improve results over CoT prompting.* |
| `llm_self_refine` | Iterative Refinement (Madaan et al., 2023) | A second LLM call critiques each plan and returns actionable violation feedback; the planner retries up to `MAX_ATTEMPTS` times. |
| `llm_verifier_loop` | Verifier-in-the-Loop (Gou et al., 2024) | Replaces the LLM critic with the deterministic `ttdp_tool.check()`, guaranteeing correct feedback. Retries up to `MAX_ATTEMPTS` times. |
| `llm_reflexion` | Reflexion (Shinn et al., 2023) | After each `T.check()` failure, a reflection call asks the model to diagnose its reasoning error. Reflections accumulate as episodic memory prepended to each subsequent attempt. |
| `llm_self_consistency` | Self-Consistency (Wang et al., 2023) | Samples `K=5` CoT plans at temperature 0.7 and selects by majority vote over POI sequence, preferring plans that pass `T.check()`. |

### Combined strategies

| Solver | Combination | Description |
|---|---|---|
| `llm_combined_1` | CoT + Verifier + Self-Consistency | K independent CoT samples each corrected by the deterministic verifier, then majority vote. |
| `llm_combined_2` | LtM + Reflexion + Self-Consistency | K independent samples using LtM decomposition and Reflexion correction, then majority vote. |
| `llm_combined_3` | CoT + Verifier + Reflexion + Self-Consistency | K independent CoT samples each corrected by a Reflexion loop (deterministic `T.check()` + verbal self-reflection), then majority vote. |

### Running the solvers

```bash
python run_tests.py                # all implemented solvers
python run_tests.py llm            # one solver
python run_tests.py llm llm_cot    # specific solvers
```

To check one output:

```bash
python ttdp_tool.py check <instance.json> <output.json>
```
