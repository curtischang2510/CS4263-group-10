"""Solvers run by `python run_tests.py`. Each takes one parsed instance and returns one
output dict; one that still raises NotImplementedError is skipped. To test another
solver, add it to SOLVERS."""
from . import csp, llm

SOLVERS = {
    "csp":                      csp.solve,                     # Solution A
    "llm":                      llm.solve,                     # Solution B — baseline
    "llm_cot":                  llm.solve_cot,                 # Solution B — safeguard 1: Chain-of-Thought
    "llm_ltm":                  llm.solve_ltm,                 # Solution B — safeguard 1a: Least-to-Most
    "llm_self_refine":          llm.solve_self_refine,         # Solution B — safeguard 2: Self-Refine
    "llm_verifier_loop":        llm.solve_verifier_loop,       # Solution B — safeguard 3: Verifier-in-the-loop
    "llm_self_consistency":     llm.solve_self_consistency,    # Solution B — safeguard 4: Self-consistency
    "llm_reflexion":            llm.solve_reflexion,           # Solution B — safeguard 5: Reflexion
    "llm_combined_1":           llm.solve_combined_1,          # Solution B — combined 1: CoT + Verifier-in-the-Loop + Self-Consistency
    "llm_combined_2":           llm.solve_combined_2,          # Solution B — combined 2: LtM + Reflexion + Self-Consistency
    "llm_combined_3":           llm.solve_combined_3,          # Solution B — combined 3: CoT + Verifier + Reflexion + Self-Consistency
}
