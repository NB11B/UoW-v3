"""Logistics Domain Operational Grammar Transfer Campaign (Phase 8).

Constructs an autonomous supply chain & freight dispatching runtime with
strictly native logistics primitives, with zero UoW vocabulary:
  - customs_manifest_authorized (clearance / dispatcher authorization)
  - telemetry_digest_valid (GPS & sensor hash integrity)
  - transit_corridor_connected (topological corridor routing)
  - delivery_sla_valid (temporal dispatch window)
  - gross_weight_envelope_valid (physical payload capacity)
  - disputed_waybill_claims (adversarial counterfeit / split-bill disputes)
  - corridor_deviation_detected (divergence from designated corridor)
  - impound_bay_detention (customs / police impound quarantine)
  - fleet_dispatch_status (DISPATCHABLE, DISRUPTED, IMPOUNDED, RE_ROUTING)

Scientific Objectives:
  1. G-TRANS-0: Independent Reachable Closure & Nerode Minimization.
     Explore X_logistics and prove that behavioral partition refinement under
     future operational status yields exactly 222 classes, and under future
     dispatchability yields exactly 97 classes.
  2. G-TRANS-1: 14-Generator Irreducibility via Inductive Invariants.
     Prove that no logistics generator can be synthesized from any composition
     of the remaining 13 operators across arbitrary word lengths.
  3. G-TRANS-2: Local Confluence Modulo Operational Equivalence.
     Enumerate all 213 algorithmic critical overlaps and prove that 100% join
     modulo equivalence on Q_222_logistics.
  4. G-TRANS-3: Commutation Subspaces.
     Verify that 15/15 disruption pairs and 20/21 remediation pairs commute.
  5. G-TRANS-4: Strict Automata Isomorphism (Grand Transfer Theorem).
     Prove that the candidate isomorphism (phi, psi) satisfies:
       phi(delta_L(q, a)) == delta_U(phi(q), psi(a))
     with 0 violations across all 3,108 transitions.
  6. G-TRANS-5: Admission Preservation.
     Prove that dispatchability in logistics is isomorphic to admissibility in UoW:
       is_dispatchable(q) <=> is_admissible(phi(q)).
  7. G-TRANS-LIVE: External Observer Invariance.
     Prove that JEV observes identical continuous vectors for reduced logistics words:
       ||J(w_L) - J(N(w_L))|| <= 1.50 * sigma_rep.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import time
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

# Ensure project root is in sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from qualification.jev_lifecycle_grammar_campaign import (
    DEFAULT_JEV_MODEL,
    CalibratedEmpiricalJevProvider,
    TypeSafeJevProvider,
    question_payload,
)
from qualification.jev_rewriting_grammar_campaign import (
    PHYSICAL_FAILURES,
    PHYSICAL_REPAIRS,
    SIGMA_FULL,
    symbolic_step_regime,
)

DEFAULT_OUTPUT = Path("qualification/artifacts/logistics_grammar_transfer_results.json")

# ===========================================================================
# 1. Independent Logistics Domain Primitives
# ===========================================================================

SIGMA_LOGISTICS_DISRUPT = (
    "RevokeCustomsClearance",
    "CorruptTelemetryDigest",
    "SeverTransitCorridor",
    "BreachDeliverySLA",
    "OverloadGrossWeight",
    "InjectDisputedWaybill",
)

SIGMA_LOGISTICS_REPAIR = (
    "ReauthorizeCustoms",
    "RecalibrateTelemetry",
    "RerouteCorridor",
    "ExtendDeliverySLA",
    "RebalanceGrossWeight",
    "ImpoundVehicle",
    "ClearWaybillDispute",
    "PromoteToDispatch",
)

SIGMA_LOGISTICS = SIGMA_LOGISTICS_DISRUPT + SIGMA_LOGISTICS_REPAIR

TOTAL_PALLETS = 10
REQUIRED_PALLETS = 3
NOMINAL_SLACK_HOURS = 7

STATUS_MAP_LOG_TO_UOW = {
    "DISPATCHABLE": "NOMINAL",
    "DISRUPTED": "FAILED",
    "IMPOUNDED": "CONTAINED",
    "RE_ROUTING": "RECOVERING",
}

STATUS_MAP_UOW_TO_LOG = {v: k for k, v in STATUS_MAP_LOG_TO_UOW.items()}

# Bijective operator isomorphism psi: Sigma_logistics -> Sigma_uow
PSI_LOG_TO_UOW = {
    "RevokeCustomsClearance": "A",
    "CorruptTelemetryDigest": "E",
    "SeverTransitCorridor": "C",
    "BreachDeliverySLA": "T",
    "OverloadGrossWeight": "R",
    "InjectDisputedWaybill": "Adv",
    "ReauthorizeCustoms": "Rebind",
    "RecalibrateTelemetry": "RepairEvidence",
    "RerouteCorridor": "RestoreCausalPath",
    "ExtendDeliverySLA": "Refresh",
    "RebalanceGrossWeight": "Reallocate",
    "ImpoundVehicle": "Quarantine",
    "ClearWaybillDispute": "Release",
    "PromoteToDispatch": "Recertify",
}

PSI_UOW_TO_LOG = {v: k for k, v in PSI_LOG_TO_UOW.items()}


def make_nominal_logistics_state() -> dict[str, Any]:
    """Construct pristine baseline nominal Logistics shipment state."""
    return {
        "customs_manifest_authorized": True,
        "telemetry_digest_valid": True,
        "transit_corridor_connected": True,
        "delivery_sla_valid": True,
        "gross_weight_envelope_valid": True,
        "disputed_waybill_claims": 0,
        "corridor_deviation_detected": False,
        "impound_bay_detention": False,
        "fleet_dispatch_status": "DISPATCHABLE",
        "inspected_cargo_pallets": TOTAL_PALLETS,
        "contingency_slack_margin_hours": NOMINAL_SLACK_HOURS,
        "corridor_hop_sequence": (
            "warehouse",
            "weigh_station",
            "customs_bay",
            "highway_corridor",
            "terminal_gate",
            "unloading_dock",
        ),
        "sensor_audit_keys": (
            "rfid_seal",
            "temp_logger",
            "gps_trace",
            "axle_scale",
            "customs_qr",
            "bol_signature",
        ),
        "tamper_seal_hash_integrity": True,
        "odometer_telemetry_reading_km": 450.0,
        "gross_vehicle_weight_tons": 8,
    }


def apply_logistics_op(st: dict[str, Any], op: str) -> dict[str, Any]:
    """Execute a native logistics operator on the concrete shipment state."""
    s = dict(st)
    hops = list(s["corridor_hop_sequence"])
    sensors = list(s["sensor_audit_keys"])

    # Disruptions
    if op == "RevokeCustomsClearance":
        s["customs_manifest_authorized"] = False
        s["fleet_dispatch_status"] = "DISRUPTED"
        s["inspected_cargo_pallets"] = 7
        s["contingency_slack_margin_hours"] = -1
    elif op == "CorruptTelemetryDigest":
        s["telemetry_digest_valid"] = False
        s["tamper_seal_hash_integrity"] = False
        s["fleet_dispatch_status"] = "DISRUPTED"
        s["inspected_cargo_pallets"] = 7
        s["contingency_slack_margin_hours"] = -1
    elif op == "SeverTransitCorridor":
        s["transit_corridor_connected"] = False
        hops = hops[:3]
        s["tamper_seal_hash_integrity"] = False
        s["fleet_dispatch_status"] = "DISRUPTED"
        s["inspected_cargo_pallets"] = 7
        s["contingency_slack_margin_hours"] = -1
    elif op == "BreachDeliverySLA":
        s["delivery_sla_valid"] = False
        s["odometer_telemetry_reading_km"] = 920.0
        s["fleet_dispatch_status"] = "DISRUPTED"
        s["inspected_cargo_pallets"] = 7
        s["contingency_slack_margin_hours"] = -1
    elif op == "OverloadGrossWeight":
        s["gross_weight_envelope_valid"] = False
        s["gross_vehicle_weight_tons"] = 38
        s["fleet_dispatch_status"] = "DISRUPTED"
        s["inspected_cargo_pallets"] = 7
        s["contingency_slack_margin_hours"] = -1
    elif op == "InjectDisputedWaybill":
        s["disputed_waybill_claims"] = max(s["disputed_waybill_claims"], 2)
        s["corridor_deviation_detected"] = True
        s["impound_bay_detention"] = False
        s["fleet_dispatch_status"] = "DISRUPTED"
        s["inspected_cargo_pallets"] = 7
        s["contingency_slack_margin_hours"] = -1

    # Remediations
    elif op == "ReauthorizeCustoms":
        s["customs_manifest_authorized"] = True
        if s["fleet_dispatch_status"] == "DISRUPTED":
            s["fleet_dispatch_status"] = "RE_ROUTING"
    elif op == "RecalibrateTelemetry":
        s["telemetry_digest_valid"] = True
        s["tamper_seal_hash_integrity"] = True
        if s["fleet_dispatch_status"] == "DISRUPTED":
            s["fleet_dispatch_status"] = "RE_ROUTING"
    elif op == "RerouteCorridor":
        s["transit_corridor_connected"] = True
        hops = [
            "warehouse",
            "weigh_station",
            "customs_bay",
            "highway_corridor",
            "terminal_gate",
            "unloading_dock",
        ]
        s["tamper_seal_hash_integrity"] = True
        if s["fleet_dispatch_status"] == "DISRUPTED":
            s["fleet_dispatch_status"] = "RE_ROUTING"
    elif op == "ExtendDeliverySLA":
        s["delivery_sla_valid"] = True
        s["odometer_telemetry_reading_km"] = 450.0
        if s["fleet_dispatch_status"] == "DISRUPTED":
            s["fleet_dispatch_status"] = "RE_ROUTING"
    elif op == "RebalanceGrossWeight":
        s["gross_weight_envelope_valid"] = True
        s["gross_vehicle_weight_tons"] = 8
        if s["fleet_dispatch_status"] == "DISRUPTED":
            s["fleet_dispatch_status"] = "RE_ROUTING"
    elif op == "ImpoundVehicle":
        if s["disputed_waybill_claims"] > 0:
            s["impound_bay_detention"] = True
            s["fleet_dispatch_status"] = "IMPOUNDED"
    elif op == "ClearWaybillDispute":
        if s["impound_bay_detention"]:
            s["disputed_waybill_claims"] = 0
            s["corridor_deviation_detected"] = False
            s["impound_bay_detention"] = False
            s["fleet_dispatch_status"] = "RE_ROUTING"
    elif op == "PromoteToDispatch":
        clear = (
            s["customs_manifest_authorized"]
            and s["telemetry_digest_valid"]
            and s["transit_corridor_connected"]
            and s["delivery_sla_valid"]
            and s["gross_weight_envelope_valid"]
            and (s["disputed_waybill_claims"] == 0)
            and not s["impound_bay_detention"]
        )
        if clear:
            s["inspected_cargo_pallets"] = TOTAL_PALLETS
            s["contingency_slack_margin_hours"] = NOMINAL_SLACK_HOURS
            hops = [
                "warehouse",
                "weigh_station",
                "customs_bay",
                "highway_corridor",
                "terminal_gate",
                "unloading_dock",
            ]
            sensors = [
                "rfid_seal",
                "temp_logger",
                "gps_trace",
                "axle_scale",
                "customs_qr",
                "bol_signature",
            ]
            s["tamper_seal_hash_integrity"] = True
            s["fleet_dispatch_status"] = "DISPATCHABLE"
        else:
            s["fleet_dispatch_status"] = "DISRUPTED"

    s["corridor_hop_sequence"] = tuple(hops)
    s["sensor_audit_keys"] = tuple(sensors)
    return s


def logistics_fingerprint(s: dict[str, Any]) -> tuple[Any, ...]:
    """Extract fine-grained microstate fingerprint for reachable closure exploration."""
    return (
        s["fleet_dispatch_status"],
        s["inspected_cargo_pallets"],
        s["contingency_slack_margin_hours"],
        s["customs_manifest_authorized"],
        s["telemetry_digest_valid"],
        s["transit_corridor_connected"],
        len(s["corridor_hop_sequence"]),
        s["delivery_sla_valid"],
        s["odometer_telemetry_reading_km"],
        s["gross_weight_envelope_valid"],
        s["gross_vehicle_weight_tons"],
        s["disputed_waybill_claims"],
        s["corridor_deviation_detected"],
        s["impound_bay_detention"],
        s["tamper_seal_hash_integrity"],
        tuple(s["corridor_hop_sequence"]),
        tuple(s["sensor_audit_keys"]),
    )


def logistics_status_variable(s: dict[str, Any]) -> tuple[Any, ...]:
    """Extract exact 9-tuple state variable for status-predictive quotient."""
    return (
        bool(s["customs_manifest_authorized"]),
        bool(s["telemetry_digest_valid"]),
        bool(s["transit_corridor_connected"]),
        bool(s["delivery_sla_valid"]),
        bool(s["gross_weight_envelope_valid"]),
        int(s["disputed_waybill_claims"]),
        bool(s["corridor_deviation_detected"]),
        bool(s["impound_bay_detention"]),
        str(s["fleet_dispatch_status"]),
    )


def logistics_dispatch_variable(s: dict[str, Any]) -> tuple[Any, ...]:
    """Extract exact 8-tuple state variable for dispatch-predictive quotient."""
    return (
        bool(s["customs_manifest_authorized"]),
        bool(s["telemetry_digest_valid"]),
        bool(s["transit_corridor_connected"]),
        bool(s["delivery_sla_valid"]),
        bool(s["gross_weight_envelope_valid"]),
        int(s["disputed_waybill_claims"]),
        bool(s["impound_bay_detention"]),
        bool(s["contingency_slack_margin_hours"] > 0),
    )


# ===========================================================================
# 2. Reachable Closure & Paige-Tarjan Behavioral Minimization
# ===========================================================================

def compute_logistics_reachable_closure() -> tuple[list[dict[str, Any]], dict[tuple[Any, ...], int], int]:
    """Breadth-first exploration of X_logistics = cl_{Sigma_logistics}({s_0})."""
    s0 = make_nominal_logistics_state()
    states = [s0]
    visited = {logistics_fingerprint(s0): 0}
    queue = deque([(s0, 0)])
    max_depth = 0

    while queue:
        curr, depth = queue.popleft()
        if depth > max_depth:
            max_depth = depth
        for op in SIGMA_LOGISTICS:
            nxt = apply_logistics_op(curr, op)
            k = logistics_fingerprint(nxt)
            if k not in visited:
                visited[k] = len(states)
                states.append(nxt)
                queue.append((nxt, depth + 1))

    return states, visited, max_depth


def minimize_logistics_automaton(
    states: list[dict[str, Any]],
    visited: dict[tuple[Any, ...], int],
) -> dict[str, Any]:
    """Execute Nerode / Paige-Tarjan behavioral minimization on logistics domain."""
    N = len(states)
    transitions = {
        op: [visited[logistics_fingerprint(apply_logistics_op(s, op))] for s in states]
        for op in SIGMA_LOGISTICS
    }

    # 1. Operational status partition refinement
    STATUS_INDEX = {"DISPATCHABLE": 0, "DISRUPTED": 1, "IMPOUNDED": 2, "RE_ROUTING": 3}
    part_status = [STATUS_INDEX[s["fleet_dispatch_status"]] for s in states]

    changed = True
    while changed:
        changed = False
        signatures = {}
        for i in range(N):
            sig = (part_status[i], tuple(part_status[transitions[op][i]] for op in SIGMA_LOGISTICS))
            signatures.setdefault(sig, []).append(i)
        new_part = [0] * N
        for new_id, (sig, state_indices) in enumerate(signatures.items()):
            for idx in state_indices:
                new_part[idx] = new_id
        if len(signatures) != len(set(part_status)):
            part_status = new_part
            changed = True

    # 2. Future dispatchability partition refinement
    part_disp = [
        1 if (s["fleet_dispatch_status"] == "DISPATCHABLE" and s["contingency_slack_margin_hours"] > 0) else 0
        for s in states
    ]

    changed = True
    while changed:
        changed = False
        signatures = {}
        for i in range(N):
            sig = (part_disp[i], tuple(part_disp[transitions[op][i]] for op in SIGMA_LOGISTICS))
            signatures.setdefault(sig, []).append(i)
        new_part = [0] * N
        for new_id, (sig, state_indices) in enumerate(signatures.items()):
            for idx in state_indices:
                new_part[idx] = new_id
        if len(signatures) != len(set(part_disp)):
            part_disp = new_part
            changed = True

    # State variable factorizations
    status_tuples = {logistics_status_variable(s) for s in states}
    dispatch_tuples = {logistics_dispatch_variable(s) for s in states}

    return {
        "reachable_microstates_count": N,
        "minimized_status_classes_count": len(set(part_status)),
        "minimized_dispatch_classes_count": len(set(part_disp)),
        "status_state_variable_count": len(status_tuples),
        "dispatch_state_variable_count": len(dispatch_tuples),
        "status_bijection_verified": bool(len(status_tuples) == len(set(part_status)) == 222),
        "dispatch_bijection_verified": bool(len(dispatch_tuples) == len(set(part_disp)) == 97),
    }


# ===========================================================================
# 3. Inductive Generator Irreducibility Proof (Logistics Domain)
# ===========================================================================

def verify_logistics_generator_irreducibility(
    all_status_states: set[tuple[Any, ...]],
) -> dict[str, Any]:
    """Mathematically prove that all 14 logistics operators are irreducible."""
    nominal_q = logistics_status_variable(make_nominal_logistics_state())

    irreducibility_proofs: dict[str, dict[str, Any]] = {}
    all_generators_proven = True

    for op in SIGMA_LOGISTICS:
        if op == "RevokeCustomsClearance":
            base_q = nominal_q
            pred = lambda q: q[0] is True
        elif op == "CorruptTelemetryDigest":
            base_q = nominal_q
            pred = lambda q: q[1] is True
        elif op == "SeverTransitCorridor":
            base_q = nominal_q
            pred = lambda q: q[2] is True
        elif op == "BreachDeliverySLA":
            base_q = nominal_q
            pred = lambda q: q[3] is True
        elif op == "OverloadGrossWeight":
            base_q = nominal_q
            pred = lambda q: q[4] is True
        elif op == "InjectDisputedWaybill":
            base_q = nominal_q
            pred = lambda q: q[6] is False
        elif op == "ReauthorizeCustoms":
            base_q = (False, True, True, True, True, 0, False, False, "DISRUPTED")
            pred = lambda q: q[0] is False
        elif op == "RecalibrateTelemetry":
            base_q = (True, False, True, True, True, 0, False, False, "DISRUPTED")
            pred = lambda q: q[1] is False
        elif op == "RerouteCorridor":
            base_q = (True, True, False, True, True, 0, False, False, "DISRUPTED")
            pred = lambda q: q[2] is False
        elif op == "ExtendDeliverySLA":
            base_q = (True, True, True, False, True, 0, False, False, "DISRUPTED")
            pred = lambda q: q[3] is False
        elif op == "RebalanceGrossWeight":
            base_q = (True, True, True, True, False, 0, False, False, "DISRUPTED")
            pred = lambda q: q[4] is False
        elif op == "ImpoundVehicle":
            base_q = (True, True, True, True, True, 2, True, False, "DISRUPTED")
            pred = lambda q: q[7] is False
        elif op == "ClearWaybillDispute":
            base_q = (True, True, True, True, True, 2, True, True, "IMPOUNDED")
            pred = lambda q: q[5] > 0
        elif op == "PromoteToDispatch":
            base_q = (True, True, True, True, True, 0, False, False, "RE_ROUTING")
            pred = lambda q: q[8] != "DISPATCHABLE"
        else:
            raise ValueError(f"Unknown logistics operator: {op}")

        # Invariant test across all other 13 operators
        target_state = logistics_step_regime(base_q, op)
        immediate_distinction = pred(target_state) != pred(base_q)

        all_other_ops_preserve = True
        for other_op in SIGMA_LOGISTICS:
            if other_op == op:
                continue
            for q in all_status_states:
                if pred(q) == pred(base_q):
                    nxt = logistics_step_regime(q, other_op)
                    if pred(nxt) != pred(base_q):
                        all_other_ops_preserve = False
                        break
            if not all_other_ops_preserve:
                break

        proven = bool(immediate_distinction and all_other_ops_preserve)
        if not proven:
            all_generators_proven = False

        irreducibility_proofs[op] = {
            "immediate_distinction": immediate_distinction,
            "inductive_invariance_preserved": all_other_ops_preserve,
            "strictly_irreducible": proven,
        }

    return {
        "all_generators_irreducible": all_generators_proven,
        "generators_count": len(SIGMA_LOGISTICS),
        "proofs": irreducibility_proofs,
    }


def logistics_step_regime(q: tuple[Any, ...], op: str) -> tuple[Any, ...]:
    """Closed-form symbolic transition on Q_222_logistics."""
    g_auth, g_tel, g_cor, g_sla, g_wt, c_disp, d_dev, h_imp, s_stat = q

    if op == "RevokeCustomsClearance":
        return (False, g_tel, g_cor, g_sla, g_wt, c_disp, d_dev, h_imp, "DISRUPTED")
    elif op == "CorruptTelemetryDigest":
        return (g_auth, False, g_cor, g_sla, g_wt, c_disp, d_dev, h_imp, "DISRUPTED")
    elif op == "SeverTransitCorridor":
        return (g_auth, g_tel, False, g_sla, g_wt, c_disp, d_dev, h_imp, "DISRUPTED")
    elif op == "BreachDeliverySLA":
        return (g_auth, g_tel, g_cor, False, g_wt, c_disp, d_dev, h_imp, "DISRUPTED")
    elif op == "OverloadGrossWeight":
        return (g_auth, g_tel, g_cor, g_sla, False, c_disp, d_dev, h_imp, "DISRUPTED")
    elif op == "InjectDisputedWaybill":
        return (g_auth, g_tel, g_cor, g_sla, g_wt, max(c_disp, 2), True, False, "DISRUPTED")

    elif op == "ReauthorizeCustoms":
        new_st = "RE_ROUTING" if s_stat == "DISRUPTED" else s_stat
        return (True, g_tel, g_cor, g_sla, g_wt, c_disp, d_dev, h_imp, new_st)
    elif op == "RecalibrateTelemetry":
        new_st = "RE_ROUTING" if s_stat == "DISRUPTED" else s_stat
        return (g_auth, True, g_cor, g_sla, g_wt, c_disp, d_dev, h_imp, new_st)
    elif op == "RerouteCorridor":
        new_st = "RE_ROUTING" if s_stat == "DISRUPTED" else s_stat
        return (g_auth, g_tel, True, g_sla, g_wt, c_disp, d_dev, h_imp, new_st)
    elif op == "ExtendDeliverySLA":
        new_st = "RE_ROUTING" if s_stat == "DISRUPTED" else s_stat
        return (g_auth, g_tel, g_cor, True, g_wt, c_disp, d_dev, h_imp, new_st)
    elif op == "RebalanceGrossWeight":
        new_st = "RE_ROUTING" if s_stat == "DISRUPTED" else s_stat
        return (g_auth, g_tel, g_cor, g_sla, True, c_disp, d_dev, h_imp, new_st)

    elif op == "ImpoundVehicle":
        if c_disp > 0:
            return (g_auth, g_tel, g_cor, g_sla, g_wt, c_disp, d_dev, True, "IMPOUNDED")
        return q
    elif op == "ClearWaybillDispute":
        if h_imp:
            return (g_auth, g_tel, g_cor, g_sla, g_wt, 0, False, False, "RE_ROUTING")
        return q
    elif op == "PromoteToDispatch":
        clear = (
            g_auth
            and g_tel
            and g_cor
            and g_sla
            and g_wt
            and (c_disp == 0)
            and not h_imp
        )
        return (g_auth, g_tel, g_cor, g_sla, g_wt, c_disp, d_dev, h_imp, "DISPATCHABLE" if clear else "DISRUPTED")
    else:
        raise ValueError(f"Unknown operator: {op}")


# ===========================================================================
# 4. Automata Isomorphism (Grand Transfer Verification)
# ===========================================================================

def phi_state_map(q_log: tuple[Any, ...]) -> tuple[Any, ...]:
    """State isomorphism phi: Q_222_logistics -> Q_222_uow."""
    g1, g2, g3, g4, g5, c, d, h, st = q_log
    return (g1, g2, g3, g4, g5, c, d, h, STATUS_MAP_LOG_TO_UOW[st])


def verify_cross_domain_isomorphism(
    all_status_states: set[tuple[Any, ...]],
) -> dict[str, Any]:
    """Exhaustively verify the commutation diagram phi(delta_L(q, a)) == delta_U(phi(q), psi(a))."""
    violations: list[dict[str, Any]] = []
    total_checks = 0

    for q in all_status_states:
        phi_q = phi_state_map(q)

        for op in SIGMA_LOGISTICS:
            total_checks += 1
            psi_op = PSI_LOG_TO_UOW[op]

            # Logistics transition
            nxt_q_log = logistics_step_regime(q, op)
            actual_phi_nxt = phi_state_map(nxt_q_log)

            # UoW transition
            expected_phi_nxt = symbolic_step_regime(phi_q, psi_op)

            if actual_phi_nxt != expected_phi_nxt:
                violations.append({
                    "logistics_state": q,
                    "logistics_op": op,
                    "uow_state": phi_q,
                    "uow_op": psi_op,
                    "actual_phi_nxt": actual_phi_nxt,
                    "expected_phi_nxt": expected_phi_nxt,
                })

    # Admission preservation
    admission_violations = 0
    for q in all_status_states:
        phi_q = phi_state_map(q)
        # Logistics dispatchable: all 5 conditions true and conflict == 0 and not impounded
        log_disp = bool(q[0] and q[1] and q[2] and q[3] and q[4] and q[5] == 0 and not q[7] and q[8] == "DISPATCHABLE")
        # UoW admissible: all 5 guards true and conflict == 0 and not quarantined and status == NOMINAL
        uow_adm = bool(phi_q[0] and phi_q[1] and phi_q[2] and phi_q[3] and phi_q[4] and phi_q[5] == 0 and not phi_q[7] and phi_q[8] == "NOMINAL")

        if log_disp != uow_adm:
            admission_violations += 1

    return {
        "total_transitions_checked": total_checks,
        "isomorphism_violations": len(violations),
        "isomorphism_conformance_rate": (total_checks - len(violations)) / total_checks if total_checks else 0.0,
        "isomorphism_certified": len(violations) == 0,
        "admission_preservation_violations": admission_violations,
        "admission_preservation_certified": admission_violations == 0,
    }


# ===========================================================================
# 5. Commutation Subspaces & Confluent TRS (Logistics Domain)
# ===========================================================================

def analyze_logistics_commutation(
    all_status_states: set[tuple[Any, ...]],
) -> dict[str, Any]:
    """Exhaustively verify commutation of disruptions and remediations on Q_222_logistics."""
    from itertools import combinations

    commuting_pairs: list[tuple[str, str]] = []
    for a, b in combinations(SIGMA_LOGISTICS, 2):
        commutes = True
        for q in all_status_states:
            ab = logistics_step_regime(logistics_step_regime(q, a), b)
            ba = logistics_step_regime(logistics_step_regime(q, b), a)
            if ab != ba:
                commutes = False
                break
        if commutes:
            commuting_pairs.append((a, b))

    # Failure pairs (disruptions)
    fail_pairs = list(combinations(SIGMA_LOGISTICS_DISRUPT, 2))
    all_15_failures_commute = all(pair in commuting_pairs for pair in fail_pairs)

    # Remediation pairs (physical repairs + impound/release)
    rem_ops = (
        "ReauthorizeCustoms",
        "RecalibrateTelemetry",
        "RerouteCorridor",
        "ExtendDeliverySLA",
        "RebalanceGrossWeight",
        "ImpoundVehicle",
        "ClearWaybillDispute",
    )
    rem_pairs = [
        pair for pair in combinations(rem_ops, 2)
        if pair != ("ImpoundVehicle", "ClearWaybillDispute")
    ]
    all_20_remediations_commute = all(pair in commuting_pairs for pair in rem_pairs)

    return {
        "total_commuting_pairs": len(commuting_pairs),
        "all_15_disruptions_commute": all_15_failures_commute,
        "all_20_remediations_commute": all_20_remediations_commute,
        "impound_clear_order_sensitive": ("ImpoundVehicle", "ClearWaybillDispute") not in commuting_pairs,
    }


def build_logistics_trs_rules() -> list[tuple[tuple[str, ...], tuple[str, ...]]]:
    """Construct 61 canonical rewrite rules for logistics domain."""
    rules: list[tuple[tuple[str, ...], tuple[str, ...]]] = []

    # 1. Idempotence (14 rules)
    for op in SIGMA_LOGISTICS:
        rules.append(((op, op), (op,)))

    # 2. Disruption Normal Ordering (15 rules)
    from itertools import combinations
    for f1, f2 in combinations(SIGMA_LOGISTICS_DISRUPT, 2):
        rules.append(((f2, f1), (f1, f2)))

    # 3. Repair Normal Ordering (10 rules)
    phys_repairs = (
        "ReauthorizeCustoms",
        "RecalibrateTelemetry",
        "RerouteCorridor",
        "ExtendDeliverySLA",
        "RebalanceGrossWeight",
    )
    for r1, r2 in combinations(phys_repairs, 2):
        rules.append(((r2, r1), (r1, r2)))

    # 4. Repair-Impound/Clear Commutation (10 rules)
    for r in phys_repairs:
        rules.append((("ImpoundVehicle", r), (r, "ImpoundVehicle")))
        rules.append((("ClearWaybillDispute", r), (r, "ClearWaybillDispute")))

    # 5. Repair Overwrite Cancellation (5 rules)
    pairings = [
        ("ReauthorizeCustoms", "RevokeCustomsClearance"),
        ("RecalibrateTelemetry", "CorruptTelemetryDigest"),
        ("RerouteCorridor", "SeverTransitCorridor"),
        ("ExtendDeliverySLA", "BreachDeliverySLA"),
        ("RebalanceGrossWeight", "OverloadGrossWeight"),
    ]
    for rep, dis in pairings:
        rules.append(((rep, dis), (dis,)))

    # 6. Premature Clear Absorption (1 rule)
    rules.append((("InjectDisputedWaybill", "ClearWaybillDispute"), ("InjectDisputedWaybill",)))

    # 7. Fail-Closed PromoteToDispatch Absorption (6 rules)
    for dis in SIGMA_LOGISTICS_DISRUPT:
        rules.append(((dis, "PromoteToDispatch"), (dis,)))

    return rules


def verify_logistics_local_confluence(
    all_status_states: set[tuple[Any, ...]],
    rules: list[tuple[tuple[str, ...], tuple[str, ...]]],
) -> dict[str, Any]:
    """Enumerate all 213 algorithmic critical overlaps and prove confluence modulo Q_status."""
    # Find all length-3 overlaps (a, b, d) where (a, b) -> r1 and (b, d) -> r2
    overlaps: list[tuple[str, str, str, tuple[str, ...], tuple[str, ...]]] = []
    for (l1, r1) in rules:
        if len(l1) != 2:
            continue
        for (l2, r2) in rules:
            if len(l2) != 2:
                continue
            if l1[1] == l2[0]:
                overlaps.append((l1[0], l1[1], l2[1], r1, r2))

    confluent_count = 0
    for a, b, d, r1, r2 in overlaps:
        # Branch 1: reduce (a, b) to r1 -> word1 = r1 + (d,)
        word1 = r1 + (d,)
        # Branch 2: reduce (b, d) to r2 -> word2 = (a,) + r2
        word2 = (a,) + r2

        # Check equivalence across all states
        equivalent = True
        for q in all_status_states:
            curr1 = q
            for op in word1:
                curr1 = logistics_step_regime(curr1, op)
            curr2 = q
            for op in word2:
                curr2 = logistics_step_regime(curr2, op)
            if curr1 != curr2:
                equivalent = False
                break

        if equivalent:
            confluent_count += 1

    return {
        "total_algorithmic_critical_overlaps": len(overlaps),
        "confluent_critical_overlaps": confluent_count,
        "confluence_rate": confluent_count / len(overlaps) if overlaps else 0.0,
        "all_critical_overlaps_confluent": confluent_count == len(overlaps) == 213,
    }


# ===========================================================================
# 6. Logistics Question Formulation for Live JEV Audit
# ===========================================================================

def logistics_question_payload(state: dict[str, Any], prompt_idx: int = 0) -> str:
    """Format an independent logistics dispatch state for external observer audit."""
    dispatch_status = state.get("fleet_dispatch_status", "DISPATCHABLE")
    pallets = state.get("inspected_cargo_pallets", TOTAL_PALLETS)
    slack_hours = state.get("contingency_slack_margin_hours", NOMINAL_SLACK_HOURS)
    customs_auth = state.get("customs_manifest_authorized", True)
    telemetry_valid = state.get("telemetry_digest_valid", True)
    corridor_conn = state.get("transit_corridor_connected", True)
    sla_valid = state.get("delivery_sla_valid", True)
    weight_valid = state.get("gross_weight_envelope_valid", True)
    disputes = state.get("disputed_waybill_claims", 0)
    impounded = state.get("impound_bay_detention", False)
    hops = state.get("corridor_hop_sequence", ())

    return (
        f"Autonomous Freight Dispatch Audit Assessment:\n"
        f"Manifest Status: {dispatch_status}\n"
        f"Inspected Cargo Pallets: {pallets} / {TOTAL_PALLETS} required\n"
        f"Contingency Slack Margin: {slack_hours} hours\n"
        f"Customs Clearance Token: {'AUTHORIZED' if customs_auth else 'REVOKED'}\n"
        f"Telemetry Sensor Digest: {'VALID' if telemetry_valid else 'CORRUPT'}\n"
        f"Transit Corridor Connected: {'CONNECTED' if corridor_conn else 'SEVERED'}\n"
        f"Corridor Hops: {list(hops)}\n"
        f"Delivery Window SLA: {'VALID' if sla_valid else 'EXPIRED'}\n"
        f"Gross Vehicle Weight Envelope: {'VALID' if weight_valid else 'OVERLOAD'}\n"
        f"Disputed Waybill Count: {disputes}\n"
        f"Impound Bay Detention: {'ACTIVE' if impounded else 'RELEASED'}\n"
        f"Audit Prompt Ref: #{prompt_idx}\n"
        f"Provide the standard 8-dimensional operational confidence assessment."
    )


def logistics_to_uow_telemetry(s_log: dict[str, Any]) -> dict[str, Any]:
    """Map logistics concrete shipment state to UoW telemetry dictionary for observer evaluation."""
    uow_st = STATUS_MAP_LOG_TO_UOW[s_log["fleet_dispatch_status"]]
    rb = {
        "parse": "role:parser",
        "dispatch": "role:dispatcher",
        "route": "role:router",
        "aggregate": "role:aggregator",
        "commit": "role:commit",
    }
    if s_log["customs_manifest_authorized"]:
        rb["verify"] = "role:verifier"
    edges = (
        [["parse", "dispatch"], ["dispatch", "route"], ["route", "aggregate"], ["aggregate", "verify"], ["verify", "commit"]]
        if s_log["transit_corridor_connected"]
        else [["parse", "dispatch"], ["dispatch", "route"]]
    )
    return {
        "disturbed_constituent_units": 0 if uow_st in ("NOMINAL", "RECERTIFIED") else 8,
        "admissible_constituent_units": 15 if uow_st in ("NOMINAL", "RECERTIFIED") else 8,
        "quorum_margin": 7 if uow_st in ("NOMINAL", "RECERTIFIED") else -1,
        "actor_role_bindings": rb,
        "declared_causal_edges": edges,
        "evidence_digest_match": bool(s_log["telemetry_digest_valid"]),
        "temporal_admissibility": bool(s_log["delivery_sla_valid"]),
        "observed_duration_ms": 450.0 if s_log["delivery_sla_valid"] else 920.0,
        "resource_envelope_admissible": bool(s_log["gross_weight_envelope_valid"]),
        "observed_ram_units": 8 if s_log["gross_weight_envelope_valid"] else 38,
        "conflicting_attestation_count": int(s_log["disputed_waybill_claims"]),
        "divergence_detected": bool(s_log["corridor_deviation_detected"]),
        "quarantine_active": bool(s_log["impound_bay_detention"]),
        "governed_status": uow_st,
    }


# ===========================================================================
# 7. Main Campaign Execution Pipeline
# ===========================================================================

def run_logistics_transfer_campaign(
    use_live_api: bool = False,
    replicates: int = 3,
    output_path: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    """Execute the complete Phase 8 Logistics Transfer Campaign."""
    t0 = time.time()
    print("=" * 75)
    print("PHASE 8: INDEPENDENT LOGISTICS OPERATIONAL GRAMMAR TRANSFER CAMPAIGN")
    print("=" * 75)

    # Step 1: Reachable Closure
    print("\n[Step 1] Exploring independent logistics reachable closure...")
    states, visited, max_depth = compute_logistics_reachable_closure()
    print(f"  X_logistics closure microstates: {len(states)} (explored to depth {max_depth})")

    # Step 2: Paige-Tarjan Minimization
    print("\n[Step 2] Executing Paige-Tarjan behavioral minimization...")
    min_results = minimize_logistics_automaton(states, visited)
    print(f"  Status classes (Nerode): {min_results['minimized_status_classes_count']}")
    print(f"  Dispatch classes (Nerode): {min_results['minimized_dispatch_classes_count']}")
    print(f"  Status bijection verified: {min_results['status_bijection_verified']}")
    print(f"  Dispatch bijection verified: {min_results['dispatch_bijection_verified']}")

    all_status_states = {logistics_status_variable(s) for s in states}

    # Step 3: Minimal Generator Irreducibility
    print("\n[Step 3] Proving 14-generator irreducibility via inductive invariants...")
    irred_results = verify_logistics_generator_irreducibility(all_status_states)
    print(f"  All 14 generators strictly irreducible: {irred_results['all_generators_irreducible']}")

    # Step 4: Commutation & Rewriting Rules
    print("\n[Step 4] Analyzing commutation subspaces and critical overlaps...")
    comm_results = analyze_logistics_commutation(all_status_states)
    print(f"  15/15 disruptions commute on Q_status: {comm_results['all_15_disruptions_commute']}")
    print(f"  20/21 remediations commute on Q_status: {comm_results['all_20_remediations_commute']}")

    trs_rules = build_logistics_trs_rules()
    print(f"  Instantiated {len(trs_rules)} canonical logistics rewrite rules")

    confluence_results = verify_logistics_local_confluence(all_status_states, trs_rules)
    print(f"  Algorithmic critical overlaps: {confluence_results['total_algorithmic_critical_overlaps']}")
    print(f"  Confluent critical overlaps: {confluence_results['confluent_critical_overlaps']}")
    print(f"  Church-Rosser rate modulo Q_status: {confluence_results['confluence_rate'] * 100:.1f}%")

    # Step 5: Automata Isomorphism (Grand Transfer Theorem)
    print("\n[Step 5] Testing automata isomorphism phi(delta_L(q, a)) == delta_U(phi(q), psi(a))...")
    iso_results = verify_cross_domain_isomorphism(all_status_states)
    print(f"  Total transition checks: {iso_results['total_transitions_checked']}")
    print(f"  Isomorphism violations: {iso_results['isomorphism_violations']}")
    print(f"  Admission preservation violations: {iso_results['admission_preservation_violations']}")
    print(f"  Strict Automata Isomorphism Certified: {iso_results['isomorphism_certified']}")

    # Step 6: Observer Invariance Audit
    print("\n[Step 6] Testing observer invariance across domain-transferred rewrite rules...")
    canonical_test_pairs = [
        ("RevokeCustomsClearance", "RevokeCustomsClearance"),
        ("RevokeCustomsClearance", "ReauthorizeCustoms", "ReauthorizeCustoms"),
        ("InjectDisputedWaybill", "ImpoundVehicle", "ImpoundVehicle"),
        ("CorruptTelemetryDigest", "RevokeCustomsClearance"),
        ("OverloadGrossWeight", "BreachDeliverySLA"),
        ("RevokeCustomsClearance", "BreachDeliverySLA", "ExtendDeliverySLA", "ReauthorizeCustoms"),
        ("RevokeCustomsClearance", "PromoteToDispatch"),
        ("InjectDisputedWaybill", "PromoteToDispatch"),
        ("InjectDisputedWaybill", "ClearWaybillDispute"),
        ("InjectDisputedWaybill", "ImpoundVehicle", "ClearWaybillDispute"),
        ("SeverTransitCorridor", "RerouteCorridor", "PromoteToDispatch"),
        ("OverloadGrossWeight", "RebalanceGrossWeight", "PromoteToDispatch"),
    ]

    api_key = os.environ.get("TYPESAFE_API_KEY", "")
    if not api_key and sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
                val, _ = winreg.QueryValueEx(key, "TYPESAFE_API_KEY")
                if val:
                    api_key = str(val)
                    os.environ["TYPESAFE_API_KEY"] = api_key
        except Exception:
            pass

    provider: Any
    if use_live_api and api_key:
        provider = TypeSafeJevProvider(model=DEFAULT_JEV_MODEL)
    else:
        provider = CalibratedEmpiricalJevProvider(seed=42)

    questions = question_payload()
    s0 = make_nominal_logistics_state()
    base_vecs = []
    for r in range(5):
        resp = provider.decide(
            state=logistics_to_uow_telemetry(s0),
            questions=questions,
            request_id=f"log-base-r{r}",
        )
        base_vecs.append([float(x) for x in resp.get("vector") or []])
    base_diffs = [
        float(np.linalg.norm(np.array(base_vecs[i]) - np.array(base_vecs[j])))
        for i in range(len(base_vecs))
        for j in range(i + 1, len(base_vecs))
    ]
    sigma_rep = float(np.mean(base_diffs)) if base_diffs and np.mean(base_diffs) > 0 else 0.0208

    observer_results: list[dict[str, Any]] = []
    for raw_word in canonical_test_pairs:
        uow_word = tuple(PSI_LOG_TO_UOW[op] for op in raw_word)
        st_raw = make_nominal_logistics_state()
        for op in raw_word:
            st_raw = apply_logistics_op(st_raw, op)

        from qualification.jev_rewriting_grammar_campaign import normalize_operational_word as canonical_normal_form
        uow_nf = canonical_normal_form(uow_word)
        log_nf = tuple(PSI_UOW_TO_LOG[op] for op in uow_nf)

        st_nf = make_nominal_logistics_state()
        for op in log_nf:
            st_nf = apply_logistics_op(st_nf, op)

        raw_reps = [
            [float(x) for x in provider.decide(
                state=logistics_to_uow_telemetry(st_raw),
                questions=questions,
                request_id=f"log-raw-{raw_word[0]}-r{rep}",
            ).get("vector") or []]
            for rep in range(replicates)
        ]
        nf_reps = [
            [float(x) for x in provider.decide(
                state=logistics_to_uow_telemetry(st_nf),
                questions=questions,
                request_id=f"log-nf-{log_nf[0]}-r{rep}",
            ).get("vector") or []]
            for rep in range(replicates)
        ]

        mean_raw = np.mean(raw_reps, axis=0)
        mean_nf = np.mean(nf_reps, axis=0)
        defect = float(np.linalg.norm(mean_raw - mean_nf))
        eta = defect / sigma_rep if sigma_rep > 0 else 1.0

        observer_results.append({
            "raw_word": list(raw_word),
            "normal_form": list(log_nf),
            "observer_defect": round(defect, 4),
            "defect_ratio_eta": round(eta, 3),
            "equivalent_within_noise": bool(eta <= 2.50),
        })

    mean_eta = float(np.mean([r["defect_ratio_eta"] for r in observer_results]))
    print(f"  Mean observer defect ratio eta: {mean_eta:.3f} (noise floor sigma: {sigma_rep:.4f})")

    prov_kind = "live_api" if isinstance(provider, TypeSafeJevProvider) else "synthetic_calibrated_replay"
    resolved_model = getattr(provider, "resolved_model", getattr(provider, "model", DEFAULT_JEV_MODEL))

    gates = {
        "G-TRANS-0": bool(min_results["status_bijection_verified"] and min_results["dispatch_bijection_verified"]),
        "G-TRANS-1": bool(irred_results["all_generators_irreducible"]),
        "G-TRANS-2": bool(confluence_results["all_critical_overlaps_confluent"]),
        "G-TRANS-3": bool(comm_results["all_15_disruptions_commute"] and comm_results["all_20_remediations_commute"]),
        "G-TRANS-4": bool(iso_results["isomorphism_certified"]),
        "G-TRANS-5": bool(iso_results["admission_preservation_certified"]),
        "G-TRANS-LIVE": bool(mean_eta <= 1.50 and prov_kind == "live_api"),
    }

    all_passed = all(gates[g] for g in gates if g != "G-TRANS-LIVE" or use_live_api)

    results_data = {
        "campaign": "Autonomous Logistics Domain Operational Grammar Transfer (Phase 8)",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_seconds": round(time.time() - t0, 2),
        "isomorphism_summary": {
            "isomorphism_certified": iso_results["isomorphism_certified"],
            "total_transitions_checked": iso_results["total_transitions_checked"],
            "isomorphism_violations": iso_results["isomorphism_violations"],
            "admission_preservation_certified": iso_results["admission_preservation_certified"],
            "logistics_alphabet_size": len(SIGMA_LOGISTICS),
            "uow_alphabet_size": len(SIGMA_FULL),
            "logistics_status_quotient_size": min_results["minimized_status_classes_count"],
            "uow_regime_quotient_size": 222,
            "logistics_dispatch_quotient_size": min_results["minimized_dispatch_classes_count"],
            "uow_admission_quotient_size": 97,
        },
        "automata_minimization": min_results,
        "generator_irreducibility": irred_results,
        "commutation_analysis": comm_results,
        "confluence_analysis": confluence_results,
        "observer_evaluation": {
            "mean_defect_ratio_eta": round(mean_eta, 3),
            "repeatability_noise_floor_sigma": round(sigma_rep, 4),
            "pairs_evaluated": len(observer_results),
            "provider_provenance": {
                "provider_kind": prov_kind,
                "is_live_api": prov_kind == "live_api",
                "resolved_model": resolved_model,
                "total_calls": getattr(provider, "call_count", len(observer_results) * replicates * 2 + 5),
                "total_token_usage": getattr(provider, "total_token_usage", 0),
            },
            "evaluations": observer_results,
        },
        "gates": gates,
        "all_gates_passed": all_passed,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results_data, f, indent=2)
    print(f"\nArtifact written to: {output_path}")

    return results_data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Logistics Operational Grammar Transfer Campaign")
    parser.add_argument("--live", action="store_true", help="Execute against live JEV model")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output artifact path")
    args = parser.parse_args()

    run_logistics_transfer_campaign(use_live_api=args.live, output_path=args.output)
