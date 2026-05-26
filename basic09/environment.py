from __future__ import annotations
from typing import Any, Optional
from .types import B9Value, TypeTag, DEFAULT_VALUES


class Basic09Error(Exception):
    pass


class UndefinedVariable(Basic09Error):
    pass


class TypeMismatch(Basic09Error):
    pass


class Environment:
    """One scope frame (program level or procedure level)."""

    def __init__(self, parent: Optional["Environment"] = None):
        self._vars: dict[str, B9Value] = {}
        self._arrays: dict[str, dict[tuple, B9Value]] = {}
        self._types: dict[str, TypeTag] = {}
        self._array_dims: dict[str, list[int]] = {}
        self._record_templates: dict[str, dict] = {}  # name → field defaults for arrays of records
        self.parent = parent

    # ------------------------------------------------------------------ #
    # DIM declarations                                                     #
    # ------------------------------------------------------------------ #

    def declare(self, name: str, tag: TypeTag) -> None:
        self._types[name] = tag
        self._vars[name] = DEFAULT_VALUES[tag]

    def declare_array(self, name: str, dims: list[int], tag: TypeTag,
                      record_template: dict | None = None) -> None:
        self._types[name] = tag
        self._array_dims[name] = dims
        self._arrays[name] = {}
        if record_template is not None:
            self._record_templates[name] = record_template

    def declare_record(self, name: str, fields: dict) -> None:
        self._types[name] = TypeTag.RECORD
        self._vars[name] = B9Value.record(fields)

    # ------------------------------------------------------------------ #
    # Scalar get / set                                                     #
    # ------------------------------------------------------------------ #

    def get(self, name: str) -> B9Value:
        if name in self._vars:
            return self._vars[name]
        if self.parent:
            return self.parent.get(name)
        # Auto-initialize: string variables default to "", numerics to 0
        default = B9Value.string("") if name.endswith("$") else B9Value.integer(0)
        self._vars[name] = default
        self._types[name] = default.tag
        return default

    def set(self, name: str, value: B9Value) -> None:
        if name in self._vars:
            expected = self._types[name]
            value = _cast(value, expected, name)
            self._vars[name] = value
            return
        if self.parent and self.parent._owns(name):
            self.parent.set(name, value)
            return
        # Auto-declare at this scope (undeclared assignment)
        self._vars[name] = value
        self._types[name] = value.tag

    def _owns(self, name: str) -> bool:
        return name in self._vars or (self.parent is not None and self.parent._owns(name))

    # ------------------------------------------------------------------ #
    # Array get / set                                                      #
    # ------------------------------------------------------------------ #

    def get_array(self, name: str, indices: tuple) -> B9Value:
        if name in self._arrays:
            tag = self._types[name]
            if indices not in self._arrays[name]:
                if tag == TypeTag.RECORD and name in self._record_templates:
                    import copy
                    val = B9Value.record(copy.deepcopy(self._record_templates[name]))
                    self._arrays[name][indices] = val
                    return val
                return DEFAULT_VALUES[tag]
            return self._arrays[name][indices]
        if self.parent:
            return self.parent.get_array(name, indices)
        raise UndefinedVariable(f"Array '{name}' not defined")

    def set_array(self, name: str, indices: tuple, value: B9Value) -> None:
        if name in self._arrays:
            tag = self._types[name]
            self._arrays[name][indices] = _cast(value, tag, name)
            return
        if self.parent:
            self.parent.set_array(name, indices, value)
            return
        raise UndefinedVariable(f"Array '{name}' not defined")


def _cast(value: B9Value, target: TypeTag, name: str) -> B9Value:
    if value.tag == target:
        return value
    if target == TypeTag.RECORD:
        return value  # accept any record assignment
    # Allowed coercions
    if target == TypeTag.REAL and value.tag == TypeTag.INTEGER:
        return B9Value.real(float(value.value))
    if target == TypeTag.INTEGER and value.tag == TypeTag.REAL:
        return B9Value.integer(int(value.value))
    if target == TypeTag.BYTE and value.tag == TypeTag.INTEGER:
        return B9Value.byte(value.value)
    raise TypeMismatch(
        f"Cannot assign {value.tag.name} to '{name}' (declared {target.name})"
    )
