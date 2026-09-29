"""Frozen seven-letter semantic work basis.

Defines the frozen abstract calculus:
    Σ_W = {O, E, K, C, F, D, S}
    O: OBSERVE
    E: ESTIMATE
    K: CLASSIFY
    C: COMPARE
    F: FORM
    D: DECOMPOSE
    S: SELECT
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
from typing import FrozenSet, Optional, Tuple

from uow.state import canonical_json


class WorkArtifact(str, Enum):
    SIGNAL = "SIGNAL"
    OBSERVATION = "OBSERVATION"
    BELIEF = "BELIEF"
    MEANING = "MEANING"
    DIFFERENCE = "DIFFERENCE"
    INTENT = "INTENT"
    GOAL = "GOAL"
    WORK = "WORK"
    NECESSARY_WORK = "NECESSARY_WORK"
    DISPOSITION = "DISPOSITION"
    FAILURE = "FAILURE"
    AFFECTED_WORK = "AFFECTED_WORK"
    TRIAL = "TRIAL"
    CHANGE = "CHANGE"
    EFFECT = "EFFECT"
    VOTES = "VOTES"
    AUTHORITY_SCOPE = "AUTHORITY_SCOPE"
    RESOURCE_STATE = "RESOURCE_STATE"
    SCHEDULE = "SCHEDULE"
    CERTIFICATE = "CERTIFICATE"
    RECEIPT = "RECEIPT"
    ASSIGNMENT = "ASSIGNMENT"


@dataclass(frozen=True)
class CertifiedOperator:
    symbol: str
    name: str
    transitions: Tuple[Tuple[WorkArtifact, WorkArtifact], ...]
    effects: FrozenSet[str]


@dataclass(frozen=True)
class CertifiedWorkBasis:
    basis_id: str
    operators: Tuple[CertifiedOperator, ...]
    artifacts: Tuple[WorkArtifact, ...]
    effects: FrozenSet[str]

    def get_operator(self, symbol: str) -> Optional[CertifiedOperator]:
        for op in self.operators:
            if op.symbol == symbol:
                return op
        return None


# Backward-compatible alias
CertifiedSemanticBasis = CertifiedWorkBasis


def load_certified_basis() -> CertifiedWorkBasis:
    """Instantiate and hash-bind the frozen seven-letter abstract calculus."""
    ops = (
        CertifiedOperator(
            "O",
            "OBSERVE",
            ((WorkArtifact.SIGNAL, WorkArtifact.OBSERVATION),),
            frozenset({"observe"}),
        ),
        CertifiedOperator(
            "E",
            "ESTIMATE",
            ((WorkArtifact.OBSERVATION, WorkArtifact.BELIEF),),
            frozenset({"estimate"}),
        ),
        CertifiedOperator(
            "K",
            "CLASSIFY",
            (
                (WorkArtifact.SIGNAL, WorkArtifact.MEANING),
                (WorkArtifact.OBSERVATION, WorkArtifact.MEANING),
                (WorkArtifact.BELIEF, WorkArtifact.MEANING),
                (WorkArtifact.RECEIPT, WorkArtifact.MEANING),
                (WorkArtifact.DIFFERENCE, WorkArtifact.DISPOSITION),
                (WorkArtifact.NECESSARY_WORK, WorkArtifact.DISPOSITION),
            ),
            frozenset({"classify"}),
        ),
        CertifiedOperator(
            "C",
            "COMPARE",
            (
                (WorkArtifact.BELIEF, WorkArtifact.DIFFERENCE),
                (WorkArtifact.TRIAL, WorkArtifact.DIFFERENCE),
                (WorkArtifact.WORK, WorkArtifact.DIFFERENCE),
                (WorkArtifact.AUTHORITY_SCOPE, WorkArtifact.DIFFERENCE),
                (WorkArtifact.RESOURCE_STATE, WorkArtifact.DIFFERENCE),
                (WorkArtifact.VOTES, WorkArtifact.DIFFERENCE),
            ),
            frozenset({"compare"}),
        ),
        CertifiedOperator(
            "F",
            "FORM",
            (
                (WorkArtifact.DIFFERENCE, WorkArtifact.GOAL),
                (WorkArtifact.INTENT, WorkArtifact.GOAL),
                (WorkArtifact.MEANING, WorkArtifact.INTENT),
                (WorkArtifact.MEANING, WorkArtifact.GOAL),
                (WorkArtifact.DIFFERENCE, WorkArtifact.CHANGE),
                (WorkArtifact.DISPOSITION, WorkArtifact.GOAL),
                (WorkArtifact.DISPOSITION, WorkArtifact.CERTIFICATE),
            ),
            frozenset({"form"}),
        ),
        CertifiedOperator(
            "D",
            "DECOMPOSE",
            (
                (WorkArtifact.GOAL, WorkArtifact.WORK),
                (WorkArtifact.AFFECTED_WORK, WorkArtifact.WORK),
            ),
            frozenset({"decompose"}),
        ),
        CertifiedOperator(
            "S",
            "SELECT",
            (
                (WorkArtifact.WORK, WorkArtifact.NECESSARY_WORK),
                (WorkArtifact.WORK, WorkArtifact.SCHEDULE),
                (WorkArtifact.WORK, WorkArtifact.ASSIGNMENT),
                (WorkArtifact.FAILURE, WorkArtifact.AFFECTED_WORK),
            ),
            frozenset({"select"}),
        ),
    )
    all_artifacts: set[WorkArtifact] = set()
    all_effects: set[str] = set()
    for cop in ops:
        for src, tgt in cop.transitions:
            all_artifacts.add(src)
            all_artifacts.add(tgt)
        all_effects.update(cop.effects)

    payload = {
        "basis_name": "frozen_seven_letter_semantic_basis",
        "operators": [
            {
                "symbol": cop.symbol,
                "name": cop.name,
                "transitions": [
                    [src.value, tgt.value] for src, tgt in cop.transitions
                ],
                "effects": sorted(list(cop.effects)),
            }
            for cop in ops
        ],
    }
    basis_id = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    return CertifiedWorkBasis(
        basis_id=basis_id,
        operators=ops,
        artifacts=tuple(sorted(all_artifacts, key=lambda a: a.value)),
        effects=frozenset(all_effects),
    )


__all__ = [
    "CertifiedOperator",
    "CertifiedSemanticBasis",
    "CertifiedWorkBasis",
    "WorkArtifact",
    "load_certified_basis",
]
