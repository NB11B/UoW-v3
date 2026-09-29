"""Metacognition and semantic deficit detection package for UoW Autonomy.

Separates semantic adequacy from execution readiness:
    SemanticClass in {KNOWN, UNKNOWN_SURFACE, UNREPRESENTABLE}
    Readiness in {READY, MISSING_EVIDENCE, MISSING_BINDING, MISSING_CAPABILITY, RESOURCE_BLOCKED, POLICY_BLOCKED}
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
from typing import Any, FrozenSet, Mapping, Optional, Sequence, Set, Tuple

from uow.state import canonical_json
from .work_basis import CertifiedWorkBasis, WorkArtifact, load_certified_basis


class ParseStatus(str, Enum):
    """Front-end syntactic/NLP parse resolution."""
    PARSED = "PARSED"
    AMBIGUOUS = "AMBIGUOUS"
    INSUFFICIENT_INFORMATION = "INSUFFICIENT_INFORMATION"


class SemanticClass(str, Enum):
    """Three-way semantic adequacy classification."""
    KNOWN = "KNOWN"
    UNKNOWN_SURFACE = "UNKNOWN_SURFACE"
    UNREPRESENTABLE = "UNREPRESENTABLE"


class Readiness(str, Enum):
    """Orthogonal execution readiness state."""
    READY = "READY"
    MISSING_EVIDENCE = "MISSING_EVIDENCE"
    MISSING_BINDING = "MISSING_BINDING"
    MISSING_CAPABILITY = "MISSING_CAPABILITY"
    RESOURCE_BLOCKED = "RESOURCE_BLOCKED"
    POLICY_BLOCKED = "POLICY_BLOCKED"


@dataclass(frozen=True)
class TaskSemanticRequest:
    """Typed semantic task request tau = (I, O, E, G, A)."""
    task_id: str
    parse_status: ParseStatus
    input_artifacts: Tuple[WorkArtifact, ...]
    output_artifacts: Tuple[WorkArtifact, ...]
    required_effects: FrozenSet[str]
    constraints: Mapping[str, Any] = field(default_factory=dict)
    authority_requirements: Tuple[str, ...] = ()
    surface_entities: Tuple[str, ...] = ()
    grounded_entities: Tuple[str, ...] = ()

    # Orthogonal execution environment bindings
    available_tools: Tuple[str, ...] = ()
    required_tools: Tuple[str, ...] = ()
    available_resources: Mapping[str, float] = field(default_factory=dict)
    required_resources: Mapping[str, float] = field(default_factory=dict)
    authorized_scopes: Tuple[str, ...] = ()
    current_observations: Tuple[str, ...] = ()
    required_observations: Tuple[str, ...] = ()
    raw_prompt: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_artifacts", tuple(self.input_artifacts))
        object.__setattr__(self, "output_artifacts", tuple(self.output_artifacts))
        object.__setattr__(self, "required_effects", frozenset(self.required_effects))
        object.__setattr__(self, "authority_requirements", tuple(self.authority_requirements))
        object.__setattr__(self, "surface_entities", tuple(self.surface_entities))
        object.__setattr__(self, "grounded_entities", tuple(self.grounded_entities))
        object.__setattr__(self, "available_tools", tuple(self.available_tools))
        object.__setattr__(self, "required_tools", tuple(self.required_tools))
        object.__setattr__(self, "authorized_scopes", tuple(self.authorized_scopes))
        object.__setattr__(self, "current_observations", tuple(self.current_observations))
        object.__setattr__(self, "required_observations", tuple(self.required_observations))


@dataclass(frozen=True)
class ProofOfNonDerivability:
    """Deterministic mathematical proof that a task goal is unreachable in basis C_t."""
    initial_artifacts: Tuple[str, ...]
    target_artifacts: Tuple[str, ...]
    required_effects: Tuple[str, ...]
    missing_effects: Tuple[str, ...]
    reachable_closure_artifacts: Tuple[str, ...]
    reachable_closure_effects: Tuple[str, ...]
    max_search_depth: int
    total_states_explored: int
    unreachability_reason: str


@dataclass(frozen=True)
class DeficitCertificate:
    """Certified proof witness of an unrepresentable task."""
    task_id: str
    basis_id: str
    missing_requirement: str
    reachable_closure: Tuple[str, ...]
    proof: ProofOfNonDerivability
    certificate_hash: str = ""

    def __post_init__(self) -> None:
        payload = {
            "task_id": self.task_id,
            "basis_id": self.basis_id,
            "missing_requirement": self.missing_requirement,
            "reachable_closure": sorted(list(self.reachable_closure)),
            "proof": {
                "initial_artifacts": sorted(list(self.proof.initial_artifacts)),
                "target_artifacts": sorted(list(self.proof.target_artifacts)),
                "required_effects": sorted(list(self.proof.required_effects)),
                "missing_effects": sorted(list(self.proof.missing_effects)),
                "reachable_closure_artifacts": sorted(list(self.proof.reachable_closure_artifacts)),
                "reachable_closure_effects": sorted(list(self.proof.reachable_closure_effects)),
                "max_search_depth": self.proof.max_search_depth,
                "total_states_explored": self.proof.total_states_explored,
                "unreachability_reason": self.proof.unreachability_reason,
            },
        }
        expected = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
        if self.certificate_hash and self.certificate_hash != expected:
            raise ValueError("certificate_hash does not match certificate contents.")
        object.__setattr__(self, "certificate_hash", expected)

    @property
    def is_valid(self) -> bool:
        return bool(self.certificate_hash)


@dataclass(frozen=True)
class SemanticAssessment:
    """Formal two-dimensional metacognitive assessment."""
    task_id: str
    semantic_class: Optional[SemanticClass]
    readiness: Readiness
    certificate: Optional[DeficitCertificate]
    basis_id: str
    reason_codes: Tuple[str, ...] = ()
    assessment_hash: str = ""

    def __post_init__(self) -> None:
        payload = {
            "task_id": self.task_id,
            "semantic_class": self.semantic_class.value if self.semantic_class else None,
            "readiness": self.readiness.value,
            "certificate_hash": self.certificate.certificate_hash if self.certificate else None,
            "basis_id": self.basis_id,
            "reason_codes": list(self.reason_codes),
        }
        expected = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
        if self.assessment_hash and self.assessment_hash != expected:
            raise ValueError("assessment_hash does not match assessment contents.")
        object.__setattr__(self, "assessment_hash", expected)


def compute_reachability_closure(
    initial_artifacts: Sequence[WorkArtifact],
    basis: CertifiedWorkBasis,
    max_depth: int = 16,
) -> tuple[Set[WorkArtifact], Set[str], Set[tuple[WorkArtifact, FrozenSet[str]]]]:
    """Compute the finite forward reachability fixed point over basis C_t."""
    current_states: set[tuple[WorkArtifact, FrozenSet[str]]] = {
        (art, frozenset()) for art in initial_artifacts
    }
    all_reachable_states = set(current_states)
    depth = 0

    while depth < max_depth:
        depth += 1
        next_states: set[tuple[WorkArtifact, FrozenSet[str]]] = set()
        for art, effects in current_states:
            for op in basis.operators:
                for src, tgt in op.transitions:
                    if src == art:
                        new_effects = frozenset(set(effects) | set(op.effects))
                        state = (tgt, new_effects)
                        if state not in all_reachable_states:
                            next_states.add(state)
                            all_reachable_states.add(state)
        if not next_states:
            break
        current_states = next_states

    reachable_artifacts = {art for art, _ in all_reachable_states}
    reachable_effects = set().union(*(eff for _, eff in all_reachable_states)) if all_reachable_states else set()

    return reachable_artifacts, reachable_effects, all_reachable_states


def can_derive_task(
    initial_artifacts: Sequence[WorkArtifact],
    target_artifacts: Sequence[WorkArtifact],
    required_effects: FrozenSet[str],
    basis: CertifiedWorkBasis,
    max_depth: int = 16,
) -> bool:
    """Check if any valid derivation path connects initial to target artifacts satisfying required effects."""
    _, _, all_states = compute_reachability_closure(initial_artifacts, basis, max_depth)
    for tgt in target_artifacts:
        for reached_art, reached_effects in all_states:
            if reached_art == tgt and required_effects.issubset(reached_effects):
                return True
    return False


def build_deficit_certificate(
    task_id: str,
    initial_artifacts: Sequence[WorkArtifact],
    target_artifacts: Sequence[WorkArtifact],
    required_effects: FrozenSet[str],
    basis: CertifiedWorkBasis,
    max_depth: int = 16,
) -> DeficitCertificate:
    """Construct an authoritative, cryptographically certified proof of unreachability."""
    reach_arts, reach_effs, all_states = compute_reachability_closure(initial_artifacts, basis, max_depth)

    target_set = set(target_artifacts)
    missing_effects = set(required_effects) - set(basis.effects)
    unreachable_targets = target_set - reach_arts

    if missing_effects:
        reason = f"UNKNOWN_ELEMENTARY_EFFECTS:{','.join(sorted(missing_effects))}"
        missing_req = f"Effect '{next(iter(sorted(missing_effects)))}' is absent from certified basis"
    elif unreachable_targets == target_set:
        reason = "TARGET_ARTIFACTS_UNREACHABLE_FROM_INPUTS"
        missing_req = f"No typed operator pipeline connects inputs to {[t.value for t in target_artifacts]}"
    else:
        reason = "EFFECT_OBLIGATION_UNSATISFIABLE"
        missing_req = f"Required effects {sorted(list(required_effects))} cannot be accumulated on path to target"

    proof = ProofOfNonDerivability(
        initial_artifacts=tuple(sorted(a.value for a in initial_artifacts)),
        target_artifacts=tuple(sorted(a.value for a in target_artifacts)),
        required_effects=tuple(sorted(required_effects)),
        missing_effects=tuple(sorted(missing_effects)),
        reachable_closure_artifacts=tuple(sorted(a.value for a in reach_arts)),
        reachable_closure_effects=tuple(sorted(reach_effs)),
        max_search_depth=max_depth,
        total_states_explored=len(all_states),
        unreachability_reason=reason,
    )

    return DeficitCertificate(
        task_id=task_id,
        basis_id=basis.basis_id,
        missing_requirement=missing_req,
        reachable_closure=proof.reachable_closure_artifacts,
        proof=proof,
    )


def verify_deficit_certificate(
    certificate: DeficitCertificate,
    basis: CertifiedWorkBasis,
) -> bool:
    """Verify that a DeficitCertificate is mathematically sound and untampered."""
    if certificate.basis_id != basis.basis_id:
        return False

    try:
        DeficitCertificate(
            task_id=certificate.task_id,
            basis_id=certificate.basis_id,
            missing_requirement=certificate.missing_requirement,
            reachable_closure=certificate.reachable_closure,
            proof=certificate.proof,
            certificate_hash=certificate.certificate_hash,
        )
    except ValueError:
        return False

    init_arts = [WorkArtifact(a) for a in certificate.proof.initial_artifacts if a in WorkArtifact.__members__]
    tgt_arts = [WorkArtifact(a) for a in certificate.proof.target_artifacts if a in WorkArtifact.__members__]

    if len(init_arts) != len(certificate.proof.initial_artifacts) or len(tgt_arts) != len(certificate.proof.target_artifacts):
        return True

    reach_arts, reach_effs, all_states = compute_reachability_closure(
        init_arts, basis, certificate.proof.max_search_depth
    )

    actual_closure = tuple(sorted(a.value for a in reach_arts))
    if actual_closure != certificate.reachable_closure:
        return False

    req_effs = frozenset(certificate.proof.required_effects)
    for tgt in tgt_arts:
        for reached_art, reached_effects in all_states:
            if reached_art == tgt and req_effs.issubset(reached_effects):
                return False

    return True


def evaluate_readiness(
    *,
    required_tools: Sequence[str] = (),
    available_tools: Sequence[str] = (),
    required_resources: Mapping[str, float] | None = None,
    available_resources: Mapping[str, float] | None = None,
    required_authority: Sequence[str] = (),
    authorized_scopes: Sequence[str] = (),
    required_observations: Sequence[str] = (),
    current_observations: Sequence[str] = (),
    surface_entities: Sequence[str] = (),
    grounded_entities: Sequence[str] = (),
) -> Tuple[Readiness, Tuple[str, ...]]:
    """Deterministically classify execution readiness and identify blocking reasons."""
    reasons: list[str] = []

    ungrounded = [e for e in surface_entities if e not in grounded_entities]
    if ungrounded:
        reasons.append(f"UNGROUNDED_ENTITIES:{','.join(ungrounded)}")
        return Readiness.MISSING_BINDING, tuple(reasons)

    missing_obs = [o for o in required_observations if o not in current_observations]
    if missing_obs:
        reasons.append(f"MISSING_OBSERVATIONS:{','.join(missing_obs)}")
        return Readiness.MISSING_EVIDENCE, tuple(reasons)

    missing_tools = [t for t in required_tools if t not in available_tools]
    if missing_tools:
        reasons.append(f"MISSING_CAPABILITY:{','.join(missing_tools)}")
        return Readiness.MISSING_CAPABILITY, tuple(reasons)

    req_res = required_resources or {}
    avail_res = available_resources or {}
    for res_name, req_val in req_res.items():
        avail_val = avail_res.get(res_name, 0.0)
        if avail_val < req_val:
            reasons.append(f"RESOURCE_EXCEEDED:{res_name}:needed_{req_val}_have_{avail_val}")
            return Readiness.RESOURCE_BLOCKED, tuple(reasons)

    missing_auth = [a for a in required_authority if a not in authorized_scopes]
    if missing_auth:
        reasons.append(f"POLICY_DENIED:{','.join(missing_auth)}")
        return Readiness.POLICY_BLOCKED, tuple(reasons)

    return Readiness.READY, ()


def assess_semantics(
    task: TaskSemanticRequest,
    basis: Optional[CertifiedWorkBasis] = None,
) -> SemanticAssessment:
    """Deterministically assess whether a task is semantically representable in basis C_t."""
    if basis is None:
        basis = load_certified_basis()

    if task.parse_status == ParseStatus.AMBIGUOUS:
        return SemanticAssessment(
            task_id=task.task_id,
            semantic_class=None,
            readiness=Readiness.MISSING_BINDING,
            certificate=None,
            basis_id=basis.basis_id,
            reason_codes=("AMBIGUOUS_PARSE",),
        )
    elif task.parse_status == ParseStatus.INSUFFICIENT_INFORMATION:
        return SemanticAssessment(
            task_id=task.task_id,
            semantic_class=None,
            readiness=Readiness.MISSING_EVIDENCE,
            certificate=None,
            basis_id=basis.basis_id,
            reason_codes=("INSUFFICIENT_INFORMATION",),
        )

    readiness, readiness_reasons = evaluate_readiness(
        required_tools=task.required_tools,
        available_tools=task.available_tools,
        required_resources=task.required_resources,
        available_resources=task.available_resources,
        required_authority=task.authority_requirements,
        authorized_scopes=task.authorized_scopes,
        required_observations=task.required_observations,
        current_observations=task.current_observations,
        surface_entities=task.surface_entities,
        grounded_entities=task.grounded_entities,
    )

    derivable = can_derive_task(
        task.input_artifacts,
        task.output_artifacts,
        task.required_effects,
        basis,
    )

    if not derivable:
        cert = build_deficit_certificate(
            task.task_id,
            task.input_artifacts,
            task.output_artifacts,
            task.required_effects,
            basis,
        )
        return SemanticAssessment(
            task_id=task.task_id,
            semantic_class=SemanticClass.UNREPRESENTABLE,
            readiness=readiness,
            certificate=cert,
            basis_id=basis.basis_id,
            reason_codes=("SEMANTIC_CLOSURE_FAILED", cert.proof.unreachability_reason) + readiness_reasons,
        )

    ungrounded = set(task.surface_entities) - set(task.grounded_entities)
    if ungrounded:
        return SemanticAssessment(
            task_id=task.task_id,
            semantic_class=SemanticClass.UNKNOWN_SURFACE,
            readiness=Readiness.MISSING_BINDING,
            certificate=None,
            basis_id=basis.basis_id,
            reason_codes=(f"UNGROUNDED_SURFACE_ENTITIES:{','.join(sorted(ungrounded))}",) + readiness_reasons,
        )

    return SemanticAssessment(
        task_id=task.task_id,
        semantic_class=SemanticClass.KNOWN,
        readiness=readiness,
        certificate=None,
        basis_id=basis.basis_id,
        reason_codes=readiness_reasons,
    )


__all__ = [
    "DeficitCertificate",
    "ParseStatus",
    "ProofOfNonDerivability",
    "Readiness",
    "SemanticAssessment",
    "SemanticClass",
    "TaskSemanticRequest",
    "assess_semantics",
    "build_deficit_certificate",
    "can_derive_task",
    "compute_reachability_closure",
    "evaluate_readiness",
    "verify_deficit_certificate",
]
