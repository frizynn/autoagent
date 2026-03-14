"""Crash pipeline fixture — run() raises ValueError."""


def run(input_data, primitives):
    raise ValueError("something went wrong in the pipeline")
