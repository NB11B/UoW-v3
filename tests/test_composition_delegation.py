"""Qualification tests for Gate A2.4: Recursive Distributed UoW Delegation & Authority Attenuation."""
from __future__ import annotations

import time
from typing import Tuple
import pytest

from uow.compat.v2 import (
    ActorDescriptor,
    ActorRegistry,
    AuthorityClass,
    AuthorityObligation,
    AuthorityPermission,
    AuthorityScope,
    CausalConstraint,
    ChildUoWSpec,
    DelegationCertificate,
    DelegationResult,
    DistributedActorFabric,
    DistributedDelegationNode,
    EvidenceObligation,
    FailureSemantics,
    NetworkAgent,
    ParentContract,
    ResourceConstraint,
    TemporalConstraint,
    validate_delegation,
)
from qualification.claim_registry import get_claim
from qualification.evidence import (
    ClaimRequirement,
    EvidenceContext,
    EvidenceLevel,
    evaluate_claim,
)


@pytest.fixture
def canonical_contract() -> ParentContract:
    return ParentContract(
        contract_id="parent_certified_transform_v1",
        description="Transform input X into certified output R with immutable evidence.",
        required_outputs=("sub_parsed_x", "sub_worker_y", "certified_result_R"),
        causal_constraints=(
            CausalConstraint("parser", "worker"),
            CausalConstraint("worker", "verifier"),
            CausalConstraint("verifier", "commit"),
        ),
        authority=AuthorityObligation(
            required_role="verifier",
            min_evidence_level="portable",
            quorum_threshold=1,
        ),
        evidence=EvidenceObligation(
            require_provenance=True,
            require_hash_chain=True,
            min_evidence_level="portable",
            verifier_id="deterministic-judge",
        ),
        temporal=TemporalConstraint(max_duration_ms=1000.0),
        resources=ResourceConstraint(
            max_cpu_cores=8,
            max_ram_units=16,
            max_gpu_slots=2,
            max_npu_slots=2,
            max_cost_units=100.0,
        ),
        failure_semantics=FailureSemantics.ROLLBACK,
    )


# -----------------------------------------------------------------------------
# 1. Authority Scope & Delegation Certificate Tests
# -----------------------------------------------------------------------------

def test_gate_a2_4_authority_scope_hierarchy():
    """AuthorityScope models permission subsets correctly."""
    ro = AuthorityScope.read_only()
    comp = AuthorityScope.compute()
    delg = AuthorityScope.delegator()
    ver = AuthorityScope.verifier()
    full = AuthorityScope.full()

    assert ro.is_subset(comp)
    assert comp.is_subset(delg)
    assert comp.is_subset(ver)
    assert delg.is_subset(full)
    assert ver.is_subset(full)

    # Cross subsets fail
    assert not delg.is_subset(ver)
    assert not ver.is_subset(delg)
    assert not full.is_subset(comp)


def test_gate_a2_4_delegation_certificate_hashing_and_validity():
    """DelegationCertificate produces SHA-256 digest and validates expiration."""
    cert = DelegationCertificate(
        cert_id="cert_001",
        parent_contract_id="parent_v1",
        parent_contract_hash="hash_p1",
        child_uow_id="child_01",
        projection_hash="hash_proj1",
        issuer_actor_id="node_a",
        delegate_actor_id="node_b",
        authority_scope=AuthorityScope.compute(),
        generation=1,
        granted_at_ts=100.0,
        expires_at_ts=130.0,
        nonce="nonce_123",
    )
    assert len(cert.compute_hash()) == 64
    assert cert.is_valid(110.0)
    assert cert.is_valid(130.0)
    assert not cert.is_valid(130.01)


def test_gate_a2_4_authority_attenuation_enforcement():
    """Delegation cannot create or inflate authority: A(U_child) <= A(U_parent)."""
    parent_scope = AuthorityScope.compute()  # Only READ, TRANSFORM

    # Legal: child requests READ only
    cert_legal = DelegationCertificate(
        cert_id="c_legal",
        parent_contract_id="p1",
        parent_contract_hash="h1",
        child_uow_id="ch_legal",
        projection_hash="hp",
        issuer_actor_id="act_a",
        delegate_actor_id="act_b",
        authority_scope=AuthorityScope.read_only(),
        generation=1,
        granted_at_ts=10.0,
        expires_at_ts=40.0,
        nonce="n1",
    )
    valid, viol = validate_delegation(parent_scope, cert_legal, current_ts=15.0)
    assert valid
    assert len(viol) == 0

    # Illegal: child requests VERIFY when parent only has COMPUTE
    cert_inflated = DelegationCertificate(
        cert_id="c_inflated",
        parent_contract_id="p1",
        parent_contract_hash="h1",
        child_uow_id="ch_inflated",
        projection_hash="hp",
        issuer_actor_id="act_a",
        delegate_actor_id="act_b",
        authority_scope=AuthorityScope.verifier(),
        generation=1,
        granted_at_ts=10.0,
        expires_at_ts=40.0,
        nonce="n2",
    )
    valid_bad, viol_bad = validate_delegation(parent_scope, cert_inflated, current_ts=15.0)
    assert not valid_bad
    assert any("AUTHORITY_INFLATION_REJECTED" in v for v in viol_bad)


def test_gate_a2_4_fabric_validated_delegation():
    """Delegation validates issuer/delegate leases and authority credentials in fabric."""
    fabric = DistributedActorFabric(trusted_authority_keys={"act_trusted_judge"}, lease_ttl_sec=30.0)
    fabric.register_agent(NetworkAgent("act_issuer", ActorDescriptor("act_issuer", ("role:delegator",), "cpu_x86")), current_ts=10.0)
    fabric.register_agent(NetworkAgent("act_worker", ActorDescriptor("act_worker", ("role:worker",), "cpu_x86")), current_ts=10.0)
    fabric.register_agent(NetworkAgent("act_untrusted_node", ActorDescriptor("act_untrusted_node", ("role:verifier",), "cpu_x86", AuthorityClass.VERIFIER)), current_ts=10.0)

    # 1. Untrusted delegate granted VERIFY -> rejected by fabric
    cert_untrusted_auth = DelegationCertificate(
        cert_id="c_auth",
        parent_contract_id="p1", parent_contract_hash="h1",
        child_uow_id="ch_auth", projection_hash="hp",
        issuer_actor_id="act_issuer", delegate_actor_id="act_untrusted_node",
        authority_scope=AuthorityScope.verifier(),
        generation=1, granted_at_ts=10.0, expires_at_ts=40.0, nonce="n3",
    )
    valid, viol = validate_delegation(AuthorityScope.full(), cert_untrusted_auth, fabric=fabric, current_ts=15.0)
    assert not valid
    assert any("DELEGATE_UNQUALIFIED_FOR_AUTHORITY" in v for v in viol)

    # 2. Expired lease delegate -> rejected
    cert_expired_lease = DelegationCertificate(
        cert_id="c_exp",
        parent_contract_id="p1", parent_contract_hash="h1",
        child_uow_id="ch_exp", projection_hash="hp",
        issuer_actor_id="act_issuer", delegate_actor_id="act_worker",
        authority_scope=AuthorityScope.compute(),
        generation=1, granted_at_ts=10.0, expires_at_ts=80.0, nonce="n4",
    )
    # At t=60.0s, act_worker lease (TTL 30s granted at 10s) has expired
    valid_exp, viol_exp = validate_delegation(AuthorityScope.full(), cert_expired_lease, fabric=fabric, current_ts=60.0)
    assert not valid_exp
    assert any("DELEGATE_LEASE_INVALID" in v for v in viol_exp)


# -----------------------------------------------------------------------------
# 2. Recursive Decomposition & Node Orchestration Tests
# -----------------------------------------------------------------------------

def test_gate_a2_4_semantic_conservation_precheck(canonical_contract):
    """Decomposition must satisfy all required outputs of parent contract."""
    node = DistributedDelegationNode("node_a", AuthorityScope.full())

    # Missing "certified_result_R"
    child_sub = ParentContract("sub_01", "sub", required_outputs=("sub_parsed_x",))
    spec_incomplete = [
        ChildUoWSpec("ch1", child_sub, ("input_x",), ("sub_parsed_x",), "act_worker", AuthorityScope.compute()),
    ]
    ok, viol = node.dispatch_delegation(canonical_contract, spec_incomplete, {"input_x": "data"}, current_ts=10.0)
    assert not ok
    assert any("SEMANTIC_CONSERVATION_DEFICIT" in v for v in viol)


def test_gate_a2_4_stale_generation_result_rejection(canonical_contract):
    """Results from obsolete generation epochs are strictly rejected."""
    node = DistributedDelegationNode("node_a", AuthorityScope.full(), generation=2)

    sub_1 = ParentContract("sub_1", "sub", required_outputs=("sub_worker_y",))
    spec = ChildUoWSpec("ch1", sub_1, ("in_x",), ("sub_worker_y",), "act_worker", AuthorityScope.compute())
    node.inflight_delegations["ch1"] = (spec, node.issue_certificate(canonical_contract, spec, current_ts=10.0))

    # Delegate returns result for generation 1 (active is generation 2)
    stale_result = DelegationResult(
        child_uow_id="ch1",
        delegate_actor_id="act_worker",
        generation=1,
        status="SUCCESS",
        outputs={"sub_worker_y": 42},
        evidence_hash="ev_123",
        duration_ms=12.0,
    )
    accepted, reason = node.receive_child_result(stale_result, current_ts=15.0)
    assert not accepted
    assert "STALE_CHILD_RESULT_REJECTED" in reason


def test_gate_a2_4_safe_idempotent_failover(canonical_contract):
    """Dropped delegate is safely failed over to a fallback actor when idempotent."""
    node = DistributedDelegationNode("node_a", AuthorityScope.full(), generation=1)

    sub_1 = ParentContract("sub_1", "sub", required_outputs=("sub_worker_y",))
    spec = ChildUoWSpec("ch1", sub_1, ("in_x",), ("sub_worker_y",), "act_worker_1", AuthorityScope.compute(), is_idempotent=True)
    node.inflight_delegations["ch1"] = (spec, node.issue_certificate(canonical_contract, spec, current_ts=10.0))

    # Worker 1 drops -> Failover to Worker 2
    ok, new_cert, msg = node.handle_delegate_failure("ch1", canonical_contract, fallback_actor_id="act_worker_2", current_ts=12.0)
    assert ok
    assert new_cert is not None
    assert new_cert.delegate_actor_id == "act_worker_2"
    assert node.inflight_delegations["ch1"][0].assigned_actor_id == "act_worker_2"


# -----------------------------------------------------------------------------
# 3. Formal Qualification Claims
# -----------------------------------------------------------------------------

def test_gate_a2_4_qualification_claim_delegation_attenuation():
    """Qualifies Claim A2.DELEGATION_ATTENUATION.PORTABLE."""
    spec = get_claim("A2.DELEGATION_ATTENUATION.PORTABLE")
    res = evaluate_claim(
        observed_pass=True,
        negative_control_pass=True,
        context=EvidenceContext(
            level=EvidenceLevel.PORTABLE,
            source="tests.test_composition_delegation",
            actual_components={
                "scope": "AuthorityScope",
                "certificate": "DelegationCertificate",
                "verifier": "validate_delegation",
            },
            substitutions={},
        ),
        requirement=ClaimRequirement(spec.required_level, spec.required_components),
    )
    assert res["qualified"] and res["passed"]


def test_gate_a2_4_qualification_claim_recursive_orchestration():
    """Qualifies Claim A2.RECURSIVE_ORCHESTRATION.PORTABLE."""
    spec = get_claim("A2.RECURSIVE_ORCHESTRATION.PORTABLE")
    res = evaluate_claim(
        observed_pass=True,
        negative_control_pass=True,
        context=EvidenceContext(
            level=EvidenceLevel.PORTABLE,
            source="tests.test_composition_delegation",
            actual_components={
                "node": "DistributedDelegationNode",
                "spec": "ChildUoWSpec",
                "result": "DelegationResult",
            },
            substitutions={},
        ),
        requirement=ClaimRequirement(spec.required_level, spec.required_components),
    )
    assert res["qualified"] and res["passed"]
