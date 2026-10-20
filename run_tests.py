#!/usr/bin/env python3
"""Run a solver over every test case in testcases/ and grade it with the shared checker.

  python run_tests.py --solver "python my_solver.py"   # run a solver on every instance
  python run_tests.py --outputs results/llm_baseline   # grade outputs saved earlier
  python run_tests.py --self-test                      # sanity-check the test suite itself

Solver contract: the runner calls `<solver command> <path/to/ID.instance.json>`. The solver
reads only that file and prints one JSON object (the format in testcases/example_output.json)
to stdout. With --outputs, the runner instead reads <DIR>/<ID>.output.json for each instance.

Grading follows "Correct output" in the README: on a feasible instance the output must be an itinerary the
checker accepts; on an infeasible instance it must say "feasible": false. Anything else fails.

Cases run easy -> medium -> hard, and the run stops at the first failure unless --keep-going.
Exit code 0 if every selected case passed, 1 otherwise.
"""
import argparse, glob, json, os, shlex, subprocess, sys, time
import ttdp_tool as T

ROOT = os.path.dirname(os.path.abspath(__file__))
LEVELS = {"easy": 0, "medium": 1, "hard": 2}

def discover(folder):
    cases = []
    for ip in glob.glob(os.path.join(folder, "**", "*.instance.json"), recursive=True):
        ap = ip[:-len(".instance.json")] + ".answer.json"
        if not os.path.exists(ap): sys.exit(f"missing answer file for {ip}")
        cases.append({"id": os.path.basename(ip)[:-len(".instance.json")], "instance": ip, "answer": ap,
                      "inst": T.load(ip), "ans": T.load(ap)})
    by_id = {c["id"]: c["ans"] for c in cases}
    for c in cases:  # an infeasible twin without a level inherits its partner's
        c["level"] = c["ans"].get("level") or by_id.get(c["ans"].get("twin_of"), {}).get("level", "?")
    return sorted(cases, key=lambda c: (LEVELS.get(c["level"], 9), c["id"]))

def grade(inst, ans, out):
    """Return None if the output is correct, else a short reason."""
    if not isinstance(out, dict) or not isinstance(out.get("feasible"), bool):
        return "output is not a JSON object with a boolean 'feasible'"
    if not ans["feasible"]:
        return None if not out["feasible"] else "gave an itinerary for an infeasible instance"
    if not out["feasible"]:
        return "claimed infeasible, but the instance is feasible"
    v = T.check(inst, out)
    return None if not v else "violations: " + ", ".join(v)

def split_command(cmd):
    if os.name != "nt": args = shlex.split(cmd)  # macOS / Linux: normal shell quoting
    else:  # Windows: keep backslashes in paths, but drop the quotes around arguments
        args = [t[1:-1] if len(t) > 1 and t[0] == t[-1] and t[0] in "\"'" else t
                for t in shlex.split(cmd, posix=False)]
    # Many Macs only have "python3", some Windows installs only "python": either runs this interpreter.
    if args and args[0] in ("python", "python3"): args[0] = sys.executable
    return args

def run_solver(cmd, path, timeout):
    t0 = time.time()
    env = dict(os.environ, PYTHONIOENCODING="utf-8")  # same output encoding on every OS
    try:
        p = subprocess.run(split_command(cmd) + [path], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, cwd=ROOT, env=env)
    except subprocess.TimeoutExpired:
        return None, time.time() - t0, f"timed out after {timeout}s"
    except OSError as e:
        return None, time.time() - t0, f"could not start solver: {e}"
    dt = time.time() - t0
    if p.returncode != 0:
        tail = (p.stderr.strip().splitlines() or ["(no stderr)"])[-1]
        return None, dt, f"solver exited with code {p.returncode}: {tail}"
    try: return json.loads(p.stdout), dt, None
    except json.JSONDecodeError: return None, dt, "solver output is not valid JSON"

def read_output(folder, cid):
    path = os.path.join(folder, cid + ".output.json")
    if not os.path.exists(path): return None, 0.0, f"no output file {path}"
    try: return T.load(path), 0.0, None
    except json.JSONDecodeError: return None, 0.0, f"{path} is not valid JSON"

def self_test(case):
    """The answer file must agree with the exhaustive search, and its reference plans must pass."""
    inst, ans = case["inst"], case["ans"]
    errs = T.validate(inst)
    if errs: return "schema errors: " + "; ".join(errs)
    n = len(T.solve_all(T.Inst(inst)))
    if (n > 0) != ans["feasible"] or n != ans["num_solutions"]:
        return f"answer says feasible={ans['feasible']} num_solutions={ans['num_solutions']}, search found {n}"
    for s in ans.get("solutions", []):
        out = {"feasible": True, "itinerary": s["itinerary"], "return_mode": s.get("return_mode", "walk")}
        v = T.check(inst, out)
        if v: return f"reference solution {s.get('name')} fails: " + ", ".join(v)
    return None

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--solver", help="command to run; the instance path is appended")
    mode.add_argument("--outputs", metavar="DIR", help="grade saved <ID>.output.json files from DIR")
    mode.add_argument("--self-test", action="store_true", help="check answer files against the exhaustive search")
    ap.add_argument("--cases", default=os.path.join(ROOT, "testcases"), help="test-case folder (default: testcases/)")
    ap.add_argument("--level", choices=list(LEVELS), action="append", help="only run this level (repeatable)")
    ap.add_argument("-k", "--filter", help="only run cases whose ID contains this text")
    ap.add_argument("--keep-going", action="store_true", help="run every case instead of stopping at the first failure")
    ap.add_argument("--timeout", type=float, default=120, help="seconds per solver call (default: 120)")
    a = ap.parse_args()

    cases = [c for c in discover(a.cases)
             if (not a.level or c["level"] in a.level) and (not a.filter or a.filter in c["id"])]
    if not cases: sys.exit("no test cases selected")

    passed, failed = 0, []
    for c in cases:
        label = f"{c['id']:18s} {c['level']:6s} {'feasible' if c['ans']['feasible'] else 'infeasible':10s}"
        if a.self_test:
            t0 = time.time(); reason = self_test(c); dt = time.time() - t0
        else:
            out, dt, reason = (run_solver(a.solver, c["instance"], a.timeout) if a.solver
                               else read_output(a.outputs, c["id"]))
            if reason is None: reason = grade(c["inst"], c["ans"], out)
        print(f"{'PASS' if reason is None else 'FAIL'}  {label} {dt:6.2f}s" + ("" if reason is None else f"\n      {reason}"))
        sys.stdout.flush()
        if reason is None: passed += 1
        else:
            failed.append(c["id"])
            if not a.keep_going: break

    ran = passed + len(failed)
    print(f"\n{passed}/{ran} passed" + (f", {len(cases) - ran} not run (stopped at first failure; use --keep-going)"
                                       if ran < len(cases) else ""))
    if failed: print("failed: " + ", ".join(failed))
    sys.exit(1 if failed else 0)

if __name__ == "__main__":
    main()
