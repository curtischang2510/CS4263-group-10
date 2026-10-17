# CS4263 Group 10: Tourist Trip Design as a Constraint Satisfaction Problem

This project compares two ways of planning a one-day tourist itinerary when both
get exactly the same deterministic information:

- **Solution A**: a classical constraint-satisfaction solver.
- **Solution B**: an LLM planner, tested first on its own and then with safeguards added one at a time.

This document covers the problem scope, the hard constraints, what counts as a
correct output, the success criteria, and the test instances.

---

## 1. Background

Tourist itinerary planning is usually formulated as the **Tourist Trip Design
Problem (TTDP)**. A planner has to choose points of interest (POIs) and put them
in order while respecting routing and time constraints. Prior work names the
Orienteering Problem as the main formulation, and treats opening hours, visit
durations and travel times as the key constraints (Gavalas et al., 2014;
Ruiz-Meza & Montoya-Torres, 2022). Constraint programming has worked well on
NP-hard variants with time windows (Gedik et al., 2017).

LLM-based travel planning, on the other hand, is still unreliable. On
TravelPlanner, GPT-4 reached a final pass rate of only 0.6% (Xie et al., 2024), and
o1-preview produced about 10% viable plans (Hao et al., 2024). We therefore
compare CSP planning and LLM planning on identical deterministic inputs.

---

## 2. Problem Definition

### 2.1 Instance (input)

An instance is the tuple **I = (P, [oᵢ, cᵢ], dᵢ, t, [S, E], M)**, where:

| Symbol | Meaning |
|---|---|
| **P** | A finite set of points of interest (POIs). |
| **[oᵢ, cᵢ]** | The opening window of POI *i ∈ P*: it opens at *oᵢ* and closes at *cᵢ*. |
| **dᵢ** | The visit duration of POI *i*. |
| **tᵢⱼ** | The travel-time matrix: the time to travel from POI *i* to POI *j*. It need not be symmetric. |
| **[S, E]** | The day window: the itinerary may not start before *S* or end after *E*. |
| **M ⊆ P** | The set of must-visit POIs. |

All times are whole minutes, written as `HH:MM` in the instance files.

### 2.2 Decision variables (output)

The planner must produce:

1. An **ordered sequence** of distinct POIs, *π = (π₁, π₂, …, πₖ)*, with each *πⱼ ∈ P*.
2. A **start time** *sᵢ* for every POI *i* in the sequence. A visit to *i*
   occupies the interval *[sᵢ, sᵢ + dᵢ]*.

### 2.3 Hard constraints

A plan is feasible **if and only if** it satisfies all of the following:

| ID | Constraint | Formal statement |
|---|---|---|
| **C1** | **Opening hours.** Every visit starts and ends within the POI's opening hours. | *oᵢ ≤ sᵢ* and *sᵢ + dᵢ ≤ cᵢ*, for every visited *i* |
| **C2** | **Travel time.** Consecutive visits leave enough time to travel between them. | *sπⱼ + dπⱼ + tπⱼπⱼ₊₁ ≤ sπⱼ₊₁*, for *j = 1, …, k−1* |
| **C3** | **Day window.** The whole itinerary fits within the day. | *S ≤ sπ₁* and *sπₖ + dπₖ ≤ E* |
| **C4** | **Must-visit.** Every must-visit POI is visited exactly once. | every *i ∈ M* appears in *π* exactly once |

Notes on these constraints:

- A plan may wait. If you arrive before a POI opens, you wait until it opens.
  That is why C2 is an inequality.
- An optional POI (one in *P \ M*) may be visited at most once, or skipped.
- When an instance gives a start location *h* and asks you to return to it,
  C3 includes the legs from and back to *h*:
  *S + tₕπ₁ ≤ sπ₁* and *sπₖ + dπₖ + tπₖₕ ≤ E*.

### 2.4 Problem class

This is a **satisfaction** problem, not an optimisation problem. Any plan that
meets every hard constraint is equally correct, and we do not score plans on
quality. The problem is still hard: deciding whether a feasible plan exists
includes the decision version of the Travelling Salesman Problem with Time
Windows, which is NP-complete.

---

## 3. Correctness and Success Criteria

### 3.1 What counts as correct

For a given instance, an output is **correct** only if it is one of these:

- **(a)** An itinerary that the shared deterministic checker confirms meets
  every hard constraint (§2.3), on an instance that is feasible.
- **(b)** A statement that the instance is infeasible, on an instance that
  really is infeasible.

Every other output is **incorrect**. That includes:

- an itinerary that breaks any constraint,
- an itinerary given for an infeasible instance,
- a claim of infeasibility for a feasible instance,
- an output that cannot be parsed.

### 3.2 Solution A (CSP solver)

We implement constraint search with the MRV, degree and least-constraining-value
heuristics, plus AC-3 constraint propagation.

**Criterion:** Solution A must be correct on **100%** of instances, both
feasible and infeasible.

### 3.3 Solution B (LLM planner)

Solution B receives the same instance input as Solution A, with all the
constraints spelled out. We test a baseline first, then add these safeguards
one at a time:

1. **Chain-of-Thought prompting.**
2. **Self-verification.** A second LLM pass reads the proposed itinerary and
   checks each constraint.
3. **Verifier-in-the-loop.** The shared deterministic checker runs on the
   LLM's plan.
4. **Self-consistency.** We call the LLM *K* times with temperature > 0, which
   gives *K* independent plans, and keep the one that most checkers agree on.

**Evaluation metrics:**

| Metric | Definition |
|---|---|
| Correctness rate | The share of instances solved correctly (§3.1). |
| Violations by type | How often each constraint type is broken (C1–C4 and the extensions in §4.3). |
| Infeasibility detection | How accurately infeasible instances are detected: precision and recall on "infeasible" claims. |
| Cost | Runtime or token cost on each instance. |

### 3.4 Project success

The project succeeds if we can show **where Solution B adds value beyond
Solution A**, for example:

- working from live, real-world information (current opening hours, closures, traffic),
- producing more flexible plans.

We also measure:

- **how much correctness that costs**: the gap between Solution B and Solution A's 100%,
- **how far each safeguard closes that gap.**

---

## 4. Test Instances

### 4.1 Design principles

- **Ground truth by exhaustive search.** We know whether each instance is
  feasible, and how many solutions it has, because `ttdp_tool.py analyse` runs
  an exhaustive search on it. This search is only for building test cases. It
  is not Solution A.
- **Feasible and infeasible cases.** Every difficulty level includes instances
  that are infeasible on purpose.
- **Near-miss twins.** An infeasible twin (suffix `-X`) is its feasible
  partner with one parameter tightened. Each constraint still looks
  satisfiable on its own, and only their combination fails. This tests whether
  a planner can detect infeasibility, rather than just failing to find a plan.
- **Distractors.** Free-text `description` fields are for information only and
  never bind. Some instances include text in them that contradicts the
  structured data, such as "the timetable can be ignored". A correct planner
  follows only the structured fields.

### 4.2 Difficulty levels

| Level | Constraints used | Typical characteristics |
|---|---|---|
| **Easy** | C1–C4 only | A few POIs, one opening window each, slack in the schedule, many solutions. |
| **Medium** | C1–C4 plus some calendar extensions | Split windows, last-entry times, closed days, fixed departure slots; fewer solutions. |
| **Hard** | C1–C4 plus several interacting extensions | Budget, choice of travel mode, rush-hour travel, a lunch window, precedence, either/or groups, distractor text; only a handful of solutions, or none. |

### 4.3 Constraint extensions used in harder instances

These extensions are refinements of C1–C4, or extra hard constraints with the
same deterministic semantics. The checker enforces every one that an instance
uses.

| Field | Constraint |
|---|---|
| `opening_windows` (more than one) | The visit must fit entirely inside **one** window (refines C1). |
| `last_entry` | *sᵢ ≤ last_entry* (refines C1). |
| `fixed_start_times` | *sᵢ* must be one of the listed times (refines C1). |
| `closed_days` | The POI cannot be visited on the instance's `weekday`. |
| `start_location`, `return_to_start` | The day starts at *h* and must end back at *h* by *E* (refines C3). |
| `travel_modes` | Each leg picks a mode. Travel time is ⌈*tᵢⱼ* × `time_factor`⌉, and each leg adds `cost_per_leg`. |
| `time_dependent_travel` | A leg that departs inside the given interval has its travel time multiplied by `multiplier`. |
| `budget` | Entry fees plus transport costs, including the return leg, must be ≤ budget. |
| `precedence` [a, b] | If *b* is visited, *a* must be visited earlier. |
| `at_least_one_of` | Each group must contain at least one visited POI. |
| `lunch` | Exactly one lunch candidate is visited, and it starts within `start_between`. |

### 4.4 File layout and naming

| File | Purpose |
|---|---|
| `<ID>.instance.json` | The instance. This is the **only** file the solvers see. |
| `<ID>.answer.json` | The ground truth: `level`, `feasible`, `num_solutions`, reference solutions, `design_intent` and `features`. **Never give this file to a solver.** |
| `<ID>-X.*` | The deliberately infeasible near-miss twin of `<ID>`. |
| `example_output.json` | The output format both solvers must produce. |

The required output format is:

```json
{
  "feasible": true,
  "itinerary": [{"poi": "V", "mode": "walk", "start": "09:05", "end": "09:20"}],
  "return_mode": "walk",
  "reason": ""
}
```

To report an infeasible instance, set `"feasible": false` and give a
justification in `reason`.

### 4.5 Current instances

| ID | Level | Feasible | Solutions | Notes |
|---|---|---|---|---|
| `TTDP-M-017` | hard | yes | 3 | The budget of $65 is met exactly by one of the two strategies. |
| `TTDP-M-017-X` | hard | **no** | 0 | Identical to M-017 except the budget is $62. Every constraint passes on its own, and only the combination fails. |

---

## 5. Tooling

`ttdp_tool.py` validates instances, computes ground truth, and checks outputs.

Validate an instance and enumerate its ground-truth solutions:

```bash
python ttdp_tool.py analyse TTDP-M-017.instance.json
```

Check a solver's or LLM's output against an instance:

```bash
python ttdp_tool.py check TTDP-M-017.instance.json example_output.json
```

The `check` command prints `VALID` or a list of violations. Each violation code
corresponds to one constraint type, for example `outside_opening_hours`,
`insufficient_travel`, `exceeds_day_window`, `missing_must_visit` or
`over_budget`. These codes feed the "violations by type" metric.

> On a Windows console, set `PYTHONIOENCODING=utf-8` before running `analyse`.
> Otherwise it fails when it prints the `→` arrows.

---

## 6. Division of Work

| Member | Responsibility |
|---|---|
| Ansel | Define the problem scope, hard constraints and success criteria. Prepare test instances at different difficulty levels, including infeasible cases. |
| Jingjing | Conduct the background review. Review the literature on AI safeguards and connect the findings to our methodology. |
| Curtis | Develop Solution A, including the search heuristics and constraint propagation. |
| Ting Xuan | Develop Solution B: a baseline first, then the safeguards added step by step. |
| Ming Yuan | Implement the shared deterministic itinerary checker. Consolidate the results and compare correctness and efficiency across difficulty levels. |

---

## References

- Gavalas, D., Konstantopoulos, C., Mastakas, K., & Pantziou, G. (2014). A survey on algorithmic approaches for solving tourist trip design problems. *Journal of Heuristics, 20*(3), 291–328. https://doi.org/10.1007/s10732-014-9242-5
- Gedik, R., Kirac, E., Milburn, A. B., & Rainwater, C. (2017). A constraint programming approach for the team orienteering problem with time windows. *Computers & Industrial Engineering, 107*, 178–195. https://doi.org/10.1016/j.cie.2017.03.017
- Hao, Y., Chen, Y., Zhang, Y., & Fan, C. (2024). Large language models can solve real-world planning rigorously with formal verification tools. arXiv. https://arxiv.org/abs/2404.11891
- Ruiz-Meza, J., & Montoya-Torres, J. R. (2022). A systematic literature review for the tourist trip design problem: Extensions, solution techniques and future research lines. *Operations Research Perspectives, 9*, 100228. https://doi.org/10.1016/j.orp.2022.100228
- Xie, J., Zhang, K., Chen, J., Zhu, T., Lou, R., Tian, Y., Xiao, Y., & Su, Y. (2024). TravelPlanner: A benchmark for real-world planning with language agents. arXiv. https://arxiv.org/abs/2402.01622
