from __future__ import annotations
import math
import re
import sys
from typing import Any, Optional

from lark import Lark, Tree, Token
from lark.visitors import Interpreter as LarkInterpreter

from .types import B9Value, TypeTag, coerce
from .environment import Environment, Basic09Error, UndefinedVariable, TypeMismatch


def _strip_comments(source: str) -> str:
    """Remove // and REM line comments, respecting string literals.
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
            elif not in_str and re.match(r'REM\b', line[i:], re.IGNORECASE):
                break
            elif not in_str and c == '\\':
                out.append('\n')   # statement separator
                i += 1
            else:
                out.append(c)
                i += 1
        result.append(''.join(out))
    return ''.join(result)


# ------------------------------------------------------------------ #
# Control-flow signals                                                #
# ------------------------------------------------------------------ #

class _Return(Exception):
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

_BUILTINS: dict[str, Any] = {
    "ABS":    lambda a: B9Value.real(abs(a.as_float())) if a.tag == TypeTag.REAL else B9Value.integer(abs(a.as_int())),
    "INT":    lambda a: B9Value.integer(int(a.as_float())),
    "FIX":    lambda a: B9Value.integer(round(a.as_float())),
    "FLOAT":  lambda a: B9Value.real(float(a.as_float())),
    "SQR":    lambda a: B9Value.real(math.sqrt(a.as_float())),
    "SIN":    lambda a: B9Value.real(math.sin(a.as_float())),
    "COS":    lambda a: B9Value.real(math.cos(a.as_float())),
    "TAN":    lambda a: B9Value.real(math.tan(a.as_float())),
    "ATN":    lambda a: B9Value.real(math.atan(a.as_float())),
    "ACS":    lambda a: B9Value.real(math.acos(a.as_float())),
    "ASN":    lambda a: B9Value.real(math.asin(a.as_float())),
    "EXP":    lambda a: B9Value.real(math.exp(a.as_float())),
    "LOG":    lambda a: B9Value.real(math.log(a.as_float())),
    "SGN":    lambda a: B9Value.integer(int(math.copysign(1, a.as_float())) if a.value != 0 else 0),
    "RND":    lambda a: B9Value.real(__import__('random').random()),
    "LEN":    lambda a: B9Value.integer(len(a.as_str())),
    "ASC":    lambda a: B9Value.integer(ord(a.as_str()[0])),
    "CHR$":   lambda a: B9Value.string(chr(a.as_int())),
    "STR$":   lambda a: B9Value.string(str(a)),
    "VAL":    lambda a: B9Value.real(float(a.as_str())),
    "LEFT$":  lambda a, b: B9Value.string(a.as_str()[:b.as_int()]),
    "RIGHT$": lambda a, b: B9Value.string(a.as_str()[-b.as_int():] if b.as_int() else ""),
    "MID$":   lambda a, b, *rest: B9Value.string(
        a.as_str()[b.as_int()-1 : b.as_int()-1 + (rest[0].as_int() if rest else len(a.as_str()))]
    ),
    "MOD":    lambda a, b: B9Value.integer(a.as_int() % b.as_int()),
    "SUBSTR": lambda a, b: B9Value.integer(b.as_str().find(a.as_str()) + 1 if a.as_str() in b.as_str() else 0),
    "MOD":    lambda a, b: B9Value.integer(a.as_int() % b.as_int()),
    "LAND":   lambda a, b: B9Value.integer(a.as_int() & b.as_int()),
    "LOR":    lambda a, b: B9Value.integer(a.as_int() | b.as_int()),
    "LXOR":   lambda a, b: B9Value.integer(a.as_int() ^ b.as_int()),
    "LNOT":   lambda a: B9Value.integer(~a.as_int() & 0xFFFF),
}


# ------------------------------------------------------------------ #
# Interpreter                                                         #
# ------------------------------------------------------------------ #

class Basic09Interpreter:
    def __init__(self, source: str | None = None, *, debug: bool = False):
        self.debug = debug
        self._procedures: dict[str, Tree] = {}
        self._type_defs: dict[str, list[tuple[str, TypeTag]]] = {}
        self._data: list[B9Value] = []
        self._data_ptr: int = 0
        self._env = Environment()

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

    def run(self) -> None:
        self._exec_statement_list(self._tree.children, self._env)

    def run_procedure(self, name: str, args: list[B9Value] | None = None) -> None:
        proc = self._procedures.get(name.upper())
        if proc is None:
            raise Basic09Error(f"Procedure '{name}' not found")
        self._call_procedure(proc, args or [], self._env)

    # ------------------------------------------------------------------ #
    # Pre-passes                                                           #
    # ------------------------------------------------------------------ #

    def _collect_procedures(self, tree: Tree) -> None:
        for node in tree.iter_subtrees():
            if isinstance(node, Tree) and node.data == "procedure_stmt":
                name = str(node.children[0]).upper()
                self._procedures[name] = node

    def _collect_type_defs(self, tree: Tree) -> None:
        for node in tree.iter_subtrees():
            if isinstance(node, Tree) and node.data == "type_stmt":
                type_name = str(node.children[0]).upper()
                fields = []
                for child in node.children[1:]:
                    if isinstance(child, Tree) and child.data == "type_field":
                        fname = str(child.children[0]).upper()
                        ftag = self._parse_type(child.children[1])
                        fields.append((fname, ftag))
                self._type_defs[type_name] = fields

    def _collect_data(self, tree: Tree) -> None:
        for node in tree.iter_subtrees():
            if isinstance(node, Tree) and node.data == "data_stmt":
                for child in node.children:
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

    def _exec_statement_list(self, stmts: list, env: Environment) -> None:
        stmts = self._flatten_stmts(stmts)

        # Build label index
        labels: dict[str, int] = {}
        for i, s in enumerate(stmts):
            if isinstance(s, Tree) and s.data == "label_stmt":
                labels[str(s.children[0]).upper()] = i

        i = 0
        while i < len(stmts):
            stmt = stmts[i]
            if not isinstance(stmt, Tree):
                i += 1
                continue
            try:
                self._exec_stmt(stmt, env)
            except _Goto as g:
                target = g.label.upper()
                if target in labels:
                    i = labels[target]
                    continue
                raise
            i += 1

    def _exec_stmt(self, stmt: Tree, env: Environment) -> None:
        name = stmt.data
        if self.debug:
            print(f"[DBG] {name}", file=sys.stderr)

        dispatch = {
            "dim_stmt":       self._exec_dim,
            "type_stmt":      lambda s, e: None,   # pre-collected
            "param_stmt":     lambda s, e: None,   # handled during procedure setup
            "let_stmt":       self._exec_let,
            "print_stmt":     self._exec_print,
            "input_stmt":     self._exec_input,
            "if_stmt":        self._exec_if,
            "for_stmt":       self._exec_for,
            "while_stmt":     self._exec_while,
            "repeat_stmt":    self._exec_repeat,
            "loop_stmt":      self._exec_loop,
            "exit_stmt":      self._exec_exit,
            "exitif_stmt":    self._exec_exitif,
            "run_stmt":       self._exec_run,
            "procedure_stmt": lambda s, e: None,   # skip — pre-collected
            "return_stmt":    lambda s, e: (_ for _ in ()).throw(_Return()),
            "end_stmt":       lambda s, e: sys.exit(0),
            "goto_stmt":      self._exec_goto,
            "gosub_stmt":     self._exec_gosub,
            "on_goto_stmt":   self._exec_on_goto,
            "read_stmt":      self._exec_read,
            "data_stmt":      lambda s, e: None,
            "restore_stmt":   self._exec_restore,
            "deg_stmt":       lambda s, e: None,
            "rad_stmt":       lambda s, e: None,
            "base_stmt":      lambda s, e: None,
            "rem_stmt":       lambda s, e: None,
            "label_stmt":     lambda s, e: None,
            "expr_stmt":      lambda s, e: self._eval_expr(s.children[0], e),
        }
        handler = dispatch.get(name)
        if handler:
            handler(stmt, env)
        else:
            raise Basic09Error(f"Unknown statement: {name}")

    # ------------------------------------------------------------------ #
    # DIM                                                                  #
    # ------------------------------------------------------------------ #

    def _exec_dim(self, stmt: Tree, env: Environment) -> None:
        # Last child is always the type_spec; preceding children are dim_var nodes
        type_node = stmt.children[-1]
        tag = self._parse_type(type_node)
        for decl in stmt.children[:-1]:
            if not isinstance(decl, Tree):
                continue
            name = str(decl.children[0]).upper()
            if tag == TypeTag.RECORD:
                type_name = str(type_node.children[0]).upper()
                fields = self._type_defs.get(type_name, [])
                from .types import DEFAULT_VALUES
                record_fields = {fname: DEFAULT_VALUES[ftag] for fname, ftag in fields}
                env.declare_record(name, record_fields)
            elif len(decl.children) > 1:
                # Array: child 1 is expr_list with dimensions
                dims = [self._eval_expr(e, env).as_int()
                        for e in self._exprs_from_list(decl.children[1])]
                env.declare_array(name, dims, tag)
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

    def _assign_var(self, var_node: Tree, value: B9Value, env: Environment) -> None:
        name = str(var_node.children[0]).upper()
        # Collect children that are Trees vs Token IDENTs for dot notation
        token_children = [c for c in var_node.children if isinstance(c, Token)]
        tree_children = [c for c in var_node.children if isinstance(c, Tree)]

        if len(token_children) == 2:
            # Record field assignment: var.field := value
            field = str(token_children[1]).upper()
            record = env.get(name)
            record.value[field] = value
        elif tree_children and tree_children[0].data == "array_index":
            indices = tuple(self._eval_expr(e, env).as_int()
                            for e in self._exprs_from_index(tree_children[0]))
            env.set_array(name, indices, value)
        else:
            env.set(name, value)

    # ------------------------------------------------------------------ #
    # PRINT                                                                #
    # ------------------------------------------------------------------ #

    def _exec_print(self, stmt: Tree, env: Environment) -> None:
        if not stmt.children:
            print()
            return
        args_node = stmt.children[0]
        parts = []
        sep_after = False
        children = [c for c in args_node.children if isinstance(c, Tree)]
        for item in children:
            if item.data == "print_item":
                parts.append(str(self._eval_expr(item.children[0], env)))
            sep_after = False  # simplified: always newline at end for now
        print("".join(parts))

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

        line = input(prompt + "? " if prompt else "? ")
        values = [v.strip() for v in line.split(",")]
        if var_list_node:
            for var_node, raw in zip(var_list_node.children, values):
                if not isinstance(var_node, Tree):
                    continue
                name = str(var_node.children[0]).upper()
                try:
                    existing = env.get(name)
                    if existing.tag in (TypeTag.INTEGER, TypeTag.BYTE):
                        value = B9Value.integer(int(raw))
                    elif existing.tag == TypeTag.REAL:
                        value = B9Value.real(float(raw))
                    else:
                        value = B9Value.string(raw)
                except UndefinedVariable:
                    value = B9Value.string(raw)
                env.set(name, value)

    # ------------------------------------------------------------------ #
    # IF                                                                   #
    # ------------------------------------------------------------------ #

    def _exec_if(self, stmt: Tree, env: Environment) -> None:
        cond = self._eval_expr(stmt.children[0], env).as_bool()
        body_children = [c for c in stmt.children[1:] if isinstance(c, Tree)]

        # Detect ELSE split: look for marker (we use position in grammar)
        # Grammar: IF expr THEN stmts [ELSE stmts] ENIF
        # All statement-list children are collected; if there's an ELSE,
        # children are split by a sentinel. We use a simpler approach:
        # flatten and look for none marker. For now assume max 2 blocks.
        then_stmts = []
        else_stmts = []
        in_else = False
        for c in stmt.children[1:]:
            if isinstance(c, Token):
                continue
            if c.data == "statement_list":
                if not in_else:
                    then_stmts = c.children
                    in_else = True
                else:
                    else_stmts = c.children
            else:
                if not in_else:
                    then_stmts.append(c)

        if cond:
            self._exec_statement_list(then_stmts, env)
        else:
            self._exec_statement_list(else_stmts, env)

    # ------------------------------------------------------------------ #
    # FOR                                                                  #
    # ------------------------------------------------------------------ #

    def _exec_for(self, stmt: Tree, env: Environment) -> None:
        var_name = str(stmt.children[0]).upper()

        # Filter to Tree nodes only — NEWLINE and IDENT tokens are kept by lark
        # but aren't expressions. Layout: [start, stop, (step)?, statement_list]
        tree_children = [c for c in stmt.children if isinstance(c, Tree)]
        body_idx = next(i for i, c in enumerate(tree_children) if c.data == "statement_list")

        start_val = self._eval_expr(tree_children[0], env)
        stop_val  = self._eval_expr(tree_children[1], env)
        step_val  = self._eval_expr(tree_children[2], env) if body_idx > 2 else B9Value.integer(1)
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
                self._exec_statement_list(body_stmts, env)
                new_val = env.get(var_name).as_float() + step
                if env.get(var_name).tag == TypeTag.INTEGER:
                    env.set(var_name, B9Value.integer(int(new_val)))
                else:
                    env.set(var_name, B9Value.real(new_val))
        except _Exit:
            pass

    # ------------------------------------------------------------------ #
    # REPEAT/UNTIL                                                         #
    # ------------------------------------------------------------------ #

    def _exec_repeat(self, stmt: Tree, env: Environment) -> None:
        body = [c for c in stmt.children if isinstance(c, Tree) and c.data == "statement_list"]
        cond_node = stmt.children[-1]
        body_stmts = body[0].children if body else []
        try:
            while True:
                self._exec_statement_list(body_stmts, env)
                if self._eval_expr(cond_node, env).as_bool():
                    break
        except _Exit:
            pass

    # ------------------------------------------------------------------ #
    # LOOP/ENDLOOP                                                         #
    # ------------------------------------------------------------------ #

    def _exec_loop(self, stmt: Tree, env: Environment) -> None:
        body = [c for c in stmt.children if isinstance(c, Tree) and c.data == "statement_list"]
        body_stmts = body[0].children if body else []
        try:
            while True:
                self._exec_statement_list(body_stmts, env)
        except _Exit:
            pass

    # ------------------------------------------------------------------ #
    # WHILE/DO/ENDWHILE                                                    #
    # ------------------------------------------------------------------ #

    def _exec_while(self, stmt: Tree, env: Environment) -> None:
        cond_node = stmt.children[0]
        body = [c for c in stmt.children if isinstance(c, Tree) and c.data == "statement_list"]
        body_stmts = body[0].children if body else []
        try:
            while self._eval_expr(cond_node, env).as_bool():
                self._exec_statement_list(body_stmts, env)
        except _Exit:
            pass

    # ------------------------------------------------------------------ #
    # EXIT                                                                 #
    # ------------------------------------------------------------------ #

    def _exec_exit(self, stmt: Tree, env: Environment) -> None:
        raise _Exit()

    def _exec_exitif(self, stmt: Tree, env: Environment) -> None:
        cond = self._eval_expr(stmt.children[0], env).as_bool()
        if cond:
            body = [c for c in stmt.children[1:] if isinstance(c, Tree) and c.data == "statement_list"]
            body_stmts = body[0].children if body else []
            self._exec_statement_list(body_stmts, env)
            raise _Exit()

    # ------------------------------------------------------------------ #
    # RUN (procedure call)                                                 #
    # ------------------------------------------------------------------ #

    def _exec_run(self, stmt: Tree, env: Environment) -> None:
        name = str(stmt.children[0]).upper()
        arg_exprs: list[Tree] = []
        args: list[B9Value] = []
        for child in stmt.children[1:]:
            if isinstance(child, Tree) and child.data == "expr_list":
                arg_exprs = [e for e in child.children if isinstance(e, Tree)]
                args = [self._eval_expr(e, env) for e in arg_exprs]
        proc = self._procedures.get(name)
        if proc is None:
            raise Basic09Error(f"Procedure '{name}' not defined")
        self._call_procedure(proc, args, env, arg_exprs)

    def _call_procedure(self, proc: Tree, args: list[B9Value], caller_env: Environment,
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
                        fname = str(child.children[0]).upper()
                        ftag = self._parse_type(child.children[1])
                        fields.append((fname, ftag))
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

        try:
            self._exec_statement_list(body_stmts, local_env)
        except _Return:
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

    def _eval_expr(self, node: Any, env: Environment) -> B9Value:
        if isinstance(node, Token):
            return B9Value.string(str(node))
        if not isinstance(node, Tree):
            return B9Value.integer(0)

        name = node.data

        # Literals
        if name == "int_lit":
            return B9Value.integer(int(node.children[0]))
        if name == "float_lit":
            return B9Value.real(float(node.children[0]))
        if name == "string_lit":
            return B9Value.string(str(node.children[0])[1:-1])
        if name == "true_lit":
            return B9Value.boolean(True)
        if name == "false_lit":
            return B9Value.boolean(False)
        if name == "pi_lit":
            return B9Value.real(math.pi)

        # Variable
        if name == "var":
            vname = str(node.children[0]).upper()
            token_children = [c for c in node.children if isinstance(c, Token)]
            tree_children = [c for c in node.children if isinstance(c, Tree)]

            if len(token_children) == 2:
                # Record field access: var.field
                field = str(token_children[1]).upper()
                record = env.get(vname)
                return record.value[field]

            if tree_children and tree_children[0].data == "array_index":
                exprs = self._exprs_from_index(tree_children[0])
                if vname in _BUILTINS:
                    args = [self._eval_expr(e, env) for e in exprs]
                    return _BUILTINS[vname](*args)
                indices = tuple(self._eval_expr(e, env).as_int() for e in exprs)
                return env.get_array(vname, indices)
            return env.get(vname)

        # Function call
        if name == "func_call":
            fname = str(node.children[0]).upper()
            args: list[B9Value] = []
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
            "pow_op":  lambda a, b: B9Value.real(a.as_float() ** b.as_float()),
            "eq_op":   lambda a, b: B9Value.boolean(self._compare(a, b) == 0),
            "ne_op":   lambda a, b: B9Value.boolean(self._compare(a, b) != 0),
            "lt_op":   lambda a, b: B9Value.boolean(self._compare(a, b) < 0),
            "le_op":   lambda a, b: B9Value.boolean(self._compare(a, b) <= 0),
            "gt_op":   lambda a, b: B9Value.boolean(self._compare(a, b) > 0),
            "ge_op":   lambda a, b: B9Value.boolean(self._compare(a, b) >= 0),
            "and_op":  lambda a, b: B9Value.boolean(a.as_bool() and b.as_bool()),
            "or_op":   lambda a, b: B9Value.boolean(a.as_bool() or b.as_bool()),
            "xor_op":  lambda a, b: B9Value.boolean(a.as_bool() != b.as_bool()),
        }
        if name in ops:
            a = self._eval_expr(node.children[0], env)
            b = self._eval_expr(node.children[1], env)
            return ops[name](a, b)

        if name == "neg_op":
            a = self._eval_expr(node.children[0], env)
            if a.tag == TypeTag.REAL:
                return B9Value.real(-a.value)
            return B9Value.integer(-a.as_int())

        if name == "not_op":
            return B9Value.boolean(not self._eval_expr(node.children[0], env).as_bool())

        # Fallthrough: try first child
        if node.children:
            return self._eval_expr(node.children[0], env)
        return B9Value.integer(0)

    def _arith(self, a: B9Value, b: B9Value, op: str) -> B9Value:
        # String concatenation
        if op == "+" and a.tag == TypeTag.STRING:
            return B9Value.string(a.as_str() + b.as_str())
        a, b = coerce(a, b)
        if a.tag == TypeTag.REAL:
            v = eval(f"{a.value} {op} {b.value}")  # safe: only numeric operands  # noqa: S307
            return B9Value.real(v)
        if op == "/":
            return B9Value.real(a.as_int() / b.as_int())
        v = eval(f"{a.as_int()} {op} {b.as_int()}")  # noqa: S307
        return B9Value.integer(int(v))

    def _compare(self, a: B9Value, b: B9Value) -> int:
        if a.tag == TypeTag.STRING:
            sa, sb = a.as_str(), b.as_str()
            return (sa > sb) - (sa < sb)
        fa, fb = a.as_float(), b.as_float()
        return (fa > fb) - (fa < fb)

    def _eval_literal(self, node: Any) -> B9Value:
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
