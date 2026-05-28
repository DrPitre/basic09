"""Run all files in --b09-dir through the interpreter.

Usage:
    pytest --b09-dir /path/to/basic09/sources
"""
from contextlib import redirect_stdout
from io import StringIO
from threading import Thread
from unittest.mock import patch

import pytest

from basic09 import Basic09Interpreter

_TIMEOUT = 5  # seconds


def _run_with_timeout(fn):
    """Run fn in a thread; raise TimeoutError if it doesn't finish in time."""
    exc = []
    def target():
        try:
            fn()
        except Exception as e:
            exc.append(e)
    t = Thread(target=target, daemon=True)
    t.start()
    t.join(_TIMEOUT)
    if t.is_alive():
        raise TimeoutError(f"did not complete within {_TIMEOUT}s (infinite loop?)")
    if exc:
        raise exc[0]


def test_parses(b09_file):
    source = b09_file.read_text()
    with patch("builtins.input", return_value="0"):
        Basic09Interpreter(source)


def test_runs(b09_file):
    source = b09_file.read_text()
    try:
        with patch("builtins.input", return_value="0"):
            interp = Basic09Interpreter(source)
    except Exception as e:
        pytest.skip(f"Parse failed: {e}")
    buf = StringIO()
    def run():
        with redirect_stdout(buf), patch("builtins.input", return_value="0"):
            interp.run()
    _run_with_timeout(run)
