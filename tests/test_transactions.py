"""Comprehensive tests for Optimistic Concurrency Control (OCC) and Sequencer / WAL."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import pytest

from uow import (
    DeterministicSequencer,
    EvidenceLedger,
    EvidenceRecord,
    Guard,
    GuardOp,
    HazardType,
    Mutation,
    MutationOp,
    Proposal,
    Route,
    Successor,
    TransactionConflictError,
    WALSequencer,
    WorldState,
    certify,
    create_transaction_descriptor,
    make_uow,
    propose,
    validate_occ,
    verify_commit_bindings,
)
from uow.state import canonical_json


def _make_task(uow_id: str, write_key: str, write_val: int, read_key: str | None = None):
    muts = [Mutation(MutationOp.SET, write_key, write_val)]
    if read_key:
        guard = Guard(GuardOp.EXISTS, read_key)
    else:
        guard = Guard(GuardOp.ALWAYS)
    return make_uow(
        uow_id,
        [Route(guard=guard, mutations=tuple(muts), successor=Successor.halt())],
    )


def test_gate_u12_3_read_write_hazard_detection():
    """If U_reader reads what U_writer concurrently modifies, U_reader fails OCC."""
    u_writer = _make_task("writer", write_key="r0", write_val=5)
    u_reader = _make_task("reader", write_key="r1", write_val=10, read_key="r0")

    base_state = WorldState(attributes={"r0": 0, "r1": 0})
    sequencer = DeterministicSequencer(base_state)

    # Both propose against base_state
    prop_w = propose(u_writer, base_state)
    tx_w = create_transaction_descriptor(u_writer, base_state)
    cert_w = certify(u_writer, base_state, prop_w)

    prop_r = propose(u_reader, base_state)
    tx_r = create_transaction_descriptor(u_reader, base_state)
    cert_r = certify(u_reader, base_state, prop_r)

    # Writer commits first
    s_committed, ev_w = sequencer.commit(u_writer, prop_w, tx_w, cert_w)
    assert s_committed.require("r0") == 5

    # Reader OCC validation against updated state must detect READ_WRITE_HAZARD
    is_valid, hazard, details = validate_occ(sequencer.current_state, tx_r)
    assert not is_valid
    assert hazard == HazardType.READ_WRITE_HAZARD
    assert "r0" in (details or "")

    with pytest.raises(TransactionConflictError) as exc_info:
        sequencer.commit(u_reader, prop_r, tx_r, cert_r)
    assert exc_info.value.hazard_type == HazardType.READ_WRITE_HAZARD


def test_gate_u12_4_write_write_hazard_detection():
    """If two concurrent transactions write to the same key, second fails WRITE_WRITE_HAZARD."""
    u_w1 = _make_task("w1", write_key="r0", write_val=10)
    u_w2 = _make_task("w2", write_key="r0", write_val=20)

    base_state = WorldState(attributes={"r0": 0})
    sequencer = DeterministicSequencer(base_state)

    prop_1 = propose(u_w1, base_state)
    tx_1 = create_transaction_descriptor(u_w1, base_state)
    cert_1 = certify(u_w1, base_state, prop_1)

    prop_2 = propose(u_w2, base_state)
    tx_2 = create_transaction_descriptor(u_w2, base_state)
    cert_2 = certify(u_w2, base_state, prop_2)

    # W1 commits
    sequencer.commit(u_w1, prop_1, tx_1, cert_1)

    # W2 fails OCC
    is_valid, hazard, details = validate_occ(sequencer.current_state, tx_2)
    assert not is_valid
    assert hazard == HazardType.WRITE_WRITE_HAZARD
    assert "r0" in (details or "")

    with pytest.raises(TransactionConflictError) as exc_info:
        sequencer.commit(u_w2, prop_2, tx_2, cert_2)
    assert exc_info.value.hazard_type == HazardType.WRITE_WRITE_HAZARD


def test_gate_u12_10_hidden_coupling_hazard_detection():
    """Coupled state evolution must trigger HIDDEN_COUPLING_HAZARD."""
    # Attribute 'y' is coupled to 'x'
    base_state = WorldState(
        attributes={
            "x": 100,
            "y": 200,
            "__couplings__": {"y": ["x"]},
        }
    )
    sequencer = DeterministicSequencer(base_state)

    # Tx1 modifies 'x'
    u_mod_x = _make_task("mod_x", write_key="x", write_val=105)
    # Tx2 modifies 'y' (which is coupled to 'x')
    u_mod_y = _make_task("mod_y", write_key="y", write_val=205)

    prop_x = propose(u_mod_x, base_state)
    tx_x = create_transaction_descriptor(u_mod_x, base_state)
    cert_x = certify(u_mod_x, base_state, prop_x)

    prop_y = propose(u_mod_y, base_state)
    tx_y = create_transaction_descriptor(u_mod_y, base_state)
    cert_y = certify(u_mod_y, base_state, prop_y)

    # Commit Tx1 (updates 'x')
    sequencer.commit(u_mod_x, prop_x, tx_x, cert_x)

    # Tx2 should fail due to hidden coupling invariant
    is_valid, hazard, details = validate_occ(sequencer.current_state, tx_y)
    assert not is_valid
    assert hazard == HazardType.HIDDEN_COUPLING_HAZARD
    assert "coupled" in (details or "").lower()


def test_zero_partial_mutation_on_conflict():
    """When a transaction aborts due to conflict, the authoritative state is completely untouched."""
    base_state = WorldState(attributes={"r0": 0, "r1": 10})
    sequencer = DeterministicSequencer(base_state)

    # Task commits and bumps version of r0
    u_first = _make_task("first", write_key="r0", write_val=99)
    prop_1 = propose(u_first, base_state)
    tx_1 = create_transaction_descriptor(u_first, base_state)
    cert_1 = certify(u_first, base_state, prop_1)
    sequencer.commit(u_first, prop_1, tx_1, cert_1)

    state_before_abort = sequencer.current_state
    hash_before_abort = state_before_abort.state_hash
    ledger_len_before = len(sequencer.ledger.records)

    # Conflicting task attempting to write r0 and r1
    u_conflict = make_uow(
        "conflict",
        [
            Route(
                guard=Guard(GuardOp.ALWAYS),
                mutations=(
                    Mutation(MutationOp.SET, "r0", 500),
                    Mutation(MutationOp.SET, "r1", 777),
                ),
                successor=Successor.halt(),
            )
        ],
    )
    prop_c = propose(u_conflict, base_state)
    tx_c = create_transaction_descriptor(u_conflict, base_state)
    cert_c = certify(u_conflict, base_state, prop_c)

    with pytest.raises(TransactionConflictError):
        sequencer.commit(u_conflict, prop_c, tx_c, cert_c)

    # Assert 100% clean state
    assert sequencer.current_state.state_hash == hash_before_abort
    assert sequencer.current_state.require("r0") == 99
    assert sequencer.current_state.require("r1") == 10
    assert len(sequencer.ledger.records) == ledger_len_before


def test_wal_sequencer_commit_and_crash_recovery():
    """WALSequencer persists commits to append-only log and recovers exact state and ledger."""
    with tempfile.TemporaryDirectory() as tmpdir:
        wal_path = Path(tmpdir) / "test.wal"

        base_state = WorldState(attributes={"counter": 0, "status_flag": "init"})
        wal_seq = WALSequencer(wal_path, base_state)

        u1 = _make_task("t1", write_key="counter", write_val=1)
        p1 = propose(u1, wal_seq.current_state)
        tx1 = create_transaction_descriptor(u1, wal_seq.current_state)
        c1 = certify(u1, wal_seq.current_state, p1)
        wal_seq.commit(u1, p1, tx1, c1)

        u2 = _make_task("t2", write_key="counter", write_val=2)
        p2 = propose(u2, wal_seq.current_state)
        tx2 = create_transaction_descriptor(u2, wal_seq.current_state)
        c2 = certify(u2, wal_seq.current_state, p2)
        final_state, _ = wal_seq.commit(u2, p2, tx2, c2)

        assert final_state.require("counter") == 2
        assert wal_path.exists()

        # Crash recovery from WAL
        recovered_state, recovered_ledger = WALSequencer.recover(wal_path)
        assert recovered_state.state_hash == final_state.state_hash
        assert recovered_state.require("counter") == 2
        assert recovered_state.sequence == final_state.sequence
        assert recovered_ledger.root_hash() == wal_seq.ledger.root_hash()
        assert len(recovered_ledger.records) == 2
        assert recovered_ledger.verify_integrity()


# ===========================================================================
# Pass 2.1 Hardening: Multi-Object Cryptographic Cross-Binding Tests
# ===========================================================================

def test_binding_reuse_certificate_from_another_uow_rejected():
    """Attempting to commit UoW A with a certificate from UoW B is rejected."""
    s = WorldState(attributes={"x": 0})
    u_a = _make_task("task_A", write_key="x", write_val=1)
    u_b = _make_task("task_B", write_key="x", write_val=2)

    prop_a = propose(u_a, s)
    tx_a = create_transaction_descriptor(u_a, s)

    prop_b = propose(u_b, s)
    cert_b = certify(u_b, s, prop_b)

    seq = DeterministicSequencer(s)
    with pytest.raises(ValueError, match="Certificate identity mismatch"):
        seq.commit(u_a, prop_a, tx_a, cert_b)


def test_binding_certificate_proposal_hash_mismatch_rejected():
    """If proposed state in certificate does not match proposal, commit is rejected."""
    s = WorldState(attributes={"x": 0})
    u = _make_task("task_1", write_key="x", write_val=1)

    prop = propose(u, s)
    tx = create_transaction_descriptor(u, s)
    cert = certify(u, s, prop)

    # Tamper proposal with a different state using replace
    tampered_prop = replace(prop, proposed_state=s.with_attribute("x", 999))

    seq = DeterministicSequencer(s)
    with pytest.raises(ValueError, match="does not match proposed state hash"):
        seq.commit(u, tampered_prop, tx, cert)


def test_binding_transaction_proposal_hash_mismatch_rejected():
    """If proposed state in transaction does not match proposal, commit is rejected."""
    s = WorldState(attributes={"x": 0})
    u = _make_task("task_1", write_key="x", write_val=1)

    prop = propose(u, s)
    tx = create_transaction_descriptor(u, s)
    cert = certify(u, s, prop)

    # Tamper transaction proposed state hash
    tampered_tx = replace(tx, proposed_state_hash="0" * 64)

    seq = DeterministicSequencer(s)
    with pytest.raises(ValueError, match="Transaction descriptor does not match proposed state hash"):
        seq.commit(u, prop, tampered_tx, cert)


def test_binding_stale_pre_state_certificate_rejected():
    """Certificate computed against old pre-state hash is rejected."""
    s0 = WorldState(attributes={"x": 0})
    u = _make_task("task_1", write_key="x", write_val=1)

    prop0 = propose(u, s0)
    cert0 = certify(u, s0, prop0)

    # State advances
    s1 = s0.with_attribute("y", 10).advance_sequence()
    prop1 = propose(u, s1)
    tx1 = create_transaction_descriptor(u, s1)

    seq = DeterministicSequencer(s1)
    with pytest.raises(ValueError, match="Certificate is not bound to proposal pre-state"):
        seq.commit(u, prop1, tx1, cert0)


def test_binding_route_and_successor_divergence_rejected():
    """Certificate and proposal must agree on route index, successor, and halt decision."""
    s = WorldState(attributes={"x": 0})
    u = _make_task("task_1", write_key="x", write_val=1)
    prop = propose(u, s)
    tx = create_transaction_descriptor(u, s)
    cert = certify(u, s, prop)

    # Tamper route index
    tampered_cert = replace(cert, selected_route_index=99)

    seq = DeterministicSequencer(s)
    with pytest.raises(ValueError, match="Route index divergence"):
        seq.commit(u, prop, tx, tampered_cert)


# ===========================================================================
# Pass 2.1 Hardening: Hidden-Coupling Nonzero Initial Version Accuracy
# ===========================================================================

def test_hidden_coupling_nonzero_initial_version_no_false_conflict():
    """If coupled key x already has version n > 0 at proposal time, and DOES NOT evolve, no false conflict occurs."""
    s = WorldState(
        attributes={
            "x": 100,
            "y": 200,
            "__versions__": {"x": 5, "y": 1},
            "__couplings__": {"y": ["x"]},
        }
    )
    u = _make_task("task_mod_y", write_key="y", write_val=205)

    tx = create_transaction_descriptor(u, s)
    # tx.coupled_versions must capture x at version 5
    assert tx.coupled_versions.get("x") == 5

    # OCC validation against SAME state must succeed (no false conflict!)
    is_valid, hazard, details = validate_occ(s, tx)
    assert is_valid is True
    assert hazard is None


def test_hidden_coupling_actual_concurrent_evolution_detected():
    """If coupled key x evolves concurrently after snapshot, conflict is detected."""
    s = WorldState(
        attributes={
            "x": 100,
            "y": 200,
            "__versions__": {"x": 5, "y": 1},
            "__couplings__": {"y": ["x"]},
        }
    )
    u = _make_task("task_mod_y", write_key="y", write_val=205)
    tx = create_transaction_descriptor(u, s)

    # Another commit advances x to version 6
    s_evolved = s.with_attribute("x", 101).with_attribute(
        "__versions__", {"x": 6, "y": 1}
    )

    is_valid, hazard, details = validate_occ(s_evolved, tx)
    assert is_valid is False
    assert hazard == HazardType.HIDDEN_COUPLING_HAZARD
    assert "coupled invariant violated" in (details or "").lower()


# ===========================================================================
# Pass 2.1 Hardening: Crash Recovery Matrix & True Write-Ahead Order
# ===========================================================================

def test_crash_matrix_1_before_wal_append():
    """Crash before WAL append recovers old state and old ledger root."""
    with tempfile.TemporaryDirectory() as tmpdir:
        wal_path = Path(tmpdir) / "test.wal"
        s0 = WorldState(attributes={"cnt": 0})
        _wal = WALSequencer(wal_path, s0)

        # State in memory before any commit attempt
        rec_s, rec_ledger = WALSequencer.recover(wal_path)
        assert rec_s.state_hash == s0.state_hash
        assert len(rec_ledger.records) == 0


def test_crash_matrix_2_incomplete_wal_append_torn_tail():
    """Crash during WAL append (torn tail / partial line at EOF) is ignored; recovers last valid state."""
    with tempfile.TemporaryDirectory() as tmpdir:
        wal_path = Path(tmpdir) / "test.wal"
        s0 = WorldState(attributes={"cnt": 0})
        wal = WALSequencer(wal_path, s0)

        u1 = _make_task("t1", write_key="cnt", write_val=1)
        p1 = propose(u1, wal.current_state)
        tx1 = create_transaction_descriptor(u1, wal.current_state)
        c1 = certify(u1, wal.current_state, p1)
        wal.commit(u1, p1, tx1, c1)

        # Simulate crash during next commit writing partial bytes to WAL
        with open(wal_path, "ab") as f:
            f.write(b'{"type": "COMMIT", "step_number": 2, "post_state_hash": "corrupt_partial_json')

        # Recovery should ignore torn tail and cleanly recover commit 1
        rec_s, rec_ledger = WALSequencer.recover(wal_path, ignore_torn_tail=True)
        assert rec_s.require("cnt") == 1
        assert len(rec_ledger.records) == 1
        assert rec_ledger.verify_integrity()


def test_crash_matrix_3_after_durable_wal_before_memory_publish():
    """Crash after durable WAL write but before in-memory publish recovers the NEW state & NEW ledger."""
    with tempfile.TemporaryDirectory() as tmpdir:
        wal_path = Path(tmpdir) / "test.wal"
        s0 = WorldState(attributes={"cnt": 0})
        wal = WALSequencer(wal_path, s0)

        u1 = _make_task("t1", write_key="cnt", write_val=1)
        p1 = propose(u1, wal.current_state)
        tx1 = create_transaction_descriptor(u1, wal.current_state)
        c1 = certify(u1, wal.current_state, p1)

        # Intercept before memory publish by simulating crash right after _write_entry
        comm_state = s0.with_attribute("cnt", 1).advance_sequence()
        ev = EvidenceRecord(
            step_number=1,
            uow_id="t1",
            source_category=u1.H.source_category.value,
            target_category=u1.H.target_category.value,
            pre_state_hash=s0.state_hash,
            selected_route_index=0,
            proposed_state_hash=p1.proposed_state.state_hash,
            certificate_hash=c1.certificate_hash,
            post_state_hash=comm_state.state_hash,
            next_uow_pointer=None,
            prev_evidence_hash="0" * 64,
        )
        entry = {
            "type": "COMMIT",
            "step_number": 1,
            "post_state_hash": comm_state.state_hash,
            "state": comm_state.to_dict(),
            "evidence": {
                "step_number": ev.step_number,
                "uow_id": ev.uow_id,
                "source_category": ev.source_category,
                "target_category": ev.target_category,
                "pre_state_hash": ev.pre_state_hash,
                "selected_route_index": ev.selected_route_index,
                "proposed_state_hash": ev.proposed_state_hash,
                "certificate_hash": ev.certificate_hash,
                "post_state_hash": ev.post_state_hash,
                "next_uow_pointer": ev.next_uow_pointer,
                "prev_evidence_hash": ev.prev_evidence_hash,
                "record_hash": ev.record_hash,
            },
        }
        wal._write_entry(entry)
        # Authoritative memory was NOT updated in `wal`

        # Recovery from disk MUST recover the new state and the evidence record!
        rec_s, rec_ledger = WALSequencer.recover(wal_path)
        assert rec_s.state_hash == comm_state.state_hash
        assert rec_s.require("cnt") == 1
        assert len(rec_ledger.records) == 1
        assert rec_ledger.records[0].record_hash == ev.record_hash
        assert rec_ledger.verify_integrity()


def test_complete_evidence_ledger_reconstruction_and_integrity():
    """S_recovered == S_continuous AND E_recovered == E_continuous across multiple commits."""
    with tempfile.TemporaryDirectory() as tmpdir:
        wal_path = Path(tmpdir) / "test.wal"
        s0 = WorldState(attributes={"v": 0})
        wal = WALSequencer(wal_path, s0)

        for i in range(1, 6):
            u = _make_task(f"task_{i}", write_key="v", write_val=i * 10)
            p = propose(u, wal.current_state)
            tx = create_transaction_descriptor(u, wal.current_state)
            c = certify(u, wal.current_state, p)
            wal.commit(u, p, tx, c)

        continuous_state = wal.current_state
        continuous_ledger = wal.ledger

        # Crash recovery
        recovered_state, recovered_ledger = WALSequencer.recover(wal_path)

        # 1. State equality
        assert recovered_state.state_hash == continuous_state.state_hash
        assert recovered_state.require("v") == 50
        assert recovered_state.sequence == continuous_state.sequence

        # 2. Complete Evidence Ledger equality
        assert len(recovered_ledger.records) == len(continuous_ledger.records)
        assert recovered_ledger.root_hash() == continuous_ledger.root_hash()
        assert recovered_ledger.verify_integrity()

        for rec_rec, cont_rec in zip(recovered_ledger.records, continuous_ledger.records):
            assert rec_rec.record_hash == cont_rec.record_hash
            assert rec_rec.post_state_hash == cont_rec.post_state_hash


def test_tampered_wal_evidence_record_fails_recovery():
    """If a single byte of an evidence record in the WAL is modified, recovery fails cryptographically."""
    with tempfile.TemporaryDirectory() as tmpdir:
        wal_path = Path(tmpdir) / "test.wal"
        s0 = WorldState(attributes={"v": 0})
        wal = WALSequencer(wal_path, s0)

        u = _make_task("task_1", write_key="v", write_val=10)
        p = propose(u, wal.current_state)
        tx = create_transaction_descriptor(u, wal.current_state)
        c = certify(u, wal.current_state, p)
        wal.commit(u, p, tx, c)

        # Tamper the evidence record in the WAL file
        with open(wal_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        tampered_entry = json.loads(lines[1])
        # Tamper step number in evidence
        tampered_entry["evidence"]["step_number"] = 999
        lines[1] = canonical_json(tampered_entry) + "\n"

        with open(wal_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

        with pytest.raises(ValueError, match="hash does not match its contents"):
            WALSequencer.recover(wal_path)


def test_reordered_wal_entries_fails_recovery():
    """If commits in the WAL are reordered, hash-chain integrity check fails during recovery."""
    with tempfile.TemporaryDirectory() as tmpdir:
        wal_path = Path(tmpdir) / "test.wal"
        s0 = WorldState(attributes={"v": 0})
        wal = WALSequencer(wal_path, s0)

        for i in range(1, 3):
            u = _make_task(f"task_{i}", write_key="v", write_val=i)
            p = propose(u, wal.current_state)
            tx = create_transaction_descriptor(u, wal.current_state)
            c = certify(u, wal.current_state, p)
            wal.commit(u, p, tx, c)

        with open(wal_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # Swap commit 1 (lines[1]) and commit 2 (lines[2])
        swapped = [lines[0], lines[2], lines[1]]
        with open(wal_path, "w", encoding="utf-8") as f:
            f.writelines(swapped)

        with pytest.raises(ValueError, match="does not extend the current ledger root"):
            WALSequencer.recover(wal_path)

