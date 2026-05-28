# Basic09 Interpreter in Python

A Python interpreter for **Basic09** — the structured BASIC dialect developed by Microware for the 6809.

Basic09 differs from most BASICs of its era by supporting structured control flow, typed variables, record types, and proper procedure abstraction with pass-by-reference parameters.

## Features

- `:=` assignment and full expression evaluation with correct operator precedence
- Typed variables: `INTEGER`, `REAL`, `STRING[n]`, `BOOLEAN`, `BYTE`
- `TYPE` record declarations with dot-notation field access
- `DIM` for scalars and multi-dimensional arrays (shared type syntax: `DIM i,j,k:INTEGER`)
- `PARAM` pass-by-reference procedure parameters
- `PROCEDURE` / `END` with `RUN` calls
- Control flow: `IF/THEN/ELSE/ENDIF`, `FOR/NEXT`, `WHILE/DO/ENDWHILE`, `REPEAT/UNTIL`, `LOOP/ENDLOOP`, `EXITIF`
- `GOTO`, `GOSUB`, `ON n GOTO`, numeric line labels
- `READ` / `DATA` / `RESTORE`
- Math: `ABS`, `INT`, `FIX`, `FLOAT`, `SQR`, `SIN`, `COS`, `TAN`, `ATN`, `ACS`, `ASN`, `EXP`, `LOG`, `SGN`, `MOD`, `PI`
- Bitwise: `LAND`, `LOR`, `LXOR`, `LNOT`
- String: `LEN`, `LEFT$`, `RIGHT$`, `MID$`, `SUBSTR$`, `ASC`, `CHR$`, `STR$`, `VAL`, `INSTR`
- Logical operators: `AND`, `OR`, `NOT`, `XOR`
- Line and block comments (`//`, `REM`, `(* ... *)`)
- File I/O: `OPEN`, `CREATE`, `CLOSE`, `DELETE`, `READ #`, `WRITE #`, `GET #`, `PUT #`, `SEEK`, `EOF`
- `SHELL` to run host OS commands, `CHD` to change directory (`CHX` is a no-op)
- `\` statement separator (multiple statements on one line)

## Installation

```bash
python3 -m venv .
source bin/activate
pip install -r requirements.txt
```

## Usage

### Run a file

```bash
python main.py examples/hello.b09
```

### Interactive REPL

```bash
python main.py
```

Type Basic09 statements, then `RUN` to execute. `NEW` clears the buffer, `LIST` shows it.

### Python API

```python
from basic09 import Basic09Interpreter, B09Value

source = """
PROCEDURE greet
PARAM name:STRING[20]
PRINT "Hello, ";name
END
"""

interp = Basic09Interpreter(source)
interp.run_procedure("greet", [B09Value.string("World")])
```

`run_procedure` accepts a list of `B09Value` arguments matching the procedure's `PARAM` declarations. Use the appropriate constructor for each type:

| Basic09 type | Python constructor |
|---|---|
| `INTEGER` | `B09Value.integer(42)` |
| `REAL` | `B09Value.real(3.14)` |
| `STRING[n]` | `B09Value.string("hello")` |
| `BOOLEAN` | `B09Value.boolean(True)` |
| `BYTE` | `B09Value.byte(0xFF)` |

## Language overview

```basic09
(* Fibonacci sequence *)
PROCEDURE fibonacci
DIM i,a,b,c:INTEGER

a:=0
b:=1
FOR i:=1 TO 10
PRINT a
c:=a+b
a:=b
b:=c
NEXT i
END
```

```basic09
(* Record types and pass-by-reference *)
TYPE point=x:INTEGER; y:INTEGER

PROCEDURE movePoint
PARAM p:point
PARAM dx,dy:INTEGER
p.x:=p.x+dx
p.y:=p.y+dy
END
```

```basic09
(* WHILE loop *)
PROCEDURE countdown
DIM n:INTEGER
n:=10
WHILE n>0 DO
PRINT n
n:=n-1
ENDWHILE
PRINT "Liftoff!"
END
```

## Running the tests

The Basic09 test source files live in the [NitrOS-9 repository](https://github.com/nitros9project/nitros9) under `3rdparty/packages/basic09/tests/`. Set `NITROS9DIR` to the root of your NitrOS-9 checkout before running:

```bash
export NITROS9DIR=~/Projects/coco-shelf/nitros9
python -m pytest
```

If `NITROS9DIR` is not set it defaults to `~/Projects/coco-shelf/nitros9`.

There are three test suites:

- **Unit tests** (`tests/test_interpreter.py`): runs 42 Basic09 test procedures from `$NITROS9DIR/3rdparty/packages/basic09/tests/unittests.b09`. Each procedure receives `passed` and `failed` counters by reference and the test asserts no `FAIL` lines appear in the output.
- **Wiki samples** (`tests/test_wiki_samples.py`): parses and runs 110 procedures from `$NITROS9DIR/3rdparty/packages/basic09/tests/wiki_procs/` drawn from the Basic09 Command Reference wiki. Procedures that rely on unsupported OS-9 features (`SHELL`, `CHAIN`, `ADDR`/`PEEK`/`POKE`, etc.) are skipped. Regenerate with `python scripts/generate_wiki_tests.py`.
- **External files** (`tests/test_external_b09.py`): pass `--b09-dir` to run all `.b09` files in any directory through the interpreter, e.g. `pytest --b09-dir $NITROS9DIR/3rdparty/packages/basic09/samples`.

## Project layout

```
basic09/
  __init__.py          public API
  grammar.lark         Lark Earley grammar
  interpreter.py       tree-walking interpreter
  types.py             B09Value / TypeTag
  environment.py       scoped variable storage
scripts/
  generate_wiki_tests.py  regenerate wiki test fixtures
tests/
  conftest.py          pytest fixtures and --b09-dir option
  test_interpreter.py  pytest driver for unit tests
  test_wiki_samples.py pytest driver for wiki samples
  test_shell_chd.py    tests for SHELL, CHD, CHX
  test_external_b09.py pytest driver for external .b09 files
main.py                CLI entry point
requirements.txt
```

Basic09 test sources (`unittests.b09`, `wiki_procs/`, sample programs) live in the NitrOS-9 repo under `3rdparty/packages/basic09/tests/` — a single source of truth usable by any Basic09 interpreter implementation.

## License

MIT
