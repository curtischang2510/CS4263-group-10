# Test case justification

Each section covers one person's cases and why they make the set more
reasonable or robust for comparing the CSP solver (Solution A) with the LLM
planner (Solution B). Ground truth was computed exhaustively with
`python ttdp_tool.py analyse <instance>` and the reference plans confirmed
with `python ttdp_tool.py check`.

## testcase_6 and testcase_7 (Ming Yuan)

### Gap in the existing set

Each existing infeasible twin had a short certificate:

- **One POI's window** (`testcase_1-X`, `testcase_2-X`).
- **A return bound over all orders** (`testcase_3-X`, `testcase_4-X`,
  `testcase_5-X`).

Every feasible case also had 7 to 126 valid visiting orders. Nothing tested an
infeasibility that comes from POIs interacting, or a feasible case with only
one way through.

### testcase_6 (medium: 7 POIs, 5 must-visit) — a pair of windows that conflict

- **Feasible:** the Wet Market (must end by 10:30) and the Jade Temple
  (opens 10:00) are 20 min apart. Only market-then-temple fits, so all 7
  solutions begin that way.
- **Twin (`-X`):** the temple closes at 10:50 instead of 11:30. Each POI
  still fits on its own, and the shortest loop needs only 435 of 480 min. But
  the two can't both be visited, in either order. Making either one optional
  restores feasibility.

**Why:** it adds a third kind of infeasibility, a binary conflict. This
targets constraint propagation directly. With one start-time variable per
must-visit and a pairwise "i before j or j before i, plus travel" constraint,
AC-3 empties the market's domain with no search. An LLM has to compare both
orders explicitly.

### testcase_7 (hard: 10 POIs, 7 must-visit) — one visiting order, forced wait

**Provenance:** found by a seeded random search (seed 20996). The search kept
only instances that met all of these:

- exactly one valid visiting order;
- a forced wait of at least 15 min;
- a one-parameter twin with no single-POI, pair or loop-length certificate.

The POIs were named afterwards.

- **Feasible:** the only order is C → A → F → B → G → D → E, home 17:55.
  - It waits 70 min at the Clock Tower Tour (A).
  - From A to the Orchid Conservatory (B) there is zero slack: B ends at
    exactly its 13:15 close.
  - **Trap:** filling the wait with the Waterfront Promenade (K) reaches A at
    10:35, so B ends late.
  - **Trap:** K costs no extra walking near the end of the day, but only
    5 min of slack is left for its 30 min visit.
- **Twin (`-X`):** A opens at 10:35, 5 min later. There is no short
  certificate:
  - every POI fits alone;
  - every pair fits together;
  - the shortest loop needs 455 of 570 min;
  - making any one must-visit optional restores feasibility.

**Why:** a planner cannot land on a valid plan by trying a few plausible
orders. It has to accept idle time instead of greedily filling it, and to
prove the twin infeasible it has to carry a chain of deductions across
several POIs. The start-time CSP above still settles the twin with AC-3 alone,
so this case stresses the LLM much more than the CSP.

### What the full set covers

How plain AC-3 on the start-time CSP above handles each twin, checked by
running it:

| Twin | Proved infeasible by |
|---|---|
| `testcase_1-X`, `testcase_2-X` | node consistency (one POI) |
| `testcase_6-X`, `testcase_7-X` | AC-3 (pairwise, then chained propagation) |
| `testcase_3-X`, `testcase_4-X`, `testcase_5-X` | search (AC-3 alone is not enough) |

The feasible cases now range from 1 to 126 valid visiting orders. Case 6 is
at the same scale and uses the same constraint types as `testcase_2`, and
case 7 matches `testcase_3` the same way. They are not controlled pairs,
though: the POIs, windows and travel tables all differ.

**Limitation:** `testcase_7` may be hard enough that every LLM variant fails
it. It should be run several times per variant, and read alongside the
easier cases rather than on its own.

New feature tags: `infeasible_pair` (two POIs can't both be visited),
`infeasible_chain` (infeasible with no single-POI, pair or loop-length
certificate), `forced_wait` (the solution must idle before a visit), and
`unique_solution` (exactly one valid visiting order).
