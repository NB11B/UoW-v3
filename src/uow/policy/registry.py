r"""Transactionally Versioned Policy Registry.

Stores, versions, and retrieves promoted policies certifying valid operational regions.
Guarantees:
- Monotonic transactional versioning (\Pi_k -> \Pi_{k+1}).
- Deterministic conflict resolution: Resolve(U, S, \Pi) = G identically every time.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .models import (
    DistributedPolicyCertificate,
    Policy,
    PolicyLifecycleEvent,
    PolicyLifecycleRecord,
    PolicyRegion,
    PolicyState,
    PolicyTransitionType,
    ResourceCapability,
    WorkRequirement,
    WorldConditions,
)


class PolicyRegistry:
    """Thread-safe, auditable, transactionally versioned repository of promoted policies."""

    def __init__(self) -> None:
        self._policies: Dict[str, Policy] = {}  # policy_id -> latest Policy
        self._policy_versions: Dict[Tuple[str, int], Policy] = {}  # (policy_id, version) -> Policy state
        self._lifecycle_records: List[PolicyLifecycleRecord] = []
        self._invalidation_log: List[Dict[str, Any]] = []
        self._version: int = 1

    @property
    def version(self) -> int:
        r"""Monotonic version \Pi_k of the policy registry."""
        return self._version

    @property
    def total_policies(self) -> int:
        return len(self._policies)

    @property
    def active_policies_count(self) -> int:
        return sum(1 for p in self._policies.values() if p.is_active)

    def _record_lifecycle_event(
        self,
        policy_id: str,
        policy_version: int,
        v_before: int,
        v_after: int,
        event_type: PolicyLifecycleEvent,
        triggering_evidence_digest: str,
        world_snapshot_id: str = "",
        replacement_policy_id: Optional[str] = None,
        authority_certificate_digest: Optional[str] = None,
        details: Optional[Mapping[str, Any]] = None,
    ) -> PolicyLifecycleRecord:
        import time
        rec_id = f"lc_{policy_id}_v{policy_version}_{event_type.value}_{len(self._lifecycle_records)+1}"
        record = PolicyLifecycleRecord(
            lifecycle_id=rec_id,
            policy_id=policy_id,
            policy_version=policy_version,
            registry_version_before=v_before,
            registry_version_after=v_after,
            event_type=event_type,
            triggering_evidence_digest=triggering_evidence_digest,
            world_snapshot_id=world_snapshot_id,
            timestamp=time.time(),
            replacement_policy_id=replacement_policy_id,
            authority_certificate_digest=authority_certificate_digest,
            details=dict(details or {}),
        )
        self._lifecycle_records.append(record)
        return record

    def register_policy(
        self,
        policy: Policy,
        world_snapshot_id: str = "",
        authority_certificate_digest: Optional[str] = None,
    ) -> int:
        r"""Register a newly promoted policy. Fails if evidence shows correctness breaches.
        
        Atomically increments the registry version (\Pi_k -> \Pi_{k+1}).
        Preserves prior policy versions in operational history.
        """
        if policy.evidence.correctness_breaches > 0:
            raise ValueError(
                f"Cannot register policy {policy.policy_id}: evidence contains "
                f"{policy.evidence.correctness_breaches} correctness breaches."
            )

        v_before = self._version
        v_after = self._version + 1
        pol_id = policy.policy_id

        # If previous version existed, archive it as SUPERSEDED
        old_policy = self._policies.get(pol_id)
        if old_policy is not None:
            superseded = old_policy.with_state(
                PolicyState.SUPERSEDED,
                is_active=False,
            )
            self._policy_versions[(old_policy.policy_id, old_policy.policy_version)] = superseded

            self._record_lifecycle_event(
                policy_id=old_policy.policy_id,
                policy_version=old_policy.policy_version,
                v_before=v_before,
                v_after=v_after,
                event_type=PolicyLifecycleEvent.SUPERSEDED,
                triggering_evidence_digest=policy.evidence.evidence_digest,
                world_snapshot_id=world_snapshot_id,
                replacement_policy_id=f"{policy.policy_id}:v{policy.policy_version}",
                authority_certificate_digest=authority_certificate_digest,
                details={"reason": "New policy version promoted"},
            )

        # Record PROMOTED lifecycle event
        lc_rec = self._record_lifecycle_event(
            policy_id=policy.policy_id,
            policy_version=policy.policy_version,
            v_before=v_before,
            v_after=v_after,
            event_type=PolicyLifecycleEvent.PROMOTED,
            triggering_evidence_digest=policy.evidence.evidence_digest,
            world_snapshot_id=world_snapshot_id,
            authority_certificate_digest=authority_certificate_digest,
            details={"expected_energy_wh": policy.evidence.expected_energy_wh},
        )

        promoted = policy.with_state(
            PolicyState.ACTIVE,
            is_active=True,
            lifecycle_digest=lc_rec.lifecycle_digest,
        )
        self._policies[pol_id] = promoted
        self._policy_versions[(pol_id, policy.policy_version)] = promoted

        self._version = v_after
        return self._version

    def lookup(
        self,
        requirement: WorkRequirement,
        conditions: WorldConditions,
    ) -> Optional[Policy]:
        r"""Deterministic resolution: eligibility -> specificity -> qualification strength -> objective -> ID.
        
        Guarantees that Resolve(U, S, \Pi) returns the exact same policy every time.
        """
        # Step 1: Eligibility filter
        matching = [
            p for p in self._policies.values()
            if p.is_active and p.region.contains(requirement, conditions)
        ]

        if not matching:
            return None

        # Step 2: Deterministic multi-tier ranking
        # Python's sort is stable; we compute an explicit comparable tuple:
        def ranking_key(p: Policy) -> Tuple[int, int, int, float, float, float, str, int]:
            # Tier 1: Specificity (narrower scale range is more specific, more capabilities required)
            scale_span = p.region.max_scale - p.region.min_scale
            cap_specificity = len(p.region.required_capabilities)

            # Tier 2: Qualification Strength (more observations, tighter 95% confidence interval)
            obs = p.evidence.observations_count
            ci_width = p.evidence.energy_ci95_upper - p.evidence.energy_ci95_lower

            # Tier 3: Objective (lower expected energy, lower latency)
            exp_e = p.evidence.expected_energy_wh
            exp_lat = p.evidence.expected_latency_ms

            # Tier 4: Stable Lexicographic Tie-Breaker
            pol_id = p.policy_id
            ver = p.policy_version

            # We want:
            # - smaller scale span (min) -> scale_span
            # - larger cap specificity (max) -> -cap_specificity
            # - larger observations (max) -> -obs
            # - smaller ci_width (min) -> ci_width
            # - smaller expected energy (min) -> exp_e
            # - smaller expected latency (min) -> exp_lat
            # - smaller policy id lexicographically (min) -> pol_id
            # - larger version (max) -> -ver
            return (
                scale_span,
                -cap_specificity,
                -obs,
                ci_width,
                exp_e,
                exp_lat,
                pol_id,
                -ver,
            )

        matching.sort(key=ranking_key)
        return matching[0]

    def invalidate(
        self,
        policy_id: str,
        reason: str,
        world_snapshot_id: str = "",
        triggering_evidence_digest: str = "",
        authority_certificate_digest: Optional[str] = None,
        details: Optional[Mapping[str, Any]] = None,
    ) -> bool:
        r"""Invalidate a policy upon detected operational drift or contract violation.
        
        Atomically increments registry version (\Pi_k -> \Pi_{k+1}).
        Preserves auditable historical evidence.
        """
        if policy_id not in self._policies:
            return False

        old_p = self._policies[policy_id]
        if not old_p.is_active:
            return False

        v_before = self._version
        v_after = self._version + 1

        details_dict = dict(details or {})
        details_dict["reason"] = reason

        lc_rec = self._record_lifecycle_event(
            policy_id=old_p.policy_id,
            policy_version=old_p.policy_version,
            v_before=v_before,
            v_after=v_after,
            event_type=PolicyLifecycleEvent.INVALIDATED,
            triggering_evidence_digest=triggering_evidence_digest or old_p.evidence.evidence_digest,
            world_snapshot_id=world_snapshot_id,
            authority_certificate_digest=authority_certificate_digest,
            details=details_dict,
        )

        invalidated = old_p.with_state(
            PolicyState.INVALIDATED,
            is_active=False,
            lifecycle_digest=lc_rec.lifecycle_digest,
        )
        self._policies[policy_id] = invalidated
        self._policy_versions[(policy_id, old_p.policy_version)] = invalidated

        self._invalidation_log.append({
            "policy_id": policy_id,
            "version": old_p.policy_version,
            "reason": reason,
            "lifecycle_digest": lc_rec.lifecycle_digest,
        })
        self._version = v_after
        return True

    def mark_drift_suspected(
        self,
        policy_id: str,
        reason: str,
        world_snapshot_id: str = "",
        triggering_evidence_digest: str = "",
        details: Optional[Mapping[str, Any]] = None,
    ) -> bool:
        """Mark policy as DRIFT_SUSPECTED without full invalidation (hysteresis)."""
        if policy_id not in self._policies:
            return False
        old_p = self._policies[policy_id]
        if old_p.state != PolicyState.ACTIVE:
            return False

        details_dict = dict(details or {})
        details_dict["reason"] = reason

        lc_rec = self._record_lifecycle_event(
            policy_id=old_p.policy_id,
            policy_version=old_p.policy_version,
            v_before=self._version,
            v_after=self._version,
            event_type=PolicyLifecycleEvent.DRIFT_SUSPECTED,
            triggering_evidence_digest=triggering_evidence_digest or old_p.evidence.evidence_digest,
            world_snapshot_id=world_snapshot_id,
            details=details_dict,
        )

        suspected = old_p.with_state(
            PolicyState.DRIFT_SUSPECTED,
            is_active=True,
            lifecycle_digest=lc_rec.lifecycle_digest,
        )
        self._policies[policy_id] = suspected
        self._policy_versions[(policy_id, old_p.policy_version)] = suspected
        return True

    def clear_drift_suspicion(
        self,
        policy_id: str,
        world_snapshot_id: str = "",
        details: Optional[Mapping[str, Any]] = None,
    ) -> bool:
        """Return policy from DRIFT_SUSPECTED back to ACTIVE when observations return to envelope."""
        if policy_id not in self._policies:
            return False
        old_p = self._policies[policy_id]
        if old_p.state != PolicyState.DRIFT_SUSPECTED:
            return False

        lc_rec = self._record_lifecycle_event(
            policy_id=old_p.policy_id,
            policy_version=old_p.policy_version,
            v_before=self._version,
            v_after=self._version,
            event_type=PolicyLifecycleEvent.DRIFT_CLEARED,
            triggering_evidence_digest=old_p.evidence.evidence_digest,
            world_snapshot_id=world_snapshot_id,
            details=details or {"reason": "Observations returned to certified envelope"},
        )

        active = old_p.with_state(
            PolicyState.ACTIVE,
            is_active=True,
            lifecycle_digest=lc_rec.lifecycle_digest,
        )
        self._policies[policy_id] = active
        self._policy_versions[(policy_id, old_p.policy_version)] = active
        return True

    def reactivate_policy(
        self,
        policy_id: str,
        policy_version: Optional[int] = None,
        reason: str = "Requalified for restored operating regime",
        world_snapshot_id: str = "",
        authority_certificate_digest: Optional[str] = None,
    ) -> bool:
        """Reactivate an invalidated policy upon verified return of operating conditions."""
        target_policy = self.get_policy(policy_id, policy_version)
        if target_policy is None or target_policy.is_active:
            return False

        v_before = self._version
        v_after = self._version + 1

        lc_rec = self._record_lifecycle_event(
            policy_id=target_policy.policy_id,
            policy_version=target_policy.policy_version,
            v_before=v_before,
            v_after=v_after,
            event_type=PolicyLifecycleEvent.REQUALIFIED,
            triggering_evidence_digest=target_policy.evidence.evidence_digest,
            world_snapshot_id=world_snapshot_id,
            authority_certificate_digest=authority_certificate_digest,
            details={"reason": reason},
        )

        reactivated = target_policy.with_state(
            PolicyState.ACTIVE,
            is_active=True,
            lifecycle_digest=lc_rec.lifecycle_digest,
        )
        self._policies[policy_id] = reactivated
        self._policy_versions[(policy_id, target_policy.policy_version)] = reactivated
        self._version = v_after
        return True

    def compute_digest(self) -> str:
        """Compute deterministic cryptographic digest of current policy registry state."""
        import hashlib
        active_repr = ";".join(
            f"{p.policy_id}:{p.policy_version}:{p.compute_digest()}"
            for p in sorted(self._policies.values(), key=lambda p: p.policy_id)
        )
        raw = f"REGISTRY:{self._version}:{active_repr}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

    def predict_transition_digest(
        self,
        transition_type: PolicyTransitionType,
        policy_id: str,
        policy: Optional[Policy] = None,
    ) -> str:
        """Deterministically predict post-transition registry digest prior to commit."""
        import hashlib
        sim_policies = dict(self._policies)
        next_version = self._version + 1

        if transition_type == PolicyTransitionType.PROMOTE:
            if policy is None:
                raise ValueError("Promote requires candidate policy")
            active_policy = policy.with_state(PolicyState.ACTIVE, is_active=True)
            sim_policies[policy_id] = active_policy
        elif transition_type == PolicyTransitionType.INVALIDATE:
            if policy_id in sim_policies:
                sim_policies[policy_id] = sim_policies[policy_id].with_state(PolicyState.INVALIDATED, is_active=False)
        elif transition_type == PolicyTransitionType.REQUALIFY:
            if policy is not None:
                sim_policies[policy_id] = policy.with_state(PolicyState.ACTIVE, is_active=True)
            elif policy_id in sim_policies:
                sim_policies[policy_id] = sim_policies[policy_id].with_state(PolicyState.ACTIVE, is_active=True)

        active_repr = ";".join(
            f"{p.policy_id}:{p.policy_version}:{p.compute_digest()}"
            for p in sorted(sim_policies.values(), key=lambda p: p.policy_id)
        )
        raw = f"REGISTRY:{next_version}:{active_repr}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

    def register_certified_transition(
        self,
        certificate: DistributedPolicyCertificate,
        policy: Optional[Policy] = None,
    ) -> int:
        """Apply a multi-authority certified policy transition (P4)."""
        if not certificate.quorum_satisfied:
            raise ValueError(f"Cannot commit uncertified transition {certificate.transition_id}: quorum not satisfied")

        if certificate.registry_version_before != self._version:
            raise ValueError(
                f"Registry version mismatch: certificate expects version {certificate.registry_version_before}, "
                f"but local registry is at version {self._version}"
            )

        prev_digest = self.compute_digest()
        if certificate.previous_registry_digest != prev_digest:
            raise ValueError(
                f"Registry digest divergence: certificate expects previous digest {certificate.previous_registry_digest}, "
                f"but local registry digest is {prev_digest}"
            )

        if certificate.transition_type == PolicyTransitionType.PROMOTE:
            if policy is None:
                raise ValueError("Promote transition requires policy instance")
            self.register_policy(
                policy=policy,
                world_snapshot_id="",
                authority_certificate_digest=certificate.certificate_digest,
            )
        elif certificate.transition_type == PolicyTransitionType.INVALIDATE:
            self.invalidate(
                policy_id=certificate.policy_id,
                reason=f"Distributed authority consensus: rule {certificate.authority_rule_id}",
                authority_certificate_digest=certificate.certificate_digest,
            )
        elif certificate.transition_type == PolicyTransitionType.REQUALIFY:
            self.reactivate_policy(
                policy_id=certificate.policy_id,
                policy_version=certificate.policy_version,
                reason=f"Distributed authority consensus: rule {certificate.authority_rule_id}",
                authority_certificate_digest=certificate.certificate_digest,
            )
        else:
            raise ValueError(f"Unknown transition type: {certificate.transition_type}")

        return self._version

    def snapshot(self) -> Tuple[int, Dict[str, Policy]]:
        """Return an immutable snapshot of current registry state (version, active_policies)."""
        return self._version, dict(self._policies)

    def get_policy(self, policy_id: str, version: Optional[int] = None) -> Optional[Policy]:
        """Retrieve policy. If version is specified, returns historical version, else latest."""
        if version is None:
            return self._policies.get(policy_id)
        return self._policy_versions.get((policy_id, version))

    def get_policy_history(self, policy_id: str) -> List[Policy]:
        """Return list of all versions (historical and current) for policy_id."""
        versions = sorted([ver for (pid, ver) in self._policy_versions if pid == policy_id])
        return [self._policy_versions[(policy_id, v)] for v in versions]

    @property
    def lifecycle_history(self) -> List[PolicyLifecycleRecord]:
        """Return all auditable lifecycle event records in chronological order."""
        return list(self._lifecycle_records)

    def get_lifecycle_records(self, policy_id: Optional[str] = None) -> List[PolicyLifecycleRecord]:
        """Return auditable lifecycle event records."""
        if policy_id is None:
            return list(self._lifecycle_records)
        return [r for r in self._lifecycle_records if r.policy_id == policy_id]

    def list_active_policies(self) -> List[Policy]:
        return [p for p in self._policies.values() if p.is_active]

    def export_state(self) -> Dict[str, Any]:
        """Full lossless export of registry operational, versioning, and auditable state."""
        return {
            "version": self._version,
            "policies": {pid: p.to_dict() for pid, p in self._policies.items()},
            "policy_versions": [
                {"policy_id": pid, "version": ver, "policy": p.to_dict()}
                for (pid, ver), p in self._policy_versions.items()
            ],
            "lifecycle_records": [r.to_dict() for r in self._lifecycle_records],
            "invalidation_log": list(self._invalidation_log),
            "registry_digest": self.compute_digest(),
        }

    @classmethod
    def from_state(cls, data: Dict[str, Any]) -> PolicyRegistry:
        """Construct PolicyRegistry from exported state with cryptographic verification."""
        registry = cls()
        registry._version = int(data["version"])
        registry._policies = {
            pid: Policy.from_dict(p_data)
            for pid, p_data in data.get("policies", {}).items()
        }
        registry._policy_versions = {
            (item["policy_id"], int(item["version"])): Policy.from_dict(item["policy"])
            for item in data.get("policy_versions", [])
        }
        registry._lifecycle_records = [
            PolicyLifecycleRecord.from_dict(r)
            for r in data.get("lifecycle_records", [])
        ]
        registry._invalidation_log = list(data.get("invalidation_log", []))
        return registry

    def export_json(self) -> str:
        return json.dumps(self.export_state(), indent=2)

    def import_json(self, json_str: str) -> int:
        data = json.loads(json_str)
        if "policy_versions" in data and "policies" in data:
            restored = self.from_state(data)
            self._version = restored._version
            self._policies = restored._policies
            self._policy_versions = restored._policy_versions
            self._lifecycle_records = restored._lifecycle_records
            self._invalidation_log = restored._invalidation_log
            return len(self._policies)

        count = 0
        policies = data.get("policies", data) if isinstance(data, dict) else data
        for entry in policies:
            self.register_policy(Policy.from_dict(entry))
            count += 1
        return count
