from __future__ import annotations

import pytest

from uow.composition.convergence import (
    AuthoritativeHistory,
    HistoryEntry,
    HistoryEntryKind,
    MultiOrchestratorCluster,
)
from uow.composition.delegation import AuthorityScope, DistributedDelegationNode
from uow.composition.fabric import DistributedActorFabric

from uow_shadow.closure import (
    META_AUTHORIZATION_HASH,
    META_CANONICAL_HISTORY_DIGEST,
    META_CANONICAL_HISTORY_ENTRIES,
    META_CANONICAL_HISTORY_TIP_HASH,
    META_CANONICAL_HISTORY_TIP_SEQUENCE,
    execute_verified_history_reconciliation,
    make_runtime_meta_state,
    make_verified_history_reconciliation_uow,
    serialize_authoritative_history,
)


GENESIS = "GENESIS_0000000000000000000000000000000000000000000000000000000000000000"


def _canonical_history() -> AuthoritativeHistory:
    h = AuthoritativeHistory()
    e0 = HistoryEntry(
        entry_id="e0",
        sequence_number=0,
        prev_hash=GENESIS,
        kind=HistoryEntryKind.CHILD_DELEGATION,
        author_node_id="A",
        generation=1,
        payload={"child": "c1"},
    )
    ok, reason = h.append(e0)
    assert ok, reason

    e1 = HistoryEntry(
        entry_id="e1",
        sequence_number=1,
        prev_hash=e0.compute_hash(),
        kind=HistoryEntryKind.AUTHORITATIVE_COMMIT,
        author_node_id="A",
        generation=1,
        payload={"result": "ok"},
        quorum_signatures=("AUTH",),
    )
    ok, reason = h.append(e1)
    assert ok, reason
    assert h.verify_integrity()
    return h


def _cluster() -> MultiOrchestratorCluster:
    nodes = {
        "A": DistributedDelegationNode("A", AuthorityScope.full()),
        "B": DistributedDelegationNode("B", AuthorityScope.full()),
    }
    return MultiOrchestratorCluster(
        nodes,
        DistributedActorFabric(),
        authority_keys={"AUTH"},
    )


def test_verified_history_reconciliation_application_closes_over_native_uow():
    canonical = _canonical_history()
    cluster = _cluster()

    ok, reason = cluster.reconcile_to_canonical(canonical)
    assert ok, reason
    canonical_digest = canonical.state_digest()
    assert all(
        h.state_digest() == canonical_digest
        for h in cluster.node_histories.values()
    )

    uow = make_verified_history_reconciliation_uow(canonical)
    shadow_state = make_runtime_meta_state(
        active_graph_hash="history-meta",
        history_head="old-history",
        authorization_hash=canonical_digest,
        cursor=uow.H.identity,
    )
    committed, evidence, certificate = execute_verified_history_reconciliation(
        shadow_state,
        canonical,
    )

    assert certificate.is_valid
    assert committed.get(META_CANONICAL_HISTORY_DIGEST) == canonical_digest
    assert committed.get(META_CANONICAL_HISTORY_TIP_HASH) == canonical.tip_hash()
    assert committed.get(META_CANONICAL_HISTORY_TIP_SEQUENCE) == canonical.tip_sequence()
    assert tuple(committed.get(META_CANONICAL_HISTORY_ENTRIES)) == serialize_authoritative_history(canonical)
    assert evidence.certificate_hash == certificate.certificate_hash


def test_invalid_history_cannot_be_lowered_or_reconciled():
    bad_entry = HistoryEntry(
        entry_id="bad",
        sequence_number=0,
        prev_hash="not-genesis",
        kind=HistoryEntryKind.AUTHORITATIVE_COMMIT,
        author_node_id="A",
        generation=1,
        payload={"bad": True},
        quorum_signatures=("AUTH",),
    )
    invalid = AuthoritativeHistory((bad_entry,))
    assert not invalid.verify_integrity()

    cluster = _cluster()
    ok, reason = cluster.reconcile_to_canonical(invalid)
    assert not ok
    assert "CANONICAL_HISTORY_INTEGRITY_FAILURE" in reason

    with pytest.raises(ValueError, match="Invalid canonical history"):
        make_verified_history_reconciliation_uow(invalid)


def test_history_adoption_fails_closed_when_application_context_does_not_match():
    canonical = _canonical_history()
    uow = make_verified_history_reconciliation_uow(canonical)
    shadow_state = make_runtime_meta_state(
        active_graph_hash="history-meta",
        history_head="old-history",
        authorization_hash="wrong-history-digest",
        cursor=uow.H.identity,
    )

    with pytest.raises(RuntimeError, match="No applicable route"):
        execute_verified_history_reconciliation(shadow_state, canonical)

    assert shadow_state.get(META_AUTHORIZATION_HASH) == "wrong-history-digest"
    assert shadow_state.get(META_CANONICAL_HISTORY_DIGEST) is None
