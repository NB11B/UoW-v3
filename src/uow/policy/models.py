"""Capability-Based Policy & Realization Graph Models.

Implements the fundamental architectural rule:
    Architecture understands capabilities;
    Policy understands realizations;
    Drivers understand devices.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import hashlib
import json
import time
from typing import TYPE_CHECKING, Any, Dict, FrozenSet, List, Mapping, Optional, Sequence, Tuple

if TYPE_CHECKING:
    from ..contracts import UoW


class ResourceCapability(str, Enum):
    """Generic capability classes decoupling policy from vendor hardware."""
    LOW_POWER_ACCELERATOR = "low_power_accelerator"          # Specialized low-wattage tensor/matrix accelerator (e.g. NPU)
    HIGH_THROUGHPUT_ACCELERATOR = "high_throughput_accelerator" # High-concurrency heavy tensor accelerator (e.g. discrete GPU)
    GENERAL_COMPUTE = "general_compute"                      # General-purpose host compute with vector extensions (e.g. host CPU)
    DETERMINISTIC_AUTHORITY = "deterministic_authority"      # Hardware security / ultra-low-power verification core (e.g. secure MCU)
    EDGE_MICROCONTROLLER = "edge_microcontroller"            # Real-time embedded microcontroller (e.g. MCU/SoC)


class DecisionSource(str, Enum):
    """Origin of a realization graph resolution decision."""
    QUALIFIED_POLICY = "QUALIFIED_POLICY"
    FALLBACK = "FALLBACK"
    DISCOVERY_CANDIDATE = "DISCOVERY_CANDIDATE"


class PolicyState(str, Enum):
    """Operational lifecycle state of a policy."""
    QUALIFIED = "QUALIFIED"
    ACTIVE = "ACTIVE"
    DRIFT_SUSPECTED = "DRIFT_SUSPECTED"
    INVALIDATED = "INVALIDATED"
    REQUALIFIED = "REQUALIFIED"
    SUPERSEDED = "SUPERSEDED"


class PolicyLifecycleEvent(str, Enum):
    """Auditable lifecycle transitions in a policy's lifetime."""
    PROMOTED = "PROMOTED"
    ACTIVATED = "ACTIVATED"
    DRIFT_SUSPECTED = "DRIFT_SUSPECTED"
    DRIFT_CLEARED = "DRIFT_CLEARED"
    INVALIDATED = "INVALIDATED"
    REQUALIFIED = "REQUALIFIED"
    SUPERSEDED = "SUPERSEDED"


class PolicyTransitionType(str, Enum):
    """Types of policy transitions governed by distributed authority (P4)."""
    PROMOTE = "PROMOTE"
    INVALIDATE = "INVALIDATE"
    REQUALIFY = "REQUALIFY"
    SUPERSEDE = "SUPERSEDE"


@dataclass(frozen=True)
class WorkRequirement:
    """Declared computational requirement (U) independent of physical realization.
    
    Can be projected directly from an existing UoW via WorkRequirement.from_uow(uow).
    """
    workload_class: str
    scale: int
    required_authority: str = "AUTHORIZED_CONTRACT_VERIFIED"
    max_latency_ms: Optional[float] = None
    canonical_meaning_digest: str = ""
    uow_id: str = ""

    def __post_init__(self) -> None:
        if not self.canonical_meaning_digest:
            # Deterministic semantic digest for outcome invariance
            raw = f"REQ_SEMANTICS:{self.workload_class}:{self.required_authority}"
            digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
            object.__setattr__(self, "canonical_meaning_digest", digest)

    @classmethod
    def from_uow(cls, uow: UoW, scale: Optional[int] = None) -> WorkRequirement:
        """Canonical projection from an authoritative UoW to a WorkRequirement."""
        workload_class = (getattr(uow, "workload_class", None) or f"{uow.H.source_category.value}_{uow.H.target_category.value}").lower()
        computed_scale = scale if scale is not None else max(1, len(uow.Gamma.routes))
        required_authority = f"AUTH_{uow.E.verifier}_{uow.M.phase.value}"

        raw_semantic = (
            f"UOW_SEMANTICS:{uow.H.matrix_cell.source.value}:{uow.H.matrix_cell.target.value}:"
            f"{len(uow.Gamma.routes)}:{uow.B.schema_version}:{workload_class}:{required_authority}"
        )
        meaning_digest = hashlib.sha256(raw_semantic.encode("utf-8")).hexdigest()[:24]

        return cls(
            workload_class=workload_class,
            scale=computed_scale,
            required_authority=required_authority,
            max_latency_ms=None,
            canonical_meaning_digest=meaning_digest,
            uow_id=uow.H.identity,
        )


@dataclass(frozen=True)
class WorldConditions:
    """Environmental operating conditions (S) characterizing the execution envelope."""
    snapshot_id: str
    timestamp: float
    available_capabilities: FrozenSet[ResourceCapability]
    power_budget_w: float = 120.0
    max_concurrency: int = 4
    congestion_factors: Mapping[ResourceCapability, float] = field(default_factory=dict)
    device_health: Mapping[str, bool] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        available_capabilities: Sequence[ResourceCapability] | FrozenSet[ResourceCapability],
        power_budget_w: float = 120.0,
        max_concurrency: int = 4,
        congestion_factors: Optional[Mapping[ResourceCapability, float]] = None,
        device_health: Optional[Mapping[str, bool]] = None,
        timestamp: Optional[float] = None,
        snapshot_id: Optional[str] = None,
    ) -> WorldConditions:
        """Create a versioned runtime snapshot of the world operating envelope."""
        caps = frozenset(available_capabilities)
        c_map = congestion_factors or {}
        h_map = device_health or {}
        ts = timestamp if timestamp is not None else time.time()

        if not snapshot_id:
            sorted_caps = sorted(c.value for c in caps)
            raw = f"WORLD:{sorted_caps}:{power_budget_w}:{max_concurrency}:{sorted(c_map.items())}:{ts:.4f}"
            s_id = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
        else:
            s_id = snapshot_id

        return cls(
            snapshot_id=s_id,
            timestamp=ts,
            available_capabilities=caps,
            power_budget_w=power_budget_w,
            max_concurrency=max_concurrency,
            congestion_factors=c_map,
            device_health=h_map,
        )


@dataclass(frozen=True)
class RealizationStage:
    """An individual stage in a multi-stage realization graph."""
    stage_id: str
    capability: ResourceCapability
    nominal_energy_wh: float
    nominal_latency_ms: float
    dependencies: Tuple[str, ...] = ()


@dataclass(frozen=True)
class RealizationGraph:
    """An ordered multi-stage computational graph G = (V, E, M) realizing a requirement."""
    graph_id: str
    stages: Tuple[RealizationStage, ...]
    inter_stage_transfer_energy_wh: float = 0.0
    inter_stage_transfer_latency_ms: float = 0.0
    meaning_digest: str = ""
    is_valid: bool = True

    @property
    def total_energy_wh(self) -> float:
        return sum(s.nominal_energy_wh for s in self.stages) + self.inter_stage_transfer_energy_wh

    @property
    def total_latency_ms(self) -> float:
        return sum(s.nominal_latency_ms for s in self.stages) + self.inter_stage_transfer_latency_ms

    def matches_meaning(self, expected_digest: str) -> bool:
        return self.is_valid and (self.meaning_digest == expected_digest)

    def compute_digest(self) -> str:
        """Compute deterministic digest of graph structure and capability bindings."""
        stages_repr = ";".join(
            f"{s.stage_id}:{s.capability.value}:{s.nominal_energy_wh:.8f}:{','.join(s.dependencies)}"
            for s in self.stages
        )
        raw = f"{self.graph_id}:{stages_repr}:{self.inter_stage_transfer_energy_wh:.8f}:{self.meaning_digest}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "stages": [
                {
                    "stage": s.stage_id,
                    "resource_class": s.capability.value,
                    "nominal_energy_wh": s.nominal_energy_wh,
                    "nominal_latency_ms": s.nominal_latency_ms,
                    "dependencies": list(s.dependencies),
                }
                for s in self.stages
            ],
            "inter_stage_transfer_energy_wh": self.inter_stage_transfer_energy_wh,
            "inter_stage_transfer_latency_ms": self.inter_stage_transfer_latency_ms,
            "meaning_digest": self.meaning_digest,
            "is_valid": self.is_valid,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RealizationGraph:
        stages = tuple(
            RealizationStage(
                stage_id=s["stage"],
                capability=ResourceCapability(s["resource_class"]),
                nominal_energy_wh=float(s.get("nominal_energy_wh", 0.0)),
                nominal_latency_ms=float(s.get("nominal_latency_ms", 0.0)),
                dependencies=tuple(s.get("dependencies", ())),
            )
            for s in data["stages"]
        )
        return cls(
            graph_id=data["graph_id"],
            stages=stages,
            inter_stage_transfer_energy_wh=float(data.get("inter_stage_transfer_energy_wh", 0.0)),
            inter_stage_transfer_latency_ms=float(data.get("inter_stage_transfer_latency_ms", 0.0)),
            meaning_digest=data.get("meaning_digest", ""),
            is_valid=bool(data.get("is_valid", True)),
        )


@dataclass(frozen=True)
class PolicyRegion:
    r"""Precondition domain R_pi \subseteq U \times S over which a policy is certified to apply."""
    workload_class: str
    min_scale: int
    max_scale: int
    min_power_budget_w: float = 0.0
    max_power_budget_w: float = float("inf")
    max_concurrency: int = 16
    required_capabilities: FrozenSet[ResourceCapability] = field(default_factory=frozenset)
    max_congestion: Mapping[ResourceCapability, float] = field(default_factory=dict)

    def contains(self, req: WorkRequirement, cond: WorldConditions) -> bool:
        """Evaluate if requirement U and world snapshot S lie inside region R_pi."""
        if req.workload_class != self.workload_class:
            return False
        if not (self.min_scale <= req.scale <= self.max_scale):
            return False
        if not (self.min_power_budget_w <= cond.power_budget_w <= self.max_power_budget_w):
            return False
        if cond.max_concurrency > self.max_concurrency:
            return False
        if not self.required_capabilities.issubset(cond.available_capabilities):
            return False
        for cap, max_cong in self.max_congestion.items():
            if cond.congestion_factors.get(cap, 1.0) > max_cong:
                return False
        return True


@dataclass(frozen=True)
class PolicyEvidence:
    """Auditable evidence certifying empirical qualification and break-even ROI."""
    evidence_digest: str
    observations_count: int
    expected_energy_wh: float
    energy_ci95_lower: float
    energy_ci95_upper: float
    expected_latency_ms: float
    break_even_uows: int
    correctness_breaches: int = 0


@dataclass(frozen=True)
class PolicyLifecycleRecord:
    """Auditable record capturing policy lifecycle transitions (P3/P4)."""
    lifecycle_id: str
    policy_id: str
    policy_version: int
    registry_version_before: int
    registry_version_after: int
    event_type: PolicyLifecycleEvent
    triggering_evidence_digest: str
    world_snapshot_id: str
    timestamp: float
    replacement_policy_id: Optional[str] = None
    authority_certificate_digest: Optional[str] = None
    details: Mapping[str, Any] = field(default_factory=dict)
    lifecycle_digest: str = ""

    def __post_init__(self) -> None:
        if not self.lifecycle_digest:
            details_str = json.dumps(self.details, sort_keys=True) if self.details else ""
            raw = (
                f"LIFECYCLE:{self.lifecycle_id}:{self.policy_id}:{self.policy_version}:"
                f"{self.registry_version_before}:{self.registry_version_after}:"
                f"{self.event_type.value}:{self.triggering_evidence_digest}:"
                f"{self.world_snapshot_id}:{self.replacement_policy_id}:{self.authority_certificate_digest}:{details_str}:{self.timestamp:.4f}"
            )
            d_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            object.__setattr__(self, "lifecycle_digest", d_hash)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lifecycle_id": self.lifecycle_id,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "registry_version_before": self.registry_version_before,
            "registry_version_after": self.registry_version_after,
            "event_type": self.event_type.value,
            "triggering_evidence_digest": self.triggering_evidence_digest,
            "world_snapshot_id": self.world_snapshot_id,
            "timestamp": self.timestamp,
            "replacement_policy_id": self.replacement_policy_id,
            "authority_certificate_digest": self.authority_certificate_digest,
            "details": dict(self.details),
            "lifecycle_digest": self.lifecycle_digest,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PolicyLifecycleRecord:
        return cls(
            lifecycle_id=data["lifecycle_id"],
            policy_id=data["policy_id"],
            policy_version=int(data["policy_version"]),
            registry_version_before=int(data["registry_version_before"]),
            registry_version_after=int(data["registry_version_after"]),
            event_type=PolicyLifecycleEvent(data["event_type"]),
            triggering_evidence_digest=data.get("triggering_evidence_digest", ""),
            world_snapshot_id=data.get("world_snapshot_id", ""),
            timestamp=float(data.get("timestamp", 0.0)),
            replacement_policy_id=data.get("replacement_policy_id"),
            authority_certificate_digest=data.get("authority_certificate_digest"),
            details=data.get("details", {}),
            lifecycle_digest=data.get("lifecycle_digest", ""),
        )


@dataclass(frozen=True)
class PolicyTransitionProposal:
    """Formal proposal to transition operational policy state (P4)."""
    proposal_id: str
    transition_type: PolicyTransitionType
    policy_id: str
    candidate_policy_version: int
    registry_version_expected: int
    previous_registry_digest: str
    candidate_policy_digest: str
    evidence_digest: str
    qualification_digest: str
    world_snapshot_id: str
    proposer_id: str
    timestamp: float
    details: Mapping[str, Any] = field(default_factory=dict)
    proposal_digest: str = ""

    def __post_init__(self) -> None:
        if not self.proposal_digest:
            details_str = json.dumps(self.details, sort_keys=True) if self.details else ""
            raw = (
                f"PROP:{self.proposal_id}:{self.transition_type.value}:{self.policy_id}:"
                f"{self.candidate_policy_version}:{self.registry_version_expected}:{self.previous_registry_digest}:"
                f"{self.candidate_policy_digest}:{self.evidence_digest}:{self.qualification_digest}:"
                f"{self.world_snapshot_id}:{self.proposer_id}:{details_str}:{self.timestamp:.4f}"
            )
            d_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            object.__setattr__(self, "proposal_digest", d_hash)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "transition_type": self.transition_type.value,
            "policy_id": self.policy_id,
            "candidate_policy_version": self.candidate_policy_version,
            "registry_version_expected": self.registry_version_expected,
            "previous_registry_digest": self.previous_registry_digest,
            "candidate_policy_digest": self.candidate_policy_digest,
            "evidence_digest": self.evidence_digest,
            "qualification_digest": self.qualification_digest,
            "world_snapshot_id": self.world_snapshot_id,
            "proposer_id": self.proposer_id,
            "timestamp": self.timestamp,
            "details": dict(self.details),
            "proposal_digest": self.proposal_digest,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PolicyTransitionProposal:
        return cls(
            proposal_id=data["proposal_id"],
            transition_type=PolicyTransitionType(data["transition_type"]),
            policy_id=data["policy_id"],
            candidate_policy_version=int(data["candidate_policy_version"]),
            registry_version_expected=int(data["registry_version_expected"]),
            previous_registry_digest=data["previous_registry_digest"],
            candidate_policy_digest=data["candidate_policy_digest"],
            evidence_digest=data["evidence_digest"],
            qualification_digest=data["qualification_digest"],
            world_snapshot_id=data["world_snapshot_id"],
            proposer_id=data["proposer_id"],
            timestamp=float(data["timestamp"]),
            details=data.get("details", {}),
            proposal_digest=data.get("proposal_digest", ""),
        )


@dataclass(frozen=True)
class AuthorityVote:
    """Independent vote by a physical authority node on a policy transition proposal."""
    authority_id: str             # e.g. "A1_HOST", "A2_ESP32S3", "A3_STM32U585"
    node_id: str                  # e.g. "node_host", "node_esp32", "node_stm32"
    proposal_id: str
    proposal_digest: str
    vote: bool                    # True for approve, False for reject
    pre_state_hash: str           # Expected registry digest
    post_state_hash: str          # Resulting registry digest upon transition
    reason: str
    timestamp: float
    signature_or_digest: str = ""

    def __post_init__(self) -> None:
        if not self.signature_or_digest:
            raw = (
                f"VOTE:{self.authority_id}:{self.node_id}:{self.proposal_id}:{self.proposal_digest}:"
                f"{self.vote}:{self.pre_state_hash}:{self.post_state_hash}:{self.reason}:{self.timestamp:.4f}"
            )
            sig = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            object.__setattr__(self, "signature_or_digest", sig)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "authority_id": self.authority_id,
            "node_id": self.node_id,
            "proposal_id": self.proposal_id,
            "proposal_digest": self.proposal_digest,
            "vote": self.vote,
            "pre_state_hash": self.pre_state_hash,
            "post_state_hash": self.post_state_hash,
            "reason": self.reason,
            "timestamp": self.timestamp,
            "signature_or_digest": self.signature_or_digest,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AuthorityVote:
        return cls(
            authority_id=data["authority_id"],
            node_id=data["node_id"],
            proposal_id=data["proposal_id"],
            proposal_digest=data["proposal_digest"],
            vote=bool(data["vote"]),
            pre_state_hash=data["pre_state_hash"],
            post_state_hash=data["post_state_hash"],
            reason=data["reason"],
            timestamp=float(data["timestamp"]),
            signature_or_digest=data.get("signature_or_digest", ""),
        )


@dataclass(frozen=True)
class DistributedPolicyCertificate:
    """Cryptographic certificate attesting multi-authority consensus on policy transition."""
    transition_id: str
    transition_type: PolicyTransitionType
    policy_id: str
    policy_version: int
    registry_version_before: int
    registry_version_after: int
    previous_registry_digest: str
    new_registry_digest: str
    proposal_digest: str
    qualification_digest: str
    evidence_digest: str
    authority_rule_id: str
    authority_votes: Tuple[AuthorityVote, ...]
    quorum_satisfied: bool
    commit_timestamp: float
    certificate_digest: str = ""

    def __post_init__(self) -> None:
        if not self.certificate_digest:
            votes_repr = ";".join(
                f"{v.authority_id}:{v.vote}:{v.signature_or_digest}"
                for v in sorted(self.authority_votes, key=lambda v: v.authority_id)
            )
            raw = (
                f"CERT:{self.transition_id}:{self.transition_type.value}:{self.policy_id}:{self.policy_version}:"
                f"{self.registry_version_before}:{self.registry_version_after}:"
                f"{self.previous_registry_digest}:{self.new_registry_digest}:"
                f"{self.proposal_digest}:{self.qualification_digest}:{self.evidence_digest}:"
                f"{self.authority_rule_id}:{self.quorum_satisfied}:{votes_repr}:{self.commit_timestamp:.4f}"
            )
            c_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            object.__setattr__(self, "certificate_digest", c_hash)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "transition_id": self.transition_id,
            "transition_type": self.transition_type.value,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "registry_version_before": self.registry_version_before,
            "registry_version_after": self.registry_version_after,
            "previous_registry_digest": self.previous_registry_digest,
            "new_registry_digest": self.new_registry_digest,
            "proposal_digest": self.proposal_digest,
            "qualification_digest": self.qualification_digest,
            "evidence_digest": self.evidence_digest,
            "authority_rule_id": self.authority_rule_id,
            "authority_votes": [v.to_dict() for v in self.authority_votes],
            "quorum_satisfied": self.quorum_satisfied,
            "commit_timestamp": self.commit_timestamp,
            "certificate_digest": self.certificate_digest,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DistributedPolicyCertificate:
        votes = tuple(AuthorityVote.from_dict(v) for v in data.get("authority_votes", []))
        return cls(
            transition_id=data["transition_id"],
            transition_type=PolicyTransitionType(data["transition_type"]),
            policy_id=data["policy_id"],
            policy_version=int(data["policy_version"]),
            registry_version_before=int(data["registry_version_before"]),
            registry_version_after=int(data["registry_version_after"]),
            previous_registry_digest=data["previous_registry_digest"],
            new_registry_digest=data["new_registry_digest"],
            proposal_digest=data["proposal_digest"],
            qualification_digest=data["qualification_digest"],
            evidence_digest=data["evidence_digest"],
            authority_rule_id=data["authority_rule_id"],
            authority_votes=votes,
            quorum_satisfied=bool(data["quorum_satisfied"]),
            commit_timestamp=float(data["commit_timestamp"]),
            certificate_digest=data.get("certificate_digest", ""),
        )


@dataclass(frozen=True)
class Policy:
    """Machine-readable, promoted orchestration policy artifact."""
    policy_id: str
    policy_version: int
    region: PolicyRegion
    realization_graph: RealizationGraph
    evidence: PolicyEvidence
    fallback_policy_id: str = "residual_discovery"
    is_active: bool = True
    state: PolicyState = PolicyState.ACTIVE
    latest_lifecycle_digest: str = ""

    def with_state(
        self,
        new_state: PolicyState,
        is_active: Optional[bool] = None,
        lifecycle_digest: str = "",
    ) -> Policy:
        """Create a new Policy instance with updated lifecycle state."""
        active = is_active if is_active is not None else (new_state in (PolicyState.ACTIVE, PolicyState.DRIFT_SUSPECTED))
        return Policy(
            policy_id=self.policy_id,
            policy_version=self.policy_version,
            region=self.region,
            realization_graph=self.realization_graph,
            evidence=self.evidence,
            fallback_policy_id=self.fallback_policy_id,
            is_active=active,
            state=new_state,
            latest_lifecycle_digest=lifecycle_digest or self.latest_lifecycle_digest,
        )

    def compute_digest(self) -> str:
        """Deterministic digest of policy structure, region, realization, and evidence."""
        raw = (
            f"POL:{self.policy_id}:{self.policy_version}:{self.is_active}:{self.state.value}:"
            f"{self.region.workload_class}:{self.region.min_scale}:{self.region.max_scale}:"
            f"{self.realization_graph.compute_digest()}:{self.evidence.evidence_digest}"
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "requirement": {
                "workload_class": self.region.workload_class,
                "scale": {"min": self.region.min_scale, "max": self.region.max_scale},
            },
            "conditions": {
                "min_power_budget_w": self.region.min_power_budget_w,
                "max_power_budget_w": self.region.max_power_budget_w if self.region.max_power_budget_w != float("inf") else None,
                "max_concurrency": self.region.max_concurrency,
                "required_capabilities": [c.value for c in self.region.required_capabilities],
                "max_congestion": {c.value: v for c, v in self.region.max_congestion.items()},
            },
            "realization": self.realization_graph.to_dict(),
            "qualification": {
                "evidence_digest": self.evidence.evidence_digest,
                "observations": self.evidence.observations_count,
                "expected_energy_wh": self.evidence.expected_energy_wh,
                "energy_ci95": [self.evidence.energy_ci95_lower, self.evidence.energy_ci95_upper],
                "expected_latency_ms": self.evidence.expected_latency_ms,
                "break_even_uows": self.evidence.break_even_uows,
                "correctness_breaches": self.evidence.correctness_breaches,
            },
            "fallback": {"policy": self.fallback_policy_id},
            "is_active": self.is_active,
            "state": self.state.value,
            "latest_lifecycle_digest": self.latest_lifecycle_digest,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Policy:
        req = data["requirement"]
        cond = data["conditions"]
        qual = data["qualification"]

        max_p = cond.get("max_power_budget_w")
        region = PolicyRegion(
            workload_class=req["workload_class"],
            min_scale=int(req["scale"]["min"]),
            max_scale=int(req["scale"]["max"]),
            min_power_budget_w=float(cond.get("min_power_budget_w", 0.0)),
            max_power_budget_w=float(max_p) if max_p is not None else float("inf"),
            max_concurrency=int(cond.get("max_concurrency", 16)),
            required_capabilities=frozenset(ResourceCapability(c) for c in cond.get("required_capabilities", [])),
            max_congestion={ResourceCapability(c): float(v) for c, v in cond.get("max_congestion", {}).items()},
        )
        graph = RealizationGraph.from_dict(data["realization"])
        ci = qual.get("energy_ci95", [qual["expected_energy_wh"], qual["expected_energy_wh"]])
        evidence = PolicyEvidence(
            evidence_digest=qual["evidence_digest"],
            observations_count=int(qual["observations"]),
            expected_energy_wh=float(qual["expected_energy_wh"]),
            energy_ci95_lower=float(ci[0]),
            energy_ci95_upper=float(ci[1]),
            expected_latency_ms=float(qual.get("expected_latency_ms", 0.0)),
            break_even_uows=int(qual.get("break_even_uows", 0)),
            correctness_breaches=int(qual.get("correctness_breaches", 0)),
        )
        state_str = data.get("state", "ACTIVE")
        state = PolicyState(state_str) if state_str in PolicyState.__members__ else PolicyState.ACTIVE
        return cls(
            policy_id=data["policy_id"],
            policy_version=int(data["policy_version"]),
            region=region,
            realization_graph=graph,
            evidence=evidence,
            fallback_policy_id=data.get("fallback", {}).get("policy", "residual_discovery"),
            is_active=bool(data.get("is_active", True)),
            state=state,
            latest_lifecycle_digest=data.get("latest_lifecycle_digest", ""),
        )


@dataclass(frozen=True)
class PolicyDecisionRecord:
    """Forensic and chain-of-custody record separating selection rationale from execution outcome."""
    decision_id: str
    uow_id: str
    work_requirement_digest: str
    world_snapshot_id: str
    registry_version: int
    resolution_status: str              # "QUALIFIED_MATCH", "NO_QUALIFIED_POLICY", "DRIFT_FALLBACK"
    matched_policy_ids: Tuple[str, ...]
    selected_policy_id: Optional[str]
    selected_policy_version: Optional[int]
    realization_graph_digest: str
    decision_source: DecisionSource
    objective_values: Mapping[str, float]
    constraint_checks: Mapping[str, bool]
    timestamp: float
    lifecycle_digest: Optional[str] = None
    decision_digest: str = ""

    def __post_init__(self) -> None:
        if not self.decision_digest:
            raw = (
                f"{self.decision_id}:{self.uow_id}:{self.work_requirement_digest}:"
                f"{self.world_snapshot_id}:{self.registry_version}:{self.resolution_status}:"
                f"{sorted(self.matched_policy_ids)}:{self.selected_policy_id}:{self.selected_policy_version}:"
                f"{self.realization_graph_digest}:{self.decision_source.value}:{self.lifecycle_digest}:{self.timestamp:.4f}"
            )
            d_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            object.__setattr__(self, "decision_digest", d_hash)


@dataclass(frozen=True)
class ExecutionCertificate:
    """Cryptographic certificate attesting execution compliance and telemetry."""
    certificate_id: str
    uow_id: str
    graph_id: str
    state_hash: str
    is_certified: bool
    measured_energy_wh: float
    measured_latency_ms: float
    authority_compliant: bool
    policy_registry_version: int = 1
    policy_id: Optional[str] = None
    policy_version: Optional[int] = None
    world_snapshot_id: str = ""
    realization_graph_digest: str = ""
    decision_id: str = ""
    decision_digest: str = ""
    correctness_breaches: int = 0
    composite_hash: str = ""

    def __post_init__(self) -> None:
        if not self.composite_hash:
            # Composite certification hash C = H(U, S, \Pi, G, R, E) chained with DecisionRecord
            raw = (
                f"{self.uow_id}:{self.world_snapshot_id}:{self.policy_id}:{self.policy_version}:"
                f"{self.policy_registry_version}:{self.realization_graph_digest}:{self.state_hash}:"
                f"{self.measured_energy_wh:.8f}:{self.is_certified}:{self.correctness_breaches}:"
                f"{self.decision_digest}"
            )
            c_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            object.__setattr__(self, "composite_hash", c_hash)


class TransactionExecutionStatus(str, Enum):
    """Lifecycle classification of an in-flight workload transaction during recovery (P5)."""
    NOT_STARTED = "NOT_STARTED"
    IN_FLIGHT = "IN_FLIGHT"
    EXECUTED_UNCOMMITTED = "EXECUTED_UNCOMMITTED"
    COMMITTED = "COMMITTED"
    ABORTED = "ABORTED"


@dataclass(frozen=True)
class InFlightTransaction:
    """Operational record of a workload execution transaction tracked across restarts."""
    uow_id: str
    requirement_digest: str
    world_snapshot_id: str
    registry_version: int
    selected_policy_id: Optional[str]
    graph_id: str
    status: TransactionExecutionStatus
    executed_stages: Tuple[str, ...] = ()
    external_effect_applied: bool = False
    execution_certificate_id: Optional[str] = None
    timestamp: float = 0.0

    def with_status(
        self,
        new_status: TransactionExecutionStatus,
        executed_stages: Optional[Tuple[str, ...]] = None,
        external_effect_applied: Optional[bool] = None,
        execution_certificate_id: Optional[str] = None,
    ) -> InFlightTransaction:
        return InFlightTransaction(
            uow_id=self.uow_id,
            requirement_digest=self.requirement_digest,
            world_snapshot_id=self.world_snapshot_id,
            registry_version=self.registry_version,
            selected_policy_id=self.selected_policy_id,
            graph_id=self.graph_id,
            status=new_status,
            executed_stages=executed_stages if executed_stages is not None else self.executed_stages,
            external_effect_applied=external_effect_applied if external_effect_applied is not None else self.external_effect_applied,
            execution_certificate_id=execution_certificate_id if execution_certificate_id is not None else self.execution_certificate_id,
            timestamp=self.timestamp,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uow_id": self.uow_id,
            "requirement_digest": self.requirement_digest,
            "world_snapshot_id": self.world_snapshot_id,
            "registry_version": self.registry_version,
            "selected_policy_id": self.selected_policy_id,
            "graph_id": self.graph_id,
            "status": self.status.value,
            "executed_stages": list(self.executed_stages),
            "external_effect_applied": self.external_effect_applied,
            "execution_certificate_id": self.execution_certificate_id,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> InFlightTransaction:
        return cls(
            uow_id=data["uow_id"],
            requirement_digest=data["requirement_digest"],
            world_snapshot_id=data["world_snapshot_id"],
            registry_version=int(data["registry_version"]),
            selected_policy_id=data.get("selected_policy_id"),
            graph_id=data["graph_id"],
            status=TransactionExecutionStatus(data["status"]),
            executed_stages=tuple(data.get("executed_stages", ())),
            external_effect_applied=bool(data.get("external_effect_applied", False)),
            execution_certificate_id=data.get("execution_certificate_id"),
            timestamp=float(data.get("timestamp", 0.0)),
        )


class RecoveryResultStatus(str, Enum):
    """Outcome status of an authority or node recovery operation (P5)."""
    CLEAN_RECOVERY = "CLEAN_RECOVERY"
    RECONCILED_FROM_PEERS = "RECONCILED_FROM_PEERS"
    FAIL_CLOSED_CORRUPTION = "FAIL_CLOSED_CORRUPTION"
    FAIL_CLOSED_SPLIT_BRAIN = "FAIL_CLOSED_SPLIT_BRAIN"


@dataclass(frozen=True)
class RecoveryRecord:
    """Cryptographic provenance record documenting crash recovery and state reconciliation (P5).
    
    Establishes the audit chain link:
        authority history -> recovery history -> decision -> execution
    """
    recovery_id: str
    node_id: str
    startup_time: float
    local_registry_version: int
    local_registry_digest: str
    committed_registry_version: int
    committed_registry_digest: str
    replayed_certificates: Tuple[str, ...]
    rejected_certificates: Tuple[str, ...]
    inflight_transactions_found: int
    transactions_resumed: int
    transactions_aborted: int
    transactions_already_committed: int
    duplicate_effects_prevented: int
    recovery_result: RecoveryResultStatus
    details: Mapping[str, Any] = field(default_factory=dict)
    recovery_digest: str = ""

    def __post_init__(self) -> None:
        if not self.recovery_digest:
            replayed_str = ",".join(self.replayed_certificates)
            rejected_str = ",".join(self.rejected_certificates)
            details_str = json.dumps(self.details, sort_keys=True) if self.details else ""
            raw = (
                f"RECOVERY:{self.recovery_id}:{self.node_id}:{self.startup_time:.4f}:"
                f"{self.local_registry_version}:{self.local_registry_digest}:"
                f"{self.committed_registry_version}:{self.committed_registry_digest}:"
                f"{replayed_str}:{rejected_str}:{self.inflight_transactions_found}:"
                f"{self.transactions_resumed}:{self.transactions_aborted}:"
                f"{self.transactions_already_committed}:{self.duplicate_effects_prevented}:"
                f"{self.recovery_result.value}:{details_str}"
            )
            r_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            object.__setattr__(self, "recovery_digest", r_hash)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recovery_id": self.recovery_id,
            "node_id": self.node_id,
            "startup_time": self.startup_time,
            "local_registry_version": self.local_registry_version,
            "local_registry_digest": self.local_registry_digest,
            "committed_registry_version": self.committed_registry_version,
            "committed_registry_digest": self.committed_registry_digest,
            "replayed_certificates": list(self.replayed_certificates),
            "rejected_certificates": list(self.rejected_certificates),
            "inflight_transactions_found": self.inflight_transactions_found,
            "transactions_resumed": self.transactions_resumed,
            "transactions_aborted": self.transactions_aborted,
            "transactions_already_committed": self.transactions_already_committed,
            "duplicate_effects_prevented": self.duplicate_effects_prevented,
            "recovery_result": self.recovery_result.value,
            "details": dict(self.details),
            "recovery_digest": self.recovery_digest,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RecoveryRecord:
        return cls(
            recovery_id=data["recovery_id"],
            node_id=data["node_id"],
            startup_time=float(data["startup_time"]),
            local_registry_version=int(data["local_registry_version"]),
            local_registry_digest=data["local_registry_digest"],
            committed_registry_version=int(data["committed_registry_version"]),
            committed_registry_digest=data["committed_registry_digest"],
            replayed_certificates=tuple(data.get("replayed_certificates", ())),
            rejected_certificates=tuple(data.get("rejected_certificates", ())),
            inflight_transactions_found=int(data.get("inflight_transactions_found", 0)),
            transactions_resumed=int(data.get("transactions_resumed", 0)),
            transactions_aborted=int(data.get("transactions_aborted", 0)),
            transactions_already_committed=int(data.get("transactions_already_committed", 0)),
            duplicate_effects_prevented=int(data.get("duplicate_effects_prevented", 0)),
            recovery_result=RecoveryResultStatus(data["recovery_result"]),
            details=data.get("details", {}),
            recovery_digest=data.get("recovery_digest", ""),
        )

