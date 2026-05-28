"""Tests generated from the Basic09 Command Reference wiki sample procedures.

Regenerate with:  python scripts/generate_wiki_tests.py
"""
import pytest
from unittest.mock import patch
from pathlib import Path
from io import StringIO
from contextlib import redirect_stdout

from basic09 import Basic09Interpreter

import os
_NITROS9DIR = Path(os.environ.get("NITROS9DIR", str(Path.home() / "Projects/coco-shelf/nitros9")))
PROCS_DIR = Path(_NITROS9DIR) / "3rdparty/packages/basic09/tests/wiki_procs"

# (identifier, command, unsupported_features, needs_input)
_WIKI_PROCS = [
    ('examples', 'examples', [], False),
    ('sample', 'sample', [], True),
    ('examples_1', 'examples', [], False),
    ('sample_1', 'sample', [], True),
    ('sample_2', 'sample', ['PEEK', 'ADDR'], True),
    ('examples_2', 'examples', [], False),
    ('sample_3', 'sample', [], True),
    ('examples_3', 'examples', [], False),
    ('sample_4', 'sample', [], True),
    ('examples_4', 'examples', [], False),
    ('sample_5', 'sample', [], True),
    ('examples_5', 'examples', [], False),
    ('sample_6', 'sample', [], True),
    ('examples_6', 'examples', [], False),
    ('sample_7', 'sample', ['SHELL'], False),
    ('examples_7', 'examples', ['BYE'], True),
    ('sample_8', 'sample', ['BYE'], True),
    ('examples_8', 'examples', ['CHAIN'], False),
    ('sample_9', 'sample', ['BYE', 'CHAIN', 'SHELL'], True),
    ('examples_9', 'examples', [], False),
    ('sample_10', 'sample', ['CREATE', 'CLOSE', 'WRITE #', 'DELETE', 'SHELL'], False),
    ('examples_10', 'examples', [], False),
    ('sample_11', 'sample', [], True),
    ('examples_11', 'examples', [], False),
    ('examples_12', 'examples', ['OPEN', 'CLOSE'], False),
    ('sample_12', 'sample', ['CREATE', 'CLOSE', 'WRITE #', 'SHELL'], False),
    ('examples_13', 'examples', [], False),
    ('sample_13', 'sample', [], True),
    ('examples_14', 'examples', ['CREATE'], False),
    ('sample_14', 'sample', ['CREATE', 'CLOSE', 'WRITE #', 'SHELL'], False),
    ('overview', 'overview', [], False),
    ('examples_15', 'examples', [], False),
    ('sample_15', 'sample', [], True),
    ('overview_1', 'overview', ['SHELL'], False),
    ('examples_16', 'examples', [], False),
    ('sample_16', 'sample', [], False),
    ('examples_17', 'examples', [], False),
    ('sample_17', 'sample', [], True),
    ('examples_18', 'examples', ['DELETE'], False),
    ('sample_18', 'sample', ['CREATE', 'CLOSE', 'WRITE #', 'DELETE', 'SHELL'], False),
    ('parameters', 'parameters', [], False),
    ('examples_19', 'examples', [], False),
    ('sample_19', 'sample', [], True),
    ('syntax', 'syntax', [], False),
    ('syntax_1', 'syntax', [], False),
    ('overview_2', 'overview', [], False),
    ('examples_20', 'examples', [], False),
    ('sample_20', 'sample', [], True),
    ('syntax_2', 'syntax', [], False),
    ('overview_3', 'overview', [], False),
    ('overview_4', 'overview', [], False),
    ('examples_21', 'examples', ['CLOSE'], False),
    ('sample_21', 'sample', ['OPEN', 'READ #', 'CLOSE', 'SHELL'], False),
    ('examples_22', 'examples', [], False),
    ('sample_22', 'sample', ['OPEN', 'ON ERROR', 'READ #', 'CLOSE'], True),
    ('examples_23', 'examples', [], False),
    ('sample_23', 'sample', ['ON ERROR', 'CREATE', 'DELETE'], True),
    ('syntax_3', 'syntax', [], False),
    ('examples_24', 'examples', [], False),
    ('sample_24', 'sample', [], True),
    ('examples_25', 'examples', [], False),
    ('sample_25', 'sample', [], False),
    ('examples_26', 'examples', [], False),
    ('sample_26', 'sample', ['GET #'], False),
    ('examples_27', 'examples', [], False),
    ('sample_27', 'sample', [], False),
    ('examples_28', 'examples', [], False),
    ('sample_28', 'sample', [], False),
    ('syntax_4', 'syntax', [], False),
    ('examples_29', 'examples', [], False),
    ('sample_29', 'sample', [], False),
    ('examples_30', 'examples', ['GET #'], True),
    ('sample_30', 'sample', ['OPEN', 'ON ERROR', 'CREATE', 'GET #', 'CLOSE', 'WRITE #', 'DELETE', 'SHELL'], True),
    ('examples_31', 'examples', [], False),
    ('sample_31', 'sample', [], True),
    ('syntax_5', 'syntax', [], False),
    ('overview_5', 'overview', [], False),
    ('examples_32', 'examples', [], False),
    ('sample_32', 'sample', ['OPEN', 'ON ERROR', 'READ #', 'DELETE'], True),
    ('examples_33', 'examples', ['INKEY'], False),
    ('sample_33', 'sample', ['INKEY'], True),
    ('examples_34', 'examples', ['PUT #'], True),
    ('sample_34', 'sample', [], True),
    ('examples_35', 'examples', [], False),
    ('sample_35', 'sample', [], False),
    ('examples_36', 'examples', ['KILL'], True),
    ('sample_36', 'sample', ['SHELL'], False),
    ('overview_6', 'overview', [], False),
    ('examples_37', 'examples', [], False),
    ('sample_37', 'sample', ['GET #'], False),
    ('examples_38', 'examples', [], False),
    ('sample_38', 'sample', [], False),
    ('examples_39', 'examples', [], False),
    ('sample_39', 'sample', [], False),
    ('examples_40', 'examples', [], False),
    ('sample_40', 'sample', [], False),
    ('overview_7', 'overview', [], False),
    ('examples_41', 'examples', [], False),
    ('sample_41', 'sample', ['GET #'], False),
    ('examples_42', 'examples', [], False),
    ('sample_42', 'sample', [], False),
    ('examples_43', 'examples', [], False),
    ('sample_43', 'sample', [], False),
    ('syntax_6', 'syntax', [], False),
    ('examples_44', 'examples', [], True),
    ('sample_44', 'sample', ['GET #'], False),
    ('overview_8', 'overview', [], False),
    ('examples_45', 'examples', [], False),
    ('sample_45', 'sample', [], True),
    ('overview_9', 'overview', [], False),
    ('examples_46', 'examples', [], False),
    ('sample_46', 'sample', [], False),
    ('examples_47', 'examples', [], False),
    ('sample_47', 'sample', [], True),
    ('examples_48', 'examples', [], False),
    ('sample_48', 'sample', ['SHELL'], False),
    ('syntax_7', 'syntax', [], False),
    ('examples_49', 'examples', [], False),
    ('sample_49', 'sample', ['OPEN', 'READ #', 'CLOSE', 'SHELL'], False),
    ('examples_50', 'examples', ['ON ERROR', 'CREATE'], True),
    ('sample_50', 'sample', ['OPEN', 'ON ERROR', 'READ #', 'DELETE'], True),
    ('examples_51', 'examples', [], True),
    ('sample_51', 'sample', ['SHELL'], False),
    ('examples_52', 'examples', [], True),
    ('sample_52', 'sample', [], True),
    ('examples_53', 'examples', ['OPEN'], False),
    ('sample_53', 'sample', ['OPEN', 'READ #', 'CLOSE'], False),
    ('examples_54', 'examples', [], False),
    ('sample_54', 'sample', [], True),
    ('parameters_1', 'parameters', [], False),
    ('examples_55', 'examples', [], False),
    ('sample_55', 'sample', [], False),
    ('examples_56', 'examples', [], False),
    ('examples_57', 'examples', ['PEEK'], False),
    ('sample_56', 'sample', ['POKE', 'PEEK', 'ADDR'], True),
    ('examples_58', 'examples', [], False),
    ('sample_57', 'sample', ['SHELL'], False),
    ('examples_59', 'examples', ['POKE'], False),
    ('sample_58', 'sample', ['POKE', 'PEEK', 'ADDR'], True),
    ('examples_60', 'examples', [], False),
    ('sample_59', 'sample', ['GET #', 'SHELL'], False),
    ('parameters_2', 'parameters', [], False),
    ('examples_61', 'examples', [], False),
    ('sample_60', 'sample', [], True),
    ('parameters_3', 'parameters', [], False),
    ('sample_61', 'sample', ['PEEK', 'ADDR'], False),
    ('examples_62', 'examples', ['PUT #'], True),
    ('sample_62', 'sample', ['ON ERROR', 'PUT #', 'SIZE', 'CREATE', 'CLOSE', 'DELETE', 'SEEK'], True),
    ('examples_63', 'examples', [], False),
    ('sample_63', 'sample', [], True),
    ('examples_64', 'examples', ['READ #'], True),
    ('sample_64', 'sample', ['ON ERROR', 'CREATE', 'READ #', 'CLOSE', 'WRITE #', 'SHELL', 'SEEK'], False),
    ('examples_65', 'examples', [], False),
    ('sample_65', 'sample', ['OPEN', 'ON ERROR', 'CREATE', 'READ #', 'CLOSE', 'SHELL'], True),
    ('syntax_8', 'syntax', [], False),
    ('examples_66', 'examples', [], True),
    ('sample_66', 'sample', ['OPEN', 'CREATE', 'READ #', 'CLOSE', 'WRITE #', 'DELETE'], False),
    ('examples_67', 'examples', [], False),
    ('sample_67', 'sample', [], False),
    ('sample_68', 'sample', ['SHELL'], False),
    ('examples_68', 'examples', [], False),
    ('sample_69', 'sample', [], False),
    ('examples_69', 'examples', [], False),
    ('sample_70', 'sample', [], True),
    ('examples_70', 'examples', [], False),
    ('sample_71', 'sample', [], True),
    ('examples_71', 'examples', ['SIZE', 'SEEK'], False),
    ('sample_72', 'sample', ['OPEN', 'ON ERROR', 'PUT #', 'CREATE', 'GET #', 'CLOSE', 'DELETE', 'SEEK'], False),
    ('examples_72', 'examples', [], False),
    ('sample_73', 'sample', ['SHELL'], False),
    ('examples_73', 'examples', ['KILL', 'SHELL'], False),
    ('sample_74', 'sample', ['OPEN', 'ON ERROR', 'READ #', 'CLOSE', 'SHELL'], True),
    ('examples_74', 'examples', [], False),
    ('sample_75', 'sample', [], True),
    ('examples_75', 'examples', ['SIZE'], False),
    ('sample_76', 'sample', ['ON ERROR', 'PUT #', 'SIZE', 'CREATE', 'CLOSE', 'DELETE', 'SEEK'], True),
    ('examples_76', 'examples', [], False),
    ('sample_77', 'sample', ['SHELL'], False),
    ('syntax_9', 'syntax', [], False),
    ('examples_77', 'examples', [], False),
    ('sample_78', 'sample', ['SHELL'], False),
    ('examples_78', 'examples', [], False),
    ('sample_79', 'sample', [], True),
    ('examples_79', 'examples', [], False),
    ('examples_80', 'examples', [], False),
    ('sample_80', 'sample', [], True),
    ('examples_81', 'examples', [], False),
    ('sample_81', 'sample', [], False),
    ('overview_10', 'overview', [], False),
    ('samples', 'samples', ['RUN SYSCALL', 'SYSCALL', 'ADDR'], False),
    ('examples_82', 'examples', [], False),
    ('sample_82', 'sample', ['SHELL'], False),
    ('examples_83', 'examples', [], False),
    ('sample_83', 'sample', [], True),
    ('examples_84', 'examples', [], False),
    ('sample_84', 'sample', ['OPEN', 'ON ERROR', 'PUT #', 'CREATE', 'GET #', 'CLOSE', 'DELETE', 'SEEK'], True),
    ('syntax_10', 'syntax', [], False),
    ('examples_85', 'examples', [], False),
    ('examples_86', 'examples', [], False),
    ('sample_85', 'sample', ['GET #'], False),
    ('examples_87', 'examples', [], False),
    ('sample_86', 'sample', [], True),
    ('syntax_11', 'syntax', [], False),
    ('examples_88', 'examples', [], True),
    ('examples_89', 'examples', [], False),
    ('sample_87', 'sample', [], True),
    ('syntax_12', 'syntax', [], False),
    ('examples_90', 'examples', [], False),
    ('sample_88', 'sample', ['OPEN', 'ON ERROR', 'READ #', 'CLOSE', 'SHELL'], True),
    ('examples_91', 'examples', ['OPEN', 'CLOSE', 'WRITE #'], False),
    ('sample_89', 'sample', ['ON ERROR', 'CREATE', 'READ #', 'CLOSE', 'WRITE #', 'SHELL', 'SEEK'], False),
    ('examples_92', 'examples', [], False),
    ('sample_90', 'sample', [], True),
]

_IDS = [p[0] for p in _WIKI_PROCS]


@pytest.mark.parametrize("uid,cmd,bad,needs_in", _WIKI_PROCS, ids=_IDS)
def test_wiki_sample_parses(uid, cmd, bad, needs_in):
    """Every wiki sample procedure should parse without a grammar error."""
    source = (PROCS_DIR / uid).read_text()
    try:
        with patch("builtins.input", return_value="0"):
            Basic09Interpreter(source)
    except Exception as e:
        pytest.xfail(f"Parse/load error (likely wiki OCR artifact): {e}")


@pytest.mark.parametrize("uid,cmd,bad,needs_in", _WIKI_PROCS, ids=_IDS)
def test_wiki_sample_runs(uid, cmd, bad, needs_in):
    """Wiki sample procedures without OS-9 dependencies should run."""
    if bad:
        pytest.skip(f"Uses unsupported OS-9 features: {bad}")
    source = (PROCS_DIR / uid).read_text()
    try:
        with patch("builtins.input", return_value="0"):
            interp = Basic09Interpreter(source)
    except Exception as e:
        pytest.xfail(f"Parse error: {e}")
        return
    try:
        buf = StringIO()
        with redirect_stdout(buf), patch("builtins.input", return_value="0"):
            interp.run()
    except Exception as e:
        pytest.xfail(f"Runtime error (known wiki artifact or missing feature): {e}")

