from __future__ import annotations

import pytest

from uow.composition.contract import ParentContract
from uow.composition.delegation import (
    AuthorityScope,
    ChildUoWSpec,
    DistributedDelegationNode,
)

from uow_shadow.adapters import delegation_adapter
from uow_shadow.closure import (
    META_AUTHORIZATION_HASH,
    META_DELEGATION_ACTOR_PREFIX,
    META_DELEGATION_CERT_PREFIX,
    META_DELEGATION_GENERATION_PREFIX,
    META_DELEGATION_SCOPE_PREFIX,
    execute_validated_delegation_registration,
    make_runtime_meta_state,
    make_validated_delegation_registration_uow,
)


def _contracts():
    parent = ParentContract(
        contract_id="parent-delegation",
        description="delegation closure parent",
        required_outputs=("result",),
    )
    child = ParentContract(
        contract_id="child-delegation",
        description="delegation closure child",
        required_outputs=("result",),
    )
    return parent, child


def _spec(child_contract, *, actor="delegate-A", scope=None, idempotent=True):
    return ChildUoWSpec(
        child_uow_id="child-1",
        sub_contract=child_contract,
        input_keys=("input",),
        expected_outputs=("result",),
        assigned_actor_id=actor,
        authority_scope=scope or AuthorityScope.read_only(),
        is_idempotent=idempotent,
    )


def _key(prefix: str) -> str:
    return f"{prefix}child-1"


def test_validated_delegation_registration_closes_over_native_uow():
    parent, child = _contracts()
    node = DistributedDelegationNode(
        "issuer",
        AuthorityScope.compute(),
        generation=1,
        delegation_ttl_sec=30.0,
    )
    spec = _spec(child)

    ok, violations = node.dispatch_delegation(
        parent,
        [spec],
        {"input": 1},
        current_ts=10.0,
    )
    assert ok, violations
    canonical_spec, cert = node.inflight_delegations["child-1"]

    conformance = delegation_adapter(
        node.authority_scope,
        cert,
        current_ts=15.0,
    )
    assert conformance.accepted

    uow = make_validated_delegation_registration_uow(cert, conformance)
    shadow_state = make_runtime_meta_state(
        active_graph_hash="delegation-meta",
        generation=node.generation,
        history_head="delegation-history",
        authorization_hash=cert.compute_hash(),
        cursor=uow.H.identity,
    )
    committed, evidence, certificate = execute_validated_delegation_registration(
        shadow_state,
        cert,
        conformance,
    )

    assert certificate.is_valid
    assert committed.get(_key(META_DELEGATION_CERT_PREFIX)) == cert.compute_hash()
    assert committed.get(_key(META_DELEGATION_ACTOR_PREFIX)) == canonical_spec.assigned_actor_id
    assert committed.get(_key(META_DELEGATION_GENERATION_PREFIX)) == cert.generation
    assert tuple(committed.get(_key(META_DELEGATION_SCOPE_PREFIX))) == cert.authority_scope.to_strings()
    assert evidence.certificate_hash == certificate.certificate_hash


def test_authority_inflation_cannot_be_lowered_as_delegation_registration():
    parent, child = _contracts()
    node = DistributedDelegationNode(
        "issuer",
        AuthorityScope.compute(),
        generation=1,
    )
    inflated_spec = _spec(child, scope=AuthorityScope.full())
    cert = node.issue_certificate(parent, inflated_spec, current_ts=10.0)

    conformance = delegation_adapter(
        node.authority_scope,
        cert,
        current_ts=11.0,
    )
    assert not conformance.accepted
    assert any("AUTHORITY_INFLATION_REJECTED" in v for v in conformance.violations)

    with pytest.raises(ValueError, match="Rejected delegation conformance"):
        make_validated_delegation_registration_uow(cert, conformance)


def test_idempotent_failover_certificate_can_replace_registered_delegation():
    parent, child = _contracts()
    node = DistributedDelegationNode(
        "issuer",
        AuthorityScope.compute(),
        generation=1,
        delegation_ttl_sec=30.0,
    )
    spec = _spec(child, actor="delegate-A", idempotent=True)
    ok, violations = node.dispatch_delegation(
        parent,
        [spec],
        {"input": 1},
        current_ts=10.0,
    )
    assert ok, violations
    _, old_cert = node.inflight_delegations["child-1"]

    old_conf = delegation_adapter(node.authority_scope, old_cert, current_ts=11.0)
    assert old_conf.accepted
    old_uow = make_validated_delegation_registration_uow(old_cert, old_conf)
    state = make_runtime_meta_state(
        active_graph_hash="delegation-meta",
        generation=node.generation,
        history_head="delegation-history",
        authorization_hash=old_cert.compute_hash(),
        cursor=old_uow.H.identity,
    )
    state, old_evidence, _ = execute_validated_delegation_registration(
        state,
        old_cert,
        old_conf,
    )

    failover_ok, new_cert, reason = node.handle_delegate_failure(
        "child-1",
        parent,
        "delegate-B",
        current_ts=20.0,
    )
    assert failover_ok, reason
    assert new_cert is not None
    canonical_spec, canonical_cert = node.inflight_delegations["child-1"]
    assert canonical_cert.compute_hash() == new_cert.compute_hash()
    assert canonical_spec.assigned_actor_id == "delegate-B"

    new_conf = delegation_adapter(node.authority_scope, new_cert, current_ts=21.0)
    assert new_conf.accepted
    new_uow = make_validated_delegation_registration_uow(new_cert, new_conf)
    state = state.with_attribute(META_AUTHORIZATION_HASH, new_cert.compute_hash()).with_cursor(
        new_uow.H.identity
    )
    committed, evidence, certificate = execute_validated_delegation_registration(
        state,
        new_cert,
        new_conf,
        step_number=2,
        prev_evidence_hash=old_evidence.record_hash,
    )

    assert certificate.is_valid
    assert committed.get(_key(META_DELEGATION_CERT_PREFIX)) == new_cert.compute_hash()
    assert committed.get(_key(META_DELEGATION_ACTOR_PREFIX)) == "delegate-B"
    assert evidence.prev_evidence_hash == old_evidence.record_hash
    assert evidence.certificate_hash == certificate.certificate_hash


def test_non_idempotent_delegate_failure_does_not_create_replacement_authority():
    parent, child = _contracts()
    node = DistributedDelegationNode(
        "issuer",
        AuthorityScope.compute(),
        generation=1,
    )
    spec = _spec(child, actor="delegate-A", idempotent=False)

    ok, violations = node.dispatch_delegation(
        parent,
        [spec],
        {"input": 1},
        current_ts=10.0,
    )
    assert ok, violations

    failover_ok, new_cert, reason = node.handle_delegate_failure(
        "child-1",
        parent,
        "delegate-B",
        current_ts=20.0,
    )
    assert not failover_ok
    assert new_cert is None
    assert "NON_IDEMPOTENT_DELEGATION_ABORT" in reason
