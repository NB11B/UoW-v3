"""Unified adaptation qualification seam.

R6 Qualification: Universal Non-Authoritative Self-Improvement Protocol.

Core Principle:
    Can the system improve itself without acquiring authority over itself?
    Learning may modify proposals, not authority.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import math
from types import MappingProxyType
from typing import Mapping, Optional, Sequence, Tuple

from uow.state import WorldState, canonical_json
from .metacognition import SemanticAssessment, SemanticClass


class AdaptationTargetKind(str, Enum):
    PARAMETER = "PARAMETER"
    POLICY = "POLICY"
    MODEL = "MODEL"
    DEVICE_PLACEMENT = "DEVICE_PLACEMENT"
    SEMANTIC_FRONTEND = "SEMANTIC_FRONTEND"
    SEMANTIC_GRAMMAR = "SEMANTIC_GRAMMAR"
    BELIEF_FORMER = "BELIEF_FORMER"
    GOAL_FORMER = "GOAL_FORMER"
    WORK_IDENTIFIER = "WORK_IDENTIFIER"
    ROUTING_POLICY = "ROUTING_POLICY"
    PLACEMENT_POLICY = "PLACEMENT_POLICY"
    SCHEDULING_POLICY = "SCHEDULING_POLICY"
    CAPABILITY_POLICY = "CAPABILITY_POLICY"


class MetricDirection(str, Enum):
    MAXIMIZE = "MAXIMIZE"
    MINIMIZE = "MINIMIZE"


@dataclass(frozen=True)
class MetricVector:
    """Common metric vector M = (Q, D, C, E, R, S)."""
    quality: float = 1.0
    determinism: float = 1.0
    cost: float = 1.0
    energy: float = 1.0
    reliability: float = 1.0
    safety: float = 1.0
    custom_metrics: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "custom_metrics", MappingProxyType(dict(self.custom_metrics)))

    def to_dict(self) -> dict[str, float]:
        res = {
            "quality": float(self.quality),
            "determinism": float(self.determinism),
            "cost": float(self.cost),
            "energy": float(self.energy),
            "reliability": float(self.reliability),
            "safety": float(self.safety),
        }
        for k, v in self.custom_metrics.items():
            res[str(k)] = float(v)
        return res


@dataclass(frozen=True)
class MetricRule:
    metric: str
    direction: MetricDirection
    min_relative_improvement: float = 0.0
    max_relative_regression: float = 0.0

    def __post_init__(self) -> None:
        if not self.metric:
            raise ValueError("metric must be non-empty.")
        if self.min_relative_improvement < 0.0:
            raise ValueError("min_relative_improvement must be nonnegative.")
        if self.max_relative_regression < 0.0:
            raise ValueError("max_relative_regression must be nonnegative.")


@dataclass(frozen=True)
class AdaptationObjective:
    metric: str
    direction: MetricDirection
    min_relative_improvement: float = 0.0
    min_margin: float = 0.0


@dataclass(frozen=True)
class MetricConstraint:
    metric: str
    direction: MetricDirection
    bound: float
    description: str = ""


@dataclass(frozen=True)
class MetricCriterion:
    criterion_id: str
    metric: str
    direction: MetricDirection
    min_relative_improvement: float = 0.0
    max_relative_regression: float = 0.0


# Backward compatibility aliases
Constraint = MetricConstraint
Criterion = MetricCriterion


@dataclass(frozen=True)
class AdaptationProposal:
    target_kind: AdaptationTargetKind
    target_id: str
    incumbent_artifact_hash: str = ""
    candidate_artifact_hash: str = ""
    pre_state_hash: str = ""
    proposer_id: str = "adaptation.proposer"
    proposal_id: str = ""

    baseline_version: str = ""
    candidate_version: str = ""
    objective: Optional[AdaptationObjective] = None
    predicted_delta: Optional[MetricVector] = None
    safety_constraints: Tuple[MetricConstraint, ...] = ()
    qualification_requirements: Tuple[MetricCriterion, ...] = ()
    evidence_refs: Tuple[str, ...] = ()
    parent_proposal_id: Optional[str] = None
    rollback_ref: str = ""
    touches_frozen_compiler: bool = False

    def __post_init__(self) -> None:
        base = self.baseline_version or self.incumbent_artifact_hash
        cand = self.candidate_version or self.candidate_artifact_hash
        if not base or not cand:
            raise ValueError("baseline/incumbent and candidate hashes or versions are required.")
        object.__setattr__(self, "baseline_version", base)
        object.__setattr__(self, "incumbent_artifact_hash", base)
        object.__setattr__(self, "candidate_version", cand)
        object.__setattr__(self, "candidate_artifact_hash", cand)

        if not self.target_id or not self.pre_state_hash or not self.proposer_id:
            raise ValueError("target_id, pre_state_hash, and proposer_id are required.")

        rb = self.rollback_ref or base
        object.__setattr__(self, "rollback_ref", rb)
        object.__setattr__(self, "safety_constraints", tuple(self.safety_constraints))
        object.__setattr__(self, "qualification_requirements", tuple(self.qualification_requirements))
        object.__setattr__(self, "evidence_refs", tuple(str(x) for x in self.evidence_refs))

        expected = self.calculate_id()
        if self.proposal_id and self.proposal_id != expected:
            raise ValueError("proposal_id does not match adaptation proposal.")
        object.__setattr__(self, "proposal_id", expected)

    def calculate_id(self) -> str:
        payload: dict[str, object] = {
            "target_kind": self.target_kind.value,
            "target_id": self.target_id,
            "incumbent_artifact_hash": self.incumbent_artifact_hash,
            "candidate_artifact_hash": self.candidate_artifact_hash,
            "pre_state_hash": self.pre_state_hash,
            "proposer_id": self.proposer_id,
            "rollback_ref": self.rollback_ref,
        }
        if self.objective is not None:
            payload["objective"] = {
                "metric": self.objective.metric,
                "direction": self.objective.direction.value,
                "min_relative_improvement": self.objective.min_relative_improvement,
                "min_margin": self.objective.min_margin,
            }
        if self.parent_proposal_id:
            payload["parent_proposal_id"] = self.parent_proposal_id
        if self.touches_frozen_compiler:
            payload["touches_frozen_compiler"] = True
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AdaptationTrialEvidence:
    proposal_id: str
    baseline_metrics: Mapping[str, float]
    candidate_metrics: Mapping[str, float]
    sample_count: int
    invariant_breaches: int = 0
    authority_breaches: int = 0
    determinism_breaches: int = 0
    evidence_refs: Tuple[str, ...] = ()
    holdout_id: str = ""
    experiment_spec: str = ""
    tail_metric_regression: float = 0.0
    trial_hash: str = ""

    def __post_init__(self) -> None:
        if self.sample_count < 0:
            raise ValueError("sample_count must be nonnegative.")
        baseline = {str(k): float(v) for k, v in self.baseline_metrics.items()}
        candidate = {str(k): float(v) for k, v in self.candidate_metrics.items()}
        if not all(math.isfinite(v) for v in baseline.values()):
            raise ValueError("baseline metrics must be finite.")
        if not all(math.isfinite(v) for v in candidate.values()):
            raise ValueError("candidate metrics must be finite.")
        object.__setattr__(self, "baseline_metrics", MappingProxyType(baseline))
        object.__setattr__(self, "candidate_metrics", MappingProxyType(candidate))
        object.__setattr__(self, "evidence_refs", tuple(str(x) for x in self.evidence_refs))

        payload = {
            "proposal_id": self.proposal_id,
            "baseline_metrics": baseline,
            "candidate_metrics": candidate,
            "sample_count": self.sample_count,
            "invariant_breaches": self.invariant_breaches,
            "authority_breaches": self.authority_breaches,
            "determinism_breaches": self.determinism_breaches,
            "evidence_refs": list(self.evidence_refs),
            "holdout_id": self.holdout_id,
            "experiment_spec": self.experiment_spec,
            "tail_metric_regression": float(self.tail_metric_regression),
        }
        expected = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
        if self.trial_hash and self.trial_hash != expected:
            raise ValueError("trial_hash does not match trial contents.")
        object.__setattr__(self, "trial_hash", expected)


@dataclass(frozen=True)
class AdaptationQualificationPolicy:
    objective: MetricRule
    protected_metrics: Tuple[MetricRule, ...] = ()
    min_samples: int = 1
    min_hysteresis_margin: float = 0.0
    max_allowable_tail_regression: float = 0.05


@dataclass(frozen=True)
class QualificationCertificate:
    certificate_id: str
    proposal_id: str
    target_kind: AdaptationTargetKind
    target_id: str
    baseline_version: str
    candidate_version: str
    metric_deltas: Mapping[str, float]
    sample_count: int
    confidence: float
    constraint_results: Mapping[str, str]
    determinism_verified: bool
    rollback_proof: str
    experiment_spec: str
    holdout_id: str
    parent_proposal_id: Optional[str]
    certificate_hash: str


@dataclass(frozen=True)
class AdaptationPromotionRecommendation:
    promotion_id: str
    proposal_id: str
    target_kind: AdaptationTargetKind
    target_id: str
    candidate_artifact_hash: str
    rollback_artifact_hash: str
    qualification_hash: str
    evidence_refs: Tuple[str, ...]
    certificate: Optional[QualificationCertificate] = None


@dataclass(frozen=True)
class AdaptationQualificationResult:
    recommendation: Optional[AdaptationPromotionRecommendation]
    rejection_reasons: Tuple[str, ...] = ()
    certificate: Optional[QualificationCertificate] = None

    @property
    def qualified(self) -> bool:
        return self.recommendation is not None


def _relative_improvement(
    baseline: float,
    candidate: float,
    direction: MetricDirection,
) -> float:
    scale = abs(baseline)
    if scale == 0.0:
        if direction is MetricDirection.MAXIMIZE:
            return candidate - baseline
        return baseline - candidate
    if direction is MetricDirection.MAXIMIZE:
        return (candidate - baseline) / scale
    return (baseline - candidate) / scale


def _relative_regression(
    baseline: float,
    candidate: float,
    direction: MetricDirection,
) -> float:
    return max(0.0, -_relative_improvement(baseline, candidate, direction))


class HysteresisController:
    """Detects and prevents adaptation ping-pong thrashing (A <-> B <-> A <-> B)."""

    def __init__(self, min_residence_steps: int = 5) -> None:
        self.min_residence_steps = min_residence_steps
        self._history: list[tuple[str, str, int]] = []

    def record_transition(self, target_id: str, version: str, step: int) -> None:
        self._history.append((target_id, version, step))

    def check_oscillation(
        self,
        target_id: str,
        incumbent: str,
        candidate: str,
        current_step: int,
        relative_improvement: float,
        min_margin: float,
    ) -> bool:
        recent_for_target = [
            (v, step) for (t, v, step) in self._history if t == target_id
        ]
        if not recent_for_target:
            return False

        past_versions = [v for (v, _) in recent_for_target]
        if candidate in past_versions[-4:]:
            if relative_improvement <= min_margin:
                return True
        return False


class UnifiedAdaptationJudge:
    """Qualify heterogeneous adaptation candidates through one deterministic evidence contract."""

    def __init__(
        self,
        *,
        hysteresis_controller: Optional[HysteresisController] = None,
        unauthorized_targets: Sequence[str] = (),
    ) -> None:
        self.hysteresis = hysteresis_controller or HysteresisController()
        self.unauthorized_targets = frozenset(unauthorized_targets)

    def evaluate(
        self,
        proposal: AdaptationProposal,
        evidence: AdaptationTrialEvidence,
        state: WorldState,
        policy: AdaptationQualificationPolicy,
        *,
        current_step: int = 0,
        semantic_assessment: Optional[SemanticAssessment] = None,
        repair_succeeded: bool = False,
    ) -> AdaptationQualificationResult:
        reasons: list[str] = []

        if semantic_assessment is not None and semantic_assessment.semantic_class == SemanticClass.UNREPRESENTABLE:
            return AdaptationQualificationResult(
                recommendation=None,
                rejection_reasons=("SEMANTIC_DEFICIT_REQUIRES_EXTENSION",),
            )

        if repair_succeeded:
            return AdaptationQualificationResult(
                recommendation=None,
                rejection_reasons=("EXECUTION_FAILURE_REPAIRED_NOT_ADAPTED",),
            )

        if proposal.touches_frozen_compiler:
            reasons.append("FROZEN_COMPILER_MUTATION_REJECTED")

        if proposal.target_id in self.unauthorized_targets:
            reasons.append("UNAUTHORIZED_ADAPTATION_TARGET")

        if not proposal.rollback_ref:
            reasons.append("MISSING_ROLLBACK_SPECIFICATION")

        if proposal.pre_state_hash != state.state_hash:
            reasons.append("STALE_PRE_STATE")
        if evidence.proposal_id != proposal.proposal_id:
            reasons.append("TRIAL_PROPOSAL_MISMATCH")
        if proposal.candidate_artifact_hash == proposal.incumbent_artifact_hash:
            reasons.append("NO_ARTIFACT_CHANGE")

        if evidence.sample_count < policy.min_samples:
            reasons.append("INSUFFICIENT_SAMPLES")
        if evidence.invariant_breaches:
            reasons.append("INVARIANT_BREACH")
        if evidence.authority_breaches:
            reasons.append("AUTHORITY_BREACH")
        if evidence.determinism_breaches:
            reasons.append("DETERMINISM_BREACH")

        if evidence.tail_metric_regression > policy.max_allowable_tail_regression:
            reasons.append("CATASTROPHIC_TAIL_REGRESSION")

        objective = policy.objective
        improvement = 0.0
        if (
            objective.metric not in evidence.baseline_metrics
            or objective.metric not in evidence.candidate_metrics
        ):
            reasons.append("OBJECTIVE_METRIC_MISSING")
        else:
            improvement = _relative_improvement(
                evidence.baseline_metrics[objective.metric],
                evidence.candidate_metrics[objective.metric],
                objective.direction,
            )
            required_improvement = max(
                objective.min_relative_improvement,
                proposal.objective.min_relative_improvement if proposal.objective else 0.0,
            )
            if improvement < required_improvement:
                reasons.append("OBJECTIVE_IMPROVEMENT_INSUFFICIENT")

            min_margin = max(
                policy.min_hysteresis_margin,
                proposal.objective.min_margin if proposal.objective else 0.0,
            )
            if self.hysteresis.check_oscillation(
                proposal.target_id,
                proposal.incumbent_artifact_hash,
                proposal.candidate_artifact_hash,
                current_step,
                improvement,
                min_margin,
            ):
                reasons.append("HYSTERESIS_THRASHING_BLOCKED")

        metric_deltas: dict[str, float] = {}
        constraint_results: dict[str, str] = {}
        for k in evidence.candidate_metrics:
            if k in evidence.baseline_metrics:
                metric_deltas[k] = evidence.candidate_metrics[k] - evidence.baseline_metrics[k]

        for protected in policy.protected_metrics:
            if (
                protected.metric not in evidence.baseline_metrics
                or protected.metric not in evidence.candidate_metrics
            ):
                reasons.append(f"PROTECTED_METRIC_MISSING:{protected.metric}")
                continue
            regression = _relative_regression(
                evidence.baseline_metrics[protected.metric],
                evidence.candidate_metrics[protected.metric],
                protected.direction,
            )
            if regression > protected.max_relative_regression:
                reasons.append(f"PROTECTED_METRIC_REGRESSION:{protected.metric}")
                constraint_results[protected.metric] = f"REGRESSION:{regression:.4f}"
            else:
                constraint_results[protected.metric] = "PASS"

        for constraint in proposal.safety_constraints:
            cand_val = evidence.candidate_metrics.get(constraint.metric)
            if cand_val is None:
                reasons.append(f"SAFETY_CONSTRAINT_MISSING:{constraint.metric}")
                continue
            if constraint.direction == MetricDirection.MAXIMIZE:
                if cand_val < constraint.bound:
                    reasons.append(f"SAFETY_CONSTRAINT_VIOLATION:{constraint.metric}")
                    constraint_results[constraint.metric] = f"VIOLATION:{cand_val} < {constraint.bound}"
                else:
                    constraint_results[constraint.metric] = "PASS"
            else:
                if cand_val > constraint.bound:
                    reasons.append(f"SAFETY_CONSTRAINT_VIOLATION:{constraint.metric}")
                    constraint_results[constraint.metric] = f"VIOLATION:{cand_val} > {constraint.bound}"
                else:
                    constraint_results[constraint.metric] = "PASS"

        if reasons:
            return AdaptationQualificationResult(
                recommendation=None,
                rejection_reasons=tuple(dict.fromkeys(reasons)),
                certificate=None,
            )

        cert_payload = {
            "proposal_id": proposal.proposal_id,
            "target_kind": proposal.target_kind.value,
            "target_id": proposal.target_id,
            "baseline_version": proposal.baseline_version,
            "candidate_version": proposal.candidate_version,
            "sample_count": evidence.sample_count,
            "trial_hash": evidence.trial_hash,
            "state_hash": state.state_hash,
            "objective": objective.metric,
            "improvement": improvement,
            "metric_deltas": {k: float(v) for k, v in metric_deltas.items()},
            "rollback_proof": proposal.rollback_ref,
        }
        cert_hash = hashlib.sha256(canonical_json(cert_payload).encode("utf-8")).hexdigest()
        cert_id = hashlib.sha256(f"qual-cert:{proposal.proposal_id}:{cert_hash}".encode("utf-8")).hexdigest()

        certificate = QualificationCertificate(
            certificate_id=cert_id,
            proposal_id=proposal.proposal_id,
            target_kind=proposal.target_kind,
            target_id=proposal.target_id,
            baseline_version=proposal.baseline_version,
            candidate_version=proposal.candidate_version,
            metric_deltas=MappingProxyType(metric_deltas),
            sample_count=evidence.sample_count,
            confidence=min(1.0, evidence.sample_count / (evidence.sample_count + 5.0)),
            constraint_results=MappingProxyType(constraint_results),
            determinism_verified=(evidence.determinism_breaches == 0),
            rollback_proof=proposal.rollback_ref,
            experiment_spec=evidence.experiment_spec,
            holdout_id=evidence.holdout_id,
            parent_proposal_id=proposal.parent_proposal_id,
            certificate_hash=cert_hash,
        )

        promotion_id = hashlib.sha256(
            f"adaptation-promotion:{proposal.proposal_id}:{cert_hash}".encode("utf-8")
        ).hexdigest()

        recommendation = AdaptationPromotionRecommendation(
            promotion_id=promotion_id,
            proposal_id=proposal.proposal_id,
            target_kind=proposal.target_kind,
            target_id=proposal.target_id,
            candidate_artifact_hash=proposal.candidate_artifact_hash,
            rollback_artifact_hash=proposal.rollback_ref,
            qualification_hash=cert_hash,
            evidence_refs=evidence.evidence_refs,
            certificate=certificate,
        )

        return AdaptationQualificationResult(
            recommendation=recommendation,
            rejection_reasons=(),
            certificate=certificate,
        )


class PromotionAuthorityGate:
    """Ensures: Learning proposes change -> Evidence qualifies change -> UoW authorizes change."""

    FROZEN_TARGETS: Tuple[str, ...] = (
        "uow.autonomy.work_basis",
        "uow.autonomy.metacognition",
        "uow.autonomy.repair",
    )

    def evaluate_promotion(
        self,
        recommendation: AdaptationPromotionRecommendation,
        state: WorldState,
        *,
        authorized_authority_scopes: Sequence[str] = (),
    ) -> Tuple[bool, Tuple[str, ...]]:
        reasons: list[str] = []

        for frozen in self.FROZEN_TARGETS:
            if frozen in recommendation.target_id:
                reasons.append("PROMOTION_TO_FROZEN_SUBSYSTEM_FORBIDDEN")

        required_scope = f"adaptation.promote:{recommendation.target_kind.value.lower()}"
        if required_scope not in authorized_authority_scopes and "adaptation.admin" not in authorized_authority_scopes:
            reasons.append("UNAUTHORIZED_PROMOTION_SCOPE")

        if reasons:
            return False, tuple(reasons)
        return True, ()

    def commit_promotion(
        self,
        recommendation: AdaptationPromotionRecommendation,
        state: WorldState,
        *,
        authorized_authority_scopes: Sequence[str] = (),
    ) -> WorldState:
        allowed, reasons = self.evaluate_promotion(
            recommendation, state, authorized_authority_scopes=authorized_authority_scopes
        )
        if not allowed:
            raise PermissionError(f"Unauthorized promotion attempt: {reasons}")

        attr_key = f"adaptation:{recommendation.target_kind.value.lower()}:{recommendation.target_id}"
        return state.with_attribute(attr_key, recommendation.candidate_artifact_hash)


class MonitoringDisposition(str, Enum):
    KEEP = "KEEP"
    ROLLBACK = "ROLLBACK"


@dataclass(frozen=True)
class AdaptationMonitoringResult:
    disposition: MonitoringDisposition
    reason_codes: Tuple[str, ...]
    rollback_artifact_hash: Optional[str]


class AdaptationMonitor:
    def evaluate(
        self,
        promotion: AdaptationPromotionRecommendation,
        baseline_metrics: Mapping[str, float],
        observed_metrics: Mapping[str, float],
        policy: AdaptationQualificationPolicy,
        *,
        invariant_breaches: int = 0,
        authority_breaches: int = 0,
        determinism_breaches: int = 0,
    ) -> AdaptationMonitoringResult:
        reasons: list[str] = []
        if invariant_breaches:
            reasons.append("INVARIANT_BREACH")
        if authority_breaches:
            reasons.append("AUTHORITY_BREACH")
        if determinism_breaches:
            reasons.append("DETERMINISM_BREACH")

        for protected in policy.protected_metrics:
            if protected.metric not in baseline_metrics or protected.metric not in observed_metrics:
                reasons.append(f"PROTECTED_METRIC_MISSING:{protected.metric}")
                continue
            regression = _relative_regression(
                float(baseline_metrics[protected.metric]),
                float(observed_metrics[protected.metric]),
                protected.direction,
            )
            if regression > protected.max_relative_regression:
                reasons.append(f"PROTECTED_METRIC_REGRESSION:{protected.metric}")

        if reasons:
            return AdaptationMonitoringResult(
                disposition=MonitoringDisposition.ROLLBACK,
                reason_codes=tuple(dict.fromkeys(reasons)),
                rollback_artifact_hash=promotion.rollback_artifact_hash,
            )
        return AdaptationMonitoringResult(
            disposition=MonitoringDisposition.KEEP,
            reason_codes=("WITHIN_QUALIFIED_ENVELOPE",),
            rollback_artifact_hash=None,
        )


__all__ = [
    "AdaptationMonitor",
    "AdaptationMonitoringResult",
    "AdaptationObjective",
    "AdaptationPromotionRecommendation",
    "AdaptationProposal",
    "AdaptationQualificationPolicy",
    "AdaptationQualificationResult",
    "AdaptationTargetKind",
    "AdaptationTrialEvidence",
    "Constraint",
    "Criterion",
    "HysteresisController",
    "MetricConstraint",
    "MetricCriterion",
    "MetricDirection",
    "MetricRule",
    "MetricVector",
    "MonitoringDisposition",
    "PromotionAuthorityGate",
    "QualificationCertificate",
    "UnifiedAdaptationJudge",
]
