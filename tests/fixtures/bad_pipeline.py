"""Bad pipeline fixture — has no run() function."""

def not_run(input_data, primitives):
    return {"oops": True}
