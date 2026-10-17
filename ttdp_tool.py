#!/usr/bin/env python3
"""TTDP test-case tool (schema 2.1; 2.0 instances remain valid).

  python ttdp_tool.py analyse <instance.json> [--all]       # validate + exhaustive ground truth
  python ttdp_tool.py check   <instance.json> <output.json> # check a solver/LLM output

Semantics (must match the proposal's hard-constraint list):
  * travel(a,b,mode,depart) = ceil(walk[a][b] * mode.time_factor * rush_multiplier(depart))
  * a visit starts and ends inside ONE opening window; start <= last_entry if given;
    start must be one of fixed_start_times if given; POI unusable on closed_days
  * closures [from,to]: the visit may not overlap the interval (a one-off gap in the window)
  * arrival_buffer: start >= arrival + buffer (security / ticketing time at that POI)
  * no_modes: a leg into or out of that POI may not use the listed modes
  * max_single_walk / max_walk_total: walking minutes per leg / over the day (incl. return)
  * precedence [a,b]: if b is visited, a is visited earlier
  * immediately_after [a,b]: if b is visited, the stop directly before it is a
  * if_then [a,b]: if a is visited, b is visited too
  * at_least_one_of / at_most_one_of: each group has >= 1 / <= 1 visited POI
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
        s.b2b = d.get("immediately_after", [])
        s.cond = d.get("if_then", [])
        s.groups = d.get("at_least_one_of", [])
        s.amo = d.get("at_most_one_of", [])
        L = d.get("lunch")
        s.lunch = set(L["candidates"]) if L else set()
        s.lwin = (m(L["start_between"][0]), m(L["start_between"][1])) if L else None
        s.budget = d.get("budget", math.inf)
        s.walk_leg = d.get("max_single_walk", math.inf)
        s.walk_cap = d.get("max_walk_total", math.inf)
        s.must = {k for k, p in s.P.items() if p.get("must_visit")}
        s.closed = {k for k, p in s.P.items() if s.wd and s.wd in p.get("closed_days", [])}

    def travel(s, a, b, mode, depart):
        mult = 1.0
        for lo, hi, mu in s.rush:
            if lo <= depart < hi: mult = mu
        return math.ceil(s.T[a][b] * s.modes[mode]["time_factor"] * mult - 1e-9)

    def mode_ok(s, a, b, mode):
        return all(mode not in s.P[x].get("no_modes", []) for x in (a, b) if x in s.P)

    def windows(s, x):
        ws = [(m(o), m(c)) for o, c in s.P[x]["opening_windows"]]
        for a, b in s.P[x].get("closures", []):
            a, b = m(a), m(b)
            ws = [w for lo, hi in ws for w in ((lo, min(hi, a)), (max(lo, b), hi)) if w[0] < w[1]]
        return ws

    def earliest_start(s, x, arrive):
        p = s.P[x]
        arrive += p.get("arrival_buffer", 0)
        cands = []
        for lo, c in s.windows(x):
            hi = c - p["visit_duration"]
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
        for o, c in p["opening_windows"] + p.get("closures", []):
            if m(o) >= m(c): errs.append(f"{p['id']}: bad window")
        for mo in p.get("no_modes", []):
            if mo not in d.get("travel_modes", {"walk": 0}): errs.append(f"{p['id']}: unknown mode {mo}")
    rel = d.get("precedence", []) + d.get("immediately_after", []) + d.get("if_then", [])
    for g in d.get("at_least_one_of", []) + d.get("at_most_one_of", []) + [d.get("lunch", {}).get("candidates", [])] + rel:
        for x in g:
            if x not in ids: errs.append(f"unknown id {x} in constraint")
    return errs

def solve_all(I):
    sols = []
    ids = list(I.P)
    def done(vis):
        if not I.must <= vis: return False
        if any(not (set(g) & vis) for g in I.groups): return False
        if any(a in vis and b not in vis for a, b in I.cond): return False
        if I.lunch and len(I.lunch & vis) != 1: return False
        return True
    def leg(a, b, mo, t, walked):
        tt = I.travel(a, b, mo, t)
        if not I.mode_ok(a, b, mo): return None
        if mo == "walk" and (tt > I.walk_leg or walked + tt > I.walk_cap): return None
        return tt, walked + (tt if mo == "walk" else 0)
    def dfs(cur, t, cost, walked, seq):
        vis = {x for x, *_ in seq}
        if done(vis):
            for mo, md in I.modes.items():
                r = leg(cur, I.H, mo, t, walked); c2 = cost + md["cost_per_leg"]
                if r and t + r[0] <= I.E and c2 <= I.budget: sols.append((list(seq), mo, t + r[0], c2))
        for x in ids:
            if x in vis or x in I.closed: continue
            if x in I.lunch and (I.lunch & vis): continue
            if any(b == x and a not in vis for a, b in I.prec): continue
            if any(b == x and a != cur for a, b in I.b2b): continue
            if any(x in g and set(g) & vis for g in I.amo): continue
            for mo, md in I.modes.items():
                c2 = cost + md["cost_per_leg"] + I.P[x].get("entry_fee", 0)
                if c2 > I.budget: continue
                r = leg(cur, x, mo, t, walked)
                if not r: continue
                st = I.earliest_start(x, t + r[0])
                if st is None: continue
                en = st + I.P[x]["visit_duration"]
                if en > I.E: continue
                seq.append((x, mo, st, en)); dfs(x, en, c2, r[1], seq); seq.pop()
    dfs(I.H, I.S, 0, 0, [])
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
    cur, t, cost, walked, vis, seq = I.H, I.S, 0, 0, set(), []
    def leg(a, b, mo, depart):
        nonlocal walked
        tt = I.travel(a, b, mo, depart)
        if not I.mode_ok(a, b, mo): v.append(f"mode_not_allowed:{a}->{b}({mo})")
        if mo == "walk":
            walked += tt
            if tt > I.walk_leg: v.append(f"walk_leg_too_long:{a}->{b}")
        return tt
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
        arr = t + leg(cur, x, mo, t)
        if st < arr: v.append(f"insufficient_travel:{cur}->{x}({mo})")
        elif st < arr + p.get("arrival_buffer", 0): v.append(f"missing_arrival_buffer:{x}")
        if not any(m(o) <= st and en <= m(c) for o, c in p["opening_windows"]): v.append(f"outside_opening_hours:{x}")
        elif any(st < m(b) and en > m(a) for a, b in p.get("closures", [])): v.append(f"during_closure:{x}")
        if p.get("last_entry") and st > m(p["last_entry"]): v.append(f"after_last_entry:{x}")
        if "fixed_start_times" in p and step["start"] not in p["fixed_start_times"]: v.append(f"not_a_fixed_slot:{x}")
        if x in I.lunch and not (I.lwin[0] <= st <= I.lwin[1]): v.append(f"lunch_outside_window:{x}")
        if any(b == x and a not in vis for a, b in I.prec): v.append(f"precedence_violated:{x}")
        for a, b in I.b2b:
            if b == x and a != cur: v.append(f"not_back_to_back:{a}->{b}")
        cost += I.modes[mo]["cost_per_leg"] + p.get("entry_fee", 0)
        vis.add(x); seq.append(x); cur, t = x, en
    rmo = out.get("return_mode", "walk")
    if rmo not in I.modes: v.append(f"unknown_mode:{rmo}"); rmo = "walk"
    cost += I.modes[rmo]["cost_per_leg"]
    if t + leg(cur, I.H, rmo, t) > I.E: v.append("exceeds_day_window")
    if walked > I.walk_cap: v.append(f"walk_total_exceeded:{walked}>{I.walk_cap}")
    for x in sorted(I.must - vis): v.append(f"missing_must_visit:{x}")
    for g in I.groups:
        if not set(g) & vis: v.append(f"at_least_one_of_unmet:{'/'.join(g)}")
    for g in I.amo:
        if len(set(g) & vis) > 1: v.append(f"at_most_one_of_violated:{'/'.join(g)}")
    for a, b in I.cond:
        if a in vis and b not in vis: v.append(f"conditional_unmet:{a}->{b}")
    if I.lunch and len(I.lunch & vis) != 1: v.append("lunch_count_not_one")
    if cost > I.budget: v.append(f"over_budget:${cost}>${I.budget}")
    return v

if __name__ == "__main__":
    a = sys.argv
    if len(a) >= 3 and a[1] == "analyse": analyse(load(a[2]), "--all" in a)
    elif len(a) >= 4 and a[1] == "check":
        r = check(load(a[2]), load(a[3])); print("VALID" if not r else "VIOLATIONS:\n  " + "\n  ".join(r))
    else: print(__doc__)
