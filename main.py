#!/usr/bin/env python3
"""Basic09 interpreter entry point. Run a file or start the REPL."""
import sys
import argparse
from basic09 import Basic09Interpreter, Basic09Error


def run_file(path: str, debug: bool = False) -> None:
    with open(path) as f:
        source = f.read()
    interp = Basic09Interpreter(source, debug=debug)
    interp.run()


def repl(debug: bool = False) -> None:
    print("Basic09 interpreter  (Ctrl-D to quit)")
    interp = Basic09Interpreter(debug=debug)
    lines: list[str] = []
    prompt = ">>> "
    while True:
        try:
            line = input(prompt)
        except EOFError:
            print()
            break
        if line.strip().upper() in ("RUN", ""):
            if not lines:
                continue
            source = "\n".join(lines)
            try:
                interp.load(source)
                interp.run()
            except Basic09Error as e:
                print(f"Error: {e}")
            except Exception as e:
                print(f"Runtime error: {e}")
            finally:
                lines = []
            prompt = ">>> "
        elif line.strip().upper() == "NEW":
            lines = []
            prompt = ">>> "
        elif line.strip().upper() == "LIST":
            print("\n".join(lines))
        else:
            lines.append(line)
            prompt = "... "


def main() -> None:
    parser = argparse.ArgumentParser(description="Basic09 interpreter")
    parser.add_argument("file", nargs="?", help="Basic09 source file to run")
    parser.add_argument("--debug", action="store_true", help="Show AST debug output")
    args = parser.parse_args()

    if args.file:
        run_file(args.file, debug=args.debug)
    else:
        repl(debug=args.debug)


if __name__ == "__main__":
    main()
