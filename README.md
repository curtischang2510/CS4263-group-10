# CS4263 Group 10: Tourist Trip Design as a CSP

We compare two planners for a one-day tourist itinerary, given the same
deterministic input:

- **Solution A:** a CSP solver (MRV, degree and LCV heuristics with AC-3).
- **Solution B:** an LLM planner, tested with safeguards added one at a time
  (chain-of-thought, self-verification, verifier-in-the-loop, self-consistency).

## Problem

An instance gives:

- a set of POIs, each with an opening window [*oᵢ*, *cᵢ*] and a visit duration *dᵢ*;
- a travel-time matrix *tᵢⱼ*, which need not be symmetric;
- a day window [*S*, *E*];
- a set of must-visit POIs *M*.

The planner outputs an ordered sequence of distinct POIs, with a start time
*sᵢ* for each one. A plan is feasible if and only if:

| ID | Constraint | Formal statement |
|---|---|---|
| C1 | Opening hours | *oᵢ ≤ sᵢ* and *sᵢ + dᵢ ≤ cᵢ* |
| C2 | Travel time | *sᵢ + dᵢ + tᵢⱼ ≤ sⱼ* for each consecutive pair *i → j* |
| C3 | Day window | *S ≤ sᵢ* and *sᵢ + dᵢ ≤ E*, including the legs from and back to the start location |
| C4 | Must-visit | every *i ∈ M* is visited exactly once |

Rules for plans:

- **Waiting** for a POI to open is allowed.
- **Optional POIs** are visited at most once, or skipped.
- **Times** are whole minutes, written `HH:MM`.

**Correct output:** an itinerary the checker accepts on a feasible instance,
or `"feasible": false` on an infeasible one. Anything else is wrong.

## Test cases

`testcases/testcase_N/` holds a feasible instance and its infeasible
near-miss twin (`-X`), which differs in one parameter. Levels:

- **Easy** uses C1–C4 only.
- **Medium** adds calendar rules.
- **Hard** adds budget, travel modes and logic rules.

- `<ID>.instance.json` is the only file a solver may read.
- `<ID>.answer.json` is the ground truth. **Never give it to a solver.**

Description fields are free text and never bind; some contain deliberate
distractors. The extra fields used by medium and hard instances:

| Field | Rule |
|---|---|
| `opening_windows` (several) | The visit fits inside **one** window. |
| `last_entry` | *sᵢ ≤ last_entry*. |
| `fixed_start_times` | *sᵢ* is one of the listed times (one time = a fixed appointment). |
| `closures` | The visit may not overlap a listed interval. |
| `arrival_buffer` | *sᵢ ≥ arrival + buffer*. |
| `closed_days` | Not visitable on the instance's `weekday`. |
| `start_location`, `return_to_start` | Start at *h* and be back at *h* by *E*. |
| `travel_modes` | Per-leg mode: time ⌈*tᵢⱼ* × `time_factor`⌉, cost `cost_per_leg`. |
| `time_dependent_travel` | Legs departing in the interval take × `multiplier`. |
| `no_modes` | Listed modes cannot enter or leave this POI. |
| `max_single_walk` / `max_walk_total` | Walking minutes per leg / per day, including the return leg. |
| `budget` | Entry fees plus fares, including the return leg, ≤ budget. |
| `precedence` [a, b] | If *b* is visited, *a* comes earlier. |
| `immediately_after` [a, b] | If *b* is visited, the stop directly before it is *a*. |
| `if_then` [a, b] | If *a* is visited, *b* is visited too. |
| `at_least_one_of` / `at_most_one_of` | Each group has ≥ 1 / ≤ 1 visited POI. |
| `lunch` | Exactly one candidate, starting within `start_between`. |

## Testing your solver

Make your solver a command that takes one instance path and prints one JSON
object in the format of [`testcases/example_output.json`](testcases/example_output.json).
Then plug the command into the runner:

```bash
python run_tests.py --solver "python solver_a.py"
```

It runs every case, easy first, and stops at the first failure with the
reason.

- **Run everything:** `--keep-going` runs every case instead of stopping.
- **Pick cases:** `--level easy` or `-k HARD-001` chooses which cases run.
- **Saved outputs:** `--outputs DIR` grades saved `DIR/<ID>.output.json` files,
  for example from LLM runs.
- **Platforms:** it works the same on macOS and Windows. On a Mac without
  `python`, use `python3`.

To check one output:

```bash
python ttdp_tool.py check <instance.json> <output.json>
```
