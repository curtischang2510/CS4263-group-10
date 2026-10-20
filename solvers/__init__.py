"""Solvers run by `python run_tests.py`. Each takes one parsed instance and returns one
output dict; one that still raises NotImplementedError is skipped. To test another
solver, add it to SOLVERS."""
from . import csp, llm

SOLVERS = {
    "csp": csp.solve,  # Solution A
    "llm": llm.solve,  # Solution B
}
