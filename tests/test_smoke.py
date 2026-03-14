"""Smoke tests to verify package structure."""

from autoagent import __version__


def test_version() -> None:
    assert __version__ == "0.1.0"


def test_import() -> None:
    import autoagent

    assert hasattr(autoagent, "__version__")
