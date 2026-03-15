"""Slow pipeline fixture — sleeps for 10s to trigger per-example timeout."""

import time


def run(input_data, primitives):
    """Pipeline that sleeps too long, used for timeout testing."""
    time.sleep(10)
    return "should never reach here"
