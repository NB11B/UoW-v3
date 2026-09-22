"""Semantic work ontology.

The 8 x 8 matrix classifies what kind of work a Unit of Work represents.
It is intentionally orthogonal to execution semantics and is not an opcode set.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Tuple


class WorkCategory(str, Enum):
    PEOPLE = "People"
    PROCESSES = "Processes"
    DATA = "Data"
    DEVICES = "Devices"
    RULES = "Rules"
    POLICIES = "Policies"
    AGENTS = "Agents"
    GUIDANCE = "Guidance"


@dataclass(frozen=True, order=True)
class MatrixCell:
    source: WorkCategory
    target: WorkCategory


ALL_MATRIX_CELLS: Tuple[MatrixCell, ...] = tuple(
    MatrixCell(source, target)
    for source in WorkCategory
    for target in WorkCategory
)

if len(ALL_MATRIX_CELLS) != 64:
    raise RuntimeError("UoW ontology must contain exactly 64 directed pairings.")
