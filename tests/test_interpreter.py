"""Tests for the Basic09 interpreter, driven by unittest.b09."""
import os
import sys
from contextlib import redirect_stdout
from io import StringIO

import pytest

from basic09 import Basic09Interpreter

UNITTEST_B09 = os.path.join(os.path.dirname(__file__), "unittest.b09")

_PROCEDURE_NAMES = [
    "testIntegerArithmetic",
    "testRealArithmetic",
    "testStringFunctions",
    "testArrayIndexing",
    "testBooleanLogic",
    "testRecordFields",
    "testRepeatUntil",
    "testForNext",
    "testWhile",
    "testLoop",
    "testMathFunctions",
    "testMoreStrings",
    "testReadData",
    "testGoto",
    "testComparisons",
    "testIf",
    "test2DArrays",
    "testStrConv",
    "testProcedures",
    "testOnGoto",
    "testGosub",
    "testTrig",
    "testLogExp",
    "testNestedFor",
    "testMod",
    "testStringCompare",
    "testWhileLoop",
    "testXor",
    "testMoreMath",
    "testBitwise",
    "testSubstr",
    "testArithmetic",
    "testArrays",
    "testTypedVars",
    "testForLoop",
    "testGotoBasic",
    "testIfBasic",
    "testLoopBasic",
    "testMathBasic",
    "testPrint",
    "testProcs",
    "testStringsExt",
]


@pytest.fixture(scope="session")
def b09_interp():
    with open(UNITTEST_B09) as f:
        source = f.read()
    return Basic09Interpreter(source)


@pytest.fixture(scope="session")
def b09_results(b09_interp):
    """Run unittest and return a dict of {test_label: 'PASS'|'FAIL: ...'}.

    Each PASS/FAIL line from the BASIC09 output maps the label to its status.
    """
    buf = StringIO()
    with redirect_stdout(buf):
        b09_interp.run_procedure("unittest")
    results = {}
    for line in buf.getvalue().splitlines():
        if line.startswith("PASS "):
            label = line[5:]
            results[label] = "PASS"
        elif line.startswith("FAIL "):
            rest = line[5:]
            label = rest.split(":")[0]
            results[label] = line
    return results


def _run_procedure(interp, name):
    """Run a single BASIC09 test procedure and return its output lines."""
    buf = StringIO()
    with redirect_stdout(buf):
        from basic09.types import B9Value
        passed = B9Value.integer(0)
        failed = B9Value.integer(0)
        interp.run_procedure(name, [passed, failed])
    return buf.getvalue().splitlines()


@pytest.mark.parametrize("proc_name", _PROCEDURE_NAMES)
def test_procedure(b09_interp, proc_name):
    """Each BASIC09 test procedure should produce only PASS lines."""
    from basic09.types import B9Value
    buf = StringIO()
    with redirect_stdout(buf):
        passed = B9Value.integer(0)
        failed = B9Value.integer(0)
        b09_interp.run_procedure(proc_name, [passed, failed])
    output = buf.getvalue()
    fail_lines = [l for l in output.splitlines() if l.startswith("FAIL")]
    assert not fail_lines, "\n".join(fail_lines)
