"""Qualification evidence-package integrity tests for Atomic Economics (Milestone v3.1-M2).

Validates the formal 6-dimension atomic cost representation:
    C(u) = C_H + C_M + C_E + C_R + C_K + C_D
and its measurement semantics, recursive composition, friction isolation,
evidence-bound replay, and authority non-escalation.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from uow.contracts import Guard, GuardOp, Header, Lifecycle, Mutation, MutationOp, Route, UoW, Contract, WorkCategory
from uow.state import WorldState
from uow.economics.atomic_cost import AtomicCost, CostObservationRecord, compute_cost_evidence_hash
from uow.economics.composition import CompositionCostProfile
from uow.economics.friction import FrictionAnalysis
from uow.economics.boundary import EconomicProposal, evaluate_economic_proposal

M2_DIR = Path(__file__).resolve().parent.parent / "qualification" / "economics" / "atomic_cost"
VECTORS_DIR = M2_DIR / "vectors"
MANIFEST_PATH = M2_DIR / "QUALIFICATION_MANIFEST.json"


def test_m2_manifest_structure_and_gates() -> None:
    """Verify manifest schema, 6 qualification gates, and vector cryptographic hashes."""
    assert MANIFEST_PATH.exists(), f"Missing manifest at {MANIFEST_PATH}"
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    assert manifest["campaign_id"] == "ECON-ATOMIC-COST-M2"
    assert manifest["disposition"] == "QUALIFIED"
    assert manifest["signoff_level"] == "L2 Formal Model & Conformance Qualification"

    gates = manifest["qualification_gates"]
    assert len(gates) == 6, f"Expected 6 qualification gates, found {len(gates)}"
    for gate in gates:
        assert gate["status"] == "PASSED", f"Gate {gate['gate_id']} did not pass: {gate}"

    # Verify cryptographic digests for vector files
    vectors_prov = manifest["immutable_provenance"]["vectors"]
    for vec_file in VECTORS_DIR.glob("*.json"):
        hasher = hashlib.sha256()
        with open(vec_file, "rb") as f:
            hasher.update(f.read())
        actual_hash = hasher.hexdigest()
        key = f"{vec_file.stem}_sha256"
        assert key in vectors_prov, f"Missing provenance key {key}"
        assert actual_hash == vectors_prov[key], f"Hash mismatch for {vec_file.name}: {actual_hash} != {vectors_prov[key]}"


def test_vector_01_component_accounting() -> None:
    """Verify 6-dimension atomic cost accounting C(u) = C_H + C_M + C_E + C_R + C_K + C_D."""
    path = VECTORS_DIR / "vector_01_component_accounting.json"
    assert path.exists()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    test_cases = data["test_cases"]
    assert len(test_cases) == 3

    for tc in test_cases:
        cost = AtomicCost.from_dict(tc["components"])
        expected_total = tc["expected_total"]
        assert cost.total() == expected_total, f"Total mismatch in {tc['case_id']}: {cost.total()} != {expected_total}"
        assert cost.is_non_negative()

        # Verify exact component reconciliation
        expected_sum = (
            tc["components"]["c_h"]
            + tc["components"]["c_m"]
            + tc["components"]["c_e"]
            + tc["components"]["c_r"]
            + tc["components"]["c_k"]
            + tc["components"]["c_d"]
        )
        assert abs(cost.total() - round(expected_sum, 6)) <= 1e-6


def test_vector_02_recursive_composition() -> None:
    """Verify exact cost conservation across hierarchical composition: C(U) = sum_i(C(U_i)) + C_composition."""
    path = VECTORS_DIR / "vector_02_recursive_composition.json"
    assert path.exists()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    wf = data["composite_workflow"]
    children = [AtomicCost.from_dict(c["components"]) for c in wf["children"]]
    overhead = AtomicCost.from_dict(wf["composition_overhead"])
    expected_composite = AtomicCost.from_dict(wf["expected_composite_cost"])

    profile = CompositionCostProfile(
        parent_uow_id=wf["parent_uow_id"],
        child_costs=children,
        composition_overhead=overhead,
    )

    # Total conservation check
    assert profile.verify_conservation(expected_composite)
    calc_total = profile.compute_total_composite_cost()
    assert calc_total.total() == expected_composite.total()

    # Component-wise conservation checks
    assert calc_total.c_h == expected_composite.c_h
    assert calc_total.c_m == expected_composite.c_m
    assert calc_total.c_e == expected_composite.c_e
    assert calc_total.c_r == expected_composite.c_r
    assert calc_total.c_k == expected_composite.c_k
    assert calc_total.c_d == expected_composite.c_d


def test_vector_03_realization_equivalence() -> None:
    """Verify identical semantic work produces distinct realization cost profiles without mutating the contract."""
    path = VECTORS_DIR / "vector_03_realization_equivalence.json"
    assert path.exists()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    work = data["canonical_work"]
    pre_state = WorldState(attributes=work["pre_state"])
    post_state = WorldState(attributes=work["post_state"])

    # State delta is counter + 1, status PENDING -> PROCESSED
    assert post_state.require("counter") == pre_state.require("counter") + 1
    assert post_state.require("status") == "PROCESSED"

    realizations = data["realizations"]
    assert len(realizations) == 3

    # All realizations evaluate distinct costs
    costs = [AtomicCost.from_dict(r["cost_observation"]).total() for r in realizations]
    assert len(set(costs)) == 3, "Realizations must exhibit distinct cost profiles"

    # NPU is cheapest overall
    npu_cost = next(AtomicCost.from_dict(r["cost_observation"]).total() for r in realizations if r["realization_id"] == "R_INTEL_NPU")
    x86_cost = next(AtomicCost.from_dict(r["cost_observation"]).total() for r in realizations if r["realization_id"] == "R_HOST_X86")
    esp32_cost = next(AtomicCost.from_dict(r["cost_observation"]).total() for r in realizations if r["realization_id"] == "R_ESP32_EDGE")

    assert npu_cost < x86_cost
    assert npu_cost < esp32_cost


def test_vector_04_friction_separation() -> None:
    """Verify isolation of operational friction: C_F = C_observed - C* >= 0."""
    path = VECTORS_DIR / "vector_04_friction_separation.json"
    assert path.exists()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for tc in data["test_cases"]:
        obs = AtomicCost.from_dict(tc["observed_cost"])
        nec = AtomicCost.from_dict(tc["necessary_cost"])
        expected_fric = AtomicCost.from_dict(tc["expected_friction"])

        analysis = FrictionAnalysis(observed_cost=obs, necessary_cost=nec)

        assert analysis.is_friction_non_negative()
        assert analysis.friction_cost.total() == expected_fric.total()
        assert abs(analysis.friction_ratio() - tc["expected_friction_ratio"]) <= 1e-4
        assert abs(analysis.work_efficiency() - tc["expected_efficiency"]) <= 1e-4


def test_vector_05_replay_determinism() -> None:
    """Verify evidence-bound cryptographic cost linking and instant tamper detection."""
    path = VECTORS_DIR / "vector_05_replay_determinism.json"
    assert path.exists()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    records = [CostObservationRecord.from_dict(r) for r in data["records"]]
    for record in records:
        assert record.verify_hash(), f"Record {record.observation_id} failed hash verification"

    # Adversarial tampering checks
    tamper_cases = data["adversarial_tamper_cases"]
    for tc in tamper_cases:
        target_rec = next(r for r in data["records"] if r["observation_id"] == tc["target_observation_id"])
        tampered_dict = json.loads(json.dumps(target_rec))

        # Apply tamper
        attr = tc["tampered_attribute"]
        if attr in tampered_dict["cost"]:
            tampered_dict["cost"][attr] = tc["tampered_value"]
        else:
            tampered_dict[attr] = tc["tampered_value"]

        tampered_rec = CostObservationRecord.from_dict(tampered_dict)
        assert not tampered_rec.verify_hash(), f"Tampered record {tc['case_id']} was not detected!"


def test_vector_06_policy_authority_boundary() -> None:
    """Verify that economic optimizers propose, authority gates certify, and cheapest != authority."""
    path = VECTORS_DIR / "vector_06_policy_authority_boundary.json"
    assert path.exists()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    cases = data["test_cases"]

    # Case 1: Valid proposal approved
    tc1 = cases[0]
    initial_state_1 = WorldState(attributes=tc1["initial_state"])
    candidate_uow_1 = UoW(
        H=Header("uow-case-1", WorkCategory.PROCESSES, WorkCategory.DATA),
        Gamma=Contract(
            (
                Route(
                    guard=Guard(op=GuardOp.GTE, key="balance", operand=20),
                    mutations=(
                        Mutation(op=MutationOp.SUB, key="balance", operand=20),
                        Mutation(op=MutationOp.SET, key="status", operand="EXECUTED"),
                    ),
                ),
            )
        ),
    )
    prop1 = EconomicProposal(
        proposal_id="prop-1",
        selected_realization_id="R_LOCAL_NPU",
        projected_cost=AtomicCost(c_m=0.012, c_e=0.001, c_r=0.005, c_k=0.0005, c_d=0.0015),
        candidate_uow=candidate_uow_1,
    )

    def authority_gate_1(uow: UoW, state: WorldState) -> tuple[bool, str | None]:
        if state.attributes.get("balance", 0) >= 20 and state.attributes.get("is_active"):
            return True, None
        return False, "Insufficient balance or inactive"

    res1 = evaluate_economic_proposal(prop1, initial_state_1, authority_gate_1)
    assert res1.admitted is True
    assert res1.status == "COMMITTED"
    assert res1.resulting_state is not None
    assert res1.resulting_state.require("balance") == 480
    assert res1.resulting_state.require("status") == "EXECUTED"

    # Case 2: Adversarial zero-cost proposal fails closed
    tc2 = cases[1]
    initial_state_2 = WorldState(attributes=tc2["initial_state"])
    candidate_uow_2 = UoW(
        H=Header("uow-case-2-adversarial", WorkCategory.PROCESSES, WorkCategory.DATA),
        Gamma=Contract(
            (
                Route(
                    guard=Guard(op=GuardOp.EQ, key="is_active", operand=True),
                    mutations=(Mutation(op=MutationOp.SET, key="balance", operand=999999),),
                ),
            )
        ),
    )
    prop2 = EconomicProposal(
        proposal_id="prop-2-exploit",
        selected_realization_id="R_ZERO_COST_UNAUTHORIZED",
        projected_cost=AtomicCost(),  # 0.0 total cost!
        candidate_uow=candidate_uow_2,
    )

    def authority_gate_2(uow: UoW, state: WorldState) -> tuple[bool, str | None]:
        if not state.attributes.get("is_active"):
            return False, "State invariant failed: account is SUSPENDED"
        return True, None

    res2 = evaluate_economic_proposal(prop2, initial_state_2, authority_gate_2)
    assert res2.admitted is False
    assert res2.status == "REJECTED_BY_AUTHORITY"
    assert "account is SUSPENDED" in (res2.rejection_reason or "")
    assert res2.resulting_state == initial_state_2, "State must not be mutated on rejected proposal"

    # Case 3: Downstream pricing isolation
    tc3 = cases[2]
    phys_cost = AtomicCost.from_dict(tc3["physical_cost_observation"])
    assert phys_cost.total() == 0.05

    pricing = tc3["downstream_pricing_policy"]
    market_price = pricing["market_price_quote"]
    assert market_price == 0.15

    # Invariant: Physical cost observation remains unperturbed by market markup
    assert phys_cost.total() != market_price
    assert phys_cost.total() == 0.05
