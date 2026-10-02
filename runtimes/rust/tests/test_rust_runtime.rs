//! Comprehensive Integration Test Suite for UoW Rust Native Runtime (Levels 0-2).

use serde_json::json;
use std::collections::BTreeMap;

use uow_runtime::engine::TransitionEngine;
use uow_runtime::evidence::{EvidenceLedger, EvidenceRecord};
use uow_runtime::orchestration::{DagError, OrchestrationDAG};
use uow_runtime::state::WorldState;
use uow_runtime::transactions::{
    DeterministicSequencer, OccDisposition, OccHazard, OccTracker, TransactionDescriptor,
};
use uow_runtime::wal::WALSequencer;

// ===========================================================================
// Level 0: State, Transitions, Evidence & Idempotency
// ===========================================================================

#[test]
fn test_level0_canonical_json_and_state_hashing() {
    let mut attrs = BTreeMap::new();
    attrs.insert("b".to_string(), json!(2));
    attrs.insert("a".to_string(), json!(1));
    attrs.insert("unicode".to_string(), json!("こんにちは 🚀"));
    attrs.insert("big_int".to_string(), json!(9007199254740991i64));

    let state = WorldState::new(attrs, None, "RUNNING", 0);
    let hash = state.compute_hash();

    assert_eq!(hash.len(), 64);
    assert_eq!(state.state_hash, hash);

    // Deterministic re-computation
    let hash2 = state.compute_hash();
    assert_eq!(hash, hash2);
}

#[test]
fn test_level0_evidence_chain_integrity() {
    let mut ledger = EvidenceLedger::new();
    assert!(ledger.verify_integrity());
    assert_eq!(ledger.root_hash(), "0".repeat(64));

    let rec1 = EvidenceRecord::new(
        1,
        "uow-1",
        "Processes",
        "Data",
        "hash-pre-1",
        0,
        "hash-prop-1",
        "hash-cert-1",
        "hash-post-1",
        Some("uow-2".to_string()),
        &ledger.root_hash(),
    );
    ledger.append(rec1.clone());
    assert!(ledger.verify_integrity());
    assert_eq!(ledger.root_hash(), rec1.record_hash);

    let rec2 = EvidenceRecord::new(
        2,
        "uow-2",
        "Processes",
        "Data",
        "hash-post-1",
        0,
        "hash-prop-2",
        "hash-cert-2",
        "hash-post-2",
        None,
        &ledger.root_hash(),
    );
    ledger.append(rec2.clone());
    assert!(ledger.verify_integrity());
    assert_eq!(ledger.len(), 2);
}

// ===========================================================================
// Level 1: OCC (Gate 2) & Deterministic Sequencing (Gate 3)
// ===========================================================================

#[test]
fn test_gate2_occ_conflict_equivalence() {
    let mut tracker = OccTracker::new();

    // 1. Initial committed transaction: reads "x", writes "y", commits at seq 1
    let tx1 = TransactionDescriptor::new(
        "tx-1",
        &["x"],
        &["y"],
        0,
        BTreeMap::from([("y".to_string(), json!(10))]),
    );
    tracker.record_commit(&tx1, 1);

    // 2. Disjoint writes -> ACCEPT
    let tx_disjoint = TransactionDescriptor::new(
        "tx-disjoint",
        &["a"],
        &["b"],
        1,
        BTreeMap::from([("b".to_string(), json!(20))]),
    );
    assert_eq!(
        tracker.validate_tx(1, &tx_disjoint),
        OccDisposition::Accept
    );

    // 3. Write/Write collision -> REJECT
    let tx_ww = TransactionDescriptor::new(
        "tx-ww",
        &["a"],
        &["y"], // "y" was written by tx1
        0,
        BTreeMap::from([("y".to_string(), json!(30))]),
    );
    assert_eq!(
        tracker.validate_tx(1, &tx_ww),
        OccDisposition::Reject(OccHazard::WriteWriteConflict)
    );

    // 4. Read/Write hazard (stale read) -> REJECT
    let tx_rw = TransactionDescriptor::new(
        "tx-rw",
        &["y"], // "y" was written by tx1 after tx_rw began at seq 0
        &["z"],
        0,
        BTreeMap::from([("z".to_string(), json!(40))]),
    );
    assert_eq!(
        tracker.validate_tx(1, &tx_rw),
        OccDisposition::Reject(OccHazard::ReadWriteConflict)
    );

    // 5. Write/Read collision -> REJECT
    let tx_wr = TransactionDescriptor::new(
        "tx-wr",
        &["a"],
        &["x"], // "x" was read by tx1 at seq 0
        0,
        BTreeMap::from([("x".to_string(), json!(50))]),
    );
    assert_eq!(
        tracker.validate_tx(1, &tx_wr),
        OccDisposition::Reject(OccHazard::WriteReadConflict)
    );

    // 6. Stale base sequence -> REJECT
    let tx_stale = TransactionDescriptor::new(
        "tx-stale",
        &[],
        &[],
        0,
        BTreeMap::new(),
    );
    assert_eq!(
        tracker.validate_tx(1, &tx_stale),
        OccDisposition::Reject(OccHazard::StaleBaseSequence)
    );
}

#[test]
fn test_gate3_deterministic_sequencing_invariance() {
    let make_batch = || vec![
        TransactionDescriptor::new("t1", &["balance"], &["balance"], 0, BTreeMap::from([("balance".to_string(), json!(100))])),
        TransactionDescriptor::new("t2", &["stock"], &["stock"], 0, BTreeMap::from([("stock".to_string(), json!(50))])),
        TransactionDescriptor::new("t3", &["balance"], &["balance"], 0, BTreeMap::from([("balance".to_string(), json!(200))])), // Conflicts with t1
        TransactionDescriptor::new("t4", &["status"], &["status"], 1, BTreeMap::from([("status".to_string(), json!("ACTIVE"))])),
    ];

    let mut reference_log = Vec::new();
    let mut reference_final_hash = String::new();

    // Run trial 50 times: exact identical log and final state hash every time
    for trial in 0..50 {
        let initial_state = WorldState::new(
            BTreeMap::from([
                ("balance".to_string(), json!(0)),
                ("stock".to_string(), json!(10)),
                ("status".to_string(), json!("INIT")),
            ]),
            None,
            "RUNNING",
            0,
        );

        let mut sequencer = DeterministicSequencer::new(initial_state);
        let batch = make_batch();
        let _ = sequencer.process_batch(&batch);

        if trial == 0 {
            reference_log = sequencer.log.clone();
            reference_final_hash = sequencer.state.state_hash.clone();
            assert_eq!(reference_log.len(), 4);
            assert_eq!(reference_log[0].disposition, "COMMITTED");
            assert_eq!(reference_log[1].disposition, "COMMITTED");
            assert_eq!(reference_log[2].disposition, "REJECTED_WriteWriteConflict");
            assert_eq!(reference_log[3].disposition, "COMMITTED");
        } else {
            assert_eq!(sequencer.log, reference_log);
            assert_eq!(sequencer.state.state_hash, reference_final_hash);
        }
    }
}

// ===========================================================================
// Level 1: WAL & Crash Replay (Gate 4)
// ===========================================================================

#[test]
fn test_gate4_wal_crash_replay_equivalence() {
    let initial_state = WorldState::new(
        BTreeMap::from([("counter".to_string(), json!(0))]),
        None,
        "RUNNING",
        0,
    );

    let mut sequencer = WALSequencer::new(initial_state.clone());

    // Commit 4 transactions
    for i in 1..=4 {
        sequencer.commit(
            &format!("uow-step-{}", i),
            BTreeMap::from([("counter".to_string(), json!(i))]),
            if i < 4 { Some(format!("uow-step-{}", i + 1)) } else { None },
        );
    }

    let committed_state = sequencer.current_state.clone();
    let committed_ledger = sequencer.ledger.clone();
    let wal_log = sequencer.wal_log.clone();

    assert_eq!(committed_state.sequence, 4);
    assert_eq!(committed_ledger.len(), 4);
    assert_eq!(wal_log.len(), 4);
    assert!(committed_ledger.verify_integrity());

    // SIMULATE CRASH: discard sequencer memory, reconstruct from initial state + WAL log
    let (replayed_state, replayed_ledger) =
        WALSequencer::replay(&initial_state, &wal_log).expect("Replay failed");

    // S_replayed == S_committed
    assert_eq!(replayed_state.attributes, committed_state.attributes);
    assert_eq!(replayed_state.sequence, committed_state.sequence);
    assert_eq!(replayed_state.status, committed_state.status);
    assert_eq!(replayed_state.state_hash, committed_state.state_hash);

    // E_replayed == E_committed
    assert_eq!(replayed_ledger.root_hash(), committed_ledger.root_hash());
    assert_eq!(replayed_ledger.len(), committed_ledger.len());
    assert!(replayed_ledger.verify_integrity());

    // Idempotent duplicate replay test: replaying already-applied WAL records does not mutate state
    let new_applied = sequencer.replay_idempotent(&wal_log).expect("Idempotent replay failed");
    assert_eq!(new_applied, 0); // Zero duplicate effects
    assert_eq!(sequencer.current_state.sequence, 4);
    assert_eq!(sequencer.current_state.state_hash, committed_state.state_hash);
}

// ===========================================================================
// Level 2: Deterministic DAG Orchestration (Gate 5)
// ===========================================================================

#[test]
fn test_gate5_deterministic_dag_orchestration() {
    // Graph:
    // A ──► C
    // B ──► C ──► D
    let mut dag = OrchestrationDAG::new();
    dag.add_task("A", &[]).unwrap();
    dag.add_task("B", &[]).unwrap();
    dag.add_task("C", &["A", "B"]).unwrap();
    dag.add_task("D", &["C"]).unwrap();

    // 1. Initially eligible: A, B
    let eligible0 = dag.eligible_tasks();
    assert_eq!(eligible0, vec!["A".to_string(), "B".to_string()]);

    // 2. Dispatch and complete A
    dag.dispatch_task("A").unwrap();
    let eligible_mid = dag.eligible_tasks();
    assert_eq!(eligible_mid, vec!["B".to_string()]); // Only B eligible while A active
    dag.complete_task("A").unwrap();

    // After A only: B eligible
    let eligible1 = dag.eligible_tasks();
    assert_eq!(eligible1, vec!["B".to_string()]);

    // 3. Dispatch and complete B
    dag.dispatch_task("B").unwrap();
    dag.complete_task("B").unwrap();

    // After A + B: C eligible
    let eligible2 = dag.eligible_tasks();
    assert_eq!(eligible2, vec!["C".to_string()]);

    // 4. Dispatch and complete C
    dag.dispatch_task("C").unwrap();
    dag.complete_task("C").unwrap();

    // After C: D eligible
    let eligible3 = dag.eligible_tasks();
    assert_eq!(eligible3, vec!["D".to_string()]);

    // 5. Dispatch and complete D
    dag.dispatch_task("D").unwrap();
    dag.complete_task("D").unwrap();

    // After D: HALT
    assert!(dag.eligible_tasks().is_empty());
    assert!(dag.is_halted());
}

#[test]
fn test_gate5_dag_fault_and_defense_cases() {
    let mut dag = OrchestrationDAG::new();
    dag.add_task("A", &[]).unwrap();
    dag.add_task("B", &["A"]).unwrap();

    // 1. Dependency violation rejection: dispatching B before A completed
    let err_dep = dag.dispatch_task("B").unwrap_err();
    match err_dep {
        DagError::DependencyViolation(_) => {}
        _ => panic!("Expected DependencyViolation, got {:?}", err_dep),
    }

    // 2. Missing node rejection
    let err_missing = dag.dispatch_task("UNKNOWN").unwrap_err();
    match err_missing {
        DagError::MissingNode(_) => {}
        _ => panic!("Expected MissingNode, got {:?}", err_missing),
    }

    // 3. Duplicate completion rejection
    dag.dispatch_task("A").unwrap();
    dag.complete_task("A").unwrap();
    let err_dup = dag.complete_task("A").unwrap_err();
    match err_dup {
        DagError::DuplicateCompletion(_) => {}
        _ => panic!("Expected DuplicateCompletion, got {:?}", err_dup),
    }

    // 4. Cycle rejection: A -> B -> A
    let mut cyclic_dag = OrchestrationDAG::new();
    cyclic_dag.add_task("node1", &["node2"]).unwrap();
    let err_cycle = cyclic_dag.add_task("node2", &["node1"]).unwrap_err();
    assert_eq!(err_cycle, DagError::CycleDetected);
}

// ===========================================================================
// Level 0-2 Architectural Gate: Proposer Has Zero Authority (Gate 6)
// ===========================================================================

#[test]
fn test_gate6_proposer_zero_authority_boundary() {
    let mut engine = TransitionEngine::new();

    // 1. Wrong route / Guard violation
    let bad_route_envelope = json!({
        "protocol_version": "1.0.0",
        "operation": "uow.transition.execute_one",
        "operation_version": "1.0.0",
        "request_id": "req-malicious-1",
        "correlation_id": "corr-1",
        "actor": {"id": "malicious-proposer", "claim_type": "AUTHENTICATED"},
        "payload": {
            "uow": {
                "identity": "exploit-uow",
                "routes": [{
                    "guard": {"op": "EQ", "key": "authorized", "operand": true},
                    "mutations": [{"op": "SET", "key": "admin", "operand": true}]
                }]
            },
            "state": {
                "attributes": {"authorized": false},
                "status": "RUNNING",
                "sequence": 0
            }
        }
    });
    let res1 = engine.execute_envelope(&bad_route_envelope);
    assert_eq!(res1["status"], "REJECTED");
    assert_eq!(res1["errors"][0]["code"], "ERR_GUARD_UNSATISFIED");

    // 2. Stale pre-state
    let stale_pre_state = json!({
        "protocol_version": "1.0.0",
        "operation": "uow.transition.certify",
        "operation_version": "1.0.0",
        "request_id": "req-malicious-2",
        "correlation_id": "corr-2",
        "actor": {"id": "malicious-proposer"},
        "payload": {
            "state": {"attributes": {"balance": 100}, "sequence": 5, "status": "RUNNING"},
            "proposal": {
                "pre_state_hash": "stale_or_forged_hash_0000000000000000000000000000000000000000000000",
                "proposed_state": {"attributes": {"balance": 500}}
            }
        }
    });
    let res2 = engine.execute_envelope(&stale_pre_state);
    assert_eq!(res2["status"], "REJECTED");
    assert_eq!(res2["errors"][0]["code"], "ERR_STALE_PRE_STATE");

    // 3. Forged proposed state / State divergence
    let valid_state = WorldState::new(BTreeMap::from([("balance".to_string(), json!(100))]), None, "RUNNING", 1);
    let forged_state = json!({
        "protocol_version": "1.0.0",
        "operation": "uow.transition.certify",
        "operation_version": "1.0.0",
        "request_id": "req-malicious-3",
        "correlation_id": "corr-3",
        "actor": {"id": "malicious-proposer"},
        "payload": {
            "state": valid_state.to_json_value(),
            "proposal": {
                "pre_state_hash": valid_state.state_hash,
                "proposed_state": {
                    "attributes": {
                        "balance": 9999, // Unauthorized balance manipulation
                        "tampered_token": "forged_privilege"
                    }
                }
            }
        }
    });
    let res3 = engine.execute_envelope(&forged_state);
    assert_eq!(res3["status"], "REJECTED");
    assert_eq!(res3["errors"][0]["code"], "ERR_ROUTE_DIVERGENCE");

    // 4. Invalid authority / Unverified actor claiming fund transfer
    let unauthorized_auth = json!({
        "protocol_version": "1.0.0",
        "operation": "uow.transition.execute_one",
        "operation_version": "1.0.0",
        "request_id": "req-malicious-4",
        "correlation_id": "corr-4",
        "actor": {"id": "guest", "claim_type": "UNVERIFIED_CLAIM"},
        "payload": {
            "uow": {"identity": "fund_transfer", "routes": []},
            "state": {"attributes": {}}
        }
    });
    let res4 = engine.execute_envelope(&unauthorized_auth);
    assert_eq!(res4["status"], "REJECTED");
    assert_eq!(res4["errors"][0]["code"], "ERR_AUTHORITY_DENIED");
}
