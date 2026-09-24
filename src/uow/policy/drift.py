"""Continuous Multidimensional Drift Monitor (P3).

Monitors live execution telemetry against certified policy evidence across 5 dimensions:
    ΔE (Energy drift)
    ΔL (Latency drift)
    ΔP (Power envelope drift)
    ΔC (Congestion / Cost drift)
    ΔQ (Quality / Operational degradation drift)

Hysteresis State Machine:
    QUALIFIED -> ACTIVE -> DRIFT_SUSPECTED
      ├── evidence returns to envelope -> ACTIVE
      └── sustained drift (>= threshold) -> INVALIDATED
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Tuple

from .models import (
    ExecutionCertificate,
    Policy,
    PolicyLifecycleEvent,
    PolicyState,
    WorldConditions,
)
from .registry import PolicyRegistry


@dataclass(frozen=True)
class DriftEvaluationResult:
    """Detailed evaluation result from a telemetry observation."""
    is_invalidated: bool
    is_suspected: bool
    drift_detected: bool
    drift_dimensions: Tuple[str, ...]
    dimension_ratios: Mapping[str, float]
    consecutive_violations: int
    consecutive_compliant: int
    policy_state: PolicyState
    reason: str = ""


class MultidimensionalDriftMonitor:
    """Evaluates 5-dimensional operational drift with hysteresis and hard-gate enforcement."""

    def __init__(
        self,
        registry: PolicyRegistry,
        energy_drift_threshold: float = 0.20,      # ΔE > 20%
        latency_drift_threshold: float = 0.30,     # ΔL > 30%
        power_drift_threshold: float = 0.25,       # ΔP > 25%
        congestion_drift_threshold: float = 0.40,  # ΔC > 40%
        quality_drift_threshold: float = 0.15,     # ΔQ > 15%
        consecutive_violations_to_invalidate: int = 3,
        consecutive_compliant_to_clear: int = 2,
    ) -> None:
        self.registry = registry
        self.energy_drift_threshold = energy_drift_threshold
        self.latency_drift_threshold = latency_drift_threshold
        self.power_drift_threshold = power_drift_threshold
        self.congestion_drift_threshold = congestion_drift_threshold
        self.quality_drift_threshold = quality_drift_threshold
        self.consecutive_violations_to_invalidate = consecutive_violations_to_invalidate
        self.consecutive_compliant_to_clear = consecutive_compliant_to_clear

        self._violation_counts: Dict[str, int] = {}
        self._compliant_counts: Dict[str, int] = {}
        self.drift_events_count = 0
        self.suspicion_events_count = 0

    def record_and_evaluate(
        self,
        certificate: ExecutionCertificate,
        policy: Optional[Policy] = None,
        conditions: Optional[WorldConditions] = None,
        measured_power_w: Optional[float] = None,
        congestion_factor: Optional[float] = None,
        quality_metric: Optional[float] = None,
    ) -> bool:
        """Evaluate an execution certificate against certified policy bounds.
        
        Returns:
            True if policy was invalidated, False otherwise.
        """
        result = self.evaluate(
            certificate=certificate,
            policy=policy,
            conditions=conditions,
            measured_power_w=measured_power_w,
            congestion_factor=congestion_factor,
            quality_metric=quality_metric,
        )
        return result.is_invalidated

    def evaluate(
        self,
        certificate: ExecutionCertificate,
        policy: Optional[Policy] = None,
        conditions: Optional[WorldConditions] = None,
        measured_power_w: Optional[float] = None,
        congestion_factor: Optional[float] = None,
        quality_metric: Optional[float] = None,
    ) -> DriftEvaluationResult:
        """Detailed evaluation of multidimensional drift with state machine hysteresis."""
        if not policy:
            return DriftEvaluationResult(
                is_invalidated=False,
                is_suspected=False,
                drift_detected=False,
                drift_dimensions=(),
                dimension_ratios={},
                consecutive_violations=0,
                consecutive_compliant=0,
                policy_state=PolicyState.INVALIDATED,
                reason="No policy provided",
            )

        pol_id = policy.policy_id

        # 1. HARD GATES: Immediate Invalidation with zero tolerance
        if certificate.correctness_breaches > 0 or not certificate.authority_compliant or not certificate.is_certified:
            reason = f"Hard gate breach: correctness_breaches={certificate.correctness_breaches}, authority={certificate.authority_compliant}"
            self.registry.invalidate(
                pol_id,
                reason=reason,
                world_snapshot_id=conditions.snapshot_id if conditions else certificate.world_snapshot_id,
                triggering_evidence_digest=certificate.composite_hash,
                details={"correctness_breaches": certificate.correctness_breaches, "authority_compliant": certificate.authority_compliant},
            )
            self.drift_events_count += 1
            self._violation_counts[pol_id] = 0
            self._compliant_counts[pol_id] = 0
            return DriftEvaluationResult(
                is_invalidated=True,
                is_suspected=False,
                drift_detected=True,
                drift_dimensions=("HARD_GATE",),
                dimension_ratios={"correctness": float(certificate.correctness_breaches)},
                consecutive_violations=1,
                consecutive_compliant=0,
                policy_state=PolicyState.INVALIDATED,
                reason=reason,
            )

        # 2. STATISTICAL MULTIDIMENSIONAL METRICS
        drift_dims: List[str] = []
        ratios: Dict[str, float] = {}

        # ΔE: Energy drift
        expected_e = policy.evidence.expected_energy_wh
        measured_e = certificate.measured_energy_wh
        if expected_e > 0:
            delta_e = (measured_e - expected_e) / expected_e
            ratios["delta_energy"] = delta_e
            if delta_e > self.energy_drift_threshold:
                drift_dims.append("DELTA_E")

        # ΔL: Latency drift
        expected_l = policy.evidence.expected_latency_ms
        measured_l = certificate.measured_latency_ms
        if expected_l > 0:
            delta_l = (measured_l - expected_l) / expected_l
            ratios["delta_latency"] = delta_l
            if delta_l > self.latency_drift_threshold:
                drift_dims.append("DELTA_L")

        # ΔP: Power envelope drift
        p_meas = measured_power_w
        if p_meas is None and measured_l > 0:
            # Derived power: Wh / (ms/1000/3600) = W
            p_meas = (measured_e * 3600.0) / (measured_l / 1000.0)

        budget_p = conditions.power_budget_w if conditions else policy.region.max_power_budget_w
        if p_meas is not None and budget_p != float("inf") and budget_p > 0:
            delta_p = (p_meas - budget_p) / budget_p
            ratios["delta_power"] = delta_p
            if delta_p > self.power_drift_threshold:
                drift_dims.append("DELTA_P")

        # ΔC: Congestion / Cost drift
        if congestion_factor is not None:
            ratios["delta_congestion"] = congestion_factor
            if congestion_factor > self.congestion_drift_threshold:
                drift_dims.append("DELTA_C")
        elif conditions and conditions.congestion_factors:
            max_c = max(conditions.congestion_factors.values(), default=1.0)
            if max_c > (1.0 + self.congestion_drift_threshold):
                ratios["delta_congestion"] = max_c - 1.0
                drift_dims.append("DELTA_C")

        # ΔQ: Quality / Operational Degradation drift
        if quality_metric is not None:
            ratios["delta_quality"] = quality_metric
            if quality_metric > self.quality_drift_threshold:
                drift_dims.append("DELTA_Q")

        drift_detected = len(drift_dims) > 0
        current_state = policy.state

        # 3. HYSTERESIS STATE MACHINE
        if drift_detected:
            self._compliant_counts[pol_id] = 0
            v_count = self._violation_counts.get(pol_id, 0) + 1
            self._violation_counts[pol_id] = v_count

            reason_str = f"Drift detected in {', '.join(drift_dims)}: " + ", ".join(
                f"{k}={v:+.2%}" for k, v in ratios.items() if any(d.lower() in k for d in drift_dims)
            )

            if v_count >= self.consecutive_violations_to_invalidate:
                # Sustained drift -> transition to INVALIDATED
                self.registry.invalidate(
                    pol_id,
                    reason=f"Sustained drift ({v_count} violations): {reason_str}",
                    world_snapshot_id=conditions.snapshot_id if conditions else certificate.world_snapshot_id,
                    triggering_evidence_digest=certificate.composite_hash,
                    details={"drift_dimensions": drift_dims, "dimension_ratios": ratios, "violations": v_count},
                )
                self.drift_events_count += 1
                self._violation_counts[pol_id] = 0
                return DriftEvaluationResult(
                    is_invalidated=True,
                    is_suspected=False,
                    drift_detected=True,
                    drift_dimensions=tuple(drift_dims),
                    dimension_ratios=ratios,
                    consecutive_violations=v_count,
                    consecutive_compliant=0,
                    policy_state=PolicyState.INVALIDATED,
                    reason=reason_str,
                )
            else:
                # Early deviation -> transition to DRIFT_SUSPECTED
                if current_state == PolicyState.ACTIVE:
                    self.registry.mark_drift_suspected(
                        pol_id,
                        reason=f"Suspected drift ({v_count}/{self.consecutive_violations_to_invalidate}): {reason_str}",
                        world_snapshot_id=conditions.snapshot_id if conditions else certificate.world_snapshot_id,
                        triggering_evidence_digest=certificate.composite_hash,
                        details={"drift_dimensions": drift_dims, "dimension_ratios": ratios, "violations": v_count},
                    )
                    self.suspicion_events_count += 1

                return DriftEvaluationResult(
                    is_invalidated=False,
                    is_suspected=True,
                    drift_detected=True,
                    drift_dimensions=tuple(drift_dims),
                    dimension_ratios=ratios,
                    consecutive_violations=v_count,
                    consecutive_compliant=0,
                    policy_state=PolicyState.DRIFT_SUSPECTED,
                    reason=reason_str,
                )
        else:
            # Compliant observation
            self._violation_counts[pol_id] = 0
            c_count = self._compliant_counts.get(pol_id, 0) + 1
            self._compliant_counts[pol_id] = c_count

            if current_state == PolicyState.DRIFT_SUSPECTED and c_count >= self.consecutive_compliant_to_clear:
                self.registry.clear_drift_suspicion(
                    pol_id,
                    world_snapshot_id=conditions.snapshot_id if conditions else certificate.world_snapshot_id,
                    details={"consecutive_compliant": c_count},
                )
                return DriftEvaluationResult(
                    is_invalidated=False,
                    is_suspected=False,
                    drift_detected=False,
                    drift_dimensions=(),
                    dimension_ratios=ratios,
                    consecutive_violations=0,
                    consecutive_compliant=c_count,
                    policy_state=PolicyState.ACTIVE,
                    reason="Cleared drift suspicion after compliant observations",
                )

            return DriftEvaluationResult(
                is_invalidated=False,
                is_suspected=(current_state == PolicyState.DRIFT_SUSPECTED),
                drift_detected=False,
                drift_dimensions=(),
                dimension_ratios=ratios,
                consecutive_violations=0,
                consecutive_compliant=c_count,
                policy_state=current_state,
                reason="Compliant execution",
            )


# Backward-compatible alias
class DriftMonitor(MultidimensionalDriftMonitor):
    """Backward-compatible alias for MultidimensionalDriftMonitor."""
    pass
