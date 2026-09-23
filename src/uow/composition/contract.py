"""Parent Contract definitions for Campaign A2: Adaptive Composition Runtime.

The Parent Contract U defines WHAT must remain true across all permissible realizations:
Seven Invariant Classes:
  O: Observable outputs / postconditions
  D: Dependency and causal constraints
  A: Authority requirements (Judge, 2-of-3 quorum, etc.)
  E: Evidence / provenance obligations
  T: Temporal requirements (deadlines, causal epochs)
  R: Resource / safety constraints (memory, slots, power, invariants)
  F: Failure semantics (rollback, compensation, quarantine)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ..contracts import EvidenceSpec
from ..state import canonical_json


class FailureSemantics(str, Enum):
    ROLLBACK = "ROLLBACK"
    COMPENSATE = "COMPENSATE"
    QUARANTINE_ON_DIVERGENCE = "QUARANTINE_ON_DIVERGENCE"
    FAIL_CLOSED = "FAIL_CLOSED"
    PARTIAL_COMMIT = "PARTIAL_COMMIT"  # Typically illegal in robust contracts


@dataclass(frozen=True)
class CausalConstraint:
    """Dependency constraint (D) enforcing that a predecessor role must causally precede successor."""
    predecessor_role: str
    successor_role: str
    strict_immediate: bool = False  # True: direct edge required; False: path reachable


@dataclass(frozen=True)
class AuthorityObligation:
    """Authority requirement (A) specifying the verification entity or quorum required before commit."""
    required_role: str = "authority"  # Role in the graph responsible for authoritative certification
    min_evidence_level: str = "portable"  # "portable" or "physical"
    quorum_threshold: int = 1  # 1 for deterministic judge, 2 for 2-of-3 quorum
    required_substrates: Tuple[str, ...] = ()  # Specific substrates required if physical


@dataclass(frozen=True)
class EvidenceObligation:
    """Evidence / provenance obligation (E)."""
    require_provenance: bool = True
    require_hash_chain: bool = True
    min_evidence_level: str = "portable"
    verifier_id: str = "deterministic-judge"


@dataclass(frozen=True)
class TemporalConstraint:
    """Temporal requirement (T) bounding execution duration or deadlines."""
    max_duration_ms: float = 1000.0
    deadline_epoch: Optional[int] = None


@dataclass(frozen=True)
class ResourceConstraint:
    """Resource and safety envelope (R)."""
    max_cpu_cores: int = 8
    max_ram_units: int = 16
    max_gpu_slots: int = 2
    max_npu_slots: int = 2
    max_cost_units: float = 100.0
    safety_invariants: Tuple[str, ...] = ()  # Invariant condition tags that must hold


@dataclass(frozen=True)
class ParentContract:
    """Declarative specification of parent intent U = (O, D, A, E, T, R, F).
    
    Any realization graph G satisfies U iff:
        Phi(G, U) == Phi(U)
    """
    contract_id: str
    description: str

    # 1. Observable outputs / postconditions (O)
    required_outputs: Tuple[str, ...]

    # 2. Dependency and causal constraints (D)
    causal_constraints: Tuple[CausalConstraint, ...] = ()

    # 3. Authority requirements (A)
    authority: AuthorityObligation = field(default_factory=AuthorityObligation)

    # 4. Evidence / provenance obligations (E)
    evidence: EvidenceObligation = field(default_factory=EvidenceObligation)

    # 5. Temporal requirements (T)
    temporal: TemporalConstraint = field(default_factory=TemporalConstraint)

    # 6. Resource / safety constraints (R)
    resources: ResourceConstraint = field(default_factory=ResourceConstraint)

    # 7. Failure semantics (F)
    failure_semantics: FailureSemantics = FailureSemantics.ROLLBACK

    # Canonical cryptographic digest
    contract_hash: str = ""

    def __post_init__(self) -> None:
        if not self.contract_hash:
            payload = {
                "contract_id": self.contract_id,
                "required_outputs": sorted(self.required_outputs),
                "causal_constraints": [
                    f"{c.predecessor_role}->{c.successor_role}:{'imm' if c.strict_immediate else 'reach'}"
                    for c in self.causal_constraints
                ],
                "authority": {
                    "role": self.authority.required_role,
                    "level": self.authority.min_evidence_level,
                    "threshold": self.authority.quorum_threshold,
                    "substrates": sorted(self.authority.required_substrates),
                },
                "evidence": {
                    "require_provenance": self.evidence.require_provenance,
                    "require_hash_chain": self.evidence.require_hash_chain,
                    "min_level": self.evidence.min_evidence_level,
                    "verifier_id": self.evidence.verifier_id,
                },
                "temporal": {
                    "max_duration_ms": self.temporal.max_duration_ms,
                    "deadline_epoch": self.temporal.deadline_epoch,
                },
                "resources": {
                    "max_cpu_cores": self.resources.max_cpu_cores,
                    "max_ram_units": self.resources.max_ram_units,
                    "max_gpu_slots": self.resources.max_gpu_slots,
                    "max_npu_slots": self.resources.max_npu_slots,
                    "max_cost_units": self.resources.max_cost_units,
                    "safety_invariants": sorted(self.resources.safety_invariants),
                },
                "failure_semantics": self.failure_semantics.value,
            }
            digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
            object.__setattr__(self, "contract_hash", digest)

    def compute_hash(self) -> str:
        return self.contract_hash

