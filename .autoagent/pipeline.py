"""Starter pipeline — replace with your own logic.

This file is loaded by PipelineRunner via compile()+exec().
It must define a module-level ``run(input_data, primitives)`` function
that returns a dict.
"""


def run(input_data, primitives=None):
    """Process *input_data* and return a result dict.

    Parameters
    ----------
    input_data : Any
        The input payload provided by the runner.
    primitives : PrimitivesContext | None
        Optional primitives for LLM calls, embeddings, etc.

    Returns
    -------
    dict
        Must be JSON-serializable.
    """
    return {"echo": input_data}
