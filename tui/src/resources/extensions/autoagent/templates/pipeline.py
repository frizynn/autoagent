"""Baseline pipeline — the starting point for optimization.

This file is modified by the agent during experiments.
It must define a `run(input_data, context)` function.

Current approach: echo the input back unchanged.
"""


def run(input_data, context=None):
    """Process input_data and return a result.

    Parameters
    ----------
    input_data : Any
        The input from the test case.
    context : Any, optional
        Additional context (unused in baseline).

    Returns
    -------
    dict
        Must contain an "output" key with the result.
    """
    return {"output": input_data}
