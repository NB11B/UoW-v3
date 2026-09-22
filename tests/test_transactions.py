"""Comprehensive tests for Optimistic Concurrency Control (OCC) and Sequencer / WAL."""
import tempfile
from pathlib import Path
import pytest

from uow import (
    DeterministicSequencer,
    EvidenceLedger,
    Guard,
    GuardOp,
    HazardType,
    Mutation,
    MutationOp,
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
)


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
    """WALSequencer persists commits to append-only log and recovers exact state."""
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
