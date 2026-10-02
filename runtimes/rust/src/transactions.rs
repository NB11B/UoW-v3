//! Optimistic Concurrency Control (OCC), transaction footprints, and deterministic sequencing.

use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};

use crate::state::WorldState;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct TransactionDescriptor {
    pub tx_id: String,
    pub read_set: BTreeSet<String>,
    pub write_set: BTreeSet<String>,
    pub base_sequence: u64,
    #[serde(default)]
    pub mutations: BTreeMap<String, Value>,
}

impl TransactionDescriptor {
    pub fn new(
        tx_id: &str,
        read_set: &[&str],
        write_set: &[&str],
        base_sequence: u64,
        mutations: BTreeMap<String, Value>,
    ) -> Self {
        Self {
            tx_id: tx_id.to_string(),
            read_set: read_set.iter().map(|s| s.to_string()).collect(),
            write_set: write_set.iter().map(|s| s.to_string()).collect(),
            base_sequence,
            mutations,
        }
    }
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum OccHazard {
    DisjointWrites,
    WriteWriteConflict,
    WriteReadConflict,
    ReadWriteConflict,
    StaleBaseSequence,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum OccDisposition {
    Accept,
    Reject(OccHazard),
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct CommittedTxRecord {
    pub tx_id: String,
    pub sequence: u64,
    pub read_set: BTreeSet<String>,
    pub write_set: BTreeSet<String>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct OccTracker {
    pub committed_history: Vec<CommittedTxRecord>,
}

impl OccTracker {
    pub fn new() -> Self {
        Self {
            committed_history: Vec::new(),
        }
    }

    pub fn record_commit(&mut self, tx: &TransactionDescriptor, commit_sequence: u64) {
        self.committed_history.push(CommittedTxRecord {
            tx_id: tx.tx_id.clone(),
            sequence: commit_sequence,
            read_set: tx.read_set.clone(),
            write_set: tx.write_set.clone(),
        });
    }

    /// Validate a candidate transaction against historical commits since its base_sequence
    pub fn validate_tx(
        &self,
        current_sequence: u64,
        tx: &TransactionDescriptor,
    ) -> OccDisposition {
        if tx.base_sequence > current_sequence {
            return OccDisposition::Reject(OccHazard::StaleBaseSequence);
        }

        let mut had_intervening_commit = false;

        for rec in &self.committed_history {
            if rec.sequence >= tx.base_sequence {
                had_intervening_commit = true;

                // 1. Write/Write Collision: both wrote to the same key
                if !tx.write_set.is_disjoint(&rec.write_set) {
                    return OccDisposition::Reject(OccHazard::WriteWriteConflict);
                }

                // 2. Read/Write Hazard: tx read a key that was modified by rec
                if !tx.read_set.is_disjoint(&rec.write_set) {
                    return OccDisposition::Reject(OccHazard::ReadWriteConflict);
                }

                // 3. Write/Read Collision: tx wrote a key that was read by rec
                if !tx.write_set.is_disjoint(&rec.read_set) {
                    return OccDisposition::Reject(OccHazard::WriteReadConflict);
                }
            }
        }

        // If sequence has advanced but no footprint overlapped, check if strict freshness was violated
        if tx.base_sequence < current_sequence && had_intervening_commit && tx.read_set.is_empty() && tx.write_set.is_empty() {
            return OccDisposition::Reject(OccHazard::StaleBaseSequence);
        }

        OccDisposition::Accept
    }

    /// Intra-batch OCC validation for concurrent candidates
    pub fn validate_batch_disjoint(
        batch: &[TransactionDescriptor],
    ) -> Vec<(String, OccDisposition)> {
        let mut results = Vec::new();
        let mut accumulated_writes = BTreeSet::new();
        let mut accumulated_reads = BTreeSet::new();

        for tx in batch {
            // Check write/write collision with preceding batch items
            if !tx.write_set.is_disjoint(&accumulated_writes) {
                results.push((
                    tx.tx_id.clone(),
                    OccDisposition::Reject(OccHazard::WriteWriteConflict),
                ));
                continue;
            }

            // Check read/write collision: tx reads something earlier tx wrote
            if !tx.read_set.is_disjoint(&accumulated_writes) {
                results.push((
                    tx.tx_id.clone(),
                    OccDisposition::Reject(OccHazard::ReadWriteConflict),
                ));
                continue;
            }

            // Check write/read collision: tx writes something earlier tx read
            if !tx.write_set.is_disjoint(&accumulated_reads) {
                results.push((
                    tx.tx_id.clone(),
                    OccDisposition::Reject(OccHazard::WriteReadConflict),
                ));
                continue;
            }

            for w in &tx.write_set {
                accumulated_writes.insert(w.clone());
            }
            for r in &tx.read_set {
                accumulated_reads.insert(r.clone());
            }

            results.push((tx.tx_id.clone(), OccDisposition::Accept));
        }

        results
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SequencerLogEntry {
    pub tx_id: String,
    pub disposition: String,
    pub sequence_after: u64,
    pub state_hash_after: String,
}

pub struct DeterministicSequencer {
    pub state: WorldState,
    pub tracker: OccTracker,
    pub log: Vec<SequencerLogEntry>,
}

impl DeterministicSequencer {
    pub fn new(initial_state: WorldState) -> Self {
        Self {
            state: initial_state,
            tracker: OccTracker::new(),
            log: Vec::new(),
        }
    }

    pub fn process_transaction(&mut self, tx: &TransactionDescriptor) -> OccDisposition {
        let disp = self.tracker.validate_tx(self.state.sequence, tx);
        match &disp {
            OccDisposition::Accept => {
                let mut new_attrs = self.state.attributes.clone();
                for (k, v) in &tx.mutations {
                    new_attrs.insert(k.clone(), v.clone());
                }
                let next_seq = self.state.sequence + 1;
                self.state = WorldState::new(
                    new_attrs,
                    self.state.cursor.clone(),
                    &self.state.status,
                    next_seq,
                );
                self.tracker.record_commit(tx, self.state.sequence);
                self.log.push(SequencerLogEntry {
                    tx_id: tx.tx_id.clone(),
                    disposition: "COMMITTED".to_string(),
                    sequence_after: self.state.sequence,
                    state_hash_after: self.state.state_hash.clone(),
                });
            }
            OccDisposition::Reject(hazard) => {
                self.log.push(SequencerLogEntry {
                    tx_id: tx.tx_id.clone(),
                    disposition: format!("REJECTED_{:?}", hazard),
                    sequence_after: self.state.sequence,
                    state_hash_after: self.state.state_hash.clone(),
                });
            }
        }
        disp
    }

    pub fn process_batch(&mut self, batch: &[TransactionDescriptor]) -> Vec<OccDisposition> {
        batch.iter().map(|tx| self.process_transaction(tx)).collect()
    }
}
