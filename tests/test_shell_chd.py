"""Tests for SHELL, CHD, and CHX statements."""
import os
import tempfile
from contextlib import redirect_stdout
from io import StringIO

import pytest

from basic09 import Basic09Interpreter


def _run(source: str) -> str:
    buf = StringIO()
    with redirect_stdout(buf):
        Basic09Interpreter(source).run()
    return buf.getvalue()


def test_shell_runs_command(tmp_path):
    sentinel = tmp_path / "sentinel.txt"
    source = f'SHELL "touch {sentinel}"'
    _run(source)
    assert sentinel.exists()


def test_shell_output_goes_to_stdout(capfd):
    source = 'SHELL "echo hello_from_shell"'
    Basic09Interpreter(source).run()
    assert "hello_from_shell" in capfd.readouterr().out


def test_chd_changes_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(os.getcwd())  # ensure cwd is restored after test
    source = f'CHD "{tmp_path}"'
    _run(source)
    assert os.path.realpath(os.getcwd()) == os.path.realpath(str(tmp_path))


def test_chx_is_noop():
    original = os.getcwd()
    source = 'CHX "/tmp"'
    _run(source)
    assert os.getcwd() == original
