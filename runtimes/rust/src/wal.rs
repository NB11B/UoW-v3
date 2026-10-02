//! Write-Ahead Log (WAL), crash recovery, and state/evidence replay equivalence.

use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::BTreeMap;

use crate::evidence::{EvidenceLedger, EvidenceRecord};
use crate::state::{canonical_json, sha256_hex, WorldState};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct WalRecord {
    pub sequence: u64,
    pub pre_state_hash: String,
    pub proposal_hash: String,
    pub certificate_hash: String,
    pub post_state_hash: String,
    pub uow_id: String,
    #[serde(default)]
    pub mutations: BTreeMap<String, Value>,
    pub next_pointer: Option<String>,
}

pub struct WALSequencer {
    pub current_state: WorldState,
    pub ledger: EvidenceLedger,
    pub wal_log: Vec<WalRecord>,
}

impl WALSequencer {
    pub fn new(initial_state: WorldState) -> Self {
        Self {
            current_state: initial_state,
            ledger: EvidenceLedger::new(),
            wal_log: Vec::new(),
        }
    }

    pub fn commit(
        &mut self,
        uow_id: &str,
        mutations: BTreeMap<String, Value>,
        next_pointer: Option<String>,
    ) -> (WorldState, EvidenceRecord, WalRecord) {
        let pre_state_hash = self.current_state.state_hash.clone();
        let next_seq = self.current_state.sequence + 1;

        let mut new_attrs = self.current_state.attributes.clone();
        for (k, v) in &mutations {
            new_attrs.insert(k.clone(), v.clone());
        }

        // 1. Proposed state (unincremented sequence)
        let prop_st = WorldState::new(
            new_attrs.clone(),
            next_pointer.clone(),
            "RUNNING",
            self.current_state.sequence,
        );
        let proposal_hash = prop_st.state_hash.clone();

        // 2. Post state (advanced sequence)
        let post_st = WorldState::new(
            new_attrs,
            next_pointer.clone(),
            "HALTED",
            next_seq,
        );
        let post_state_hash = post_st.state_hash.clone();

        // 3. Certificate hash
        let mut cert_payload = serde_json::Map::new();
        cert_payload.insert("pre_state_hash".to_string(), Value::String(pre_state_hash.clone()));
        cert_payload.insert("proposed_state_hash".to_string(), Value::String(proposal_hash.clone()));
        cert_payload.insert("uow_id".to_string(), Value::String(uow_id.to_string()));
        let certificate_hash = sha256_hex(canonical_json(&Value::Object(cert_payload)).as_bytes());

        // 4. Evidence record
        let step_number = (self.ledger.len() + 1) as u64;
        let prev_evidence_hash = self.ledger.root_hash();
        let evidence = EvidenceRecord::new(
            step_number,
            uow_id,
            "Processes",
            "Data",
            &pre_state_hash,
            0,
            &proposal_hash,
            &certificate_hash,
            &post_state_hash,
            next_pointer.clone(),
            &prev_evidence_hash,
        );
        self.ledger.append(evidence.clone());

        // 5. Wal record
        let wal_record = WalRecord {
            sequence: next_seq,
            pre_state_hash,
            proposal_hash,
            certificate_hash,
            post_state_hash,
            uow_id: uow_id.to_string(),
            mutations,
            next_pointer,
        };
        self.wal_log.push(wal_record.clone());
        self.current_state = post_st.clone();

        (post_st, evidence, wal_record)
    }

    /// Reconstruct authoritative state and evidence ledger strictly from initial state and WAL records
    pub fn replay(
        initial_state: &WorldState,
        wal_records: &[WalRecord],
    ) -> Result<(WorldState, EvidenceLedger), String> {
        let mut state = initial_state.clone();
        let mut ledger = EvidenceLedger::new();

        for (idx, record) in wal_records.iter().enumerate() {
            if state.state_hash != record.pre_state_hash {
                return Err(format!(
                    "WAL replay error at step {}: pre_state_hash mismatch (expected {}, got {})",
                    idx + 1,
                    record.pre_state_hash,
                    state.state_hash
                ));
            }

            let mut new_attrs = state.attributes.clone();
            for (k, v) in &record.mutations {
                new_attrs.insert(k.clone(), v.clone());
            }

            let post_st = WorldState::new(
                new_attrs,
                record.next_pointer.clone(),
                "HALTED",
                record.sequence,
            );

            if post_st.state_hash != record.post_state_hash {
                return Err(format!(
                    "WAL replay error at step {}: post_state_hash mismatch (expected {}, computed {})",
                    idx + 1,
                    record.post_state_hash,
                    post_st.state_hash
                ));
            }

            let step_number = (ledger.len() + 1) as u64;
            let prev_evidence_hash = ledger.root_hash();
            let evidence = EvidenceRecord::new(
                step_number,
                &record.uow_id,
                "Processes",
                "Data",
                &record.pre_state_hash,
                0,
                &record.proposal_hash,
                &record.certificate_hash,
                &record.post_state_hash,
                record.next_pointer.clone(),
                &prev_evidence_hash,
            );
            ledger.append(evidence);
            state = post_st;
        }

        if !ledger.verify_integrity() {
            return Err("Replayed evidence ledger failed hash-chain integrity check".to_string());
        }

        Ok((state, ledger))
    }

    /// Replay records against an existing sequencer idempotently (skipping already committed records)
    pub fn replay_idempotent(&mut self, wal_records: &[WalRecord]) -> Result<usize, String> {
        let mut applied = 0;
        for record in wal_records {
            if record.sequence <= self.current_state.sequence {
                // Already committed or past sequence: verify state consistency and skip
                continue;
            }
            if self.current_state.state_hash != record.pre_state_hash {
                return Err(format!(
                    "Idempotent replay conflict at sequence {}: current hash {} does not match pre_state_hash {}",
                    record.sequence,
                    self.current_state.state_hash,
                    record.pre_state_hash
                ));
            }

            let mut new_attrs = self.current_state.attributes.clone();
            for (k, v) in &record.mutations {
                new_attrs.insert(k.clone(), v.clone());
            }

            let post_st = WorldState::new(
                new_attrs,
                record.next_pointer.clone(),
                "HALTED",
                record.sequence,
            );

            let step_number = (self.ledger.len() + 1) as u64;
            let prev_evidence_hash = self.ledger.root_hash();
            let evidence = EvidenceRecord::new(
                step_number,
                &record.uow_id,
                "Processes",
                "Data",
                &record.pre_state_hash,
                0,
                &record.proposal_hash,
                &record.certificate_hash,
                &record.post_state_hash,
                record.next_pointer.clone(),
                &prev_evidence_hash,
            );
            self.ledger.append(evidence);
            self.wal_log.push(record.clone());
            self.current_state = post_st;
            applied += 1;
        }
        Ok(applied)
    }
}
