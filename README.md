# basic09

A Python interpreter for **BASIC09** — the structured BASIC dialect developed by Microware for the TRS-80 Color Computer running OS-9.

BASIC09 differs from most BASICs of its era by supporting structured control flow, typed variables, record types, and proper procedure abstraction with pass-by-reference parameters.

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

Type BASIC09 statements, then `RUN` to execute. `NEW` clears the buffer, `LIST` shows it.

### Python API

```python
from basic09 import Basic09Interpreter

source = """
PROCEDURE greet
PARAM name:STRING[20]
PRINT "Hello, ";name
END
"""

interp = Basic09Interpreter(source)
interp.run_procedure("greet", [interp._env.__class__])  # or pass B9Value args
```

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

```bash
python -m pytest
```

The test suite runs 32 procedures from `tests/unittest.b09` through the interpreter and asserts no `FAIL` lines appear in the output.

## Project layout

```
basic09/
  __init__.py       public API
  grammar.lark      Lark Earley grammar
  interpreter.py    tree-walking interpreter
  types.py          B9Value / TypeTag
  environment.py    scoped variable storage
examples/           sample .b09 programs
tests/
  unittest.b09      BASIC09-language unit tests
  test_interpreter.py  pytest driver
main.py             CLI entry point
requirements.txt
```

## License

MIT
