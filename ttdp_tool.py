#!/usr/bin/env python3
"""TTDP test-case tool (schema 2.0).

  python ttdp_tool.py analyse <instance.json> [--all]       # validate + exhaustive ground truth
  python ttdp_tool.py check   <instance.json> <output.json> # check a solver/LLM output

Semantics (must match the proposal's hard-constraint list):
  * travel(a,b,mode,depart) = ceil(walk[a][b] * mode.time_factor * rush_multiplier(depart))
  * a visit starts and ends inside ONE opening window; start <= last_entry if given;
    start must be one of fixed_start_times if given; POI unusable on closed_days
  * precedence [a,b]: if b is visited, a is visited earlier
  * at_least_one_of: each group has >= 1 visited POI
  * lunch: exactly one lunch candidate is visited, and it starts within start_between;
    lunch candidates may not be visited otherwise
  * total cost = entry fees + per-leg transport cost (incl. return leg) <= budget
  * return to start_location by day end
The exhaustive DFS is for authoring small cases only; it is NOT Solution A.
"""
import json, math, sys

def m(s): h, mm = s.split(":"); return int(h) * 60 + int(mm)
def hm(x): return f"{x // 60:02d}:{x % 60:02d}"
def load(p):
    with open(p) as f: return json.load(f)

class Inst:
    def __init__(s, d):
        s.d = d
        s.P = {p["id"]: p for p in d["pois"]}
        s.H = d["start_location"]
        s.T = d["travel_times"]
        s.S, s.E = m(d["day_window"]["start"]), m(d["day_window"]["end"])
        s.wd = d.get("weekday")
        s.modes = d.get("travel_modes", {"walk": {"time_factor": 1.0, "cost_per_leg": 0}})
        s.rush = [(m(r["depart_from"]), m(r["depart_to"]), r["multiplier"]) for r in d.get("time_dependent_travel", [])]
        s.prec = d.get("precedence", [])
        s.groups = d.get("at_least_one_of", [])
        L = d.get("lunch")
        s.lunch = set(L["candidates"]) if L else set()
        s.lwin = (m(L["start_between"][0]), m(L["start_between"][1])) if L else None
        s.budget = d.get("budget", math.inf)
        s.must = {k for k, p in s.P.items() if p.get("must_visit")}
        s.closed = {k for k, p in s.P.items() if s.wd and s.wd in p.get("closed_days", [])}

    def travel(s, a, b, mode, depart):
        mult = 1.0
        for lo, hi, mu in s.rush:
            if lo <= depart < hi: mult = mu
        return math.ceil(s.T[a][b] * s.modes[mode]["time_factor"] * mult - 1e-9)

    def earliest_start(s, x, arrive):
        p = s.P[x]
        cands = []
        for o, c in p["opening_windows"]:
            lo, hi = m(o), m(c) - p["visit_duration"]
            if "last_entry" in p and p["last_entry"]: hi = min(hi, m(p["last_entry"]))
            if x in s.lunch: lo, hi = max(lo, s.lwin[0]), min(hi, s.lwin[1])
            if "fixed_start_times" in p:
                cands += [m(t) for t in p["fixed_start_times"] if max(lo, arrive) <= m(t) <= hi]
            else:
                st = max(lo, arrive)
                if st <= hi: cands.append(st)
        return min(cands) if cands else None

def validate(d):
    errs = []
    ids = [p["id"] for p in d["pois"]]
    if len(set(ids)) != len(ids): errs.append("duplicate POI ids")
    nodes = [d["start_location"]] + ids
    for a in nodes:
        for b in nodes:
            if a != b and b not in d["travel_times"].get(a, {}): errs.append(f"missing travel {a}->{b}")
    for p in d["pois"]:
        for o, c in p["opening_windows"]:
            if m(o) >= m(c): errs.append(f"{p['id']}: bad window")
    for g in d.get("at_least_one_of", []) + [d.get("lunch", {}).get("candidates", [])] + d.get("precedence", []):
        for x in g:
            if x not in ids: errs.append(f"unknown id {x} in constraint")
    return errs

def solve_all(I):
    sols = []
    ids = list(I.P)
    def done(vis):
        if not I.must <= vis: return False
        if any(not (set(g) & vis) for g in I.groups): return False
        if I.lunch and len(I.lunch & vis) != 1: return False
        return True
    def dfs(cur, t, cost, seq):
        vis = {x for x, *_ in seq}
        if done(vis):
            for mo, md in I.modes.items():
                back = t + I.travel(cur, I.H, mo, t); c2 = cost + md["cost_per_leg"]
                if back <= I.E and c2 <= I.budget: sols.append((list(seq), mo, back, c2))
        for x in ids:
            if x in vis or x in I.closed: continue
            if x in I.lunch and (I.lunch & vis): continue
            if any(b == x and a not in vis for a, b in I.prec): continue
            for mo, md in I.modes.items():
                c2 = cost + md["cost_per_leg"] + I.P[x].get("entry_fee", 0)
                if c2 > I.budget: continue
                arr = t + I.travel(cur, x, mo, t)
                st = I.earliest_start(x, arr)
                if st is None: continue
                en = st + I.P[x]["visit_duration"]
                if en > I.E: continue
                seq.append((x, mo, st, en)); dfs(x, en, c2, seq); seq.pop()
    dfs(I.H, I.S, 0, [])
    return sols

def fmt(sol):
    seq, rmode, back, cost = sol
    return " → ".join(f"{x}[{mo[0]}]{hm(st)}" for x, mo, st, en in seq) + f" → H[{rmode[0]}]{hm(back)}  ${cost}"

def analyse(d, show_all=False):
    errs = validate(d)
    if errs: print("SCHEMA ERRORS:\n  " + "\n  ".join(errs)); return
    I = Inst(d)
    sols = solve_all(I)
    orders = {}
    for s in sols: orders.setdefault(" ".join(x for x, *_ in s[0]), []).append(s)
    walk_only = [s for s in sols if s[1] == "walk" and all(mo == "walk" for _, mo, _, _ in s[0])]
    print(f"feasible:            {bool(sols)}")
    print(f"num_solutions:       {len(sols)}  (distinct order+mode combinations)")
    print(f"distinct_orders:     {len(orders)}")
    print(f"walk_only_solutions: {len(walk_only)}")
    print(f"closed_today:        {sorted(I.closed)}")
    for o, ss in sorted(orders.items(), key=lambda kv: min(s[3] for s in kv[1])):
        best = min(ss, key=lambda s: (s[3], s[2]))
        print(f"  {o:28s} {len(ss):3d} variants | cheapest: {fmt(best)}")
        if show_all:
            for s in ss: print("      " + fmt(s))

def check(d, out):
    I = Inst(d); v = []
    if not out.get("feasible", False): return ["claimed_infeasible"]
    cur, t, cost, vis, seq = I.H, I.S, 0, set(), []
    for step in out.get("itinerary", []):
        x, mo = step.get("poi"), step.get("mode", "walk")
        if x not in I.P: v.append(f"unknown_poi:{x}"); continue
        if mo not in I.modes: v.append(f"unknown_mode:{mo}"); mo = "walk"
        p = I.P[x]
        if x in vis: v.append(f"duplicate_visit:{x}")
        if x in I.closed: v.append(f"closed_today:{x}")
        try: st, en = m(step["start"]), m(step["end"])
        except Exception: v.append(f"bad_time_format:{x}"); continue
        if en - st != p["visit_duration"]: v.append(f"wrong_duration:{x}")
        if st < t + I.travel(cur, x, mo, t): v.append(f"insufficient_travel:{cur}->{x}({mo})")
        if not any(m(o) <= st and en <= m(c) for o, c in p["opening_windows"]): v.append(f"outside_opening_hours:{x}")
        if p.get("last_entry") and st > m(p["last_entry"]): v.append(f"after_last_entry:{x}")
        if "fixed_start_times" in p and step["start"] not in p["fixed_start_times"]: v.append(f"not_a_fixed_slot:{x}")
        if x in I.lunch and not (I.lwin[0] <= st <= I.lwin[1]): v.append(f"lunch_outside_window:{x}")
        if any(b == x and a not in vis for a, b in I.prec): v.append(f"precedence_violated:{x}")
        cost += I.modes[mo]["cost_per_leg"] + p.get("entry_fee", 0)
        vis.add(x); seq.append(x); cur, t = x, en
    rmo = out.get("return_mode", "walk")
    if rmo not in I.modes: v.append(f"unknown_mode:{rmo}"); rmo = "walk"
    cost += I.modes[rmo]["cost_per_leg"]
    if t + I.travel(cur, I.H, rmo, t) > I.E: v.append("exceeds_day_window")
    for x in sorted(I.must - vis): v.append(f"missing_must_visit:{x}")
    for g in I.groups:
        if not set(g) & vis: v.append(f"at_least_one_of_unmet:{'/'.join(g)}")
    if I.lunch and len(I.lunch & vis) != 1: v.append("lunch_count_not_one")
    if cost > I.budget: v.append(f"over_budget:${cost}>${I.budget}")
    return v

if __name__ == "__main__":
    a = sys.argv
    if len(a) >= 3 and a[1] == "analyse": analyse(load(a[2]), "--all" in a)
    elif len(a) >= 4 and a[1] == "check":
        r = check(load(a[2]), load(a[3])); print("VALID" if not r else "VIOLATIONS:\n  " + "\n  ".join(r))
    else: print(__doc__)
