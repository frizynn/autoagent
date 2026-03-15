"""Pipeline fixture that raises during scoring setup — returns non-scoreable output."""


def run(input_data, primitives):
    """Return an object that will cause certain scorers to fail."""
    # Returning a type that, combined with a custom bad scorer, triggers scoring errors
    return input_data
