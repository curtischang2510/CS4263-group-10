# Summary of test cases

Each level has one feasible instance and one deliberately infeasible near-miss
twin (suffix `-X`), which differs from it in exactly one parameter. We built the
ground truth with `python ttdp_tool.py analyse <instance>`. The full design
notes and reference plans are in each `*.answer.json` file. Never give the
answer files to a solver.

In the plans below, `[t]` marks a taxi leg. Every other leg is walked.

| ID | Level | Feasible | Solutions | One-parameter change |
|---|---|---|---|---|
| TTDP-EASY-001 | easy | yes | 26 | — |
| TTDP-EASY-001-X | easy | no | 0 | Flower Market closes 12:00 → 09:55 |
| TTDP-MED-001 | medium | yes | 3 | — |
| TTDP-MED-001-X | medium | no | 0 | Museum last entry 13:30 → 13:00 |
| TTDP-HARD-001 | hard | yes | 6 | — |
| TTDP-HARD-001-X | hard | no | 0 | Day end 17:30 → 17:20 |
| TTDP-HARD-002 | hard | yes | 3 | — |
| TTDP-HARD-002-X | hard | no | 0 | Budget $65 → $62 |

## Easy: TTDP-EASY-001 (Tue, 09:00–15:30)

- **Constraints:** C1–C4 only. The day is walk-only, each POI has one opening
  window, travel times are symmetric, and there is no budget.
- **POIs:** four must-visits (Heritage Museum, Flower Market, Botanic Gardens,
  Clock Tower) and one optional (Riverside Promenade).
- **Example plan:** H → B 09:15 → C 10:30 → A 11:45 → D 13:30 → H 14:15.
- **Twin (`-X`):** the Flower Market closes at 09:55. The earliest arrival is
  09:15, so the 45-minute visit cannot end before 10:00. Checking that one POI
  is enough to prove the instance infeasible.

## Medium: TTDP-MED-001 (Mon, 09:00–17:30)

- **Constraints:**
  - Maritime Museum: last entry 13:30 (it closes at 17:00), gallery closed
    12:00–13:00, and a 10-minute arrival buffer.
  - Ferry: departs only at 11:00, 13:30 or 15:30, with a 10-minute ticketing
    buffer.
  - Hilltop Fort: split window (09:00–11:30 and 14:00–17:00), and every leg
    into the Fort is 15 minutes slower than the same leg out.
  - Either/or: visit the Silk Museum or the Old Town Square.
- **Trap:** the Silk Museum is closed on Mondays, so the Old Town Square is
  the only valid choice for the either/or group.
- **Plans (all 3):**
  - H → B 09:15 → D 11:00 → G 12:10 → A 13:30 → C 15:10 → F 16:20 → H 17:00
  - H → B 09:15 → C 10:30 → G 11:55 → A 13:15 → D 15:30 → F 16:35 → H 17:15
  - H → B 09:15 → D 11:00 → G 12:10 → A 13:30 → F 15:00 → C 15:55 → H 17:15
- **Twin (`-X`):** last entry moves to 13:00. Because of the closure, the
  75-minute visit must either end by 12:00 or start at exactly 13:00, and
  neither fits. Relaxing any one of these makes the twin feasible again: the
  closure, either arrival buffer, the Fort's split window, or the ferry
  timetable.

## Hard: TTDP-HARD-001 (Sat, 08:30–17:30, budget $46)

- **Constraints:**
  - Travel: walk or taxi (0.4× the walking time, $12 per leg). Walking legs
    are capped at 25 minutes, and travel is 1.5× slower when leaving between
    17:00 and 19:00. Taxis cannot reach the Old Market.
  - Lunch: exactly one lunch, starting 11:30–13:30.
  - Meeting: meet a friend at the jetty at exactly 15:00.
  - Order: collect the pass at the Visitor Centre before the Art Museum, and
    go to the Design Annex directly after the Art Museum.
  - Choices: exactly one temple (either/or plus at-most-one), and the Cable
    Car or the Waterfront Lookout. Riding the Cable Car requires visiting the
    Summit Garden.
- **Two strategies:**
  - S1–S4, cafe and walk ($44), e.g. H → B 08:50 → V 09:45 → A 10:25 → D 11:45
    → L2 12:40 → T2 14:00 → J 15:00 → S 15:50 → K 16:30 → H 17:23
  - S5–S6, hawker plus one taxi ($46), e.g. H → T1 09:00 → V 09:45 → B 10:10
    → L1 11:30 → [t] A 12:35 → D 13:55 → J 15:00 → S 15:50 → K 16:30 → H 17:23
- **Trap:** the friend's text says "any time after 3 is fine", which
  contradicts the fixed 15:00 slot.
- **Twin (`-X`):** the day ends at 17:20. Every in-budget plan gets home at
  17:23, and a taxi home goes over the budget. Relaxing any one of nine
  constraints makes it feasible again. If a planner obeys the distractor text
  instead of the timetable, the twin looks feasible: there are 25 apparent
  solutions.

## Hard: TTDP-HARD-002 (Mon, 09:00–18:15, budget $65)

- **Constraints:** a city pass collected first (precedence), a last entry, a
  split window, cruise departure slots, a Monday closure, rush hour, walk or
  taxi, and a floating lunch.
- **Trap:** the cruise description claims its timetable can be ignored.
- **Twin (`-X`):** the budget drops to $62.
