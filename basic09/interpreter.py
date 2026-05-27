from __future__ import annotations
import math
import random as _random
import re
import sys
from datetime import datetime
from typing import Any, Optional

from lark import Lark, Tree, Token
from lark.visitors import Interpreter as LarkInterpreter

from .types import B09Value, TypeTag, coerce
from .environment import Environment, Basic09Error, UndefinedVariable, TypeMismatch


def _strip_comments(source: str) -> str:
    """Remove //, (* and REM line comments, respecting string literals.
    Also converts leading line numbers to internal labels (100 PRINT -> LN100: PRINT)."""
    result = []
    for line in source.splitlines(keepends=True):
        # Convert leading line number to a named label
        m = re.match(r'^([ \t]*)(\d+)([ \t]+|(?=\r?\n|$))', line)
        if m:
            lineno = m.group(2)
            rest = line[len(m.group(0)):]
            line = f"{m.group(1)}LN{lineno}:\n{rest}"

        out = []
        in_str = False
        i = 0
        while i < len(line):
            c = line[i]
            if c == '"':
                in_str = not in_str
                out.append(c)
                i += 1
            elif not in_str and line[i:i+2] == '//':
                break
            elif not in_str and line[i:i+2] == '(*':
                break
            elif not in_str and re.match(r'REM\b', line[i:], re.IGNORECASE):
                break
            elif not in_str and c == '\\':
                out.append('\n')   # statement separator
                i += 1
            else:
                out.append(c if in_str else c.upper())
                i += 1
        result.append(''.join(out))
    return ''.join(result)


# ------------------------------------------------------------------ #
# Control-flow signals                                                #
# ------------------------------------------------------------------ #

class _Return(Exception):
    pass

class _End(Exception):
    pass

class _Stop(Exception):
    pass

class _Exit(Exception):
    """EXIT from LOOP."""
    pass

class _Goto(Exception):
    def __init__(self, label: str):
        self.label = label

class _Gosub(_Goto):
    pass


# ------------------------------------------------------------------ #
# Built-in functions                                                  #
# ------------------------------------------------------------------ #

_rnd_last: float = 0.0

def _rnd(a: B09Value) -> B09Value:
    global _rnd_last
    n = a.as_float()
    if n < 0:
        _random.seed(int(-n))
        _rnd_last = _random.random() * -n
    elif n == 0:
        pass  # return last value unchanged
    else:
        _rnd_last = _random.random() * n
    return B09Value.real(_rnd_last)


_BUILTINS: dict[str, Any] = {
    "ABS":    lambda a: B09Value.real(abs(a.as_float())) if a.tag == TypeTag.REAL else B09Value.integer(abs(a.as_int())),
    "INT":    lambda a: B09Value.integer(int(a.as_float())),
    "FIX":    lambda a: B09Value.integer(round(a.as_float())),
    "FLOAT":  lambda a: B09Value.real(float(a.as_float())),
    "SQR":    lambda a: B09Value.real(math.sqrt(a.as_float())),
    "SQ":     lambda a: B09Value.real(a.as_float() ** 2),
    "SIN":    lambda a: B09Value.real(math.sin(a.as_float())),
    "COS":    lambda a: B09Value.real(math.cos(a.as_float())),
    "TAN":    lambda a: B09Value.real(math.tan(a.as_float())),
    "ATN":    lambda a: B09Value.real(math.atan(a.as_float())),
    "ACS":    lambda a: B09Value.real(math.acos(a.as_float())),
    "ASN":    lambda a: B09Value.real(math.asin(a.as_float())),
    "EXP":    lambda a: B09Value.real(math.exp(a.as_float())),
    "LOG":    lambda a: B09Value.real(math.log(a.as_float())),
    "SGN":    lambda a: B09Value.integer(int(math.copysign(1, a.as_float())) if a.value != 0 else 0),
    "RND":    _rnd,
    "LEN":    lambda a: B09Value.integer(len(a.as_str())),
    "ASC":    lambda a: B09Value.integer(ord(a.as_str()[0])),
    "CHR$":   lambda a: B09Value.string(chr(a.as_int())),
    "STR$":   lambda a: B09Value.string(str(a)),
    "VAL":    lambda a: B09Value.real(float(a.as_str())),
    "LEFT$":  lambda a, b: B09Value.string(a.as_str()[:b.as_int()]),
    "RIGHT$": lambda a, b: B09Value.string(a.as_str()[-b.as_int():] if b.as_int() else ""),
    "MID$":   lambda a, b, *rest: B09Value.string(
        a.as_str()[b.as_int()-1 : b.as_int()-1 + (rest[0].as_int() if rest else len(a.as_str()))]
    ),
    "MOD":    lambda a, b: B09Value.integer(a.as_int() % b.as_int()),
    "SUBSTR": lambda a, b: B09Value.integer(b.as_str().find(a.as_str()) + 1 if a.as_str() in b.as_str() else 0),
    "LAND":   lambda a, b: B09Value.integer(a.as_int() & b.as_int()),
    "LOR":    lambda a, b: B09Value.integer(a.as_int() | b.as_int()),
    "LXOR":   lambda a, b: B09Value.integer(a.as_int() ^ b.as_int()),
    "LNOT":   lambda a: B09Value.integer(~a.as_int() & 0xFFFF),
}


# ------------------------------------------------------------------ #
# PRINT USING format interpreter                                      #
# ------------------------------------------------------------------ #

def _format_using(fmt: str, values: list) -> str:
    """
    Parse a BASIC09 PRINT USING format string and apply it to values.
    Format items inside the string:
      'literal text'   — printed as-is
      Rw.d             — real, width w, d decimal places
      Iw[<|>]          — integer, width w, optional < left or > right justify
      Ew.d             — real in scientific notation
    """
    result = []
    val_idx = 0
    i = 0
    while i < len(fmt):
        c = fmt[i]
        if c == "'":
            # Literal string up to next '
            j = fmt.find("'", i + 1)
            if j == -1:
                result.append(fmt[i + 1:])
                break
            result.append(fmt[i + 1:j])
            i = j + 1
        elif c in "RrEe" and i + 1 < len(fmt) and fmt[i + 1].isdigit():
            # Real format: R<width>.<decimals>  or  E<width>.<decimals>
            m = re.match(r'[REre](\d+)\.(\d+)', fmt[i:])
            if m and val_idx < len(values):
                width, dec = int(m.group(1)), int(m.group(2))
                v = values[val_idx].as_float()
                val_idx += 1
                s = f"{v:.{dec}f}" if c in "Rr" else f"{v:.{dec}e}"
                result.append(s)
                i += len(m.group(0))
            else:
                result.append(c)
                i += 1
        elif c in "Ii" and i + 1 < len(fmt) and fmt[i + 1].isdigit():
            # Integer format: I<width>[<|>]
            m = re.match(r'[Ii](\d+)([<>]?)', fmt[i:])
            if m and val_idx < len(values):
                width = int(m.group(1))
                align = m.group(2)
                v = values[val_idx].as_int()
                val_idx += 1
                s = str(v)
                if align == "<":
                    s = s
                else:
                    s = s.rjust(width)
                result.append(s)
                i += len(m.group(0))
            else:
                result.append(c)
                i += 1
        elif c == ",":
            result.append(" ")
            i += 1
        else:
            result.append(c)
            i += 1
    return "".join(result)




class Basic09Interpreter:
    def __init__(self, source: str | None = None, *, debug: bool = False):
        self.debug = debug
        self._procedures: dict[str, Tree] = {}
        self._type_defs: dict[str, list[tuple[str, TypeTag]]] = {}
        self._data: list[B09Value] = []
        self._data_ptr: int = 0
        self._env = Environment()
        self._global_stmts: list = []
        self._global_labels: dict[str, int] = {}
        self._main_proc: str | None = None

        grammar_path = __file__.replace("interpreter.py", "grammar.lark")
        with open(grammar_path) as f:
            grammar = f.read()

        self._parser = Lark(grammar, parser="earley", ambiguity="resolve",
                            start="program", propagate_positions=False)

        if source:
            self.load(source)

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def load(self, source: str) -> None:
        self._tree = self._parser.parse(_strip_comments(source))
        self._collect_procedures(self._tree)
        self._collect_type_defs(self._tree)
        self._collect_data(self._tree)
        # Build global label table for cross-procedure GOSUB/GOTO support
        self._global_stmts = self._flatten_stmts(self._tree.children)
        self._global_labels = self._collect_label_targets(self._tree.children)
        # Track first procedure declared (the main program entry point)
        self._main_proc = self._find_first_procedure(self._tree.children)

    def _find_first_procedure(self, nodes: list) -> str | None:
        for node in nodes:
            if isinstance(node, Tree):
                if node.data == "proc_section":
                    return str(node.children[0]).upper()
                result = self._find_first_procedure(node.children)
                if result:
                    return result
        return None

    def run(self) -> None:
        if self._main_proc and self._main_proc in self._procedures:
            proc = self._procedures[self._main_proc]
            try:
                self._call_procedure(proc, [], self._env)
            except (_Return, _End, _Stop):
                pass
        else:
            try:
                self._exec_statement_list(self._tree.children, self._env,
                                          _global_ctx=self._global_labels)
            except (_Return, _End, _Stop):
                pass

    def run_procedure(self, name: str, args: list[B09Value] | None = None) -> None:
        proc = self._procedures.get(name.upper())
        if proc is None:
            raise Basic09Error(f"Procedure '{name}' not found")
        self._call_procedure(proc, args or [], self._env)

    # ------------------------------------------------------------------ #
    # Pre-passes                                                           #
    # ------------------------------------------------------------------ #

    def _collect_procedures(self, tree: Tree) -> None:
        for node in tree.iter_subtrees():
            if isinstance(node, Tree) and node.data == "proc_section":
                name = str(node.children[0]).upper()
                self._procedures[name] = node

    def _collect_type_fields(self, node: Tree) -> list:
        """Extract (name, tag, dim) triples from a type_field node.
        Handles comma-separated field names: IDENT ("," IDENT)* ("(" INT_LIT ")")? ":" type_spec
        """
        idents = [str(c) for c in node.children
                  if isinstance(c, Token) and c.type == "IDENT"]
        dims   = [int(str(c)) for c in node.children
                  if isinstance(c, Token) and c.type == "INT_LIT"]
        types  = [c for c in node.children if isinstance(c, Tree)]
        fdim = dims[0] if dims else None
        ftag = self._parse_type(types[0]) if types else TypeTag.INTEGER
        return [(name.upper(), ftag, fdim) for name in idents]

    def _collect_type_defs(self, tree: Tree) -> None:
        for node in tree.iter_subtrees():
            if isinstance(node, Tree) and node.data == "type_stmt":
                type_name = str(node.children[0]).upper()
                fields = []
                for child in node.children[1:]:
                    if isinstance(child, Tree) and child.data == "type_field":
                        fields.extend(self._collect_type_fields(child))
                self._type_defs[type_name] = fields

    def _collect_data(self, tree: Tree) -> None:
        for node in tree.iter_subtrees():
            if isinstance(node, Tree) and node.data == "data_stmt":
                for child in node.children:
                    if isinstance(child, Tree) and child.data == "expr_list":
                        for expr in self._exprs_from_list(child):
                            self._data.append(self._eval_literal(expr))
                    elif isinstance(child, Tree):
                        self._data.append(self._eval_literal(child))

    # ------------------------------------------------------------------ #
    # Statement execution                                                  #
    # ------------------------------------------------------------------ #

    def _flatten_stmts(self, nodes: list) -> list:
        """Unwrap statement_list and statement wrapper nodes into a flat list."""
        result = []
        for node in nodes:
            if isinstance(node, Tree) and node.data in ("statement_list", "statement"):
                result.extend(self._flatten_stmts(node.children))
            else:
                result.append(node)
        return result

    def _label_index(self, stmts: list) -> dict[str, int]:
        return {
            str(s.children[0]).upper(): idx
            for idx, s in enumerate(stmts)
            if isinstance(s, Tree) and s.data == "label_stmt"
        }

    def _collect_label_targets(self, nodes: list) -> dict[str, tuple[list, int]]:
        targets: dict[str, tuple[list, int]] = {}

        def visit(children: list) -> None:
            stmts = self._flatten_stmts(children)
            for label, idx in self._label_index(stmts).items():
                if label not in targets or len(stmts) > len(targets[label][0]):
                    targets[label] = (stmts, idx)
            for child in children:
                if isinstance(child, Tree):
                    if child.data == "statement_list":
                        visit(child.children)
                    else:
                        find_statement_lists(child.children)

        def find_statement_lists(children: list) -> None:
            for child in children:
                if isinstance(child, Tree):
                    if child.data == "statement_list":
                        visit(child.children)
                    else:
                        find_statement_lists(child.children)

        visit(nodes)
        return targets

    def _exec_statement_list(self, stmts: list, env: Environment,
                             _return_stack: list | None = None,
                             _global_ctx: tuple | None = None) -> None:
        stmts = self._flatten_stmts(stmts)

        # Build label index for this scope
        labels = self._label_index(stmts)

        return_stack: list = _return_stack if _return_stack is not None else []

        i = 0
        while i < len(stmts):
            stmt = stmts[i]
            if not isinstance(stmt, Tree):
                i += 1
                continue
            try:
                self._exec_stmt(stmt, env, return_stack, _global_ctx)
            except _Gosub as g:
                target = g.label.upper()
                if target in labels:
                    return_stack.append((stmts, labels, i + 1))
                    i = labels[target]
                    continue
                if _global_ctx is not None:
                    if isinstance(_global_ctx, dict) and target in _global_ctx:
                        return_stack.append((stmts, labels, i + 1))
                        stmts, i = _global_ctx[target]
                        labels = self._label_index(stmts)
                        continue
                    if not isinstance(_global_ctx, dict):
                        g_stmts, g_labels = _global_ctx
                        if target in g_labels:
                            return_stack.append((stmts, labels, i + 1))
                            stmts, labels = g_stmts, g_labels
                            i = g_labels[target]
                            continue
                raise
            except _Goto as g:
                target = g.label.upper()
                if target in labels:
                    i = labels[target]
                    continue
                if _global_ctx is not None:
                    if isinstance(_global_ctx, dict) and target in _global_ctx:
                        stmts, i = _global_ctx[target]
                        labels = self._label_index(stmts)
                        continue
                    if not isinstance(_global_ctx, dict):
                        g_stmts, g_labels = _global_ctx
                        if target in g_labels:
                            stmts, labels = g_stmts, g_labels
                            i = g_labels[target]
                            continue
                raise
            except _Return:
                if return_stack:
                    stmts, labels, i = return_stack.pop()
                    continue
                raise
            i += 1

    # Block statement types that need return_stack + global_ctx threaded through
    _BLOCK_STMTS = {"for_stmt", "if_stmt", "repeat_stmt", "loop_stmt",
                    "while_stmt", "exitif_stmt"}

    def _exec_stmt(self, stmt: Tree, env: Environment,
                   return_stack: list | None = None,
                   global_ctx: tuple | None = None) -> None:
        name = stmt.data
        if self.debug:
            print(f"[DBG] {name}", file=sys.stderr)

        dispatch = {
            "dim_stmt":         self._exec_dim,
            "type_stmt":        lambda s, e: None,   # pre-collected
            "param_stmt":       lambda s, e: None,   # handled during procedure setup
            "let_stmt":         self._exec_let,
            "print_stmt":       self._exec_print,
            "print_using_stmt": self._exec_print_using,
            "input_stmt":       self._exec_input,
            "if_stmt":          self._exec_if,
            "if_goto_stmt":     self._exec_if_goto,
            "for_stmt":         self._exec_for,
            "while_stmt":       self._exec_while,
            "repeat_stmt":      self._exec_repeat,
            "loop_stmt":        self._exec_loop,
            "exit_stmt":        self._exec_exit,
            "exitif_stmt":      self._exec_exitif,
            "run_stmt":         self._exec_run,
            "proc_section":     lambda s, e: None,   # skip — pre-collected
            "return_stmt":      lambda s, e: (_ for _ in ()).throw(_Return()),
            "end_stmt":         lambda s, e: (_ for _ in ()).throw(_End()),
            "stop_stmt":        lambda s, e: (_ for _ in ()).throw(_Stop()),
            "goto_stmt":        self._exec_goto,
            "gosub_stmt":       self._exec_gosub,
            "on_goto_stmt":     self._exec_on_goto,
            "on_gosub_stmt":    self._exec_on_gosub,
            "read_stmt":        self._exec_read,
            "data_stmt":        lambda s, e: None,
            "restore_stmt":     self._exec_restore,
            "deg_stmt":         lambda s, e: None,
            "rad_stmt":         lambda s, e: None,
            "base_stmt":        lambda s, e: None,
            "rem_stmt":         lambda s, e: None,
            "label_stmt":       lambda s, e: None,
            "endif_stmt":       lambda s, e: None,   # no-op: orphaned ENDIF from inline-IF patterns
            "expr_stmt":        lambda s, e: self._eval_expr(s.children[0], e),
        }
        handler = dispatch.get(name)
        if handler:
            if name in self._BLOCK_STMTS:
                handler(stmt, env, return_stack, global_ctx)
            else:
                handler(stmt, env)
        else:
            raise Basic09Error(f"Unknown statement: {name}")

    # ------------------------------------------------------------------ #
    # DIM                                                                  #
    # ------------------------------------------------------------------ #

    def _exec_dim(self, stmt: Tree, env: Environment) -> None:
        for child in stmt.children:
            if isinstance(child, Tree) and child.data == "dim_group":
                self._exec_dim_group(child, env)

    def _exec_dim_group(self, group: Tree, env: Environment) -> None:
        # Last child is always the type_spec; preceding children are dim_var nodes
        type_node = group.children[-1]
        tag = self._parse_type(type_node)

        record_template: dict | None = None
        if tag == TypeTag.RECORD:
            type_name = str(type_node.children[0]).upper()
            fields = self._type_defs.get(type_name, [])
            from .types import DEFAULT_VALUES
            record_template = {}
            for fname, ftag, fdim in fields:
                if fdim is not None:
                    record_template[fname] = [DEFAULT_VALUES[ftag]] * fdim
                else:
                    record_template[fname] = DEFAULT_VALUES[ftag]

        for decl in group.children[:-1]:
            if not isinstance(decl, Tree):
                continue
            name = str(decl.children[0]).upper()
            if tag == TypeTag.RECORD and len(decl.children) == 1:
                # Scalar record
                import copy
                env.declare_record(name, copy.deepcopy(record_template))
            elif len(decl.children) > 1:
                # Array (possibly of records)
                dims = [self._eval_expr(e, env).as_int()
                        for e in self._exprs_from_list(decl.children[1])]
                env.declare_array(name, dims, tag,
                                  record_template=record_template)
            else:
                env.declare(name, tag)

    def _parse_type(self, node: Tree | Token) -> TypeTag:
        if isinstance(node, Token):
            return TypeTag[str(node).upper()]
        data = node.data
        if data == "type_user":
            return TypeTag.RECORD
        data = data.replace("type_", "").upper()
        return TypeTag[data]

    # ------------------------------------------------------------------ #
    # LET                                                                  #
    # ------------------------------------------------------------------ #

    def _exec_let(self, stmt: Tree, env: Environment) -> None:
        var_node, expr_node = stmt.children[0], stmt.children[1]
        value = self._eval_expr(expr_node, env)
        self._assign_var(var_node, value, env)

    def _assign_var(self, var_node: Tree, value: B09Value, env: Environment) -> None:
        name = str(var_node.children[0]).upper()
        children = var_node.children[1:]

        if not children:
            env.set(name, value)
            return

        c1 = children[0]
        if isinstance(c1, Tree) and c1.data == "array_index":
            # A(i)  or  A(i).field  or  A(i).field(n)
            indices = tuple(self._eval_expr(e, env).as_int()
                            for e in self._exprs_from_index(c1))
            if len(children) == 1:
                env.set_array(name, indices, value)
            else:
                field = str(children[1]).upper()
                record = env.get_array(name, indices)
                if len(children) == 3:
                    fidx = self._eval_expr(self._exprs_from_index(children[2])[0], env).as_int()
                    record.value[field][fidx] = value
                else:
                    record.value[field] = value
        else:
            # A.field  or  A.field(n)
            field = str(c1).upper()
            record = env.get(name)
            if len(children) == 2:
                fidx = self._eval_expr(self._exprs_from_index(children[1])[0], env).as_int()
                record.value[field][fidx] = value
            else:
                record.value[field] = value

    # ------------------------------------------------------------------ #
    # PRINT                                                                #
    # ------------------------------------------------------------------ #

    def _exec_print(self, stmt: Tree, env: Environment) -> None:
        if not stmt.children:
            print()
            return
        args_node = stmt.children[0]
        output: list[str] = []
        col = 0
        trailing_sep = False

        for child in args_node.children:
            if isinstance(child, Token) and child.type == "PRINT_SEP":
                sep = str(child)
                trailing_sep = True
                if sep == ",":
                    # Tab to next 16-char print zone
                    next_zone = ((col // 16) + 1) * 16
                    pad = next_zone - col
                    output.append(" " * pad)
                    col = next_zone
                # ";" outputs nothing — items run together
            elif isinstance(child, Tree) and child.data == "print_item":
                trailing_sep = False
                if (len(child.children) >= 2
                        and isinstance(child.children[0], Token)
                        and child.children[0].type == "TAB"):
                    n = self._eval_expr(child.children[1], env).as_int()
                    if n > col:
                        output.append(" " * (n - col))
                        col = n
                elif (len(child.children) == 1
                      and isinstance(child.children[0], Tree)
                      and child.children[0].data == "var"
                      and str(child.children[0].children[0]).upper() == "TAB"
                      and len(child.children[0].children) > 1):
                    n = self._eval_expr(
                        self._exprs_from_index(child.children[0].children[1])[0],
                        env,
                    ).as_int()
                    if n > col:
                        output.append(" " * (n - col))
                        col = n
                else:
                    val = str(self._eval_expr(child.children[0], env))
                    output.append(val)
                    col += len(val)

        if trailing_sep:
            print("".join(output), end="")
        else:
            print("".join(output))

    def _exec_print_using(self, stmt: Tree, env: Environment) -> None:
        """PRINT USING "fmt", val1, val2, ..."""
        fmt_token = stmt.children[0]
        fmt = str(fmt_token)[1:-1]  # strip outer quotes
        value_nodes = [c for c in stmt.children[1:] if isinstance(c, Tree)]
        values = [self._eval_expr(v, env) for v in value_nodes]
        print(_format_using(fmt, values))

    def _exec_if_goto(self, stmt: Tree, env: Environment) -> None:
        cond = self._eval_expr(stmt.children[0], env).as_bool()
        if cond:
            line_num = str(stmt.children[1])
            raise _Goto(f"LN{line_num}")

    def _exec_on_gosub(self, stmt: Tree, env: Environment) -> None:
        idx = self._eval_expr(stmt.children[0], env).as_int()
        targets = [self._resolve_goto_target(c)
                   for c in stmt.children[1:]
                   if isinstance(c, Tree) and c.data == "goto_target"]
        if 1 <= idx <= len(targets):
            raise _Gosub(targets[idx - 1])

    # ------------------------------------------------------------------ #
    # INPUT                                                                #
    # ------------------------------------------------------------------ #

    def _exec_input(self, stmt: Tree, env: Environment) -> None:
        prompt = ""
        var_list_node = None
        for child in stmt.children:
            if isinstance(child, Token) and child.type == "STRING_LIT":
                prompt = str(child)[1:-1]
            elif isinstance(child, Tree) and child.data == "var_list":
                var_list_node = child

        line = input(prompt if prompt else "? ")
        values = [v.strip() for v in line.split(",")]
        if var_list_node:
            for var_node, raw in zip(var_list_node.children, values):
                if not isinstance(var_node, Tree):
                    continue
                name = str(var_node.children[0]).upper()
                existing = env.get(name)
                if existing.tag in (TypeTag.INTEGER, TypeTag.BYTE):
                    try:
                        value = B09Value.integer(int(float(raw)))
                    except ValueError:
                        value = B09Value.integer(0)
                elif existing.tag == TypeTag.REAL:
                    try:
                        value = B09Value.real(float(raw))
                    except ValueError:
                        value = B09Value.real(0.0)
                else:
                    value = B09Value.string(raw)
                env.set(name, value)

    # ------------------------------------------------------------------ #
    # IF                                                                   #
    # ------------------------------------------------------------------ #

    def _exec_if(self, stmt: Tree, env: Environment,
                 return_stack: list | None = None,
                 global_ctx: tuple | None = None) -> None:
        cond = self._eval_expr(stmt.children[0], env).as_bool()
        body_children = [c for c in stmt.children[1:] if isinstance(c, Tree)]
        statement_lists = [c for c in body_children if c.data == "statement_list"]

        then_stmts = []
        else_stmts = []
        if body_children and body_children[0].data == "statement_list":
            then_stmts = body_children[0].children
            if len(statement_lists) > 1:
                else_stmts = statement_lists[1].children
        else:
            for child in body_children:
                if child.data == "statement_list":
                    then_stmts.extend(child.children)
                else:
                    then_stmts.append(child)

        if cond:
            self._exec_statement_list(then_stmts, env,
                                      _return_stack=return_stack,
                                      _global_ctx=global_ctx)
        else:
            self._exec_statement_list(else_stmts, env,
                                      _return_stack=return_stack,
                                      _global_ctx=global_ctx)

    # ------------------------------------------------------------------ #
    # FOR                                                                  #
    # ------------------------------------------------------------------ #

    def _exec_for(self, stmt: Tree, env: Environment,
                  return_stack: list | None = None,
                  global_ctx: tuple | None = None) -> None:
        var_name = str(stmt.children[0]).upper()

        # Filter to Tree nodes only — NEWLINE and IDENT tokens are kept by lark
        # but aren't expressions. Layout: [start, stop, (step)?, statement_list]
        tree_children = [c for c in stmt.children if isinstance(c, Tree)]
        body_idx = next(i for i, c in enumerate(tree_children) if c.data == "statement_list")

        start_val = self._eval_expr(tree_children[0], env)
        stop_val  = self._eval_expr(tree_children[1], env)
        step_val  = self._eval_expr(tree_children[2], env) if body_idx > 2 else B09Value.integer(1)
        body_stmts = tree_children[body_idx].children

        env.set(var_name, start_val)
        step = step_val.as_float()

        try:
            while True:
                current = env.get(var_name).as_float()
                limit = stop_val.as_float()
                if step >= 0 and current > limit:
                    break
                if step < 0 and current < limit:
                    break
                self._exec_statement_list(body_stmts, env,
                                          _return_stack=return_stack,
                                          _global_ctx=global_ctx)
                new_val = env.get(var_name).as_float() + step
                if env.get(var_name).tag == TypeTag.INTEGER:
                    env.set(var_name, B09Value.integer(int(new_val)))
                else:
                    env.set(var_name, B09Value.real(new_val))
        except _Exit:
            pass

    # ------------------------------------------------------------------ #
    # REPEAT/UNTIL                                                         #
    # ------------------------------------------------------------------ #

    def _exec_repeat(self, stmt: Tree, env: Environment,
                     return_stack: list | None = None,
                     global_ctx: tuple | None = None) -> None:
        body = [c for c in stmt.children if isinstance(c, Tree) and c.data == "statement_list"]
        cond_node = stmt.children[-1]
        body_stmts = body[0].children if body else []
        try:
            while True:
                self._exec_statement_list(body_stmts, env,
                                          _return_stack=return_stack,
                                          _global_ctx=global_ctx)
                if self._eval_expr(cond_node, env).as_bool():
                    break
        except _Exit:
            pass

    # ------------------------------------------------------------------ #
    # LOOP/ENDLOOP                                                         #
    # ------------------------------------------------------------------ #

    def _exec_loop(self, stmt: Tree, env: Environment,
                   return_stack: list | None = None,
                   global_ctx: tuple | None = None) -> None:
        body = [c for c in stmt.children if isinstance(c, Tree) and c.data == "statement_list"]
        body_stmts = body[0].children if body else []
        try:
            while True:
                self._exec_statement_list(body_stmts, env,
                                          _return_stack=return_stack,
                                          _global_ctx=global_ctx)
        except _Exit:
            pass

    # ------------------------------------------------------------------ #
    # WHILE/DO/ENDWHILE                                                    #
    # ------------------------------------------------------------------ #

    def _exec_while(self, stmt: Tree, env: Environment,
                    return_stack: list | None = None,
                    global_ctx: tuple | None = None) -> None:
        cond_node = stmt.children[0]
        body = [c for c in stmt.children if isinstance(c, Tree) and c.data == "statement_list"]
        body_stmts = body[0].children if body else []
        try:
            while self._eval_expr(cond_node, env).as_bool():
                self._exec_statement_list(body_stmts, env,
                                          _return_stack=return_stack,
                                          _global_ctx=global_ctx)
        except _Exit:
            pass

    # ------------------------------------------------------------------ #
    # EXIT                                                                 #
    # ------------------------------------------------------------------ #

    def _exec_exit(self, stmt: Tree, env: Environment) -> None:
        raise _Exit()

    def _exec_exitif(self, stmt: Tree, env: Environment,
                     return_stack: list | None = None,
                     global_ctx: tuple | None = None) -> None:
        cond = self._eval_expr(stmt.children[0], env).as_bool()
        if cond:
            body = [c for c in stmt.children[1:] if isinstance(c, Tree) and c.data == "statement_list"]
            body_stmts = body[0].children if body else []
            self._exec_statement_list(body_stmts, env,
                                      _return_stack=return_stack,
                                      _global_ctx=global_ctx)
            raise _Exit()

    # ------------------------------------------------------------------ #
    # RUN (procedure call)                                                 #
    # ------------------------------------------------------------------ #

    def _exec_run(self, stmt: Tree, env: Environment) -> None:
        name = str(stmt.children[0]).upper()
        arg_exprs: list[Tree] = []
        args: list[B09Value] = []
        for child in stmt.children[1:]:
            if isinstance(child, Tree) and child.data == "expr_list":
                arg_exprs = [e for e in child.children if isinstance(e, Tree)]
                args = [self._eval_expr(e, env) for e in arg_exprs]
        proc = self._procedures.get(name)
        if proc is None:
            raise Basic09Error(f"Procedure '{name}' not defined")
        self._call_procedure(proc, args, env, arg_exprs)

    def _call_procedure(self, proc: Tree, args: list[B09Value], caller_env: Environment,
                        arg_exprs: list[Tree] | None = None) -> None:
        local_env = Environment(parent=None)

        # Collect inline params (PROCEDURE name(param:type) style)
        inline_params = []
        for child in proc.children[1:]:
            if isinstance(child, Tree) and child.data == "param_list":
                inline_params = [c for c in child.children if isinstance(c, Tree) and c.data == "param"]
                break

        # Collect PARAM-statement params (BASIC09 style: PARAM a,b:INTEGER inside body)
        body = [c for c in proc.children if isinstance(c, Tree) and c.data == "statement_list"]
        body_stmts = body[0].children if body else []

        # Walk PARAM statements from the leading body statements
        # and also collect any TYPE defs local to this procedure
        for node in self._flatten_stmts(body_stmts):
            if isinstance(node, Tree) and node.data == "type_stmt":
                type_name = str(node.children[0]).upper()
                fields = []
                for child in node.children[1:]:
                    if isinstance(child, Tree) and child.data == "type_field":
                        fields.extend(self._collect_type_fields(child))
                self._type_defs[type_name] = fields

        param_names: list[str] = []   # ordered list of param variable names
        if inline_params:
            for param in inline_params:
                pname = str(param.children[0]).upper()
                ptag = self._parse_type(param.children[1])
                local_env.declare(pname, ptag)
                param_names.append(pname)
        else:
            # Walk the leading PARAM statements in the body (TYPE stmts may precede them)
            for node in self._flatten_stmts(body_stmts):
                if not isinstance(node, Tree):
                    continue  # skip NEWLINE tokens
                if node.data == "type_stmt":
                    continue  # skip type declarations before PARAM
                if node.data != "param_stmt":
                    break
                tag = self._parse_type(node.children[-1])
                for child in node.children[:-1]:
                    if isinstance(child, Token):
                        pname = str(child).upper()
                        local_env.declare(pname, tag)
                        param_names.append(pname)

        for pname, arg in zip(param_names, args):
            local_env.set(pname, arg)

        # Build a flat label table for the entire procedure body.
        # This is passed as _global_ctx so that GOSUBs/GOTOs from inside
        # block structures (FOR, IF, etc.) can resolve procedure-level labels.
        proc_global_ctx = self._collect_label_targets(body_stmts)

        try:
            self._exec_statement_list(body_stmts, local_env,
                                      _global_ctx=proc_global_ctx)
        except (_Return, _End):
            pass

        # Copy-back: write PARAM values back to simple variable args in caller's scope
        if arg_exprs:
            for pname, arg_expr in zip(param_names, arg_exprs):
                if isinstance(arg_expr, Tree) and arg_expr.data == "var" and len(arg_expr.children) == 1:
                    caller_var = str(arg_expr.children[0]).upper()
                    try:
                        caller_env.set(caller_var, local_env.get(pname))
                    except Exception:
                        pass

    # ------------------------------------------------------------------ #
    # GOTO / GOSUB                                                         #
    # ------------------------------------------------------------------ #

    def _exec_goto(self, stmt: Tree, env: Environment) -> None:
        raise _Goto(self._resolve_goto_target(stmt.children[0]))

    def _exec_gosub(self, stmt: Tree, env: Environment) -> None:
        raise _Gosub(self._resolve_goto_target(stmt.children[0]))

    def _exec_on_goto(self, stmt: Tree, env: Environment) -> None:
        idx = self._eval_expr(stmt.children[0], env).as_int()
        targets = [self._resolve_goto_target(c)
                   for c in stmt.children[1:]
                   if isinstance(c, Tree) and c.data == "goto_target"]
        if 1 <= idx <= len(targets):
            raise _Goto(targets[idx - 1])

    def _resolve_goto_target(self, node: Tree) -> str:
        """Extract label string from a goto_target node (always a line number)."""
        return f"LN{node.children[0]}"

    # ------------------------------------------------------------------ #
    # READ / DATA / RESTORE                                                #
    # ------------------------------------------------------------------ #

    def _exec_read(self, stmt: Tree, env: Environment) -> None:
        var_list = stmt.children[0]
        for var_node in var_list.children:
            if not isinstance(var_node, Tree):
                continue
            if self._data_ptr >= len(self._data):
                raise Basic09Error("Out of DATA")
            value = self._data[self._data_ptr]
            self._data_ptr += 1
            self._assign_var(var_node, value, env)

    def _exec_restore(self, stmt: Tree, env: Environment) -> None:
        self._data_ptr = 0

    # ------------------------------------------------------------------ #
    # Expression evaluation                                                #
    # ------------------------------------------------------------------ #

    def _eval_expr(self, node: Any, env: Environment) -> B09Value:
        if isinstance(node, Token):
            return B09Value.string(str(node))
        if not isinstance(node, Tree):
            return B09Value.integer(0)

        name = node.data

        # Literals
        if name == "int_lit":
            return B09Value.integer(int(node.children[0]))
        if name == "float_lit":
            return B09Value.real(float(node.children[0]))
        if name == "string_lit":
            return B09Value.string(str(node.children[0])[1:-1])
        if name == "true_lit":
            return B09Value.boolean(True)
        if name == "false_lit":
            return B09Value.boolean(False)
        if name == "pi_lit":
            return B09Value.real(math.pi)

        # Variable
        if name == "var":
            vname = str(node.children[0]).upper()

            # DATE$ system variable — OS-9 format "MM/DD/YY HH:MM:SS"
            if vname == "DATE$" and len(node.children) == 1:
                return B09Value.string(datetime.now().strftime("%m/%d/%y %H:%M:%S"))

            children = node.children[1:]

            if not children:
                return env.get(vname)

            c1 = children[0]
            if isinstance(c1, Tree) and c1.data == "array_index":
                # A(i)  or  A(i).field  or  A(i).field(n)
                exprs = self._exprs_from_index(c1)
                if vname in _BUILTINS and len(children) == 1:
                    args = [self._eval_expr(e, env) for e in exprs]
                    return _BUILTINS[vname](*args)
                indices = tuple(self._eval_expr(e, env).as_int() for e in exprs)
                if len(children) == 1:
                    return env.get_array(vname, indices)
                field = str(children[1]).upper()
                record = env.get_array(vname, indices)
                if len(children) == 3:
                    fidx = self._eval_expr(self._exprs_from_index(children[2])[0], env).as_int()
                    return record.value[field][fidx]
                return record.value[field]
            else:
                # A.field  or  A.field(n)
                field = str(c1).upper()
                record = env.get(vname)
                if len(children) == 2:
                    fidx = self._eval_expr(self._exprs_from_index(children[1])[0], env).as_int()
                    return record.value[field][fidx]
                return record.value[field]

        # Function call
        if name == "func_call":
            fname = str(node.children[0]).upper()
            args: list[B09Value] = []
            if len(node.children) > 1 and isinstance(node.children[1], Tree):
                args = self._exprs_from_list(node.children[1])
                args = [self._eval_expr(e, env) for e in args]
            fn = _BUILTINS.get(fname)
            if fn:
                return fn(*args)
            raise Basic09Error(f"Unknown function '{fname}'")

        # Binary ops
        ops = {
            "add_op":  lambda a, b: self._arith(a, b, "+"),
            "sub_op":  lambda a, b: self._arith(a, b, "-"),
            "mul_op":  lambda a, b: self._arith(a, b, "*"),
            "div_op":  lambda a, b: self._arith(a, b, "/"),
            "pow_op":  lambda a, b: B09Value.real(a.as_float() ** b.as_float()),
            "eq_op":   lambda a, b: B09Value.boolean(self._compare(a, b) == 0),
            "ne_op":   lambda a, b: B09Value.boolean(self._compare(a, b) != 0),
            "lt_op":   lambda a, b: B09Value.boolean(self._compare(a, b) < 0),
            "le_op":   lambda a, b: B09Value.boolean(self._compare(a, b) <= 0),
            "gt_op":   lambda a, b: B09Value.boolean(self._compare(a, b) > 0),
            "ge_op":   lambda a, b: B09Value.boolean(self._compare(a, b) >= 0),
            "and_op":  lambda a, b: B09Value.boolean(a.as_bool() and b.as_bool()),
            "or_op":   lambda a, b: B09Value.boolean(a.as_bool() or b.as_bool()),
            "xor_op":  lambda a, b: B09Value.boolean(a.as_bool() != b.as_bool()),
        }
        if name in ops:
            a = self._eval_expr(node.children[0], env)
            b = self._eval_expr(node.children[1], env)
            return ops[name](a, b)

        if name == "neg_op":
            a = self._eval_expr(node.children[0], env)
            if a.tag == TypeTag.REAL:
                return B09Value.real(-a.value)
            return B09Value.integer(-a.as_int())

        if name == "not_op":
            return B09Value.boolean(not self._eval_expr(node.children[0], env).as_bool())

        # Fallthrough: try first child
        if node.children:
            return self._eval_expr(node.children[0], env)
        return B09Value.integer(0)

    def _arith(self, a: B09Value, b: B09Value, op: str) -> B09Value:
        # String concatenation
        if op == "+" and a.tag == TypeTag.STRING:
            return B09Value.string(a.as_str() + b.as_str())
        a, b = coerce(a, b)
        if a.tag == TypeTag.REAL:
            v = eval(f"{a.value} {op} {b.value}")  # safe: only numeric operands  # noqa: S307
            return B09Value.real(v)
        if op == "/":
            return B09Value.real(a.as_int() / b.as_int())
        v = eval(f"{a.as_int()} {op} {b.as_int()}")  # noqa: S307
        return B09Value.integer(int(v))

    def _compare(self, a: B09Value, b: B09Value) -> int:
        if a.tag == TypeTag.STRING:
            sa, sb = a.as_str(), b.as_str()
            return (sa > sb) - (sa < sb)
        if a.tag == TypeTag.BOOLEAN or b.tag == TypeTag.BOOLEAN:
            ia = 1 if a.as_bool() else 0
            ib = 1 if b.as_bool() else 0
            return (ia > ib) - (ia < ib)
        fa, fb = a.as_float(), b.as_float()
        return (fa > fb) - (fa < fb)

    def _eval_literal(self, node: Any) -> B09Value:
        return self._eval_expr(node, self._env)

    def _exprs_from_index(self, array_index: Tree) -> list[Tree]:
        """Extract individual expr trees from an array_index node."""
        for c in array_index.children:
            if isinstance(c, Tree) and c.data == "expr_list":
                return [e for e in c.children if isinstance(e, Tree)]
        return [c for c in array_index.children if isinstance(c, Tree)]

    def _exprs_from_list(self, expr_list: Tree) -> list[Tree]:
        """Extract individual expr trees from an expr_list node."""
        return [c for c in expr_list.children if isinstance(c, Tree)]

    def _get_expr_list(self, node: Tree) -> list[Tree]:
        return [c for c in node.children if isinstance(c, Tree)]
