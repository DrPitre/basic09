from pathlib import Path
import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--b09-dir",
        metavar="DIR",
        default=None,
        help="Directory of BASIC09 source files to run through the interpreter.",
    )


def pytest_generate_tests(metafunc):
    if "b09_file" not in metafunc.fixturenames:
        return
    b09_dir = metafunc.config.getoption("--b09-dir")
    if b09_dir:
        files = sorted(f for f in Path(b09_dir).iterdir() if f.is_file())
        metafunc.parametrize("b09_file", files, ids=[f.name for f in files])
    else:
        metafunc.parametrize(
            "b09_file",
            [pytest.param(None, marks=pytest.mark.skip(reason="pass --b09-dir to enable"))],
        )
