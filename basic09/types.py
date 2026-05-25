from __future__ import annotations
from dataclasses import dataclass
from enum import Enum, auto
from typing import Union


class TypeTag(Enum):
    INTEGER = auto()
    REAL = auto()
    STRING = auto()
    BOOLEAN = auto()
    BYTE = auto()
    RECORD = auto()


@dataclass
class B9Value:
    tag: TypeTag
    value: Union[int, float, str, bool, dict]

    # Convenience constructors
    @staticmethod
    def integer(v: int) -> "B9Value":
        return B9Value(TypeTag.INTEGER, int(v))

    @staticmethod
    def real(v: float) -> "B9Value":
        return B9Value(TypeTag.REAL, float(v))

    @staticmethod
    def string(v: str) -> "B9Value":
        return B9Value(TypeTag.STRING, str(v))

    @staticmethod
    def boolean(v: bool) -> "B9Value":
        return B9Value(TypeTag.BOOLEAN, bool(v))

    @staticmethod
    def byte(v: int) -> "B9Value":
        return B9Value(TypeTag.BYTE, int(v) & 0xFF)

    @staticmethod
    def record(fields: dict) -> "B9Value":
        return B9Value(TypeTag.RECORD, fields)

    def is_numeric(self) -> bool:
        return self.tag in (TypeTag.INTEGER, TypeTag.REAL, TypeTag.BYTE)

    def as_int(self) -> int:
        if self.tag in (TypeTag.INTEGER, TypeTag.BYTE):
            return int(self.value)
        if self.tag == TypeTag.REAL:
            return int(self.value)
        raise TypeError(f"Cannot coerce {self.tag} to INTEGER")

    def as_float(self) -> float:
        if self.is_numeric():
            return float(self.value)
        raise TypeError(f"Cannot coerce {self.tag} to REAL")

    def as_bool(self) -> bool:
        if self.tag == TypeTag.BOOLEAN:
            return bool(self.value)
        if self.is_numeric():
            return self.value != 0
        raise TypeError(f"Cannot coerce {self.tag} to BOOLEAN")

    def as_str(self) -> str:
        if self.tag == TypeTag.STRING:
            return str(self.value)
        raise TypeError(f"Cannot coerce {self.tag} to STRING")

    def __str__(self) -> str:
        if self.tag == TypeTag.BOOLEAN:
            return "TRUE" if self.value else "FALSE"
        if self.tag == TypeTag.REAL:
            # Basic09 style: no trailing .0 for whole numbers
            v = float(self.value)
            if v == int(v) and abs(v) < 1e15:
                return str(int(v))
            return repr(v)
        return str(self.value)


def coerce(a: B9Value, b: B9Value) -> tuple[B9Value, B9Value]:
    """Promote INTEGER to REAL when one operand is REAL."""
    if a.tag == TypeTag.REAL and b.tag == TypeTag.INTEGER:
        return a, B9Value.real(float(b.value))
    if a.tag == TypeTag.INTEGER and b.tag == TypeTag.REAL:
        return B9Value.real(float(a.value)), b
    return a, b


DEFAULT_VALUES: dict[TypeTag, B9Value] = {
    TypeTag.INTEGER: B9Value.integer(0),
    TypeTag.REAL: B9Value.real(0.0),
    TypeTag.STRING: B9Value.string(""),
    TypeTag.BOOLEAN: B9Value.boolean(False),
    TypeTag.BYTE: B9Value.byte(0),
    TypeTag.RECORD: B9Value.record({}),
}
